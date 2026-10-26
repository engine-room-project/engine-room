"""Durable desktop rental submission and recovery; no automatic request replay."""
from dataclasses import asdict,replace
import hashlib
import json
from pathlib import Path
import time
import threading
import uuid

from .connections import Connection
from .controller_protocol import fields
from .desktop_session import DesktopSession
from .lifecycle import Quote,selection_key
from .model_server import command
from .payload import PLAN_FIELDS
from .planning import offer_plan
from .records import Receipt,Store,atomic_json


class Rental:
    def __init__(self,client,root,*,session_factory=DesktopSession,now=time.time,clock=time.monotonic):
        self.client=client; self.root=Path(root); self.intents=Store(self.root/"requests"); self.receipts=Store(self.root/"receipts")
        self.session_factory=session_factory; self.now=now; self.clock=clock; self.session=None; self.receipt=None; self.pending_operation=None; self.state_lock=threading.RLock(); self.record_lock=threading.RLock()

    def checked(self,data,original=None):
        result=Receipt(**data).validate()
        if result.mode!="rental" or result.protection_id!=self.client.endpoint.controller_id: raise ValueError("Controller identity changed.")
        if original is not None and (result.operation_key()!=original.operation_key()
                or (original.resource_id is not None and result.resource_id!=original.resource_id)):
            raise ValueError("The returned rental differs from its original scope.")
        return result

    def begin(self,request,*,confirmed,ui_touch,is_closed):
        fields(request,("connection_id","selection","plan","approved_quote","rate_ceiling","duration_seconds"))
        current_touch=lambda:ui_touch() if callable(ui_touch) else ui_touch
        if confirmed is not True or is_closed() or not 0<=self.clock()-current_touch()<60: raise ValueError("Review and confirm the rental while this window is active.")
        plan=request["plan"]
        if not isinstance(plan,dict) or set(plan)-PLAN_FIELDS-{"overheadBytes","kvBytesPerToken"}:
            raise ValueError("Use checked model metadata without credentials or unrelated settings.")
        quote=Quote(**request["approved_quote"]).validate(self.now())
        offer_plan(plan,quote); command(plan)
        duration=request["duration_seconds"]; ceiling=request["rate_ceiling"]
        if (type(duration) is not int or not 0<duration<=86400 or type(ceiling) not in (int,float)
                or not 0<ceiling<float("inf") or (quote.price is not None and quote.price>ceiling)
                or quote.selection_key!=selection_key(request["selection"])):
            raise ValueError("The confirmed duration, ceiling or selection is invalid.")
        info=self.client.call("info")
        if not isinstance(info,dict) or info.get("protection_healthy") is not True: raise ValueError("Independent protection is not healthy.")
        connections=self.client.call("connections")
        if not isinstance(connections,list): raise ValueError("Named connections could not be verified.")
        matches=[Connection(**item).validate() for item in connections if item.get("id")==request["connection_id"]]
        if len(matches)!=1 or matches[0].account_id!=quote.account_id: raise ValueError("The confirmed account differs from this connection.")
        connection=matches[0]
        if is_closed() or not 0<=self.clock()-current_touch()<60: raise ValueError("The window stopped confirming this rental.")
        operation="desktop-"+uuid.uuid4().hex
        body={**request,"operation_id":operation}
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,allow_nan=False).encode()).hexdigest()
        proof=dict(schema=1,operation_id=operation,controller_id=self.client.endpoint.controller_id,
            client_host_id=self.client.endpoint.client_host_id,connection_id=connection.id,account_id=connection.account_id,
            connector_id=connection.connector_id,quote_key=quote.confirmation_key(),rate_ceiling=ceiling,rate_unit=quote.unit,
            rate_scope=quote.rate_scope,duration_seconds=duration,state="submitted",request_sha256=digest)
        with self.intents.allocation_lock():
            if any(self.intents.root.glob("*.json")) or self.receipts.blockers():
                raise ValueError("Recover existing desktop operations before renting again.")
            atomic_json(self.intents.path(operation),proof)
            self.pending_operation=operation
        # A failed/lost response leaves the intent; neither replay nor local off is safe.
        data=self.client.call("request",body)
        with self.state_lock:
            receipt=self.checked(data)
            if (receipt.operation_id!=operation or receipt.connection_id!=connection.id or receipt.connector_id!=connection.connector_id
                    or receipt.account_id!=connection.account_id or receipt.quote_key!=quote.confirmation_key()
                    or receipt.rate_ceiling!=ceiling or receipt.rate_unit!=quote.unit or receipt.rate_scope!=quote.rate_scope
                    or receipt.deadline-receipt.created_at!=duration):
                raise ValueError("The controller returned a different rental. Preserve the request intent for recovery.")
            if self.receipts.path(operation).exists():
                existing=self.receipts.load(operation)
                if not existing.unresolved:
                    self.receipt=self.checked(asdict(existing),receipt)
                    raise ValueError("This request already has terminal recovery evidence. No lease was started.")
            self.receipts.save(receipt); self.receipt=receipt
            if is_closed() or not 0<=self.clock()-current_touch()<60:
                self.stop(); raise ValueError("The window closed during submission. Shutdown still requires provider confirmation.")
            try:
                self.session=self.session_factory(self.client,receipt,self.receipts.root,clock=self.clock,initial_touch=current_touch(),record_lock=self.record_lock)
            except Exception:
                self.stop(); raise
            atomic_json(self.intents.path(operation),{**proof,"state":"linked"})
            return receipt

    def view(self):
        if self.receipt is None: raise ValueError("No scoped session exists.")
        scope=dict(operation_id=self.receipt.operation_id,operation_key=self.receipt.operation_key())
        result=self.client.call("session_status",scope)
        fields(result,("operation_id","operation_key","phase","ready","sampled_at"))
        if (any(result[key]!=value for key,value in scope.items()) or type(result["ready"]) is not bool
                or result["phase"] not in {"intent","allocating","starting","ready","stopping","unresolved","off","cancelled","detached"}
                or result["ready"]!=(result["phase"]=="ready") or type(result["sampled_at"]) not in (int,float)
                or not 0<=self.now()-result["sampled_at"]<=30):
            raise ValueError("Fresh scoped session status could not be verified.")
        return dict(phase=result["phase"],ready=result["ready"])

    def touch(self):
        if self.session is None: raise ValueError("No active desktop session.")
        self.session.touch()

    def refresh(self,operation_id):
        path=self.intents.path(operation_id)
        if path.is_symlink() or path.stat().st_size>8192: raise ValueError("The request recovery intent is damaged.")
        proof=json.loads(path.read_text())
        if (proof.get("operation_id")!=operation_id or proof.get("controller_id")!=self.client.endpoint.controller_id
                or proof.get("client_host_id")!=self.client.endpoint.client_host_id): raise ValueError("The original controller enrollment is required.")
        status=self.client.call("status",dict(operation_id=operation_id))
        rows=status.get("records") if isinstance(status,dict) else None
        if not isinstance(rows,list) or len(rows)!=1: raise ValueError("The request remains uncertain; no off state was inferred.")
        original=self.receipts.load(operation_id) if self.receipts.path(operation_id).exists() else None
        receipt=self.checked(rows[0],original)
        if receipt.operation_id!=operation_id or receipt.connection_id!=proof["connection_id"]: raise ValueError("Recovery evidence differs.")
        if (any(getattr(receipt,name)!=proof[name] for name in ("account_id","connector_id","quote_key","rate_ceiling","rate_unit","rate_scope"))
                or receipt.deadline-receipt.created_at!=proof["duration_seconds"]): raise ValueError("Recovery differs from the confirmed account and limits.")
        with self.record_lock:
            if self.receipts.path(operation_id).exists():
                latest=self.receipts.load(operation_id)
                if not latest.unresolved and receipt.unresolved: receipt=self.checked(asdict(latest),receipt)
            self.receipts.save(receipt); self.receipt=receipt
        if not receipt.unresolved:
            path.unlink(missing_ok=True)
            if self.pending_operation==operation_id: self.pending_operation=None
        return receipt

    def abandon(self,operation_id):
        with self.state_lock:
            path=self.intents.path(operation_id)
            if path.is_symlink() or path.stat().st_size>8192: raise ValueError("The request intent is damaged.")
            proof=json.loads(path.read_text())
            if (proof.get("operation_id")!=operation_id or proof.get("controller_id")!=self.client.endpoint.controller_id
                    or proof.get("client_host_id")!=self.client.endpoint.client_host_id): raise ValueError("The original controller is required.")
            result=self.client.call("abandon_request",dict(operation_id=operation_id,connection_id=proof["connection_id"]))
            if (not isinstance(result,dict) or result.get("operation_id")!=operation_id or result.get("connection_id")!=proof["connection_id"]
                    or result.get("future_start_forbidden") is not True or type(result.get("receipt_exists")) is not bool):
                raise ValueError("Abandonment was not confirmed. Preserve recovery state.")
            if result["receipt_exists"]: return self.refresh(operation_id)
            if self.receipts.path(operation_id).exists():
                raise ValueError("The controller lost a previously known receipt. Provider state is still uncertain.")
            completed=Store(self.root/"finished-requests")
            atomic_json(completed.path(operation_id),{**proof,"state":"future-start-forbidden"})
            path.unlink()
            if self.pending_operation==operation_id: self.pending_operation=None
            return dict(operation_id=operation_id,state="cancelled-before-submission")

    def stop(self):
        with self.state_lock:
            if self.receipt is None:
                return self.abandon(self.pending_operation) if self.pending_operation is not None else None
            if self.session is not None:
                # The lease thread may already know a resource/state newer than begin's reply.
                receipt=self.session.close(); self.receipt=self.checked(asdict(receipt),self.receipt)
                self.session=None; return self.receipt
            current=self.checked(asdict(self.receipts.load(self.receipt.operation_id)),self.receipt)
            if not current.unresolved: self.receipt=current; return current
            receipt=replace(current,cancel_requested=True); self.receipts.save(receipt); self.receipt=receipt
            self.client.call("cancel",dict(operation_id=receipt.operation_id,operation_key=receipt.operation_key()))
            return receipt
