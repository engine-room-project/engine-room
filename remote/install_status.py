"""Observe only the installer process object retained by the owned kernel."""
import hashlib
import json
import os
from pathlib import Path

PHASES={
    "Installing pinned native prerequisites":"system-packages",
    "Installing isolated model Python and pinned downloader":"model-python",
    "Installing hash-verified GGUF runtime":"gguf-artifacts",
    "Runtime installed; waiting for explicit credentials and model start":"dependencies-installed",
    "Installing pinned native vLLM packages":"vllm-packages",
    "Verifying pinned native vLLM and GPU":"vllm-verification",
    "Setup failed":"failed",
}


def read_small(path,limit=4096,*,strip=True):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit: raise ValueError("Invalid owned state file")
    with path.open("rb") as stream:
        raw=stream.read(limit+1)
    if len(raw)>limit: raise ValueError("Oversized owned state file")
    text=raw.decode("utf-8").replace("\r\n","\n")
    return text.strip() if strip else text


def collect(root,operation_key,source_sha256,handle):
    unknown=dict(state="unknown",progress="installer-proof-unavailable")
    try:
        root=Path(root)
        if not root.is_absolute() or root.resolve()!=root.absolute() or root.name!="engine-room-"+operation_key[:32]: return unknown
        proof=json.loads(read_small(root/".engine-room-owner.json"))
        expected=dict(schema=1,operation_key=operation_key,source_sha256=source_sha256,state="staged")
        if not isinstance(proof,dict) or any(proof.get(k)!=v for k,v in expected.items()): return unknown
        submitted=json.loads(read_small(root/"install-start.json"))
        if submitted.get("source_sha256")!=source_sha256 or submitted.get("state")!="submitted": return unknown
        if not isinstance(handle,dict) or any(handle.get(k)!=v for k,v in dict(operation_key=operation_key,root=str(root),source_sha256=source_sha256).items()): return unknown
        process=handle.get("process")
        if process is None: return unknown
        result=process.poll()
        if result is not None and (type(result) is not int or result!=0):
            return dict(state="failed",progress="installer-exited")
        try: phase=PHASES.get(read_small(root/"phase",2048),"unrecognized")
        except (OSError,ValueError): phase="starting"
        if phase=="failed": return dict(state="failed",progress="installer-failed")
        if result is None:
            log=root/"install.log"
            size=log.stat().st_size if log.is_file() and not log.is_symlink() else 0
            return dict(state="installing",progress="native-"+phase+":"+str(size))
        # A readiness file alone cannot override a running/failed/unidentified process.
        if read_small(root/"runtime-ready")!="installed":
            return dict(state="failed",progress="installer-incomplete")
        python=root/"venv/bin/python"
        if read_small(root/"python-path")!=str(python) or not python.is_file():
            return dict(state="failed",progress="installer-python-missing")
        engine=json.loads(read_small(root/"model.json",1024*1024)).get("engine")
        if engine=="llama.cpp":
            llama=Path(read_small(root/"llama-path"))
            if (not llama.is_absolute() or not llama.is_file() or not llama.resolve().is_relative_to((root/"llama").resolve())
                    or (os.name!="nt" and not os.access(llama,os.X_OK))):
                return dict(state="failed",progress="installer-runtime-missing")
        elif engine=="vLLM":
            manifest=json.loads(read_small(root/"remote/vllm-native.json"))
            native=json.loads(read_small(root/"native-runtime.json"))
            expected=dict(schema=1,engine="vLLM",version=manifest["version"],torch=manifest["torch_version"],lock_sha256=manifest["lock_sha256"])
            capability=native.get("gpu_capability")
            if (any(native.get(k)!=v for k,v in expected.items())
                    or hashlib.sha256(read_small(root/"remote/requirements-vllm.lock",1024*1024,strip=False).encode()).hexdigest()!=manifest["lock_sha256"]
                    or not isinstance(capability,list) or len(capability)!=2 or any(type(v) is not int for v in capability)
                    or tuple(capability)<(7,5)
                    or tuple(map(int,native.get("cuda","").split(".")))<tuple(map(int,manifest["minimum_cuda"].split(".")))):
                return dict(state="failed",progress="installer-runtime-missing")
        else: return dict(state="failed",progress="installer-runtime-missing")
        return dict(state="installed",progress="dependencies-installed")
    except Exception:
        return unknown
