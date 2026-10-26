"""Optional Colab rental connector; explicit account and independently protected setup."""
from importlib import metadata
from pathlib import Path
import re
import shutil
import sys
import time

from engine_room.connectors import Descriptor
from engine_room.credentials import Credentials
from engine_room.forms import field,model_fields,connection_form,validate
from engine_room.lifecycle import Health,selection_key
from engine_room.paths import state_root
from engine_room.payload import runtime_profile
from engine_room.records import Store
from ._colab.api import ColabAPI,ACCELERATORS
from ._colab.auth import OAuthTokens
from ._colab.pricing import quote,telemetry
from ._colab.runtime import Runtime


class ColabConnector:
    descriptor=Descriptor("colab","Colab","An explicitly saved Colab OAuth login",("rental",))
    def __init__(self,root,*,credentials=None,api=None,runtime=None,now=time.time):
        self.root=Path(root); self.now=now
        self.credentials=credentials if credentials is not None else Credentials(self.root/"credentials")
        self.api=api if api is not None else ColabAPI(OAuthTokens(self.credentials,now=now),self.root/"colab-assignments",now=now)
        self.runtime=runtime if runtime is not None else Runtime(self.root/"colab-operations",self.credentials,self.api,
            Store(self.root/"receipts"),forward_root=self.root/"s",now=now)

    def form(self,purpose,connection=None,values=None):
        if purpose=="connection": return connection_form()
        if purpose!="selection" or connection is None: raise ValueError("Choose a named connection first.")
        self.bound(connection)
        return validate(dict(schema=1,fields=model_fields()+[
            field("accelerator","GPU request","choice",choices=[(name,name) for name in sorted(ACCELERATORS)]),
            field("high_mem","Request high system memory where available","boolean")],
            help="Availability, disk capacity and this rental's advance price are unconfirmed. The CCU ceiling applies to all assignments in this account; actual disk/GPU capacity is checked before installation."))

    def preflight(self,credential_ref,settings):
        if not sys.platform.startswith("linux"): raise ValueError("Configure Colab on the independently hosted Linux controller.")
        if any(not shutil.which(name) for name in ("ssh","ssh-keygen","ssh-keyscan")):
            raise ValueError("Install OpenSSH client tools on the controller before connecting Colab.")
        try: pinned=metadata.version("websocket-client")=="1.9.2"
        except metadata.PackageNotFoundError: pinned=False
        if not pinned: raise ValueError("Install the pinned optional Colab controller dependencies.")
        if (not isinstance(settings,dict) or set(settings)-{"hf_credential_ref"}
                or ("hf_credential_ref" in settings and (not isinstance(settings["hf_credential_ref"],str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",settings["hf_credential_ref"])) )):
            raise ValueError("Choose only an explicit saved model credential reference.")
        return dict(account_id=self.api.account(credential_ref),settings=dict(settings))

    @staticmethod
    def selection(value):
        if (not isinstance(value,dict) or set(value)!={"accelerator","high_mem","engine"}
                or value["accelerator"] not in ACCELERATORS or type(value["high_mem"]) is not bool):
            raise ValueError("Choose an explicit supported GPU, memory shape and runtime.")
        runtime_profile(value["engine"]); return value

    def bound(self,connection,r=None):
        if connection.connector_id!="colab" or (r is not None and (r.connector_id!="colab"
                or connection.id!=r.connection_id or connection.account_id!=r.account_id or r.mode!="rental")):
            raise ValueError("The original Colab rental connection is required.")
        if r is not None: r.validate()
    @staticmethod
    def observation(value,r,*,known=True):
        if (value.account_id!=r.account_id or value.operation_id!=r.operation_id
                or (known and value.resource_id!=r.resource_id)):
            raise ValueError("Provider evidence differs from the original rental.")
        return value
    def account_identity(self,connection):
        self.bound(connection); return self.api.account(connection.credential_ref)
    def quote(self,connection,selection):
        self.bound(connection); self.selection(selection); return quote(self.api,connection,selection,now=self.now)
    def prepare(self,connection,r,selection,plan):
        self.bound(connection,r); self.selection(selection); self.runtime.prepare(connection,r,selection,plan)
    def allocate(self,connection,r,selection,*,submit_gate):
        self.bound(connection,r); self.selection(selection)
        proof=self.runtime.read(r)
        if proof.get("state")!="prepared" or proof.get("selection_key")!=selection_key(selection):
            raise ValueError("The original prepared Colab selection is required.")
        return self.observation(self.api.allocate(connection,r,selection["accelerator"],submit_gate=submit_gate,high_mem=selection["high_mem"]),r,known=False)
    def setup(self,connection,r,plan,cancel):
        self.bound(connection,r); return self.runtime.setup(connection,r,plan,cancel)
    def observe(self,connection,r):
        self.bound(connection,r); result=self.observation(self.api.observe(connection,r),r)
        if result.status=="absent": self.runtime.close(r,discard=True)
        return result
    def reconcile(self,connection,r):
        self.bound(connection,r); return self.observation(self.api.reconcile(connection,r),r,known=False)
    def terminate(self,connection,r):
        self.bound(connection,r); self.api.terminate(connection,r); self.runtime.close(r)
    def disconnect(self,connection,r):
        raise ValueError("This connector supports managed rentals only; existing machines are never terminated.")
    def health(self,connection,r):
        self.bound(connection,r)
        observed=self.observation(self.api.observe(connection,r),r)
        if observed.status=="absent": return Health("failed",self.now(),"provider-stopped",None,"CCU","account")
        if observed.status!="active" or not observed.owned:
            return Health("unknown",self.now(),"provider-ownership-unconfirmed",None,"CCU","account")
        usage=telemetry(self.api,connection,now=self.now)
        if usage["balance"]<=0: return Health("failed",usage["observed_at"],"compute-balance-exhausted",usage["account_rate"],"CCU","account")
        try:
            state=self.runtime.status(r)
            return Health(state["status"],state["sampled_at"],state.get("progress",""),usage["account_rate"],"CCU","account")
        except Exception: return Health("unknown",self.now(),"private-status-unavailable",usage["account_rate"],"CCU","account")
    def model_endpoint(self,connection,r):
        self.bound(connection,r); return self.runtime.model_endpoint(r)


def create_connector(): return ColabConnector(state_root())
