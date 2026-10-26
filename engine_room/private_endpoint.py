"""Owner-only Linux model/status sockets bound to an operation and socket instance."""
from dataclasses import asdict,dataclass,field
import http.client
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import threading
import time


def address(path,root):
    if not isinstance(path,(str,Path)): raise ValueError("Invalid private socket address.")
    path=Path(path); root=Path(root).absolute()
    if (not path.is_absolute() or path.resolve()!=path.absolute() or len(os.fsencode(path))>100
            or any(c in str(path) for c in ("\n","\r","\x00"))
            or (os.name=="posix" and any(c in str(path) for c in (":","%")))):
        raise ValueError("Choose a shorter original private socket path without colons or percent signs.")
    try: path.relative_to(root)
    except ValueError: raise ValueError("The socket is outside private controller state.") from None
    return path


def private_parents(path,root):
    if not sys.platform.startswith("linux"): raise ValueError("Private runtime sockets require the Linux controller.")
    root=Path(root).absolute(); current=Path(path).parent
    while True:
        info=current.stat()
        if (current.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077):
            raise ValueError("Runtime socket directories must be private to the controller user.")
        if current==root: break
        if current==current.parent: raise ValueError("Invalid private socket root.")
        current=current.parent


@dataclass(frozen=True)
class ModelEndpoint:
    path: str = field(repr=False)
    operation_key: str
    resource_id: str = field(repr=False)
    device: int
    inode: int
    pid: int
    kind: str = "unix"

    def validate(self,root,scope,resource_id=None):
        if (self.kind!="unix" or not isinstance(scope,str) or not re.fullmatch(r"[a-f0-9]{64}",scope)
                or self.operation_key!=scope or not isinstance(self.resource_id,str) or not self.resource_id
                or (resource_id is not None and self.resource_id!=resource_id)
                or any(type(v) is not int or v<0 for v in (self.device,self.inode,self.pid)) or not self.inode or not self.pid):
            raise ValueError("The private endpoint differs from this operation or socket instance.")
        address(self.path,root)
        return self

    def data(self): return asdict(self)

    @classmethod
    def read(cls,data,root,scope):
        if not isinstance(data,dict) or set(data)!={"path","operation_key","resource_id","device","inode","pid","kind"}:
            raise ValueError("Invalid private endpoint descriptor.")
        return cls(**data).validate(root,scope)

    def connect(self,root,scope,*,timeout=8):
        self.validate(root,scope); path=address(self.path,root); private_parents(path,root)
        info=path.lstat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077
                or (info.st_dev,info.st_ino)!=(self.device,self.inode)):
            raise ValueError("The private socket was replaced or is not owner-only.")
        peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); peer.settimeout(timeout)
        try:
            peer.connect(str(path))
            pid,uid,_=struct.unpack("3i",peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize("3i")))
            if uid!=os.geteuid() or pid!=self.pid: raise ValueError("The private socket process changed.")
            return peer
        except Exception:
            peer.close(); raise


class EndpointHTTP(http.client.HTTPConnection):
    def __init__(self,endpoint,root,scope,*,timeout=5):
        super().__init__("localhost",timeout=timeout)
        self.endpoint=endpoint; self.root=root; self.scope=scope
    def connect(self): self.sock=self.endpoint.connect(self.root,self.scope,timeout=self.timeout)

    def json(self,path="/",*,limit=16384):
        from .provider_http import read_bounded
        import json
        self.connect(); peer=self.sock; deadline=time.monotonic()+self.timeout
        def expired():
            try: peer.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        timer=threading.Timer(self.timeout,expired); timer.daemon=True; timer.start()
        response=None
        try:
            self.request("GET",path)
            response=self.getresponse()
            if response.status!=200: raise ValueError("Private runtime status is unavailable.")
            return json.loads(read_bounded(response,limit,deadline,time.monotonic))
        finally:
            timer.cancel()
            if response is not None: response.close()
            self.close()
