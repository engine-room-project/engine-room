"""Owned read-only attachment forward with bounded parent-pipe liveness."""
import ctypes
from contextlib import nullcontext
import errno
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

from .private_endpoint import ModelEndpoint
from .records import atomic_json


def exec_child(parent,args):
    """Run only inside the dedicated single-thread child shim, never preexec_fn."""
    if not sys.platform.startswith("linux") or not isinstance(args,list) or not args or args[0]!="ssh":
        raise ValueError("Unsupported attachment child.")
    binary=shutil.which("ssh")
    if not binary: raise ValueError("OpenSSH is unavailable.")
    binary=str(Path(binary).resolve()); info=os.stat(binary)
    if not stat.S_ISREG(info.st_mode) or info.st_mode&(stat.S_ISUID|stat.S_ISGID): raise ValueError("Privileged SSH executables are unsupported.")
    try:
        if os.getxattr(binary,"security.capability"): raise ValueError("Capability-bearing SSH executables are unsupported.")
    except OSError as error:
        if error.errno not in {errno.ENODATA,errno.ENOTSUP}: raise
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0: raise OSError("Parent-death protection is unavailable.")
    if os.getppid()!=parent: raise ValueError("The original supervisor is gone.")
    os.execv(binary,[binary,*args[1:]])


class _Stopped(Exception): pass


class ForwardSupervisor:
    def __init__(self,identity,receipt,root,source,destination,*,popen=subprocess.Popen,clock=time.monotonic,lease_seconds=60,startup_seconds=10,authorize=lambda:None,gate=nullcontext):
        receipt.validate()
        if any(type(value) not in (int,float) or not math.isfinite(value) or value<=0 for value in (lease_seconds,startup_seconds)):
            raise ValueError("Finite positive forward deadlines are required.")
        if receipt.mode!="attachment" or receipt.account_id!=identity.account_id or receipt.resource_id!=identity.resource_id or receipt.state!="active" or receipt.cancel_requested:
            raise ValueError("The original attachment identity and scope are required.")
        if not sys.platform.startswith("linux"): raise ValueError("Attachment forwarding requires Linux.")
        self.identity=identity; self.receipt=receipt; self.root=Path(root).absolute(); self.path=self.root/"m.sock"
        self.state_path=self.root/"forward.json"; self.state_written=False
        self.source=source; self.destination=destination; self.popen=popen; self.clock=clock
        self.lease_seconds=lease_seconds; self.startup_seconds=startup_seconds; self.child=None; self.endpoint=None; self.authorize=authorize; self.gate=gate
    def send(self,value):
        raw=(json.dumps(value,allow_nan=False,separators=(",",":"))+"\n").encode()
        if len(raw)>4096: raise ValueError("Oversized forward status.")
        self.destination.write(raw); self.destination.flush()
    def save(self,state,**extra):
        proof=dict(schema=1,operation_key=self.receipt.operation_key(),resource_id=self.receipt.resource_id,state=state,**extra)
        if self.state_written:
            if self.state_path.is_symlink() or self.state_path.stat().st_size>8192: raise ValueError("Forward evidence changed.")
            previous=json.loads(self.state_path.read_text(encoding="utf-8"))
            if any(previous.get(key)!=proof[key] for key in ("schema","operation_key","resource_id")): raise ValueError("Forward evidence changed.")
        atomic_json(self.state_path,proof); self.state_written=True
    def close(self):
        if self.child is not None and self.child.poll() is None:
            self.child.terminate()
            try: self.child.wait(timeout=2)
            except subprocess.TimeoutExpired: self.child.kill(); self.child.wait(timeout=2)
        disconnected=self.child is None or self.child.poll() is not None
        if self.path.exists() or self.path.is_symlink():
            info=self.path.lstat(); endpoint=self.endpoint
            if (endpoint is not None and stat.S_ISSOCK(info.st_mode) and info.st_uid==os.geteuid()
                    and (info.st_dev,info.st_ino)==(endpoint.device,endpoint.inode)):
                self.path.unlink()
            else: disconnected=False
        return disconnected
    def controls(self,pending,touched):
        stopping=False
        while b"\n" in pending:
            frame,pending=pending.split(b"\n",1)
            if frame==b"pulse": self.authorize(); touched=self.clock()
            elif frame==b"stop": stopping=True; break
            else: raise ValueError("Invalid forward control frame.")
        if len(pending)>64: raise ValueError("Oversized forward control frame.")
        return pending,touched,stopping
    def run(self):
        started=self.clock(); touched=started; pending=b""; ready=False; reason="uncertain"
        try:
            if self.state_path.exists() or self.state_path.is_symlink(): raise ValueError("Existing forward evidence was preserved.")
            args=self.identity.forward_args(self.root,self.path)
            self.save("starting")
            code="import sys,json;sys.path.insert(0,sys.argv[1]);from engine_room.attachment_forward import exec_child;exec_child(int(sys.argv[2]),json.loads(sys.argv[3]))"
            command=[sys.executable,"-I","-c",code,str(Path(__file__).resolve().parents[1]),str(os.getpid()),json.dumps(args)]
            with self.gate():
                self.authorize()
                with selectors.DefaultSelector() as check:
                    check.register(self.source,selectors.EVENT_READ)
                    if check.select(0):
                        pending=os.read(self.source.fileno(),256)
                        if not pending: reason="parent-ended"; raise _Stopped()
                        pending,touched,stopping=self.controls(pending,touched)
                        if stopping: reason="disconnect-requested"; raise _Stopped()
                self.child=self.popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            with selectors.DefaultSelector() as selector:
                selector.register(self.source,selectors.EVENT_READ)
                while True:
                    now=self.clock()
                    if not 0<=now-touched<self.lease_seconds: reason="liveness-expired"; break
                    if self.child.poll() is not None: reason="forward-ended"; break
                    events=selector.select(0.05)
                    stopping=False
                    if events:
                        raw=os.read(self.source.fileno(),256)
                        if not raw: reason="parent-ended"; break
                        pending+=raw
                        pending,touched,stopping=self.controls(pending,touched)
                        if stopping: reason="disconnect-requested"
                    if stopping: break
                    if not ready:
                        if now-started>=self.startup_seconds: reason="startup-expired"; break
                        try:
                            info=self.path.lstat()
                            endpoint=ModelEndpoint(str(self.path),self.receipt.operation_key(),self.receipt.resource_id,info.st_dev,info.st_ino,self.child.pid)
                            with endpoint.connect(self.root,self.receipt.operation_key(),timeout=0.5): pass
                            self.authorize()
                            self.endpoint=endpoint
                            self.save("ready",endpoint=endpoint.data())
                            ready=True
                            self.send(dict(event="ready",endpoint=endpoint.data(),shutdown_confirmed=False))
                        except (FileNotFoundError,ConnectionRefusedError): pass
        except _Stopped: pass
        except Exception: reason="uncertain"
        finally:
            disconnected=False
            try: disconnected=self.close() if self.state_written else False
            except Exception: pass
            try:
                if self.state_written: self.save("closed",disconnected=disconnected,endpoint=self.endpoint.data() if self.endpoint is not None else None)
            except Exception: disconnected=False
            try: self.send(dict(event="closed",disconnected=disconnected,reason=reason,shutdown_confirmed=False))
            except Exception: pass
        return 0 if disconnected else 1


