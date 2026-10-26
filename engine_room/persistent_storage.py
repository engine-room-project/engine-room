"""Connector-neutral persistent storage intent and one-submit recovery journal."""
from dataclasses import asdict,replace
import json
import hashlib
import re
import threading
import time
import uuid

from .connections import Connection
from .records import Store,atomic_json
from .volume_records import StorageQuote,VolumeIntent


class PersistentStorage:
    def __init__(self,connections,registry,enrollment,host_id,*,now=time.time):
        self.connections=connections; self.registry=registry; self.enrollment=enrollment; self.host_id=host_id; self.now=now
        self.records=Store(connections.root/"storage-operations"); self.denials=Store(connections.root/"storage-start-denials"); self.closed=False
        self.locks={}; self.mutex=threading.Lock()
    def verify(self,client_id): self.enrollment.verify(self.host_id,client_id)
    def lock(self,operation_id):
        self.records.path(operation_id)
        with self.mutex: return self.locks.setdefault(operation_id,threading.RLock())
    def read(self,operation_id):
        path=self.records.path(operation_id)
        if path.is_symlink() or path.stat().st_size>131072: raise ValueError("Preserve damaged storage recovery records.")
        value=json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value,dict) or set(value)!={"schema","intent","connection","quote","submission_claimed","closed_without_submission","confirmation_source"}
                or type(value["schema"]) is not int or value["schema"]!=1 or type(value["submission_claimed"]) is not bool
                or type(value["closed_without_submission"]) is not bool or value["confirmation_source"] not in {None,"creation-response","explicit-manual-identification"}):
            raise ValueError("Invalid storage journal.")
        data=dict(value["intent"])
        if not isinstance(data.get("baseline_ids"),list): raise ValueError("Invalid storage baseline.")
        data["baseline_ids"]=tuple(data["baseline_ids"])
        intent=VolumeIntent(**data).validate(); connection=Connection(**value["connection"]).validate(); quote=StorageQuote(**value["quote"]).validate()
        if (intent.operation_id!=operation_id or intent.connection_id!=connection.id or intent.account_id!=connection.account_id
                or intent.connector_id!=connection.connector_id or any(getattr(intent,key)!=getattr(quote,key) for key in ("account_id","size_gb","data_center","storage_type"))
                or (value["closed_without_submission"] and value["submission_claimed"])
                or (intent.resource_id is not None and (not value["submission_claimed"] or value["confirmation_source"] is None))
                or (intent.state=="known" and value["confirmation_source"] is None)):
            raise ValueError("Storage journal scope changed.")
        return value,intent,connection,quote
    def save(self,value): atomic_json(self.records.path(value["intent"]["operation_id"]),value)
    def snapshot(self,operation_id):
        value,intent,_,quote=self.read(operation_id)
        result={key:getattr(intent,key) for key in ("operation_id","connection_id","connector_id","account_id","size_gb","data_center","storage_type","created_at","state","resource_id")}
        result.update(operation_key=intent.operation_key(),marker=intent.marker(),quote=asdict(quote),cost_unit="USD/month",
            submission_claimed=value["submission_claimed"],closed_without_submission=value["closed_without_submission"],confirmation_source=value["confirmation_source"],fresh_provider_observation=False)
        return result
    def listing(self,*,after="",limit=10):
        if (not isinstance(after,str) or (after and not re.fullmatch(r"[a-f0-9]{64}",after)) or type(limit) is not int or not 1<=limit<=10):
            raise ValueError("Invalid storage recovery page.")
        paths=list(self.records.root.glob("*.json"))
        if len(paths)>512: raise ValueError("Storage index needs manual reconciliation.")
        rows=[]
        for path in paths:
            cursor=hashlib.sha256(path.name.encode()).hexdigest()
            if cursor<=after: continue
            try: row=self.snapshot(path.stem)
            except (OSError,ValueError,TypeError,UnicodeError): row=dict(damaged=True,message="Preserve a damaged storage journal for manual reconciliation.")
            rows.append((cursor,row))
        rows.sort(key=lambda pair:pair[0]); page=rows[:limit]
        return dict(records=[row for _,row in page],next_cursor=page[-1][0] if len(rows)>len(page) else None)
    def quote(self,connection_id,selection,client_id):
        self.verify(client_id)
        if not isinstance(selection,dict) or set(selection)!={"size_gb","data_center","storage_type"}: raise ValueError("Choose explicit storage size, location and tier.")
        connection=self.connections.read()[connection_id]; connector=self.registry[connection.connector_id]
        if "persistent_storage" not in connector.descriptor.capabilities: raise ValueError("This connector does not support persistent storage.")
        result=connector.storage_quote(connection,selection)
        if not isinstance(result,StorageQuote) or result.account_id!=connection.account_id or any(selection[key]!=getattr(result,key) for key in selection):
            raise ValueError("The storage quote differs from the selected account or target.")
        return result.validate(self.now())
    def create(self,operation_id,connection_id,selection,approved_quote,client_id,*,continuing_costs_confirmed):
        self.verify(client_id)
        if continuing_costs_confirmed is not True or not isinstance(approved_quote,StorageQuote): raise ValueError("Approve separately billed persistent storage explicitly.")
        with self.lock(operation_id):
            with self.records.allocation_lock():
                path=self.records.path(operation_id)
                if path.exists() or path.is_symlink():
                    value,intent,connection,quote=self.read(operation_id)
                    if connection.id!=connection_id or quote.key()!=approved_quote.key() or selection!={key:getattr(intent,key) for key in ("size_gb","data_center","storage_type")}:
                        raise ValueError("Storage operation identity is already in use.")
                    return value  # Lost replies never resubmit creation, even before the final gate.
                denied=self.denials.path(operation_id)
                if denied.exists() or denied.is_symlink(): raise ValueError("This storage request was abandoned and cannot submit again.")
                if self.closed: raise ValueError("Storage creation is stopping.")
                for old in self.records.root.glob("*.json"):
                    row,record,_,_=self.read(old.stem)
                    if record.connection_id==connection_id and record.state!="known" and not row["closed_without_submission"]:
                        raise ValueError("Reconcile pending storage before creating another volume.")
                connection=self.connections.read()[connection_id]
                fresh=self.quote(connection_id,selection,client_id); approved_quote.validate(self.now())
                if fresh.key()!=approved_quote.key(): raise ValueError("Storage price or account changed. Review it again.")
                if self.connections.read().get(connection_id)!=connection: raise ValueError("The storage connection changed during pricing.")
                connector=self.registry[connection.connector_id]
                rows=connector.storage_inventory(connection)
                if not isinstance(rows,list) or any(not isinstance(row,dict) or "id" not in row for row in rows): raise ValueError("A complete storage inventory is required.")
                intent=VolumeIntent(operation_id,connection.id,connection.connector_id,connection.account_id,fresh.size_gb,fresh.data_center,self.now(),uuid.uuid4().hex,
                    tuple(row["id"] for row in rows),state="submitting",storage_type=fresh.storage_type).validate()
                value=dict(schema=1,intent=asdict(intent),connection=asdict(connection),quote=asdict(fresh),submission_claimed=False,closed_without_submission=False,confirmation_source=None)
                self.save(value)
            def gate():
                with self.records.allocation_lock():
                    latest,current,saved,quoted=self.read(operation_id)
                    denied=self.denials.path(operation_id)
                    if (self.closed or denied.exists() or denied.is_symlink() or current!=intent or saved!=connection or quoted.key()!=fresh.key() or latest["submission_claimed"] or latest["closed_without_submission"]
                            or self.connections.read().get(connection_id)!=connection): raise ValueError("Storage submission authority changed.")
                    quoted.validate(self.now())
                    latest["submission_claimed"]=True; self.save(latest)
            result=None
            try: result=connector.storage_create(connection,intent,submit_gate=gate)
            except Exception: pass  # Never expose credential-bearing provider errors or retry a POST.
            with self.records.allocation_lock():
                latest,current,_,_=self.read(operation_id)
                if current.marker()!=intent.marker() or current.baseline_ids!=intent.baseline_ids: raise ValueError("Original storage evidence changed.")
                resource=None; verified=False
                if isinstance(result,dict) and latest["submission_claimed"]:
                    resource=result.get("resource_id"); verified=result.get("verified") is True and result.get("source")=="creation-response"
                updated=replace(current,state="known" if verified else "unresolved",resource_id=resource).validate()
                latest["intent"]=asdict(updated); latest["confirmation_source"]="creation-response" if resource is not None else None
                self.save(latest); return self.read(operation_id)[0]
    def abandon(self,operation_id,connection_id,client_id):
        self.verify(client_id); self.records.path(connection_id)
        with self.records.allocation_lock():
            path=self.records.path(operation_id); value=None
            if path.exists() or path.is_symlink():
                value,intent,connection,_=self.read(operation_id)
                if intent.connection_id!=connection_id: raise ValueError("Choose the original storage connection.")
            else:
                connection=self.connections.read().get(connection_id)
                if connection is None: raise ValueError("Choose the original storage connection.")
            expected=dict(schema=1,operation_id=operation_id,connection_id=connection_id,connector_id=connection.connector_id,
                account_id=connection.account_id,controller_id=self.enrollment.controller_id,client_host_id=client_id)
            denied=self.denials.path(operation_id)
            if denied.exists() or denied.is_symlink():
                if denied.is_symlink() or denied.stat().st_size>8192 or json.loads(denied.read_text(encoding="utf-8"))!=expected:
                    raise ValueError("Preserve the original storage denial evidence.")
            else: atomic_json(denied,expected)
            claimed=value is not None and value["submission_claimed"]
            if value is not None and not claimed:
                value["closed_without_submission"]=True; self.save(value)
            return dict(operation_id=operation_id,connection_id=connection_id,new_submissions_forbidden=True,
                creation_may_complete=claimed,record=self.snapshot(operation_id) if value is not None else None)
    def abandon_unsubmitted(self,operation_id,client_id):
        self.verify(client_id)
        _,intent,_,_=self.read(operation_id)
        result=self.abandon(operation_id,intent.connection_id,client_id)
        if result["creation_may_complete"]: raise ValueError("A submitted storage request needs reconciliation; it was not deleted.")
        return self.read(operation_id)[0]
    def recover(self,operation_id,client_id,*,resource_id=None,confirmed=False):
        self.verify(client_id)
        if resource_id is not None and confirmed is not True: raise ValueError("Explicit manual identification approval is required.")
        with self.lock(operation_id):
            value,intent,connection,_=self.read(operation_id); connector=self.registry[intent.connector_id]
            if value["closed_without_submission"]: return dict(journal=value,observation=dict(status="not-submitted",candidates=[]))
            if resource_id is None:
                result=connector.storage_reconcile(connection,intent)
                if (intent.resource_id is not None and value["confirmation_source"]=="creation-response" and isinstance(result,dict)
                        and result.get("status")=="observed" and result.get("resource_id")==intent.resource_id):
                    with self.records.allocation_lock():
                        latest,current,_,_=self.read(operation_id)
                        if current!=intent: raise ValueError("Storage recovery evidence changed.")
                        latest["intent"]=asdict(replace(intent,state="known")); self.save(latest); value=latest
                return dict(journal=value,observation=result)
            if not value["submission_claimed"]: raise ValueError("No volume creation was submitted by this operation.")
            if intent.resource_id is not None and intent.resource_id!=resource_id: raise ValueError("The known storage identity cannot be substituted.")
            replace(intent,resource_id=resource_id).validate()
            result=connector.storage_identify(connection,intent,resource_id,confirmed=confirmed)
            if not isinstance(result,dict) or result.get("resource_id")!=resource_id or result.get("verified") is not True or result.get("source")!="explicit-manual-identification":
                raise ValueError("Manual volume identification was not verified.")
            updated=replace(intent,state="known",resource_id=resource_id).validate()
            with self.records.allocation_lock():
                latest,current,_,_=self.read(operation_id)
                if current!=intent: raise ValueError("Storage recovery evidence changed.")
                latest["intent"]=asdict(updated); latest["confirmation_source"]="explicit-manual-identification"; self.save(latest)
            return dict(journal=latest,observation=result)
