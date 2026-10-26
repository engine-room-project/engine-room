"""Connector-neutral existing-machine access; local disconnect never authorizes shutdown."""
from dataclasses import asdict,replace
import json
import threading
import time

from .connections import Connection
from .private_endpoint import ModelEndpoint
from .records import Receipt,Store,atomic_json


class Attachments:
    def __init__(self,connections,registry,enrollment,host_id,*,now=time.time):
        self.connections=connections; self.registry=registry; self.enrollment=enrollment; self.host_id=host_id; self.now=now
        self.store=connections.receipts; self.journal=Store(connections.root/"attachment-journal")
        self.denials=Store(connections.root/"start-denials")
        self.locks={}; self.mutex=threading.Lock(); self.closed=False
    def lock(self,operation_id):
        self.store.path(operation_id)
        with self.mutex: return self.locks.setdefault(operation_id,threading.RLock())
    def verify(self,client_id): self.enrollment.verify(self.host_id,client_id)
    def saved(self,receipt):
        path=self.journal.path(receipt.operation_id)
        if path.is_symlink() or path.stat().st_size>32768: raise ValueError("Preserve damaged attachment evidence.")
        data=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or set(data)!={"schema","receipt","connection","model_id"} or type(data["schema"]) is not int or data["schema"]!=1:
            raise ValueError("Invalid attachment journal.")
        original=Receipt(**data["receipt"]).validate(); connection=Connection(**data["connection"]).validate()
        model=data["model_id"]
        if (original.operation_key()!=receipt.operation_key() or original.resource_id!=receipt.resource_id
                or receipt.mode!="attachment" or receipt.protection_id!=self.enrollment.controller_id
                or connection.id!=receipt.connection_id or connection.account_id!=receipt.account_id or connection.connector_id!=receipt.connector_id
                or not isinstance(model,str) or not model or len(model)>500 or any(ord(c)<32 for c in model)):
            raise ValueError("The original attachment scope is required.")
        return connection,self.registry[receipt.connector_id],model
    def current(self,operation_id):
        receipt=self.store.load(operation_id); connection,connector,model=self.saved(receipt)
        if self.closed or receipt.state!="active" or receipt.cancel_requested or self.connections.read().get(connection.id)!=connection:
            raise ValueError("This attachment is not authorized for access.")
        return receipt,connection,connector,model
    def preview(self,connection_id,client_id):
        self.verify(client_id)
        connection=self.connections.read()[connection_id]; connector=self.registry[connection.connector_id]
        if "attachment" not in connector.descriptor.modes: raise ValueError("This connector cannot connect to an existing machine.")
        target=connector.attachment_target(connection)
        if not isinstance(target,dict) or set(target)!={"account_id","resource_id","model_id"} or target["account_id"]!=connection.account_id:
            raise ValueError("The saved existing-machine identity changed.")
        for field,limit in (("resource_id",200),("model_id",500)):
            value=target[field]
            if not isinstance(value,str) or not value or len(value)>limit or any(ord(c)<32 for c in value): raise ValueError("Select an explicit existing model and resource.")
        return target
    def attach(self,operation_id,connection_id,client_id,*,approved_target):
        self.verify(client_id)
        with self.lock(operation_id):
            with self.store.allocation_lock():
                if self.closed: raise ValueError("Attachment access is stopping.")
                if self.store.path(operation_id).exists():
                    receipt=self.store.load(operation_id)
                    if receipt.mode!="attachment" or receipt.connection_id!=connection_id: raise ValueError("Operation identity is already in use.")
                    self.saved(receipt)
                    return receipt  # Lost replies never reopen access or replay a helper.
                for path in (self.denials.path(operation_id),self.journal.path(operation_id)):
                    if path.exists() or path.is_symlink(): raise ValueError("Recover this original operation before reconnecting.")
                connection=self.connections.read()[connection_id]; connector=self.registry[connection.connector_id]
                target=self.preview(connection_id,client_id)
                if not isinstance(approved_target,dict) or approved_target!=target:
                    raise ValueError("Review the changed existing-machine target before connecting.")
                model=target["model_id"]
                receipt=Receipt(operation_id,connection_id,connection.connector_id,connection.account_id,"attachment","active",self.now(),
                    resource_id=target["resource_id"],protection_id=self.enrollment.controller_id).validate()
                atomic_json(self.journal.path(operation_id),dict(schema=1,receipt=asdict(receipt),connection=asdict(connection),model_id=model))
                self.store.save(receipt)
            try:
                connector.attach(connection,receipt)
                self.current(operation_id)
                return self.store.load(operation_id)
            except Exception:
                return self.disconnect(operation_id,connection_id,client_id)
    def disconnect(self,operation_id,connection_id,client_id):
        self.verify(client_id); self.store.path(connection_id)
        with self.store.allocation_lock():
            path=self.denials.path(operation_id)
            if self.store.path(operation_id).exists():
                receipt=self.store.load(operation_id)
                if receipt.mode!="attachment" or receipt.connection_id!=connection_id: raise ValueError("Choose the original attachment.")
                self.saved(receipt)
                if receipt.state=="detached": return receipt
                self.store.save(replace(receipt,cancel_requested=True))
            else:
                if self.journal.path(operation_id).exists():
                    # An interrupted durable journal must be reconciled, never replayed.
                    journal=self.journal.path(operation_id)
                    if journal.is_symlink() or journal.stat().st_size>32768: raise ValueError("Preserve damaged attachment evidence.")
                    data=json.loads(journal.read_text(encoding="utf-8"))
                    receipt=Receipt(**data["receipt"]).validate(); self.saved(receipt)
                    if receipt.connection_id!=connection_id: raise ValueError("Choose the original attachment.")
                    self.store.save(replace(receipt,cancel_requested=True))
                else: receipt=None
            expected=dict(schema=1,mode="attachment",operation_id=operation_id,connection_id=connection_id,controller_id=self.enrollment.controller_id)
            if path.exists() or path.is_symlink():
                if path.is_symlink() or path.stat().st_size>8192 or json.loads(path.read_text(encoding="utf-8"))!=expected:
                    raise ValueError("Preserve the original request denial.")
            else: atomic_json(path,expected)
        if receipt is None: return None
        with self.lock(operation_id):
            receipt=self.store.load(operation_id); connection,connector,_=self.saved(receipt)
            if receipt.state=="detached": return receipt
            state="detached"
            try: connector.disconnect(connection,receipt)
            except Exception: state="unresolved"
            with self.store.allocation_lock():
                latest=self.store.load(operation_id)
                if latest.operation_key()!=receipt.operation_key() or latest.resource_id!=receipt.resource_id:
                    raise ValueError("The original attachment recovery record changed.")
                result=replace(latest,state=state,cancel_requested=True); self.store.save(result)
            return result
    def pulse(self,operation_id,client_id):
        self.verify(client_id)
        with self.lock(operation_id):
            receipt,connection,connector,_=self.current(operation_id)
            try: connector.pulse(connection,receipt)
            except Exception:
                self.disconnect(operation_id,receipt.connection_id,client_id)
                raise ValueError("Attachment access could not be renewed.") from None
            self.current(operation_id)
            return receipt
    def stream_scope(self,operation_id,client_id):
        self.verify(client_id)
        with self.lock(operation_id):
            receipt,connection,connector,model=self.current(operation_id)
            endpoint=connector.model_endpoint(connection,receipt)
            if not isinstance(endpoint,ModelEndpoint): raise ValueError("A private scoped endpoint is required.")
            endpoint.validate(self.connections.root,receipt.operation_key(),receipt.resource_id)
            self.current(operation_id)
            return dict(endpoint=endpoint.data(),selected_model=model)
    def recover(self):
        results=[]
        ids={r.operation_id:r.connection_id for r in self.store.scan() if isinstance(r,Receipt) and r.mode=="attachment" and r.state!="detached"}
        for path in self.journal.root.glob("*.json"):
            if path.stem not in ids and not self.store.path(path.stem).exists():
                try:
                    if path.is_symlink() or path.stat().st_size>32768: raise ValueError()
                    data=json.loads(path.read_text(encoding="utf-8")); receipt=Receipt(**data["receipt"]).validate(); self.saved(receipt)
                    ids[receipt.operation_id]=receipt.connection_id
                except Exception: continue  # Preserve damaged evidence; it never permits replay.
        for operation_id,connection_id in ids.items():
            try: results.append(self.disconnect(operation_id,connection_id,self.enrollment.client_host_id))
            except Exception: pass
        return results
    def pending(self):
        if any(isinstance(r,Receipt) and r.mode=="attachment" and r.state!="detached" for r in self.store.scan()): return True
        for path in self.journal.root.glob("*.json"):
            try:
                if path.is_symlink() or not self.store.path(path.stem).exists(): return True
            except ValueError: return True
        return False
    def close(self):
        self.closed=True
        return self.recover()
