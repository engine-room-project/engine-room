"""Read-only remote hardware inventory; no credentials, hostnames or machine identity."""
import csv
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

SAFE_PATH="/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def collect(root,*,run=subprocess.run):
    folder=Path(root)
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise ValueError("The explicit runtime work filesystem is unavailable.")
    disk=shutil.disk_usage(folder)
    release={}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key,sep,value=line.partition("=")
            if sep and key in {"ID","VERSION_ID"}: release[key]=value.strip('"')[:100]
    except OSError: pass
    result=dict(schema=1,system=platform.system(),machine=platform.machine(),
        kernel_python=list(sys.version_info[:3]),libc=list(platform.libc_ver()),os=release,root=str(folder),
        disk_free_bytes=disk.free,disk_total_bytes=disk.total,gpus=[],cuda=None,
        gpu_error="GPU details could not be verified.")
    binary=shutil.which("nvidia-smi",path=SAFE_PATH)
    if not binary: return result
    def command(args):
        value=run([binary,*args],capture_output=True,text=True,timeout=10,check=True,
            env={"PATH":SAFE_PATH,"LC_ALL":"C"})
        if len(value.stdout)>65536: raise ValueError("GPU report exceeds its limit.")
        return value.stdout
    try:
        driver=command([])
        cuda=re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)",driver)
        if not cuda: return result
        rows=csv.reader(io.StringIO(command(["--query-gpu=name,memory.total,memory.free,compute_cap","--format=csv,noheader,nounits"])))
        gpus=[]
        for row in rows:
            if len(row)!=4 or len(gpus)>=16: return result
            name,memory,free,capability=(field.strip() for field in row)
            if not name or len(name)>200: return result
            gpus.append(dict(name=name,memory_mib=float(memory),free_mib=float(free),compute_capability=float(capability)))
        result.update(cuda=cuda.group(1),gpus=gpus,gpu_error=None)
    except Exception: pass
    return result


if __name__=="__main__":
    print(json.dumps(collect(sys.argv[1]),allow_nan=False,sort_keys=True))
