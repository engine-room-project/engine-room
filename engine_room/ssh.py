"""Pinned, isolated OpenSSH sessions. Never read or modify the user's SSH configuration."""
import base64
import hashlib
import ipaddress
import json
import os
import stat
import time
from pathlib import Path
import re
import socket
import subprocess

from .records import atomic_json
from .private_endpoint import ModelEndpoint,address,private_parents


class PinnedSSH:
    def __init__(self,directory,*,forward_directory=None,runner=subprocess.run,popen=subprocess.Popen):
        self.directory=Path(directory).absolute()
        self.forward_directory=Path(forward_directory or self.directory).absolute()
        address(self.forward_directory/"m.sock",self.forward_directory)
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.forward_directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        if os.name=="posix":
            private_parents(self.directory/"identity-check",self.directory)
            private_parents(self.forward_directory/"m.sock",self.forward_directory)
        self.runner=runner; self.popen=popen
        self.key=self.directory/"client-key"
        self.host_key=self.directory/"host-key"
        self.known=self.directory/"known-hosts"
        self.host=None; self.port=None; self.alias=None; self.tunnel=None
        self.model_socket=self.forward_directory/"m.sock"; self.status_socket=self.forward_directory/"s.sock"
        self.forward_state=self.directory/"forward.json"

    def generate(self):
        for path in (self.key,self.host_key):
            if path.exists(): raise ValueError("This operation already has SSH identity state; reconcile it before allocating again.")
            self.runner(["ssh-keygen","-t","ed25519","-f",str(path),"-N","","-C","engine-room-operation","-q"],check=True,capture_output=True,timeout=15)
            path.chmod(0o600)
        return {"public_key":self.public(self.key.with_suffix(".pub")),
                "host_private_b64":base64.b64encode(self.host_key.read_bytes()).decode("ascii")}

    @staticmethod
    def public(path):
        words=Path(path).read_text(encoding="utf-8").split()
        if len(words)<2 or words[0]!="ssh-ed25519" or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}",words[1]):
            raise ValueError("The operation's SSH public key is invalid.")
        return " ".join(words[:2])

    def endpoint(self,host,port):
        try: address=ipaddress.ip_address(host)
        except ValueError: raise ValueError("The provider did not return a valid SSH address.") from None
        if not address.is_global or type(port) is not int or not 1<=port<=65535:
            raise ValueError("The managed rental's SSH endpoint is invalid.")
        public=self.public(self.host_key.with_suffix(".pub"))
        self.alias="engine-room-"+hashlib.sha256(public.encode()).hexdigest()[:32]
        self.known.write_text(self.alias+" "+public+"\n",encoding="utf-8")
        self.known.chmod(0o600)
        self.host=str(address); self.port=port

    def args(self):
        if not self.host or not self.alias: raise ValueError("Pinned SSH endpoint is not ready.")
        known=self.known.resolve().as_posix()
        if '"' in known: raise ValueError("Choose a private SSH state path without quotation marks.")
        return ["ssh","-F","none","-o","BatchMode=yes","-o","IdentitiesOnly=yes","-o","IdentityAgent=none",
            "-o","StrictHostKeyChecking=yes","-o",'GlobalKnownHostsFile="'+known+'"',"-o","HostKeyAlgorithms=ssh-ed25519","-o","UpdateHostKeys=no","-o","ForwardAgent=no",
            "-o","ForwardX11=no","-o","PermitLocalCommand=no","-o",'UserKnownHostsFile="'+known+'"',"-o","HostKeyAlias="+self.alias,
            "-o","ConnectTimeout=8","-o","ServerAliveInterval=15","-o","ServerAliveCountMax=2",
            "-i",str(self.key),"-p",str(self.port)]

    def run(self,command,*,data=None,timeout=15):
        try:
            result=self.runner(self.args()+["root@"+self.host,command],input=data,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,timeout=timeout,check=False)
            if result.returncode!=0 or len(result.stdout)>65536: raise RuntimeError("SSH request failed")
            return result.stdout
        except Exception:
            raise RuntimeError("The pinned private SSH request failed. Check the rental connection.") from None

    def _forward_record(self,receipt):
        if self.forward_state.is_symlink() or self.forward_state.stat().st_size>8192:
            raise ValueError("Private forward ownership state is damaged.")
        data=json.loads(self.forward_state.read_text())
        if (not isinstance(data,dict) or data.get("schema")!=1 or data.get("operation_key")!=receipt.operation_key()
                or data.get("resource_id")!=receipt.resource_id or data.get("state") not in {"starting","ready","closed"}
                or data.get("paths")!={"model":str(self.model_socket),"status":str(self.status_socket)}):
            raise ValueError("Private forwards belong to another operation or resource.")
        return data

    def forward_endpoint(self,role,receipt):
        data=self._forward_record(receipt)
        if data["state"]!="ready" or role not in {"model","status"}: raise ValueError("Private forwards are not ready.")
        row=data["sockets"][role]
        return ModelEndpoint(data["paths"][role],receipt.operation_key(),receipt.resource_id,row["device"],row["inode"],data["pid"]).validate(self.forward_directory,receipt.operation_key(),receipt.resource_id)

    def forward(self,receipt):
        receipt.validate()
        if not receipt.resource_id: raise ValueError("Known resource identity is required before forwarding.")
        if self.tunnel is not None and self.tunnel.poll() is None:
            self._forward_record(receipt); return
        for path in (self.model_socket,self.status_socket):
            address(path,self.forward_directory)
            if path.exists() or path.is_symlink(): raise ValueError("A private forward path already exists; it was not removed or adopted.")
        if self.forward_state.exists() and self._forward_record(receipt)["state"]!="closed":
            raise ValueError("Previous forward startup is uncertain. Recover it before starting again.")
        proof=dict(schema=1,state="starting",operation_key=receipt.operation_key(),resource_id=receipt.resource_id,
            paths={"model":str(self.model_socket),"status":str(self.status_socket)})
        args=self.args()+["-N","-o","ExitOnForwardFailure=yes","-o","StreamLocalBindMask=0177","-o","StreamLocalBindUnlink=no",
            "-L",f"{self.model_socket}:127.0.0.1:8000","-L",f"{self.status_socket}:127.0.0.1:8001","root@"+self.host]
        atomic_json(self.forward_state,proof)
        self.tunnel=self.popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        sockets={}; until=time.monotonic()+10
        try:
            while time.monotonic()<until:
                if self.tunnel.poll() is not None: raise RuntimeError("The private SSH forward exited.")
                for role,path in (("model",self.model_socket),("status",self.status_socket)):
                    if role in sockets: continue
                    try:
                        info=path.lstat()
                        endpoint=ModelEndpoint(str(path),receipt.operation_key(),receipt.resource_id,info.st_dev,info.st_ino,self.tunnel.pid)
                        with endpoint.connect(self.forward_directory,receipt.operation_key(),timeout=1): pass
                    except (FileNotFoundError,ConnectionRefusedError): continue
                    sockets[role]={"device":info.st_dev,"inode":info.st_ino}
                    # Keep ownership evidence even if the other listener fails.
                    atomic_json(self.forward_state,{**proof,"pid":self.tunnel.pid,"sockets":sockets})
                if len(sockets)==2:
                    atomic_json(self.forward_state,{**proof,"state":"ready","pid":self.tunnel.pid,"sockets":sockets}); return
                time.sleep(0.05)
            raise RuntimeError("The private SSH sockets did not become ready.")
        except Exception:
            self.close(receipt); raise

    def close(self,receipt=None):
        if self.tunnel is not None and self.tunnel.poll() is None:
            self.tunnel.terminate()
            try: self.tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired: self.tunnel.kill(); self.tunnel.wait(timeout=5)
        self.tunnel=None
        if receipt is None or not self.forward_state.exists(): return
        data=self._forward_record(receipt); kept=[]
        for role,path in (("model",self.model_socket),("status",self.status_socket)):
            if not path.exists() and not path.is_symlink(): continue
            row=data.get("sockets",{}).get(role)
            info=path.lstat()
            if (row is None or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.geteuid()
                    or (info.st_dev,info.st_ino)!=(row.get("device"),row.get("inode"))):
                kept.append(role); continue
            path.unlink()
        atomic_json(self.forward_state,{**data,"state":"closed","preserved_unknown_paths":kept})

    def discard_keys(self,receipt=None):
        self.close(receipt)
        for path in (self.key,self.host_key): path.unlink(missing_ok=True)
