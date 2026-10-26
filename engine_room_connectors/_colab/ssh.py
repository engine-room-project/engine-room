"""Strict SSH through authenticated Colab native transport; no shared CLI state."""
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time

from engine_room.records import Store,atomic_json
from engine_room.ssh import PinnedSSH
from .channel import connect_ssh,public_key
from .ssh_proxy import bridge,private_directory,save_access


def scan_authenticated(lease,key,deadline,*,cancel,runner=subprocess.run,channel_factory=connect_ssh,now=time.time):
    """Initial keyscan reaches only an already authenticated, selected runtime TLS hop."""
    stopped=threading.Event(); authenticated=threading.Event(); errors=[]; connection=[]
    listener=socket.socket(); listener.bind(("127.0.0.1",0)); listener.listen(1); listener.settimeout(0.2)
    port=listener.getsockname()[1]
    def serve():
        try:
            while not stopped.is_set() and not cancel.is_set():
                try: client,_=listener.accept(); break
                except socket.timeout: continue
            else: return
            connection.append(client)
            if cancel.is_set(): return
            with client,channel_factory(lease,key,min(deadline,now()+30),cancel=stopped,now=now) as channel:
                authenticated.set()
                if bridge(channel,client.fileno(),client.fileno(),cancel=stopped)!=0: errors.append(True)
        except Exception: errors.append(True)
        finally:
            stopped.set()
            for client in connection:
                try: client.close()
                except OSError: pass
    worker=threading.Thread(target=serve,daemon=True); worker.start()
    try:
        if cancel.is_set(): raise ValueError("SSH enrollment was stopped.")
        result=runner(["ssh-keyscan","-T","12","-t","ed25519","-p",str(port),"127.0.0.1"],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode!=0 or len(result.stdout)>16384 or cancel.is_set() or not authenticated.is_set():
            raise ValueError("The selected runtime SSH identity could not be enrolled.")
        keys=set()
        for line in result.stdout.decode("ascii").splitlines():
            words=line.split()
            if len(words)!=3 or words[0]!=f"[127.0.0.1]:{port}": raise ValueError("Invalid authenticated SSH keyscan result.")
            keys.add(public_key(" ".join(words[1:])))
        if len(keys)!=1: raise ValueError("The authenticated runtime returned no unique SSH key.")
        return keys.pop()
    finally:
        stopped.set(); listener.close()
        for client in connection:
            try: client.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        worker.join(timeout=3)
        if worker.is_alive() or errors:
            raise RuntimeError("The scoped SSH enrollment did not close cleanly. Recover this rental before retrying.")


class ColabSSH(PinnedSSH):
    def __init__(self,directory,receipt,lease_supplier,authorize,*,forward_directory=None,now=time.time,runner=subprocess.run,popen=subprocess.Popen,scanner=scan_authenticated):
        directory=Path(directory)
        if not directory.is_absolute() or directory.resolve()!=directory.absolute():
            raise ValueError("Use an original absolute private SSH directory.")
        directory.mkdir(mode=0o700,parents=True,exist_ok=True); private_directory(directory)
        super().__init__(directory,forward_directory=forward_directory,runner=runner,popen=popen)
        self.receipt=receipt; self.lease_supplier=lease_supplier; self.authorize=authorize; self.now=now; self.scanner=scanner
        self.identity=self.directory/"ssh-identity.json"; self.key_intent=self.directory/"client-key-intent.json"
        self.guard=threading.RLock()
        if (self.directory/"ssh-lock").is_symlink(): raise ValueError("The SSH lock directory is a link.")
        self.file_guard=Store(self.directory/"ssh-lock")
        self.host="colab-runtime"; self.port=22; self.alias="engine-room-colab-"+receipt.operation_key()[:32]
        self._ensure()

    def _ensure(self):
        r=self.receipt; r.validate()
        if (r.mode!="rental" or r.connector_id!="colab" or not r.resource_id or not r.protection_id
                or r.state not in {"allocating","active"} or r.cancel_requested or self.now()>=r.deadline):
            raise ValueError("An ongoing protected owned Colab rental is required for SSH.")
        self.authorize()

    def _scope(self): return dict(operation_key=self.receipt.operation_key(),resource_id=self.receipt.resource_id)

    def _read(self,path,limit=4096):
        if path.is_symlink(): raise ValueError("Private SSH identity state is linked.")
        info=path.stat()
        if info.st_size>limit or info.st_uid!=os.geteuid() or info.st_mode&0o077:
            raise ValueError("Private SSH identity state is damaged or not private.")
        data=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or any(data.get(k)!=v for k,v in self._scope().items()):
            raise ValueError("The private SSH identity belongs to another operation or resource.")
        return data

    def generate(self):
        with self.guard,self.file_guard.allocation_lock():
            self._ensure()
            if self.key_intent.exists():
                proof=self._read(self.key_intent)
                if proof.get("state")!="generated" or not self.key.is_file() or self.key.is_symlink():
                    raise ValueError("SSH key creation is incomplete. Recover the rental without replacing its identity.")
                return {"public_key":public_key(self.public(self.key.with_suffix(".pub")))}
            if self.key.exists() or self.key.with_suffix(".pub").exists():
                raise ValueError("Existing identity files were not created by this operation.")
            atomic_json(self.key_intent,{**self._scope(),"state":"generating"})
            self.runner(["ssh-keygen","-t","ed25519","-f",str(self.key),"-N","","-C","engine-room-operation","-q"],
                check=True,capture_output=True,timeout=15)
            self.key.chmod(0o600); self.key.with_suffix(".pub").chmod(0o600)
            key=public_key(self.public(self.key.with_suffix(".pub")))
            atomic_json(self.key_intent,{**self._scope(),"state":"generated"})
            return {"public_key":key}

    def _known(self,key):
        expected=self.alias+" "+key+"\n"
        if self.known.exists() or self.known.is_symlink():
            if self.known.is_symlink() or self.known.stat().st_size>1024 or self.known.read_text()!=expected:
                raise ValueError("The pinned SSH host identity changed. Nothing was replaced.")
            return
        fd,name=tempfile.mkstemp(prefix=".known-",dir=self.directory)
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(expected.encode()); stream.flush(); os.fsync(stream.fileno())
            os.replace(name,self.known)
            directory=os.open(self.directory,os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally: Path(name).unlink(missing_ok=True)

    def _pin(self):
        proof=self._read(self.identity)
        if set(proof)!={"operation_key","resource_id","state","public_key"} or proof["state"]!="pinned":
            raise ValueError("SSH enrollment is incomplete. Recover this rental without accepting a new key.")
        key=public_key(proof["public_key"]); self._known(key)
        return key

    def refresh(self):
        self._ensure()
        key=public_key(self.public(self.key.with_suffix(".pub")))
        lease=self.lease_supplier()
        save_access(self.directory,self.receipt,lease,key,authorize=self.authorize,now=self.now)
        return lease,key

    def enroll(self,*,cancel):
        if cancel.is_set(): raise ValueError("SSH enrollment was stopped.")
        self.generate()
        with self.guard,self.file_guard.allocation_lock():
            self._ensure()
            if self.identity.exists(): return self._pin()
            if self.known.exists() or self.known.is_symlink(): raise ValueError("The original host identity proof is missing.")
            lease,key=self.refresh()
            atomic_json(self.identity,{**self._scope(),"state":"pending"})
            self._ensure()
            if cancel.is_set(): raise ValueError("SSH enrollment was stopped.")
            host=public_key(self.scanner(lease,key,self.receipt.deadline,cancel=cancel,runner=self.runner,now=self.now))
            self._ensure()
            if cancel.is_set(): raise ValueError("SSH enrollment was stopped.")
            atomic_json(self.identity,{**self._scope(),"state":"pinned","public_key":host})
            self._known(host)
            return host

    def args(self):
        self._ensure(); self._pin(); self.refresh()
        proxy=Path(__file__).with_name("ssh_proxy.py").resolve()
        parts=[sys.executable,"-I",str(proxy),"--access-file",str((self.directory/"ssh-access.json").resolve()),"--operation-key",self.receipt.operation_key()]
        if any("%" in item for item in parts): raise ValueError("Choose a private installation path without percent signs.")
        return super().args()+["-o","ProxyCommand="+shlex.join(parts),"-o","PreferredAuthentications=publickey",
            "-o","PasswordAuthentication=no","-o","KbdInteractiveAuthentication=no","-o","GSSAPIAuthentication=no",
            "-o","HostbasedAuthentication=no","-o","CertificateFile=none","-o","PKCS11Provider=none"]

    def run(self,*args,**kwargs):
        with self.guard:
            if self.tunnel is not None and self.tunnel.poll() is None:
                raise RuntimeError("The native SSH connection is already forwarding this session.")
            return super().run(*args,**kwargs)

    def forward(self,receipt=None):
        target=receipt or self.receipt
        if target.operation_key()!=self.receipt.operation_key() or target.resource_id!=self.receipt.resource_id:
            raise ValueError("The original SSH operation is required.")
        with self.guard: return super().forward(target)

    def close(self,receipt=None):
        target=receipt or self.receipt
        if target.operation_key()!=self.receipt.operation_key() or target.resource_id!=self.receipt.resource_id:
            raise ValueError("The original SSH operation is required.")
        return super().close(target)

    def discard_keys(self,receipt=None):
        with self.guard:
            self.close(); self._read(self.key_intent)
            owned=[self.key,self.key.with_suffix(".pub"),self.key_intent]
            if self.identity.exists():
                proof=self._read(self.identity); owned.append(self.identity)
                if self.known.exists():
                    if proof.get("state")!="pinned": raise ValueError("Unenrolled host state was not removed.")
                    expected=self.alias+" "+public_key(proof.get("public_key"))+"\n"
                    if self.known.is_symlink() or self.known.stat().st_size>1024 or self.known.read_text()!=expected:
                        raise ValueError("Changed host state was not removed.")
                    owned.append(self.known)
            elif self.known.exists() or self.known.is_symlink():
                raise ValueError("Unowned host state was not removed.")
            access_file=self.directory/"ssh-access.json"
            if access_file.exists(): self._read(access_file,32768); owned.append(access_file)
            if any(path.is_symlink() for path in owned): raise ValueError("Private SSH cleanup refused a linked path.")
            for path in owned: path.unlink(missing_ok=True)
