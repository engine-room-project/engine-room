"""Bounded desktop JSON bridge; no provider defaults, ambient credentials or shell RPC."""
from pathlib import Path
import shutil
import sys
import tempfile

from .controller_client import Client,Endpoint
from .controller_protocol import MAX_FRAME,decode,encode,fields
from .desktop_recovery import listing,recover
from .desktop_storage import DesktopStorage
from .paths import state_root
from .protection import host_identity


class Bridge:
    def __init__(self,root,*,client_type=Client,identity=host_identity,which=shutil.which):
        self.root=Path(root); self.client_type=client_type; self.identity=identity; self.which=which
    def dispatch(self,request):
        fields(request,("action",),("params",))
        action=request["action"]; params=request.get("params",{})
        if action=="startup":
            fields(params,())
            path=self.root/"controller.json"; state="missing"
            if path.exists() or path.is_symlink():
                state="damaged"
                try:
                    if path.is_symlink() or path.stat().st_size>16384: raise ValueError()
                    endpoint=Endpoint(**decode(path.read_bytes())).validate()
                    if endpoint.client_host_id!=self.identity(): raise ValueError()
                    state="configured"
                except Exception: pass
            return dict(controller_state=state,provider_configured=False if state=="missing" else None,
                python_ready=sys.version_info>=(3,12),ssh_ready=self.which("ssh") is not None,
                message="Set up an independent controller to add named connections." if state=="missing" else
                    "Verify the saved controller to load named connections." if state=="configured" else
                    "Saved controller settings need recovery. Existing files were preserved.")
        if action=="enroll_controller":
            fields(params,("endpoint",))
            values=params["endpoint"]
            expected=set(Endpoint.__dataclass_fields__)-{"client_host_id"}
            if not isinstance(values,dict) or set(values)!=expected: raise ValueError("Incomplete explicit controller enrollment.")
            if (self.root/"controller.json").exists() or (self.root/"controller.json").is_symlink():
                raise ValueError("A controller is already saved. Preserve its recovery records before changing enrollment.")
            endpoint=Endpoint(**values,client_host_id=self.identity()).validate()
            self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
            if self.root.is_symlink(): raise ValueError("Controller settings directory is linked.")
            # A failed verification cannot replace persistent trust/configuration.
            with tempfile.TemporaryDirectory(prefix=".verify-",dir=self.root) as temporary:
                candidate=self.client_type(temporary,endpoint)
                info=candidate.call("info")
                if (not isinstance(info,dict) or info.get("controller_host_id")!=endpoint.controller_host_id
                        or info.get("client_host_id")!=endpoint.client_host_id):
                    raise ValueError("The independent controller enrollment differs.")
            self.client_type(self.root,endpoint).save()
            return dict(saved=True,protection_healthy=info.get("protection_healthy") is True)
        if action=="offer_plan":
            from .lifecycle import Quote
            from .model_server import command
            from .planning import offer_plan
            import time
            fields(params,("plan","quote"))
            command(params["plan"])
            return offer_plan(params["plan"],Quote(**params["quote"]).validate(time.time()))
        if action=="model_plan":
            from .desktop_planner import plan
            return plan(params)
        if action=="recovery_list":
            fields(params,())
            rental=listing(self.root/"rentals"); attachment=listing(self.root/"attachments",mode="attachment")
            return dict(records=rental["records"]+attachment["records"],damaged_records=rental["damaged_records"]+attachment["damaged_records"])
        if action=="recover":
            fields(params,("operation_id","cancel","confirmed"),("mode",))
            if type(params["cancel"]) is not bool or params["confirmed"] is not True:
                raise ValueError("Explicit recovery confirmation is required.")
            mode=params.get("mode","rental")
            if mode not in {"rental","attachment"}: raise ValueError("Invalid recovery mode.")
            return recover(self.client_type.read(self.root),self.root/("attachments" if mode=="attachment" else "rentals"),params["operation_id"],cancel=params["cancel"],mode=mode)
        if action in {"storage_begin","storage_local_records","storage_recover_local","storage_abandon_local"}:
            storage=DesktopStorage(self.client_type.read(self.root),self.root/"storage")
            if action=="storage_begin":
                fields(params,("request","confirmed"))
                return storage.begin(params["request"],confirmed=params["confirmed"])
            if action=="storage_local_records":
                fields(params,(),("after","limit")); return storage.listing(**params)
            if action=="storage_abandon_local":
                fields(params,("operation_id","confirmed")); return storage.abandon(**params)
            fields(params,("operation_id",),("resource_id","confirmed")); return storage.recover(**params)
        if action=="controller":
            fields(params,("method",),("arguments",))
            method=params["method"]; arguments=params.get("arguments",{})
            # Rentals/leases/model streams need the UI-owned session lifecycle, not one-shot RPC.
            allowed={"info","connector_form","connections","quote","model_discover","attachment_preview","status","add_connection","remove_connection","storage_quote","storage_records","storage_status","storage_recover","storage_close_unsubmitted","storage_abandon"}
            if not isinstance(method,str) or method not in allowed or not isinstance(arguments,dict):
                raise ValueError("Unsupported desktop onboarding command.")
            return self.client_type.read(self.root).call(method,arguments)
        raise ValueError("Unsupported desktop action.")


def main(input_stream=None,output_stream=None):
    source=input_stream or sys.stdin.buffer; destination=output_stream or sys.stdout.buffer
    try:
        raw=source.readline(MAX_FRAME+1)
        if len(raw)>MAX_FRAME or source.read(1): raise ValueError("Use one bounded JSON request.")
        result=Bridge(state_root()/"desktop").dispatch(decode(raw))
        response=encode(dict(ok=True,result=result))
        code=0
    except Exception:
        response=encode(dict(ok=False,error="Desktop setup could not be verified. Check prerequisites and controller enrollment. Existing recovery state was preserved."))
        code=1
    destination.write(response); destination.flush(); return code


if __name__=="__main__": raise SystemExit(main())
