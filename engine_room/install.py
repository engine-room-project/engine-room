"""Install only verified source files into a new directory; never touch runtime state."""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import sys


def linked(path):
    value=path.lstat()
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))


def inspect_source(source):
    source=Path(source)
    if linked(source) or not source.is_dir(): raise ValueError("Use an ordinary extracted source directory.")
    manifest_path=source/"SOURCE_MANIFEST.json"
    if linked(manifest_path) or manifest_path.stat().st_size>1024*1024: raise ValueError("Invalid source manifest.")
    raw=manifest_path.read_bytes(); manifest=json.loads(raw)
    if (not isinstance(manifest,dict) or set(manifest)!={"schema","source_commit","status","files"}
            or type(manifest["schema"]) is not int or manifest["schema"]!=1
            or not isinstance(manifest["source_commit"],str) or not re.fullmatch(r"[a-f0-9]{40}",manifest["source_commit"])
            or not isinstance(manifest["status"],str) or not manifest["status"].startswith("UNPUBLISHED CANDIDATE")
            or not isinstance(manifest["files"],list) or not 1<=len(manifest["files"])<=4096):
        raise ValueError("Invalid source manifest.")
    result={}; names=set(); total=0
    for item in manifest["files"]:
        if not isinstance(item,dict) or set(item)!={"path","sha256","bytes"}: raise ValueError("Invalid manifest entry.")
        name=item["path"]
        if (not isinstance(name,str) or not name or "\\" in name or ":" in name or "\x00" in name
                or PurePosixPath(name).is_absolute() or any(part in {"..","."} or not part or part.endswith((" ",".")) for part in name.split("/"))
                or name.casefold() in names or name.casefold() in {"source_manifest.json","installation.json"}
                or type(item["bytes"]) is not int or not 0<=item["bytes"]<=8*1024*1024
                or not isinstance(item["sha256"],str) or not re.fullmatch(r"[a-f0-9]{64}",item["sha256"])):
            raise ValueError("Unsafe or duplicate manifest path.")
        names.add(name.casefold()); path=source
        for part in name.split("/"):
            path=path/part
            if linked(path): raise ValueError("Linked source files are not accepted.")
        if not path.is_file() or path.stat().st_size!=item["bytes"]: raise ValueError("Source size differs from manifest.")
        data=path.read_bytes(); total+=len(data)
        if total>128*1024*1024 or hashlib.sha256(data).hexdigest()!=item["sha256"]: raise ValueError("Source integrity verification failed.")
        result[name]=data
    if not {"EngineRoom.ps1","desktop/ui.ps1","engine_room/desktop_bridge.py","THIRD_PARTY_NOTICES/README.md"}.issubset(result):
        raise ValueError("Required application source or notices are missing.")
    result["SOURCE_MANIFEST.json"]=raw
    return manifest,result


def install(source,destination):
    manifest,files=inspect_source(source); source=Path(source).resolve(); destination=Path(destination).absolute()
    if destination==source or source in destination.parents or destination in source.parents:
        raise ValueError("Choose a separate new installation directory.")
    if destination.exists() or destination.is_symlink(): raise ValueError("An existing installation is never overwritten.")
    for parent in (destination.parent,*destination.parent.parents):
        if (parent.exists() or parent.is_symlink()) and linked(parent):
            raise ValueError("Choose an installation path without linked directories.")
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.mkdir()  # Exclusive; partial failures are preserved for inspection, never recursively deleted.
    for name,data in sorted(files.items()):
        target=destination.joinpath(*name.split("/")); target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as handle: handle.write(data)
        if os.name=="posix": target.chmod(0o700 if target.suffix==".sh" else 0o600)
    receipt=dict(schema=1,source_commit=manifest["source_commit"],destination=str(destination),python=sys.executable,
        source_manifest_sha256=hashlib.sha256(files["SOURCE_MANIFEST.json"]).hexdigest(),runtime_state_preserved=True)
    with (destination/"installation.json").open("x",encoding="utf-8") as handle: json.dump(receipt,handle,sort_keys=True,indent=2)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--source",type=Path,required=True); parser.add_argument("--destination",type=Path,required=True)
    args=parser.parse_args()
    if sys.version_info<(3,12): raise ValueError("Python 3.12 or newer is required.")
    print(json.dumps(install(args.source,args.destination),sort_keys=True))

if __name__=="__main__": main()
