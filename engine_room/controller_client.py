"""Explicit private-network SSH controller client; no ambient SSH config or TOFU."""
from dataclasses import asdict,dataclass
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from .controller_protocol import PROTOCOL,decode,encode
from .protection import Enrollment,host_identity
from .records import atomic_json

PRIVATE_NETWORKS=tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","100.64.0.0/10","fc00::/7"))


@dataclass(frozen=True)
class Endpoint:
    address: str
    port: int
    username: str
    host_key: str
    identity_file: str
    controller_id: str
    controller_host_id: str
    client_host_id: str
    independent_host_confirmed: bool

    def validate(self):
        address=ipaddress.ip_address(self.address)
        if not any(address.version==network.version and address in network for network in PRIVATE_NETWORKS):
            raise ValueError("Choose the controller's private network IP address, not a public address or local loopback.")
        if type(self.port) is not int or not 1<=self.port<=65535 or not isinstance(self.username,str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}",self.username):
            raise ValueError("Choose an explicit controller SSH account and port.")
        words=self.host_key.split() if isinstance(self.host_key,str) else []
        if len(words)!=2 or words[0]!="ssh-ed25519": raise ValueError("Verify the controller's Ed25519 SSH host key separately.")
        try:
            raw=base64.b64decode(words[1],validate=True)
            if len(raw)!=51 or raw[:19]!=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20": raise ValueError("Invalid key")
        except Exception: raise ValueError("The controller's pinned SSH host key is invalid.") from None
        key=Path(self.identity_file)
        if not key.is_absolute() or not key.is_file() or key.is_symlink() or any(c in str(key) for c in ('\n','\r','"')):
            raise ValueError("Choose an existing dedicated SSH identity file explicitly.")
        Enrollment(self.controller_id,self.controller_host_id,self.client_host_id,self.independent_host_confirmed).verify(self.controller_host_id,self.client_host_id)
        return self


class Client:
    def __init__(self,directory,endpoint,*,runner=subprocess.run,actual_host_id=None):
        self.directory=Path(directory); self.endpoint=endpoint.validate(); self.runner=runner
        actual_host_id=actual_host_id if actual_host_id is not None else host_identity()
        if actual_host_id!=endpoint.client_host_id: raise ValueError("This controller enrollment belongs to another desktop.")
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.known=self.directory/"controller-known-hosts"
        if self.directory.is_symlink() or self.known.is_symlink(): raise ValueError("Controller SSH state cannot use directory or host-key links.")
        self.alias="engine-room-controller-"+hashlib.sha256(endpoint.host_key.encode()).hexdigest()[:32]
        self.known.write_text(self.alias+" "+endpoint.host_key+"\n",encoding="utf-8"); self.known.chmod(0o600)

    def args(self):
        e=self.endpoint
        known=self.known.resolve().as_posix()
        if '"' in known: raise ValueError("Choose a controller state path without quotation marks.")
        return ["ssh","-F","none","-T","-o","BatchMode=yes","-o","IdentitiesOnly=yes",
            "-o","IdentityAgent=none","-o","StrictHostKeyChecking=yes","-o",'GlobalKnownHostsFile="'+known+'"',"-o","HostKeyAlgorithms=ssh-ed25519","-o","UpdateHostKeys=no",
            "-o",'UserKnownHostsFile="'+known+'"',"-o","HostKeyAlias="+self.alias,
            "-o","ForwardAgent=no","-o","ForwardX11=no","-o","ClearAllForwardings=yes",
            "-o","PermitLocalCommand=no","-o","ConnectTimeout=8","-o","ServerAliveInterval=15",
            "-o","ServerAliveCountMax=2","-i",self.endpoint.identity_file,"-p",str(e.port),
            e.username+"@"+str(ipaddress.ip_address(e.address)),"engine-room-controller-rpc"]

    def save(self):
        atomic_json(self.directory/"controller.json",asdict(self.endpoint))

    @classmethod
    def read(cls,directory,**kwargs):
        path=Path(directory)/"controller.json"
        try:
            if path.is_symlink() or path.stat().st_size>16384: raise ValueError("Invalid configuration")
            endpoint=Endpoint(**json.loads(path.read_text(encoding="utf-8")))
            return cls(directory,endpoint,**kwargs)
        except Exception:
            raise ValueError("Controller connection is missing or damaged. Verify its private address, dedicated SSH identity and pinned host key.") from None

    def call(self,method,params=None):
        if method=="model_stream": raise ValueError("Use a session model stream for this operation.")
        request_id=uuid.uuid4().hex
        e=self.endpoint
        message=dict(schema=PROTOCOL,request_id=request_id,controller_id=e.controller_id,
            client_host_id=e.client_host_id,method=method,params={} if params is None else params)
        raw=encode(message)
        try:
            result=self.runner(self.args(),input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15 if method=="heartbeat" else 180,check=False,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            if result.returncode!=0: raise ValueError("SSH failed")
            response=decode(result.stdout)
            if (type(response.get("schema")) is not int or response["schema"]!=PROTOCOL
                    or response.get("request_id")!=request_id or response.get("controller_id")!=e.controller_id
                    or type(response.get("ok")) is not bool): raise ValueError("Controller response differs")
            if not response["ok"]: raise ValueError("Command refused")
            value=response["result"]
            if method=="info":
                if value.get("controller_host_id")!=e.controller_host_id or value.get("client_host_id")!=e.client_host_id:
                    raise ValueError("Enrollment differs")
            return value
        except Exception:
            # SSH/provider diagnostics can contain private information. A failed/lost
            # request never implies that an allocation did not happen or is now off.
            raise RuntimeError("The verified controller request failed. Check recovery status before retrying a rental; shutdown is not confirmed.") from None
