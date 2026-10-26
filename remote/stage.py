"""Stage inspected source in a new operation-owned folder; never overwrite or delete."""
import base64
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile


def flush_directory(path):
    if os.name!="nt":
        descriptor=os.open(path,os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)


def owner_record(root,value):
    descriptor,name=tempfile.mkstemp(prefix=".owner-",dir=root)
    with os.fdopen(descriptor,"wb") as stream:
        stream.write((json.dumps(value,sort_keys=True,allow_nan=False)+"\n").encode())
        stream.flush(); os.fsync(stream.fileno())
    os.replace(name,root/".engine-room-owner.json")
    flush_directory(root)


def stage(base,operation_key,encoded,digest,expected):
    parent=Path(base)
    if (not parent.is_absolute() or parent.resolve()!=parent.absolute() or not parent.is_dir()
            or not isinstance(operation_key,str) or not re.fullmatch(r"[a-f0-9]{64}",operation_key)
            or not isinstance(digest,str) or not re.fullmatch(r"[a-f0-9]{64}",digest)
            or not isinstance(encoded,str) or len(encoded)>1024*1024):
        raise ValueError("Invalid owned runtime staging request.")
    if (not isinstance(expected,(list,tuple)) or not expected or len(expected)>100
            or any(not isinstance(name,str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*",name)
                or any(part in {".",".."} for part in name.split("/")) for name in expected)
            or len(set(expected))!=len(expected) or ".engine-room-owner.json" in expected):
        raise ValueError("Invalid runtime source allowlist.")
    raw=base64.b64decode(encoded,validate=True)
    if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError("The runtime source hash differs.")
    root=parent/("engine-room-"+operation_key[:32])
    # Validate all entries before even creating the owned folder.
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
        unpacked=zipped.read(5*1024*1024+1)
    if len(unpacked)>5*1024*1024: raise ValueError("The runtime source exceeds its extraction limit.")
    with tarfile.open(fileobj=io.BytesIO(unpacked),mode="r:") as archive:
        members=archive.getmembers(); names=[m.name for m in members]
        if (len(names)!=len(expected) or set(names)!=set(expected)
                or any(not member.isfile() or member.pax_headers or member.size<0 for member in members)
                or sum(member.size for member in members)>4*1024*1024):
            raise ValueError("The runtime source archive differs from its regular-file allowlist.")
        root.mkdir(mode=0o700)  # Existing or symlink directory is never adopted.
        flush_directory(parent)
        proof=dict(schema=1,operation_key=operation_key,source_sha256=digest,state="extracting")
        owner_record(root,proof)
        # On any failure leave the owned partial directory intact for recovery.
        for member in members:
            target=root/member.name
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with archive.extractfile(member) as source,target.open("xb") as output:
                output.write(source.read()); output.flush(); os.fsync(output.fileno())
            target.chmod(0o600)
        for directory,_,_ in os.walk(root,topdown=False): flush_directory(directory)
        owner_record(root,{**proof,"state":"staged"})
    return dict(root=str(root),source_sha256=digest,state="staged")
