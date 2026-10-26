"""Deterministic, non-secret runtime payloads from an explicit source allowlist."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

from .model_server import command

ROOT=Path(__file__).resolve().parents[1]
FILES=("engine_room/__init__.py","engine_room/billing.py","engine_room/model_server.py","engine_room/model_validation.py",
       "engine_room/storage.py","engine_room/records.py","engine_room/remote_agent.py",
       "remote/requirements.lock","remote/install-llama.sh","remote/install-colab.sh","remote/install_status.py","remote/verify_vllm.py","remote/runtimes.json",
       "THIRD_PARTY_NOTICES/llama.cpp-LICENSE.txt","THIRD_PARTY_NOTICES/huggingface-hub-LICENSE.txt",
       "THIRD_PARTY_NOTICES/vllm-LICENSE.txt","THIRD_PARTY_NOTICES/README.md")
PLAN_FIELDS=frozenset({"id","revision","context","engine","dtype","tool","reasoning","files","mmproj","fileSizes","fileHashes","weightBytes"})


def runtime_profile(engine,root=ROOT):
    data=json.loads((Path(root)/"remote/runtimes.json").read_text(encoding="utf-8"))
    if data.get("schema")!=1 or data.get("platform")!="linux/amd64" or data.get("python")!="3.12":
        raise ValueError("Unsupported runtime manifest.")
    try: profile=data["profiles"][engine]
    except KeyError: raise ValueError("Choose a supported runtime engine.") from None
    if not re.fullmatch(r"[a-z0-9./_-]+@sha256:[a-f0-9]{64}",profile.get("image","")):
        raise ValueError("The runtime image must be pinned by digest.")
    reserve=profile.get("installation_reserve_bytes")
    if type(reserve) is not int or reserve<=0:
        raise ValueError("The runtime installation reserve is missing.")
    return profile


def bootstrap_script(root=ROOT):
    data=json.loads((Path(root)/"remote/runtimes.json").read_text(encoding="utf-8"))
    snapshot=data.get("ubuntu_snapshot","")
    if not isinstance(snapshot,str) or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z",snapshot):
        raise ValueError("An immutable Ubuntu snapshot is required.")
    source=(Path(root)/"remote/bootstrap.sh").read_text(encoding="utf-8")
    if "@UBUNTU_SNAPSHOT@" not in source:
        raise ValueError("The bootstrap snapshot substitution is missing.")
    return source.replace("@UBUNTU_SNAPSHOT@",snapshot)


def payload_files(plan,*,native=False):
    extra=("remote/requirements-vllm.lock","remote/vllm-native.json") if native and plan.get("engine")=="vLLM" else ()
    return FILES+extra+("model.json",)


def source_payload(plan,root=ROOT,*,native=False):
    command(plan)
    settings={k:v for k,v in plan.items() if k in PLAN_FIELDS}
    output=io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode="wb",mtime=0,filename="") as zipped:
        with tarfile.open(fileobj=zipped,mode="w",format=tarfile.USTAR_FORMAT) as archive:
            for name in payload_files(plan,native=native):
                if name=="model.json": data=json.dumps(settings,sort_keys=True,allow_nan=False).encode()
                else:
                    path=Path(root)/name
                    if path.is_symlink() or not path.is_file():
                        raise ValueError("An inspected runtime source file is missing or is a link.")
                    data=path.read_bytes()
                info=tarfile.TarInfo(name)
                info.size=len(data); info.mode=0o600; info.mtime=0; info.uid=info.gid=0
                archive.addfile(info,io.BytesIO(data))
    raw=output.getvalue()
    return {"base64":base64.b64encode(raw).decode("ascii"),"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
