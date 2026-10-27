"""Build an unpublished source candidate from an explicit committed-file allowlist."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import zipfile

ROOT_FILES={"LICENSE","Install-EngineRoom.ps1","EngineRoom.ps1","models.ps1","tools.ps1","README.md"}
PREFIXES=("engine_room/","engine_room_connectors/","desktop/","controller/","remote/","THIRD_PARTY_NOTICES/","tests/","scripts/release/")
DOCS={"docs/COLAB_CONNECTOR.md","docs/DEPENDENCIES.md","docs/ATTACHMENTS.md","docs/CODING_TOOLS.md","docs/STORAGE_RECOVERY.md","docs/RUNPOD_CONNECTOR.md","docs/CONTROLLER.md","docs/DESKTOP.md","docs/INSTALLATION.md","docs/OPERATIONS.md","docs/PRIVACY.md","docs/SUPPORTED_COMBINATIONS.md","docs/PACKAGING.md"}
REQUIRED={"LICENSE","Install-EngineRoom.ps1","README.md","EngineRoom.ps1","desktop/ui.ps1","engine_room/desktop_bridge.py","engine_room/controller_service.py",*DOCS,
    "THIRD_PARTY_NOTICES/README.md","THIRD_PARTY_NOTICES/google-colab-cli-LICENSE.txt","THIRD_PARTY_NOTICES/vllm-LICENSE.txt","THIRD_PARTY_NOTICES/llama.cpp-LICENSE.txt","THIRD_PARTY_NOTICES/huggingface-hub-LICENSE.txt"}
FORBIDDEN={"__pycache__",".git",".venv","credentials","receipts","state","controller-owner","runpod-operations","colab-operations"}

def git(root,*args):
    return subprocess.check_output(["git","-C",str(root),*args],stderr=subprocess.PIPE)

def build(root,output,revision="HEAD"):
    if revision!="HEAD" and not re.fullmatch(r"[a-f0-9]{40}",revision): raise ValueError("Use HEAD or an exact commit ID.")
    commit=git(root,"rev-parse","--verify",revision+"^{commit}").decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40}",commit): raise ValueError("Invalid source revision.")
    entries={}
    for row in git(root,"ls-tree","-r","-z",commit).split(b"\0"):
        if not row: continue
        meta,raw=row.split(b"\t",1); mode,kind,oid=meta.split(); name=raw.decode("utf-8")
        if name not in ROOT_FILES|DOCS and not name.startswith(PREFIXES): continue
        parts=PurePosixPath(name).parts
        if (mode not in {b"100644",b"100755"} or kind!=b"blob" or "\\" in name or name.startswith("/")
                or any(part in FORBIDDEN or part in {"..","."} or part.endswith(".local") for part in parts)
                or name.endswith((".pyc",".key",".pem",".xml",".log"))):
            raise ValueError("Unsupported or state-bearing source entry: "+name)
        data=git(root,"cat-file","blob",oid.decode())
        if len(data)>8*1024*1024: raise ValueError("Source entry exceeds the package bound: "+name)
        entries[name]=(data,mode)
    missing=REQUIRED-entries.keys()
    if missing: raise ValueError("Required source documentation/notices are missing: "+", ".join(sorted(missing)))
    if sum(len(value[0]) for value in entries.values())>128*1024*1024: raise ValueError("Source package exceeds its bound.")
    manifest=dict(schema=1,source_commit=commit,status="UNPUBLISHED CANDIDATE - MIT; OWNER RELEASE APPROVAL REQUIRED",
        files=[dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)) for name,(data,_) in sorted(entries.items())])
    entries["SOURCE_MANIFEST.json"]=((json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode(),b"100644")
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation preserves any previously inspected artifact.
    with output.open("xb") as target:
        with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for name,(data,mode) in sorted(entries.items()):
                info=zipfile.ZipInfo("engine-room-source/"+name,date_time=(2020,1,1,0,0,0)); info.create_system=3
                info.external_attr=(0o100755 if mode==b"100755" else 0o100644)<<16
                info.compress_type=zipfile.ZIP_DEFLATED; archive.writestr(info,data,compresslevel=9)
    return manifest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[2]); parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--revision",default="HEAD"); args=parser.parse_args()
    result=build(args.root,args.output,args.revision)
    print("Unpublished source candidate:",result["source_commit"],"files:",len(result["files"]))

if __name__=="__main__": main()
