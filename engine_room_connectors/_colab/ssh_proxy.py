"""Runtime-only native SSH bytes. No allocation, account token or shared CLI state."""
# Direct isolated execution is used by OpenSSH's fixed ProxyCommand.
if __package__ in (None,""):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import argparse
from dataclasses import dataclass,field
import json
import math
import os
from pathlib import Path
import re
import select
import stat
import sys
import threading
import time

from engine_room.records import atomic_json
from engine_room_connectors._colab.api import endpoint
from engine_room_connectors._colab.channel import connect_ssh,public_key
from engine_room_connectors._colab.proxy import ProxyAccess,access


@dataclass(frozen=True)
class SSHAccess:
    lease: ProxyAccess = field(repr=False)
    deadline: float
    operation_key: str
    public_key: str


def private_directory(directory):
    if os.name!="posix": raise ValueError("The private SSH proxy requires the Linux controller.")
    path=Path(directory)
    if not path.is_absolute() or path.is_symlink() or path.resolve()!=path.absolute(): raise ValueError("Use an original private operation directory.")
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:
        raise ValueError("The operation directory must be private to the controller user.")
    return path


def validate(data,operation_key,now):
    fields={"schema","resource_id","url","token","expires_at","deadline","operation_key","public_key"}
    if (not isinstance(data,dict) or set(data)!=fields or data["schema"]!="colab-ssh-proxy-v1"
            or not isinstance(operation_key,str) or not re.fullmatch(r"[a-f0-9]{64}",operation_key)
            or data["operation_key"]!=operation_key): raise ValueError("The original SSH operation scope is required.")
    for name in ("expires_at","deadline"):
        value=data[name]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<value-now<=86400:
            raise ValueError("The scoped SSH access expired or is invalid.")
    identity=endpoint(data["resource_id"])
    checked=access(identity,dict(url=data["url"],token=data["token"],tokenExpiresInSeconds=1),now)
    lease=ProxyAccess(identity,checked.url,checked.token,data["expires_at"])
    return SSHAccess(lease,data["deadline"],operation_key,public_key(data["public_key"]))


def save_access(directory,receipt,lease,key,*,authorize,now=time.time):
    receipt.validate(); stamp=now()
    if (receipt.mode!="rental" or receipt.connector_id!="colab" or receipt.state not in {"allocating","active"}
            or receipt.cancel_requested or not receipt.protection_id or lease.resource_id!=receipt.resource_id):
        raise ValueError("An ongoing protected owned Colab rental is required.")
    directory=private_directory(directory)
    data=dict(schema="colab-ssh-proxy-v1",resource_id=lease.resource_id,url=lease.url,token=lease.token,
        expires_at=lease.expires_at,deadline=receipt.deadline,operation_key=receipt.operation_key(),public_key=key)
    validate(data,receipt.operation_key(),stamp)
    target=directory/"ssh-access.json"
    if target.is_symlink(): raise ValueError("The private access path is a link.")
    authorize(); atomic_json(target,data)
    return target


def load_access(path,operation_key,*,now=time.time):
    path=Path(path)
    if path.name!="ssh-access.json": raise ValueError("Use this operation's explicit runtime access file.")
    private_directory(path.parent)
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,"rb") as stream:
        info=os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077
                or info.st_size>32768): raise ValueError("The runtime access file must be private and bounded.")
        raw=stream.read(32769)
    if len(raw)>32768: raise ValueError("The runtime access file exceeds its limit.")
    return validate(json.loads(raw),operation_key,now())


def bridge(channel,input_fd,output_fd,*,cancel):
    """Bounded bytes and backpressure; an SSH parent's closed pipe stops the proxy."""
    if os.name!="posix": raise ValueError("The private SSH proxy requires the Linux controller.")
    errors=[]; was_blocking=os.get_blocking(output_fd); os.set_blocking(output_fd,False)
    def incoming():
        try:
            while not cancel.is_set():
                channel.check()
                ready,_,_=select.select([input_fd],[],[],0.5)
                if not ready: continue
                try: data=os.read(input_fd,16384)
                except BlockingIOError: continue
                if not data: break
                channel.send_bytes(data)
        except Exception: errors.append(True)
        finally:
            cancel.set(); channel.close()
    worker=threading.Thread(target=incoming,daemon=True); worker.start()
    try:
        while not cancel.is_set():
            data=channel.receive_bytes(); offset=0
            while offset<len(data) and not cancel.is_set():
                channel.check()
                _,ready,_=select.select([],[output_fd],[],0.5)
                if not ready: continue
                try: offset+=os.write(output_fd,data[offset:offset+16384])
                except BlockingIOError: continue
    except Exception:
        if not cancel.is_set(): errors.append(True)
    finally:
        cancel.set(); channel.close(); worker.join(timeout=2)
        os.set_blocking(output_fd,was_blocking)
    return 1 if errors or worker.is_alive() else 0


def main():
    parser=argparse.ArgumentParser(description="Private scoped Colab SSH transport")
    parser.add_argument("--access-file",required=True); parser.add_argument("--operation-key",required=True)
    args=parser.parse_args(); cancel=threading.Event()
    try:
        scoped=load_access(args.access_file,args.operation_key)
        with connect_ssh(scoped.lease,scoped.public_key,scoped.deadline,cancel=cancel) as channel:
            return bridge(channel,sys.stdin.fileno(),sys.stdout.fileno(),cancel=cancel)
    except Exception:
        print("The private SSH connection is unavailable. Check rental recovery.",file=sys.stderr)
        return 1


if __name__=="__main__": raise SystemExit(main())
