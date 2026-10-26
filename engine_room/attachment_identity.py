"""Explicit existing-machine SSH identity and forward argv; never run remote commands."""
from dataclasses import dataclass,field
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from .controller_client import PRIVATE_NETWORKS
from .private_endpoint import address,private_parents


def public_key(value):
    words=value.split() if isinstance(value,str) else []
    if len(words)!=2 or words[0]!="ssh-ed25519": raise ValueError("Verify an explicit Ed25519 public key.")
    try:
        data=base64.b64decode(words[1],validate=True)
        if len(data)!=51 or data[:19]!=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20": raise ValueError()
    except Exception: raise ValueError("Invalid Ed25519 public key.") from None
    return " ".join(words)


def key_file(value):
    if not isinstance(value,str) or any(c in value for c in ('%', '"', '\n', '\r', '\x00')):
        raise ValueError("Choose an explicit dedicated identity path without expansion characters.")
    path=Path(value)
    if not path.is_absolute() or path.is_symlink() or path.resolve()!=path.absolute(): raise ValueError("Identity links are not permitted.")
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=16384: raise ValueError("Invalid dedicated identity file.")
    if os.name!="nt" and (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077):
        raise ValueError("The selected identity must already be private to its owning user.")
    return path


@dataclass(frozen=True)
class Identity:
    host: str
    port: int
    username: str
    host_key: str
    model_port: int
    model_id: str
    identity_path: Path=field(repr=False)
    client_public_key: str=field(repr=False)
    @classmethod
    def load(cls,settings,credential_ref,credentials,*,runner=subprocess.run):
        expected={"host","port","username","host_key","model_port","model_id"}
        if not isinstance(settings,dict) or set(settings)!=expected: raise ValueError("Complete the explicit existing-machine details.")
        host=ipaddress.ip_address(settings["host"])
        if not any(host.version==network.version and host in network for network in PRIVATE_NETWORKS):
            raise ValueError("Choose an explicit private-network machine address.")
        for name in ("port","model_port"):
            value=settings[name]
            if type(value) is not int or not (1 if name=="port" else 1024)<=value<=65535: raise ValueError("Choose explicit valid ports.")
        user=settings["username"]; model=settings["model_id"]
        if not isinstance(user,str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}",user): raise ValueError("Choose an explicit SSH account.")
        if not isinstance(model,str) or not 1<=len(model)<=200 or any(ord(c)<33 for c in model): raise ValueError("Choose an explicit served model identity.")
        pinned=public_key(settings["host_key"])
        path=key_file(credentials.read(credential_ref))
        result=runner(["ssh-keygen","-y","-P","","-f",str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,timeout=10,check=False)
        if result.returncode or len(result.stdout)>8192: raise ValueError("Noninteractive dedicated SSH identity verification failed.")
        client=public_key(result.stdout.decode("ascii").strip())
        key_file(str(path))
        return cls(str(host),settings["port"],user,pinned,settings["model_port"],model,path,client)
    @property
    def account_id(self):
        value=(self.host,self.port,self.username,self.host_key,self.client_public_key)
        return "ssh-"+hashlib.sha256(json.dumps(value).encode()).hexdigest()
    @property
    def resource_id(self):
        value=(self.account_id,self.model_port,self.model_id)
        return "ssh-model-"+hashlib.sha256(json.dumps(value).encode()).hexdigest()[:40]
    def forward_args(self,root,socket_path):
        if not sys.platform.startswith("linux"): raise ValueError("Existing-machine forwarding requires the Linux controller.")
        key_file(str(self.identity_path))
        root=Path(root).absolute()
        if root.resolve()!=root or any(c in str(root) for c in ('"','%','\n','\r')): raise ValueError("Choose a private unlinked trust directory.")
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=address(socket_path,root); private_parents(target,root)
        if target.exists() or target.is_symlink(): raise ValueError("Existing forward paths were preserved.")
        known=root/"known-hosts"
        alias="engine-room-attachment-"+hashlib.sha256(self.host_key.encode()).hexdigest()[:32]
        descriptor=os.open(known,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,"w",encoding="utf-8") as stream:
            stream.write(alias+" "+self.host_key+"\n"); stream.flush(); os.fsync(stream.fileno())
        return ["ssh","-F","none","-N","-n","-T","-o","BatchMode=yes","-o","IdentitiesOnly=yes",
            "-o","IdentityAgent=none","-o","CertificateFile=none","-o","StrictHostKeyChecking=yes",
            "-o",'UserKnownHostsFile="'+str(known)+'"',"-o",'GlobalKnownHostsFile="'+str(known)+'"',
            "-o","HostKeyAlias="+alias,"-o","HostKeyAlgorithms=ssh-ed25519","-o","UpdateHostKeys=no",
            "-o","ProxyCommand=none","-o","ProxyJump=none","-o","ControlMaster=no","-o","ControlPath=none",
            "-o","ControlPersist=no","-o","ForwardAgent=no","-o","ForwardX11=no","-o","PermitLocalCommand=no",
            "-o","RequestTTY=no","-o","ConnectTimeout=8","-o","ServerAliveInterval=15","-o","ServerAliveCountMax=2",
            "-o","ExitOnForwardFailure=yes","-o","StreamLocalBindMask=0177","-o","StreamLocalBindUnlink=no",
            "-i",str(self.identity_path),"-p",str(self.port),"-L",str(target)+":127.0.0.1:"+str(self.model_port),
            self.username+"@"+self.host]