def main(directory):
    """Load only the original saved operation; IPC cannot substitute connection settings."""
    from .attachment_identity import Identity
    from .connections import Connections
    from .controller_protocol import decode,fields
    from .credentials import Credentials
    from .private_endpoint import private_parents
    from .records import Store
    scope_verified=False; begun=False
    try:
        root=Path(directory).absolute()
        if root.resolve()!=root: raise ValueError("Linked state is unsupported.")
        private_parents(root/"check",root)
        raw=b""; until=time.monotonic()+15
        with selectors.DefaultSelector() as selector:
            selector.register(sys.stdin.buffer,selectors.EVENT_READ)
            while not raw.endswith(b"\n"):
                if len(raw)>=4096 or time.monotonic()>=until or not selector.select(max(0,until-time.monotonic())):
                    raise ValueError("Missing bounded attachment start.")
                part=os.read(sys.stdin.fileno(),1)
                if not part: raise ValueError("The attachment parent closed.")
                raw+=part
        message=decode(raw); fields(message,("operation_id","operation_key"))
        receipt=Store(root/"receipts").load(message["operation_id"])
        if receipt.mode!="attachment" or receipt.state!="active" or receipt.cancel_requested or receipt.operation_key()!=message["operation_key"]: raise ValueError("Attachment scope changed.")
        connection=Connections(root,{}).read()[receipt.connection_id]
        if connection.account_id!=receipt.account_id or connection.connector_id!=receipt.connector_id:
            raise ValueError("The original connection is required.")
        scope_verified=True
        identity=Identity.load(connection.settings,connection.credential_ref,Credentials(root/"credentials"))
        forward_root=root/"s"/receipt.operation_key()[:16]
        def authorize():
            current=Store(root/"receipts").load(receipt.operation_id)
            saved=Connections(root,{}).read().get(connection.id)
            if (current.operation_key()!=receipt.operation_key() or current.mode!="attachment" or current.state!="active"
                    or current.cancel_requested or current.resource_id!=receipt.resource_id or saved!=connection):
                raise ValueError("Attachment authority changed.")
        supervisor=ForwardSupervisor(identity,receipt,forward_root,sys.stdin.buffer,sys.stdout.buffer,
            authorize=authorize,gate=Store(root/"receipts").allocation_lock)
        begun=True
        return supervisor.run()
    except Exception:
        confirmed=False
        if scope_verified and not begun:
            try:
                base=root/"s"; base.mkdir(mode=0o700,exist_ok=True)
                private_parents(base/"check",root)
                target=base/receipt.operation_key()[:16]
                target.mkdir(mode=0o700)  # A prior path is uncertain and must not be adopted.
                atomic_json(target/"forward.json",dict(schema=1,state="closed",disconnected=True,
                    operation_key=receipt.operation_key(),resource_id=receipt.resource_id,endpoint=None))
                confirmed=True
            except Exception: pass
        try:
            sys.stdout.buffer.write((json.dumps(dict(event="closed",disconnected=confirmed,
                reason="not-started" if confirmed else "uncertain",shutdown_confirmed=False))+"\n").encode())
            sys.stdout.buffer.flush()
        except Exception: pass
        return 1
