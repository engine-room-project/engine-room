"""Existing-machine connector with local-access-only authority."""
import json
from pathlib import Path
import sys
import time

from engine_room.attachment_client import ForwardClient
from engine_room.attachment_identity import Identity
from engine_room.connectors import Descriptor
from engine_room.credentials import Credentials
from engine_room.forms import field,validate
from engine_room.lifecycle import Health
from engine_room.private_endpoint import EndpointHTTP,ModelEndpoint,private_parents
from engine_room.recovery import Observation


class SSHAttachment:
    descriptor=Descriptor("ssh","Existing machine over SSH (experimental)","Saved dedicated SSH identity-path reference",("attachment",))
    def __init__(self,root,*,credentials=None,identity_loader=Identity.load,forward_factory=ForwardClient,http_factory=EndpointHTTP,now=time.time):
        self.root=Path(root).absolute(); self.credentials=credentials if credentials is not None else Credentials(self.root/"credentials")
        self.identity_loader=identity_loader; self.forward_factory=forward_factory; self.http_factory=http_factory; self.now=now; self.forwards={}; self.attempts={}
    def form(self,purpose,connection=None,values=None):
        if purpose!="connection": raise ValueError("Existing-machine connection details are explicit; there are no rental offers.")
        return validate(dict(schema=1,fields=[
            field("host","Existing private machine IP address","text"),field("port","SSH port","integer",minimum=1,maximum=65535),
            field("username","Dedicated SSH account","text"),field("host_key","Separately verified Ed25519 host public key","text"),
            field("model_port","Existing loopback model API port","integer",minimum=1024,maximum=65535),
            field("model_id","Exact model ID already served by this machine","text")],
            help="No software is installed and no machine/model is started or stopped. Choose a saved dedicated SSH identity-path reference. Key/host details are checked now; SSH authentication and read-only model checks occur when connecting. Outside compute/storage billing continues after disconnect."))
    def preflight(self,credential_ref,settings):
        if not sys.platform.startswith("linux"): raise ValueError("Configure this connection on the Linux controller.")
        identity=self.identity_loader(settings,credential_ref,self.credentials)
        return dict(account_id=identity.account_id,settings=dict(settings))
    def attachment_target(self,connection):
        connection.validate()
        if connection.connector_id!=self.descriptor.id: raise ValueError("Choose the original SSH connection.")
        identity=self.identity_loader(connection.settings,connection.credential_ref,self.credentials)
        return dict(account_id=identity.account_id,resource_id=identity.resource_id,model_id=connection.settings["model_id"])
    def account_identity(self,connection):
        connection.validate()
        if connection.connector_id!=self.descriptor.id: raise ValueError("Choose the original SSH connection.")
        return self.identity_loader(connection.settings,connection.credential_ref,self.credentials).account_id
    def bound(self,connection,receipt,*,verify_identity=True):
        connection.validate(); receipt.validate()
        if (receipt.mode!="attachment" or connection.connector_id!=self.descriptor.id or receipt.connector_id!=self.descriptor.id
                or receipt.connection_id!=connection.id or receipt.account_id!=connection.account_id):
            raise ValueError("The original existing-machine connection is required.")
        if verify_identity:
            identity=self.identity_loader(connection.settings,connection.credential_ref,self.credentials)
            if identity.account_id!=receipt.account_id or identity.resource_id!=receipt.resource_id: raise ValueError("Attachment principal or model changed.")
    def forward(self,receipt):
        forward=self.forwards.get(receipt.operation_id)
        if (forward is None or forward.receipt.operation_key()!=receipt.operation_key() or forward.receipt.resource_id!=receipt.resource_id
                or forward.closed or forward.process is None or forward.process.poll() is not None or forward.endpoint is None):
            raise ValueError("The original private forward is unavailable; it was not adopted or replayed.")
        endpoint=forward.endpoint
        if not isinstance(endpoint,ModelEndpoint): raise ValueError("A scoped private endpoint is required.")
        return forward,endpoint.validate(self.root,receipt.operation_key(),receipt.resource_id)
    def check_model(self,connection,receipt):
        _,endpoint=self.forward(receipt)
        response=self.http_factory(endpoint,self.root,receipt.operation_key(),timeout=5).json("/v1/models",limit=32768)
        rows=response.get("data") if isinstance(response,dict) else None
        if not isinstance(rows,list) or len(rows)>256: raise ValueError("The existing model list is invalid.")
        expected=connection.settings["model_id"]
        if len([row for row in rows if isinstance(row,dict) and row.get("id")==expected])!=1:
            raise ValueError("The explicitly selected existing model was not confirmed.")
    def attach(self,connection,receipt):
        receipt.validate()
        if receipt.mode!="attachment" or receipt.state!="active" or receipt.cancel_requested or receipt.operation_id in self.attempts:
            raise ValueError("This attachment cannot be replayed.")
        self.bound(connection,receipt,verify_identity=False)
        self.attempts[receipt.operation_id]=dict(scope=receipt.operation_key(),resource_id=receipt.resource_id,finished=False)
        forward=None
        try:
            self.bound(connection,receipt)
            forward=self.forward_factory(self.root,receipt); self.forwards[receipt.operation_id]=forward
            forward.start(); self.check_model(connection,receipt)
            return self.forward(receipt)[1]
        except Exception:
            try:
                if forward is not None: forward.close()
            except Exception: pass
            raise ValueError("The existing model connection could not be verified. The machine was not modified.") from None
        finally: self.attempts[receipt.operation_id]["finished"]=True
    def pulse(self,connection,receipt):
        forward,_=self.forward(receipt)
        try: self.bound(connection,receipt); forward.pulse()
        except Exception:
            try: forward.close()
            except Exception: pass
            raise ValueError("The original attachment can no longer be renewed.") from None
    def model_endpoint(self,connection,receipt):
        self.bound(connection,receipt); self.check_model(connection,receipt)
        return self.forward(receipt)[1]
    def health(self,connection,receipt):
        try:
            self.bound(connection,receipt); self.check_model(connection,receipt)
            return Health("ready",self.now(),"existing-model-confirmed")
        except Exception: return Health("unknown",self.now(),"existing-model-unavailable")
    def disconnect(self,connection,receipt):
        # Closing retained local access needs original saved scope, not a working rotated key.
        self.bound(connection,receipt,verify_identity=False)
        forward=self.forwards.get(receipt.operation_id)
        attempt=self.attempts.get(receipt.operation_id,{})
        if attempt and (attempt.get("scope")!=receipt.operation_key() or attempt.get("resource_id")!=receipt.resource_id):
            raise ValueError("The retained attempt belongs to another attachment.")
        if forward is None and attempt.get("finished") is True:
            return  # This live instance completed preflight without constructing any helper.
        if forward is not None:
            if forward.receipt.operation_key()!=receipt.operation_key() or forward.receipt.resource_id!=receipt.resource_id:
                raise ValueError("The retained forward belongs to another attachment.")
            if forward.close() is True: return
        root=self.root/"s"/receipt.operation_key()[:16]; proof=root/"forward.json"
        if root.resolve()!=root: raise ValueError("Linked forward evidence is unsupported.")
        private_parents(proof,root)
        if proof.is_symlink() or proof.stat().st_size>8192: raise ValueError("Forward evidence is damaged.")
        data=json.loads(proof.read_text(encoding="utf-8"))
        if (data.get("schema")==1 and data.get("state")=="closed" and data.get("disconnected") is True
                and data.get("operation_key")==receipt.operation_key() and data.get("resource_id")==receipt.resource_id): return
        raise ValueError("Local disconnection is uncertain. Preserve forward evidence; the machine was not shut down.")
    def observe(self,connection,receipt):
        self.bound(connection,receipt)
        return Observation(receipt.account_id,receipt.resource_id,receipt.operation_id,"unknown",False)
    def reconcile(self,connection,receipt): return self.observe(connection,receipt)
    def terminate(self,*args,**kwargs): raise ValueError("An existing-machine attachment never authorizes shutdown.")
    def quote(self,*args,**kwargs): raise ValueError("This connector does not rent machines or quote provider costs.")
    allocate=prepare=setup=quote
