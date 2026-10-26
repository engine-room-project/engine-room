"""Durable desktop existing-machine access; never submits rental operations."""
from dataclasses import asdict,replace
import json
import uuid

from .controller_protocol import fields
from .desktop_rental import Rental
from .desktop_session import pending
from .records import DamagedRecord,Receipt,Store,atomic_json
from .tools import served_model_plan


class Attachment(Rental):
    def checked(self,data,original=None):
        result=Receipt(**data).validate()
        if result.mode!="attachment" or result.protection_id!=self.client.endpoint.controller_id:
            raise ValueError("The original attachment controller is required.")
        if original is not None and (result.operation_key()!=original.operation_key() or result.resource_id!=original.resource_id):
            raise ValueError("Attachment recovery scope changed.")
        return result
    def proof(self,operation_id):
        path=self.intents.path(operation_id)
        if path.is_symlink() or path.stat().st_size>8192: raise ValueError("Preserve the original attachment intent.")
        proof=json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(proof,dict) or proof.get("mode")!="attachment" or proof.get("schema")!=1
                or proof.get("operation_id")!=operation_id or proof.get("controller_id")!=self.client.endpoint.controller_id
                or proof.get("client_host_id")!=self.client.endpoint.client_host_id):
            raise ValueError("The original controller and attachment intent are required.")
        return proof
    def matched(self,data,proof,original=None):
        receipt=self.checked(data,original)
        for field in ("operation_id","connection_id","account_id","connector_id","resource_id"):
            if getattr(receipt,field)!=proof[field]: raise ValueError("Attachment differs from the confirmed existing target.")
        return receipt
    def begin(self,request,*,confirmed,ui_touch,is_closed):
        fields(request,("connection_id","approved_target","context"))
        touch=lambda:ui_touch() if callable(ui_touch) else ui_touch
        def live(): return not is_closed() and 0<=self.clock()-touch()<60
        if confirmed is not True or not live(): raise ValueError("Review and confirm this existing-machine connection while the window is active.")
        target=request["approved_target"]
        if not isinstance(target,dict) or set(target)!={"account_id","resource_id","model_id"}: raise ValueError("Review the exact existing target.")
        for field,limit in (("account_id",200),("resource_id",200),("model_id",500)):
            value=target[field]
            if not isinstance(value,str) or not value or len(value)>limit or any(ord(c)<32 for c in value): raise ValueError("Invalid existing target.")
        self.tool_plan=served_model_plan(target["model_id"],request["context"])
        rows=self.client.call("connections")
        matches=[row for row in rows if row.get("id")==request["connection_id"]] if isinstance(rows,list) else []
        if len(matches)!=1 or matches[0].get("account_id")!=target["account_id"]: raise ValueError("The reviewed connection changed.")
        connection=matches[0]
        if not live(): raise ValueError("The window stopped confirming this connection.")
        operation="desktop-"+uuid.uuid4().hex
        proof=dict(schema=1,mode="attachment",operation_id=operation,controller_id=self.client.endpoint.controller_id,
            client_host_id=self.client.endpoint.client_host_id,connection_id=request["connection_id"],connector_id=connection["connector_id"],
            account_id=target["account_id"],resource_id=target["resource_id"],model_id=target["model_id"],tool_context=request["context"],state="submitted")
        with self.intents.allocation_lock():
            if any(self.intents.root.glob("*.json")) or any(isinstance(row,DamagedRecord) or pending(row) for row in self.receipts.scan()):
                raise ValueError("Recover existing attachment access before connecting again.")
            atomic_json(self.intents.path(operation),proof); self.pending_operation=operation
        data=self.client.call("attach",dict(connection_id=request["connection_id"],approved_target=target,operation_id=operation))
        with self.state_lock:
            receipt=self.matched(data,proof)
            if not self.intents.path(operation).exists():
                self.client.call("abandon_attachment",dict(operation_id=operation,connection_id=proof["connection_id"]))
                raise ValueError("This connection was already cancelled before its reply arrived.")
            if self.receipts.path(operation).exists() and not pending(self.receipts.load(operation)):
                raise ValueError("This attachment already has terminal recovery evidence.")
            self.receipts.save(receipt); self.receipt=receipt
            if not live() or receipt.state!="active" or receipt.cancel_requested:
                self.stop(); raise ValueError("Local attachment access was not confirmed. Read recovery status.")
            try:
                self.session=self.session_factory(self.client,receipt,self.receipts.root,clock=self.clock,initial_touch=touch(),record_lock=self.record_lock,selected_model=target["model_id"])
            except Exception:
                self.stop(); raise
            atomic_json(self.intents.path(operation),{**proof,"state":"linked"})
            return receipt
    def refresh(self,operation_id):
        proof=self.proof(operation_id)
        status=self.client.call("status",dict(operation_id=operation_id)); rows=status.get("records") if isinstance(status,dict) else None
        if not isinstance(rows,list) or len(rows)!=1: raise ValueError("Local disconnection remains uncertain.")
        with self.record_lock:
            original=self.receipts.load(operation_id) if self.receipts.path(operation_id).exists() else None
            receipt=self.matched(rows[0],proof,original)
            if original is not None and not pending(original) and pending(receipt): receipt=original
            self.receipts.save(receipt); self.receipt=receipt
        if receipt.state=="detached":
            self.intents.path(operation_id).unlink(missing_ok=True)
            if self.pending_operation==operation_id: self.pending_operation=None
        return receipt
    def abandon(self,operation_id):
        with self.state_lock:
            proof=self.proof(operation_id)
            result=self.client.call("abandon_attachment",dict(operation_id=operation_id,connection_id=proof["connection_id"]))
            if isinstance(result,dict) and result==dict(cancelled_before_start=True):
                if self.receipts.path(operation_id).exists(): raise ValueError("Preserve the previously known attachment receipt.")
                atomic_json(Store(self.root/"finished-requests").path(operation_id),{**proof,"state":"future-start-forbidden"})
                self.intents.path(operation_id).unlink(); self.pending_operation=None
                return dict(operation_id=operation_id,state="cancelled-before-submission")
            self.matched(result,proof)
            return self.refresh(operation_id)
    def stop(self):
        with self.state_lock:
            if self.receipt is None: return self.abandon(self.pending_operation) if self.pending_operation is not None else None
            if self.session is not None:
                receipt=self.session.close(); self.receipt=self.checked(asdict(receipt),self.receipt); self.session=None
                return self.receipt
            current=self.checked(asdict(self.receipts.load(self.receipt.operation_id)),self.receipt)
            if current.state=="detached": self.receipt=current; return current
            current=replace(current,cancel_requested=True); self.receipts.save(current); self.receipt=current
            data=self.client.call("disconnect_attachment",dict(operation_id=current.operation_id,operation_key=current.operation_key()))
            result=self.checked(data,current); self.receipts.save(result); self.receipt=result
            return result
