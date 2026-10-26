"""Owned Colab setup coordinator; no allocation, retry or provider deletion here."""
import json
from pathlib import Path
import time

from engine_room.lifecycle import selection_key
from engine_room.model_metadata import ModelMetadata
from engine_room.payload import source_payload
from engine_room.private_endpoint import EndpointHTTP,address,private_parents
from engine_room.records import atomic_json
from .api import ACCELERATORS
from .bootstrap import stage_runtime,start_install,install_status
from .kernel import KernelSession
from .model_start import start_model
from .ssh import ColabSSH


class Runtime:
    def __init__(self,root,credentials,api,receipts,*,forward_root,metadata=None,kernel=None,ssh_factory=ColabSSH,now=time.time):
        self.root=Path(root).absolute(); self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.forward_root=Path(forward_root).absolute(); self.forward_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.credentials=credentials; self.api=api; self.receipts=receipts; self.now=now
        self.metadata=metadata if metadata is not None else ModelMetadata(credentials)
        self.kernel=kernel if kernel is not None else KernelSession(api,self.root/"kernels",now=now)
        self.ssh_factory=ssh_factory; self.sessions={}

    def directory(self,r):
        r.validate(); return self.root/r.operation_id
    def sockets(self,r): return self.forward_root/r.operation_key()[:16]
    def state_path(self,r): return self.directory(r)/"setup.json"

    def prepare(self,connection,r,selection,plan):
        r.validate()
        if (r.connector_id!="colab" or r.mode!="rental" or connection.id!=r.connection_id
                or connection.account_id!=r.account_id or connection.connector_id!="colab"
                or not isinstance(selection,dict) or selection.get("accelerator") not in ACCELERATORS
                or selection.get("engine")!=plan.get("engine")):
            raise ValueError("The original Colab connection and explicit runtime selection are required.")
        payload=source_payload(plan,native=True)
        address(self.sockets(r)/"m.sock",self.forward_root); address(self.sockets(r)/"s.sock",self.forward_root)
        private_parents(self.forward_root/"check",self.forward_root)
        self.metadata.verify(plan,connection.settings.get("hf_credential_ref"))
        directory=self.directory(r); directory.mkdir(mode=0o700)
        atomic_json(self.state_path(r),dict(operation_key=r.operation_key(),resource_id=None,state="prepared",
            source_sha256=payload["sha256"],selection_key=selection_key(selection),accelerator=selection["accelerator"],progress="prepared",sampled_at=self.now()))

    def read(self,r):
        path=self.state_path(r)
        if path.is_symlink() or path.stat().st_size>8192: raise ValueError("Invalid Colab setup proof.")
        data=json.loads(path.read_text())
        if (not isinstance(data,dict) or data.get("operation_key")!=r.operation_key()
                or data.get("resource_id") not in {None,r.resource_id}):
            raise ValueError("Colab setup belongs to another rental.")
        return data

    def authority(self,connection,r,cancel):
        latest=self.receipts.load(r.operation_id)
        if (latest.operation_key()!=r.operation_key() or latest.resource_id!=r.resource_id
                or connection.id!=latest.connection_id or connection.account_id!=latest.account_id
                or connection.connector_id!="colab" or latest.connector_id!="colab"
                or latest.mode!="rental" or latest.state!="active" or latest.cancel_requested or cancel.is_set()
                or not latest.protection_id or self.now()>=latest.deadline
                or latest.lease_expires_at is None or self.now()>=latest.lease_expires_at):
            raise ValueError("This protected Colab setup is no longer authorized.")

    def setup(self,connection,r,plan,cancel):
        authorize=lambda:self.authority(connection,r,cancel)
        authorize(); proof=self.read(r)
        if proof["state"]!="prepared" or proof["source_sha256"]!=source_payload(plan,native=True)["sha256"]:
            raise ValueError("Setup was already attempted or its checked model changed. Recover the rental.")
        def progress(state,detail):
            atomic_json(self.state_path(r),{**proof,"resource_id":r.resource_id,"state":state,"progress":detail,"sampled_at":self.now()})
        progress("setting-up","owned-kernel-start")
        self.kernel.start(connection,r,authorize=authorize)
        authorize(); staged=stage_runtime(self.kernel,connection,r,plan,proof["accelerator"],authorize=authorize,cancel=cancel)
        authorize(); installing=start_install(self.kernel,connection,r,plan,staged,authorize=authorize,cancel=cancel)
        while True:
            authorize()
            status=install_status(self.kernel,connection,r,plan,installing,authorize=authorize,cancel=cancel)
            authorize(); progress("installing",status["progress"])
            if status["state"]=="installed": break
            if status["state"]!="installing": raise RuntimeError("Native installation failed or lost its process proof. Recover the rental.")
            cancel.wait(2)
        authorize(); progress("ssh-enrollment","private-ssh-enrollment")
        ssh=self.ssh_factory(self.directory(r)/"ssh",r,lambda:self.api.runtime_access(connection,r),authorize,
            forward_directory=self.sockets(r),now=self.now)
        self.sessions[r.operation_id]=ssh
        ssh.enroll(cancel=cancel); authorize()
        start_model(ssh,connection,r,plan,self.credentials,authorize=authorize,cancel=cancel,now=self.now)
        authorize(); ssh.forward(r); authorize(); progress("forwarding","private-model-starting")

    def status(self,r):
        ssh=self.sessions.get(r.operation_id)
        if ssh is None or ssh.tunnel is None:
            state=self.read(r)
            return dict(status="starting",progress=state["progress"],sampled_at=state["sampled_at"])
        if ssh.tunnel.poll() is not None: return dict(status="failed",progress="private-tunnel-exited",sampled_at=self.now())
        data=EndpointHTTP(ssh.forward_endpoint("status",r),self.forward_root,r.operation_key(),timeout=5).json()
        if not isinstance(data,dict) or data.get("status") not in {"starting","ready","failed"}: raise ValueError("Invalid private model status.")
        return data

    def model_endpoint(self,r):
        ssh=self.sessions.get(r.operation_id)
        if ssh is None or self.status(r).get("status")!="ready": raise ValueError("The private model is not ready.")
        return ssh.forward_endpoint("model",r)

    def close(self,r,*,discard=False):
        ssh=self.sessions.get(r.operation_id)
        if ssh is not None:
            if discard: ssh.discard_keys(r)
            else: ssh.close(r)
            self.sessions.pop(r.operation_id,None)
        # No process handle after restart: preserve unknown local identity/socket state.
