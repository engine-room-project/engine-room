"""Verify pinned native packages and GPU before a model or credentials are used."""
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys


def verify(root,*,load=importlib.import_module,version=importlib.metadata.version):
    root=Path(root)
    manifest=json.loads((root/"remote/vllm-native.json").read_text())
    lock=(root/"remote/requirements-vllm.lock").read_text().encode()
    if hashlib.sha256(lock).hexdigest()!=manifest["lock_sha256"]: raise ValueError("Native dependency proof changed")
    pins=dict(line.split("==",1) for line in lock.decode().splitlines() if line and not line.startswith(("#"," ")) and "==" in line)
    pins={name:value.split()[0] for name,value in pins.items()}
    if pins["torch"]!=manifest["torch_version"]: raise ValueError("Native package manifest changed")
    if version("vllm")!=manifest["version"] or version("torch").split("+")[0]!=pins["torch"]:
        raise ValueError("Native package versions differ from their pins")
    load("vllm"); load("vllm._C"); torch=load("torch")
    cuda=torch.version.cuda
    if not isinstance(cuda,str) or tuple(map(int,cuda.split(".")[:2]))<(13,0): raise ValueError("The native CUDA build is incompatible")
    if not torch.cuda.is_available() or torch.cuda.device_count()!=1: raise ValueError("Exactly one working CUDA GPU is required")
    capability=tuple(torch.cuda.get_device_capability(0))
    if len(capability)!=2 or any(type(v) is not int for v in capability) or capability<(7,5):
        raise ValueError("The actual GPU capability is unsupported")
    return dict(schema=1,engine="vLLM",version=manifest["version"],torch=pins["torch"],cuda=cuda,gpu_capability=list(capability),lock_sha256=manifest["lock_sha256"])


def main(root):
    root=Path(root); proof=verify(root)
    with (root/"native-runtime.json").open("x") as stream:
        os.chmod(root/"native-runtime.json",0o600)
        stream.write(json.dumps(proof,sort_keys=True)); stream.flush(); os.fsync(stream.fileno())
    descriptor=os.open(root,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


if __name__=="__main__": main(sys.argv[1])
