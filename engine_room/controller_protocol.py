"""Bounded controller messages; no executable paths or credential values in RPC."""
from dataclasses import asdict
import json
import hashlib
import re
import secrets

from .forms import validate as validate_form
from .credentials import Credentials
from .model_discovery import Discovery
from .lifecycle import Quote
from .records import DamagedRecord
from .volume_records import StorageQuote

MAX_FRAME=262144
PROTOCOL=1
MESSAGES={
    "info":"The independent controller could not be verified.",
    "connector_form":"Connector choices could not be loaded. Check the named connection and refresh its options.",
    "connections":"The named connections could not be read. Preserve the controller configuration.",
    "add_connection":"Connection setup failed. Check the selected connector, prerequisites and saved credential reference on the controller.",
    "remove_connection":"The connection could not be removed. Recover or disconnect its operations first.",
    "model_discover":"Model metadata could not be verified. Check the model identifier and explicit model access on the named connection.",
    "storage_quote":"Storage pricing could not be verified for the explicit account, location and tier.",
    "storage_create":"Volume creation is uncertain. Keep the original operation and reconcile before creating more storage.",
    "storage_abandon":"The delayed storage request was not confirmed cancelled. It may still complete and incur charges; no volume was deleted.",
    "storage_records":"Storage recovery records could not be read. Preserve the controller state.",
    "storage_status":"The original storage operation could not be verified.",
    "storage_recover":"Storage reconciliation is incomplete. No volume was deleted and continuing charges may remain.",
    "storage_close_unsubmitted":"The request was not proven unsubmitted. Reconcile it; no storage was deleted.",
    "quote":"A fresh offer could not be verified. Check the selected account, GPU, disk and storage prices.",
    "attachment_preview":"The saved existing-machine target could not be verified.",
    "attach":"The existing-machine connection was not confirmed. Read its recovery record before reconnecting.",
    "attachment_pulse":"Local access could not be renewed. The existing machine was not shut down.",
    "disconnect_attachment":"Local disconnection is not confirmed. Keep the original recovery evidence.",
    "abandon_attachment":"The pending attachment could not be cancelled safely. Preserve its original operation.",
    "request":"The rental was not confirmed. Read its recovery record before trying again; the offer, model access or protection may have changed.",
    "heartbeat":"This rental cannot be extended. Check its recovery status.",
    "abandon_request":"The pending request could not be cancelled safely. Preserve its recovery intent.",
    "cancel":"Shutdown is not confirmed. Keep the recovery record and check the original provider account.",
    "model_stream":"This session is not ready for private model access.",
    "session_status":"The session status is unavailable. Keep recovery records and do not assume shutdown.",
    "status":"Controller status could not be read. Do not assume a rental is off.",
}


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError("Duplicate message field")
        result[key]=value
    return result


def encode(value):
    raw=json.dumps(value,allow_nan=False,separators=(",",":"),ensure_ascii=True).encode()+b"\n"
    if len(raw)>MAX_FRAME: raise ValueError("Controller message is too large.")
    return raw


def decode(raw):
    try:
        if not isinstance(raw,bytes) or len(raw)>MAX_FRAME or not raw.endswith(b"\n") or b"\n" in raw[:-1]:
            raise ValueError("Invalid frame")
        value=json.loads(raw,object_pairs_hook=_unique,parse_constant=lambda value:(_ for _ in ()).throw(ValueError("Non-finite number")))
        if not isinstance(value,dict): raise ValueError("Expected an object")
        return value
    except (ValueError,UnicodeError,RecursionError):
        raise ValueError("The controller message is invalid or too large.") from None


def fields(params,required,optional=()):
    if not isinstance(params,dict) or not set(required).issubset(params) or set(params)-set(required)-set(optional):
        raise ValueError("Invalid command fields")


