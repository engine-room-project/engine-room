"""Fixed, finite Windows worker for the shared PowerShell model planner."""
from pathlib import Path
import math
import shutil
import subprocess

from .controller_protocol import decode,encode,fields
from .model_server import command
from .payload import PLAN_FIELDS


def plan(request,*,runner=subprocess.run,which=shutil.which):
    fields(request,("mode","discovery"),("engine","variant","context"))
    if request["mode"] not in {"describe","plan"} or not isinstance(request["discovery"],dict): raise ValueError("Invalid planning request.")
    executable=which("powershell.exe")
    if not executable: raise ValueError("Windows PowerShell is required for desktop model planning.")
    root=Path(__file__).resolve().parents[1]
    result=runner([executable,"-NoProfile","-NonInteractive","-File",str(root/"desktop/model-plan.ps1")],
        input=encode(request),capture_output=True,timeout=35,cwd=root)
    if result.returncode or len(result.stdout)>262144 or len(result.stderr)>16384: raise ValueError("The model plan could not be verified.")
    response=decode(result.stdout)
    if response.get("ok") is not True: raise ValueError("The model plan could not be verified.")
    value=response["result"]
    if request["mode"]=="describe": return value
    full=value["plan"]
    executable_plan={key:item for key,item in full.items() if key in PLAN_FIELDS|{"overheadBytes","kvBytesPerToken"}}
    command(executable_plan)
    for number in (value["estimated_memory_bytes"],full.get("weightBytes"),full.get("overheadBytes"),full.get("kvBytesPerToken")):
        if type(number) not in (int,float) or not math.isfinite(number) or number<=0:
            raise ValueError("The published memory estimate is invalid.")
    return dict(plan=executable_plan,estimated_memory_bytes=value["estimated_memory_bytes"],native_context=full["nativeContext"],
        warning=full["warning"],quality=full["quality"])
