"""Generate credential-free probes and check actual hardware against the selected plan."""
import json
import math
from pathlib import Path
import re

from engine_room.model_validation import gguf_files,safetensors_files
from engine_room.model_server import command
from engine_room.payload import runtime_profile
from engine_room.storage import plan_storage
from .api import ACCELERATORS

ROOT=Path(__file__).resolve().parents[2]


def code(root="/content"):
    if not isinstance(root,str) or not re.fullmatch(r"/[A-Za-z0-9/_-]{1,199}",root) or ".." in root:
        raise ValueError("Choose an explicit runtime work filesystem.")
    source=(ROOT/"remote/probe.py").read_text(encoding="utf-8")
    # Use a private namespace: avoid running the script's CLI or changing kernel globals.
    return f"_er_probe={{'__name__':'engine_room_probe'}}; exec({source!r},_er_probe); print(_er_probe['json'].dumps(_er_probe['collect']({root!r}),allow_nan=False,sort_keys=True)); del _er_probe"


def validate(report,plan,accelerator,root="/content"):
    command(plan)
    if accelerator not in ACCELERATORS: raise ValueError("Choose a supported Colab accelerator explicitly.")
    if (not isinstance(report,dict) or type(report.get("schema")) is not int or report["schema"]!=1
            or report.get("system")!="Linux" or report.get("machine") not in {"x86_64","amd64"}
            or report.get("root")!=root):
        raise ValueError("The actual Colab platform or work filesystem differs from the checked runtime.")
    python=report.get("kernel_python")
    if (not isinstance(python,list) or len(python)!=3 or any(type(v) is not int or v<0 for v in python)
            or python[:2] not in ([3,12],[3,13])):
        raise ValueError("This bootstrap requires a supported notebook Python (3.12 or 3.13). Model Python is installed separately.")
    os_release=report.get("os")
    if not isinstance(os_release,dict) or os_release.get("ID")!="ubuntu" or os_release.get("VERSION_ID")!="24.04":
        raise ValueError("The current pinned native bootstrap requires Ubuntu 24.04. This machine was not modified.")
    profile=runtime_profile(plan["engine"])
    if plan["engine"]=="llama.cpp":
        abi=json.loads((ROOT/"remote/runtimes.json").read_text(encoding="utf-8"))["llama"]["native_abi"]
        libc=report.get("libc")
        if (not isinstance(libc,list) or len(libc)!=2 or libc[0]!="glibc"
                or not isinstance(libc[1],str) or not re.fullmatch(r"[0-9]+\.[0-9]+",libc[1])
                or tuple(map(int,libc[1].split(".")))<tuple(map(int,abi["minimum_glibc"].split(".")))):
            raise ValueError("The actual C runtime is older than the inspected GGUF binary requires.")
    cuda=report.get("cuda")
    if not isinstance(cuda,str) or not re.fullmatch(r"[0-9]+\.[0-9]+",cuda) or tuple(map(int,cuda.split(".")))<tuple(map(int,profile["minimum_cuda"].split("."))):
        raise ValueError("The actual GPU driver does not meet the pinned runtime requirement.")
    gpus=report.get("gpus")
    if report.get("gpu_error") is not None or not isinstance(gpus,list) or len(gpus)!=1 or not isinstance(gpus[0],dict):
        raise ValueError("The actual rental must report exactly one verified GPU.")
    gpu=gpus[0]; name=gpu.get("name")
    if not isinstance(name,str) or not re.search(r"(?<![A-Za-z0-9])"+re.escape(accelerator)+r"(?![A-Za-z0-9])",name):
        raise ValueError("The actual GPU differs from the selected Colab accelerator.")
    memory=gpu.get("memory_mib"); available=gpu.get("free_mib"); capability=gpu.get("compute_capability")
    fields=[plan.get("weightBytes"),plan.get("overheadBytes"),plan.get("kvBytesPerToken"),memory,capability,available]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in fields):
        raise ValueError("The checked model or actual GPU memory details are incomplete.")
    required=fields[0]+fields[1]+fields[2]*plan["context"]
    if available>memory or required>min(memory*0.92,available)*1024**2 or (plan.get("dtype")=="bfloat16" and capability<8):
        raise ValueError("The actual GPU cannot support the checked model memory or precision.")
    sizes=plan.get("fileSizes")
    if plan["engine"]=="llama.cpp":
        files,projector=gguf_files(plan); names=files+([projector] if projector else [])
    else: names=safetensors_files(plan)
    if not isinstance(sizes,dict) or set(sizes)!=set(names):
        raise ValueError("The published sizes do not match every selected model file.")
    free=report.get("disk_free_bytes"); total=report.get("disk_total_bytes")
    if (not isinstance(sizes,dict) or not sizes or any(type(v) is not int or v<=0 for v in sizes.values())
            or type(free) is not int or type(total) is not int or not 0<=free<=total):
        raise ValueError("The model files or actual disk capacity could not be verified.")
    storage=plan_storage(list(sizes.values()),free,profile["installation_reserve_bytes"])
    if not storage.fits:
        raise ValueError("The actual rental disk cannot hold the pinned runtime and model. Nothing was removed.")
    return dict(runtime_python="3.12",required_gpu_bytes=required,available_gpu_bytes=memory*1024**2,
        storage_required_bytes=storage.required_bytes,storage_available_bytes=free)


def inspect_runtime(session,connection,receipt,plan,accelerator,*,authorize,cancel,root="/content"):
    """Consume the owned kernel channel; no installer or credential access is invoked."""
    raw=session.execute(connection,receipt,code(root),authorize=authorize,cancel=cancel,timeout=60)
    try: report=json.loads(raw)
    except (ValueError,TypeError):
        raise ValueError("The actual Colab runtime did not return a complete hardware report.") from None
    capacity=validate(report,plan,accelerator,root)
    return dict(report=report,capacity=capacity)