class Dispatcher:
    def __init__(self,controller): self.controller=controller

    def dispatch(self,message):
        correlation=None
        method=None
        try:
            fields(message,("schema","request_id","controller_id","client_host_id","method","params"))
            correlation=message["request_id"]
            if type(message["schema"]) is not int or message["schema"]!=PROTOCOL or not isinstance(correlation,str) or not re.fullmatch(r"[a-f0-9]{32}",correlation):
                raise ValueError("Invalid protocol")
            enrollment=self.controller.enrollment
            if message["controller_id"]!=enrollment.controller_id: raise ValueError("Controller differs")
            enrollment.verify(self.controller.host_id,message["client_host_id"])
            method=message["method"]
            if not isinstance(method,str) or method not in MESSAGES: raise ValueError("Unknown command")
            result=self._call(method,message["params"],message["client_host_id"])
            response=dict(schema=PROTOCOL,request_id=correlation,controller_id=enrollment.controller_id,ok=True,result=result)
            encode(response)  # A response exceeding the bound is a failure, never a partial result.
            return response
        except Exception:
            return dict(schema=PROTOCOL,request_id=correlation if isinstance(correlation,str) and re.fullmatch(r"[a-f0-9]{32}",correlation) else None,
                controller_id=self.controller.enrollment.controller_id,ok=False,error="command_failed",
                message=MESSAGES.get(method,"The controller request was refused. Check the verified enrollment and installed versions.") if isinstance(method,str) else "The controller request was refused.")

    def _call(self,method,params,client_id):
        c=self.controller
        if method=="info":
            fields(params,())
            protected=True
            try: c._protection(client_id)
            except Exception: protected=False
            return dict(controller_host_id=c.host_id,client_host_id=c.enrollment.client_host_id,
                protection_healthy=protected,lease_seconds=c.lease_seconds,
                connectors=[asdict(d) for d in c.registry.descriptors()],connector_errors=c.registry.errors)
        if method=="connector_form":
            fields(params,("connector_id","purpose"),("connection_id","values"))
            purpose=params["purpose"]
            if purpose not in {"connection","selection","storage"}: raise ValueError("Invalid connector form purpose.")
            connector=c.registry[params["connector_id"]]; connection=None
            values=params.get("values",{})
            if not isinstance(values,dict) or len(values)>24: raise ValueError("Invalid connector field values.")
            if purpose in {"selection","storage"}:
                if purpose=="storage" and "persistent_storage" not in connector.descriptor.capabilities:
                    raise ValueError("This connector does not support persistent storage.")
                connection=c.connections.read()[params["connection_id"]]
                if connection.connector_id!=params["connector_id"] or connector.account_identity(connection)!=connection.account_id:
                    raise ValueError("The original connection is required.")
            elif "connection_id" in params or values: raise ValueError("Connection fields do not accept account values.")
            return validate_form(connector.form(purpose,connection,values))
        if method=="connections":
            fields(params,())
            return [asdict(item) for item in c.connections.read().values()]
        if method=="add_connection":
            fields(params,("name","connector_id","credential_ref"),("settings",))
            return asdict(c.connections.add(**params))
        if method=="remove_connection":
            fields(params,("connection_id",)); c.connections.remove(params["connection_id"])
            return dict(removed=True)
        if method=="model_discover":
            fields(params,("connection_id","model_id"),("base_model",))
            connection=c.connections.read()[params["connection_id"]]
            connector=c.registry[connection.connector_id]
            if connector.account_identity(connection)!=connection.account_id: raise ValueError("Account changed")
            return Discovery(Credentials(c.connections.root/"credentials")).discover(params["model_id"],connection.settings.get("hf_credential_ref"),params.get("base_model"))
        if method=="storage_quote":
            fields(params,("connection_id","selection"))
            return asdict(c.storage.quote(params["connection_id"],params["selection"],client_id))
        if method=="storage_records":
            fields(params,(),("after","limit"))
            return c.storage.listing(**params)
        if method=="storage_abandon":
            fields(params,("operation_id","connection_id","confirmed"))
            if params["confirmed"] is not True: raise ValueError("Explicit pending-storage cancellation approval is required.")
            return c.storage.abandon(params["operation_id"],params["connection_id"],client_id)
        if method=="storage_create":
            fields(params,("operation_id","connection_id","selection","approved_quote","continuing_costs_confirmed"))
            c.storage.create(params["operation_id"],params["connection_id"],params["selection"],StorageQuote(**params["approved_quote"]),client_id,
                continuing_costs_confirmed=params["continuing_costs_confirmed"])
            return c.storage.snapshot(params["operation_id"])
        if method in {"storage_status","storage_recover","storage_close_unsubmitted"}:
            fields(params,("operation_id","operation_key"),("resource_id","confirmed") if method=="storage_recover" else ())
            record=c.storage.snapshot(params["operation_id"]); supplied=params["operation_key"]
            if not isinstance(supplied,str) or not re.fullmatch(r"[a-f0-9]{64}",supplied) or not secrets.compare_digest(supplied,record["operation_key"]):
                raise ValueError("Choose the original storage operation scope.")
            if method=="storage_status": return record
            if method=="storage_close_unsubmitted":
                c.storage.abandon_unsubmitted(params["operation_id"],client_id)
                return c.storage.snapshot(params["operation_id"])
            result=c.storage.recover(params["operation_id"],client_id,resource_id=params.get("resource_id"),confirmed=params.get("confirmed",False))
            return dict(record=c.storage.snapshot(params["operation_id"]),observation=result["observation"])
        if method=="quote":
            fields(params,("connection_id","selection"))
            connection=c.connections.read()[params["connection_id"]]
            connector=c.registry[connection.connector_id]
            if connector.account_identity(connection)!=connection.account_id: raise ValueError("Account changed")
            quote=connector.quote(connection,params["selection"])
            if not isinstance(quote,Quote) or quote.account_id!=connection.account_id: raise ValueError("Invalid quote")
            quote.validate(c.now())
            return asdict(quote)
        if method=="abandon_request":
            fields(params,("operation_id","connection_id"))
            return c.abandon(params["operation_id"],params["connection_id"],client_id)
        if method=="attachment_preview":
            fields(params,("connection_id",))
            return c.attachments.preview(params["connection_id"],client_id)
        if method in {"attach","abandon_attachment"}:
            fields(params,("operation_id","connection_id","approved_target") if method=="attach" else ("operation_id","connection_id"))
            receipt=(c.attachments.attach(params["operation_id"],params["connection_id"],client_id,approved_target=params["approved_target"])
                if method=="attach" else c.attachments.disconnect(params["operation_id"],params["connection_id"],client_id))
            return asdict(receipt) if receipt is not None else dict(cancelled_before_start=True)
        if method=="request":
            fields(params,("operation_id","connection_id","selection","plan","approved_quote","rate_ceiling","duration_seconds"))
            return asdict(c.request(**{**params,"approved_quote":Quote(**params["approved_quote"])},client_host_id=client_id))
        if method in {"heartbeat","cancel","model_stream","session_status","attachment_pulse","disconnect_attachment"}:
            fields(params,("operation_id","operation_key"))
            expected=c.store.load(params["operation_id"]).operation_key()
            supplied=params["operation_key"]
            if not isinstance(supplied,str) or not re.fullmatch(r"[a-f0-9]{64}",supplied) or not secrets.compare_digest(supplied,expected):
                raise ValueError("This command belongs to another operation scope.")
        if method=="attachment_pulse":
            return asdict(c.attachments.pulse(params["operation_id"],client_id))
        if method=="disconnect_attachment":
            receipt=c.store.load(params["operation_id"])
            return asdict(c.attachments.disconnect(receipt.operation_id,receipt.connection_id,client_id))
        if method=="session_status":
            receipt=c.store.load(params["operation_id"])
            if receipt.mode=="attachment":
                ready=False
                try: c.attachments.stream_scope(receipt.operation_id,client_id); ready=True
                except Exception: pass
                return dict(operation_id=receipt.operation_id,operation_key=receipt.operation_key(),phase="ready" if ready else ("starting" if receipt.state=="active" and not receipt.cancel_requested else "stopping" if receipt.state=="active" else receipt.state),ready=ready,sampled_at=c.now())
            health=c._health.get(receipt.operation_id,{})
            ready=False
            try:
                c._protection(client_id)
                ready=(receipt.state=="active" and not receipt.cancel_requested and not c._expired(receipt)
                    and health.get("ready") is True and health.get("last_status")=="ready"
                    and 0<=c.now()-health.get("sampled_at",0)<=30)
            except Exception: pass
            phase=receipt.state
            if phase=="active": phase="ready" if ready else ("unresolved" if health.get("ready") else "starting")
            if receipt.cancel_requested and receipt.unresolved: phase="stopping"
            return dict(operation_id=receipt.operation_id,operation_key=receipt.operation_key(),phase=phase,
                ready=ready,sampled_at=c.now())
        if method=="heartbeat":
            c.heartbeat(params["operation_id"],client_id)
            return asdict(c.store.load(params["operation_id"]))
        if method=="cancel":
            return [asdict(result) for result in c.cancel(params["operation_id"])]
        if method=="model_stream":
            return c.model_scope(params["operation_id"],client_id)
        if method=="status":
            fields(params,(),("operation_id","after","limit"))
            if "operation_id" in params:
                if set(params)!={"operation_id"}: raise ValueError("Invalid single-operation query")
                return dict(records=[asdict(c.store.load(params["operation_id"]))],next_cursor=None)
            limit=params.get("limit",10); after=params.get("after","")
            if type(limit) is not int or not 1<=limit<=10 or not isinstance(after,str) or (after and not re.fullmatch(r"[a-f0-9]{64}",after)):
                raise ValueError("Invalid history page")
            rows=[]
            for record in c.store.scan():
                identity=("damaged:"+record.filename) if isinstance(record,DamagedRecord) else ("operation:"+record.operation_id)
                cursor=hashlib.sha256(identity.encode()).hexdigest()
                if cursor>after: rows.append((cursor,record))
            rows.sort(key=lambda pair:pair[0])
            page=rows[:limit]
            records=[dict(damaged=True,message=r.message) if isinstance(r,DamagedRecord) else asdict(r) for _,r in page]
            return dict(records=records,next_cursor=page[-1][0] if len(rows)>len(page) else None)
        raise ValueError("Unknown command")
