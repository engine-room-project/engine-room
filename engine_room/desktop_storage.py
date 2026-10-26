"""Desktop storage intent before RPC; lost replies never replay billable creation."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid

from .connections import Connection
from .controller_protocol import fields
from .records import Store,atomic_json
from .volume_records import StorageQuote

RECORD_FIELDS=("operation_id","connection_id","connector_id","account_id","size_gb","data_center","storage_type","created_at","state","resource_id",
    "operation_key","marker","quote","cost_unit","submission_claimed","closed_without_submission","confirmation_source","fresh_provider_observation")


class DesktopStorage:
    def __init__(self,client,root,*,now=time.time):
        self.client=client; self.root=Path(root); self.operations=Store(self.root/"requests"); self.now=now
    def load(self,operation_id):
        path=self.operations.path(operation_id)
        if path.is_symlink() or path.stat().st_size>32768: raise ValueError("Preserve the damaged local storage intent.")
        proof=json.loads(path.read_text(encoding="utf-8"))
        fields(proof,("schema","operation_id","controller_id","client_host_id","connection_id","connector_id","account_id","selection","approved_quote","state","record","denial_confirmed"))
        if (type(proof["schema"]) is not int or proof["schema"]!=1 or proof["operation_id"]!=operation_id
                or proof["controller_id"]!=self.client.endpoint.controller_id or proof["client_host_id"]!=self.client.endpoint.client_host_id
                or proof["state"] not in {"submitted","known","closed"} or type(proof["denial_confirmed"]) is not bool):
            raise ValueError("The original controller enrollment and storage intent are required.")
        for key in ("connection_id","connector_id"): self.operations.path(proof[key])
        quote=StorageQuote(**proof["approved_quote"]).validate()
        if quote.account_id!=proof["account_id"] or proof["selection"]!={key:getattr(quote,key) for key in ("size_gb","data_center","storage_type")}:
            raise ValueError("The approved storage target changed.")
        if proof["record"] is not None: self.checked(proof["record"],proof)
        if proof["state"]=="known" and (proof["record"] is None or proof["record"]["state"]!="known"): raise ValueError("Known storage evidence is missing.")
        if proof["state"]=="closed" and not proof["denial_confirmed"] and (proof["record"] is None or not proof["record"]["closed_without_submission"]):
            raise ValueError("Cancellation evidence is missing.")
        return proof
    def save(self,proof): atomic_json(self.operations.path(proof["operation_id"]),proof)
    def checked(self,data,proof):
        fields(data,RECORD_FIELDS)
        for key in ("operation_id","connection_id","connector_id","account_id"):
            if data[key]!=proof[key]: raise ValueError("The returned storage operation differs from its original scope.")
        quote=StorageQuote(**data["quote"]).validate()
        if quote.key()!=StorageQuote(**proof["approved_quote"]).key() or any(data[key]!=value for key,value in proof["selection"].items()):
            raise ValueError("The returned storage differs from the reviewed price or target.")
        if (not isinstance(data["operation_key"],str) or not re.fullmatch(r"[a-f0-9]{64}",data["operation_key"])
                or data["marker"]!="engine-room-storage-"+data["operation_key"][:32] or data["state"] not in {"intent","submitting","known","unresolved"}
                or data["cost_unit"]!="USD/month" or data["fresh_provider_observation"] is not False
                or type(data["created_at"]) not in (int,float) or not math.isfinite(data["created_at"]) or data["created_at"]<=0
                or any(type(data[key]) is not bool for key in ("submission_claimed","closed_without_submission"))
                or (data["closed_without_submission"] and data["submission_claimed"])
                or data["confirmation_source"] not in {None,"creation-response","explicit-manual-identification"}):
            raise ValueError("The storage recovery response is invalid.")
        resource=data["resource_id"]
        if resource is not None:
            self.operations.path(resource)
            if not data["submission_claimed"] or data["confirmation_source"] is None: raise ValueError("Storage identity is not backed by submission evidence.")
        if data["state"]=="known" and resource is None: raise ValueError("Known storage identity is missing.")
        old=proof["record"]
        if old is not None:
            if data["operation_key"]!=old["operation_key"] or (resource is not None and old["resource_id"] is not None and resource!=old["resource_id"]):
                raise ValueError("The original storage identity changed.")
        return data
    def apply(self,operation_id,data):
        with self.operations.allocation_lock():
            proof=self.load(operation_id); data=self.checked(data,proof); old=proof["record"]
            if proof["state"]=="closed" and not data["closed_without_submission"]: raise ValueError("Preserve the confirmed cancellation and reconcile contradictory evidence.")
            if old is not None and old["state"]=="known" and data["state"]!="known": data=old
            proof["record"]=data
            proof["state"]="closed" if data["closed_without_submission"] else "known" if data["state"]=="known" else "submitted"
            self.save(proof); return data
    def begin(self,request,*,confirmed):
        fields(request,("connection_id","selection","approved_quote","continuing_costs_confirmed"))
        if confirmed is not True or request["continuing_costs_confirmed"] is not True: raise ValueError("Explicit creation and continuing-storage approval are required.")
        quote=StorageQuote(**request["approved_quote"]).validate(self.now())
        if request["selection"]!={key:getattr(quote,key) for key in ("size_gb","data_center","storage_type")}: raise ValueError("Review the exact storage target.")
        rows=self.client.call("connections")
        matches=[Connection(**row).validate() for row in rows if isinstance(row,dict) and row.get("id")==request["connection_id"]] if isinstance(rows,list) else []
        if len(matches)!=1 or matches[0].account_id!=quote.account_id: raise ValueError("The approved storage connection changed.")
        connection=matches[0]; operation="storage-"+uuid.uuid4().hex
        proof=dict(schema=1,operation_id=operation,controller_id=self.client.endpoint.controller_id,client_host_id=self.client.endpoint.client_host_id,
            connection_id=connection.id,connector_id=connection.connector_id,account_id=connection.account_id,selection=dict(request["selection"]),approved_quote=asdict(quote),state="submitted",record=None,denial_confirmed=False)
        with self.operations.allocation_lock():
            paths=list(self.operations.root.glob("*.json"))
            if len(paths)>=512: raise ValueError("Storage history needs reconciliation before creating more.")
            if any(self.load(path.stem)["state"]=="submitted" for path in paths): raise ValueError("Reconcile pending local storage before creating another volume.")
            self.save(proof)
        result=self.client.call("storage_create",dict(operation_id=operation,connection_id=connection.id,selection=dict(request["selection"]),approved_quote=asdict(quote),continuing_costs_confirmed=True))
        return self.apply(operation,result)
    def find(self,operation_id):
        proof=self.load(operation_id)
        if proof["record"] is not None: return proof["record"]
        after=""; seen=set()
        for _ in range(52):
            page=self.client.call("storage_records",dict(after=after,limit=10))
            fields(page,("records","next_cursor"))
            if not isinstance(page["records"],list) or len(page["records"])>10: raise ValueError("Invalid storage recovery page.")
            matches=[row for row in page["records"] if isinstance(row,dict) and row.get("operation_id")==operation_id]
            if len(matches)>1: raise ValueError("Duplicate storage recovery identity.")
            if matches: return self.apply(operation_id,matches[0])
            after=page["next_cursor"]
            if after is None: break
            if not isinstance(after,str) or not re.fullmatch(r"[a-f0-9]{64}",after) or after in seen: raise ValueError("Storage recovery pagination is incomplete.")
            seen.add(after)
        raise ValueError("The controller request remains unconfirmed. Preserve its intent or cancel the delayed request.")
    def recover(self,operation_id,*,resource_id=None,confirmed=False):
        if resource_id is not None and confirmed is not True: raise ValueError("Confirm the exact volume identity explicitly.")
        record=self.find(operation_id)
        params=dict(operation_id=operation_id,operation_key=record["operation_key"])
        if resource_id is not None: params.update(resource_id=resource_id,confirmed=confirmed)
        result=self.client.call("storage_recover",params); fields(result,("record","observation"))
        proof=self.load(operation_id); checked=self.checked(result["record"],proof)
        observation=result["observation"]
        if not isinstance(observation,dict): raise ValueError("Storage observation is missing.")
        if resource_id is not None:
            fields(observation,("resource_id","verified","source"))
            if (observation["resource_id"]!=resource_id or checked["resource_id"]!=resource_id
                    or observation["verified"] is not True or observation["source"]!="explicit-manual-identification"):
                raise ValueError("Manual storage identity was not verified.")
        else:
            fields(observation,("status","candidates"),("resource_id",))
            status=observation["status"]; candidates=observation["candidates"]
            if (status not in {"observed","absent","unresolved","not-submitted"} or not isinstance(candidates,list) or len(candidates)>512
                    or (status!="unresolved" and candidates)):
                raise ValueError("Invalid storage observation.")
            if status in {"observed","absent"}:
                if checked["resource_id"] is None or observation.get("resource_id")!=checked["resource_id"]:
                    raise ValueError("The provider observation differs from the saved volume identity.")
            elif status=="not-submitted":
                if not checked["closed_without_submission"] or observation.get("resource_id") is not None:
                    raise ValueError("The saved request has no confirmed cancellation.")
            elif observation.get("resource_id") is not None:
                raise ValueError("Unresolved storage cannot assert an identity.")
            seen=set()
            for candidate in candidates:
                if not isinstance(candidate,dict) or not isinstance(candidate.get("id"),str): raise ValueError("Invalid storage candidate.")
                self.operations.path(candidate["id"])
                if candidate["id"] in seen: raise ValueError("Duplicate storage candidate.")
                seen.add(candidate["id"])
        checked=self.apply(operation_id,checked)
        return dict(record=checked,observation=observation)
    def abandon(self,operation_id,*,confirmed):
        if confirmed is not True: raise ValueError("Confirm pending-storage cancellation explicitly.")
        proof=self.load(operation_id)
        result=self.client.call("storage_abandon",dict(operation_id=operation_id,connection_id=proof["connection_id"],confirmed=True))
        fields(result,("operation_id","connection_id","new_submissions_forbidden","creation_may_complete","record"))
        if (result["operation_id"]!=operation_id or result["connection_id"]!=proof["connection_id"] or result["new_submissions_forbidden"] is not True or type(result["creation_may_complete"]) is not bool):
            raise ValueError("Pending-storage cancellation was not confirmed.")
        if result["record"] is not None:
            record=self.checked(result["record"],proof)
            if result["creation_may_complete"]!=record["submission_claimed"] or (not result["creation_may_complete"] and not record["closed_without_submission"]):
                raise ValueError("Cancellation and submission evidence differ.")
            self.apply(operation_id,record)
        else:
            if result["creation_may_complete"] or proof["record"] is not None: raise ValueError("Preserve the previously known storage operation.")
            with self.operations.allocation_lock():
                latest=self.load(operation_id)
                if latest["record"] is not None: raise ValueError("Storage evidence arrived during cancellation.")
                latest.update(state="closed",denial_confirmed=True); self.save(latest)
        return result
    def listing(self,*,after="",limit=10):
        if type(limit) is not int or not 1<=limit<=10 or not isinstance(after,str) or (after and not re.fullmatch(r"[a-f0-9]{64}",after)): raise ValueError("Invalid local storage page.")
        paths=list(self.operations.root.glob("*.json"))
        if len(paths)>512: raise ValueError("Storage history needs reconciliation.")
        rows=[]
        for path in paths:
            cursor=hashlib.sha256(path.name.encode()).hexdigest()
            if cursor<=after: continue
            try:
                proof=self.load(path.stem)
                row={key:proof[key] for key in ("operation_id","connection_id","state","record")}
            except (OSError,ValueError,TypeError,UnicodeError): row=dict(damaged=True,message="Preserve a damaged local storage intent for reconciliation.")
            rows.append((cursor,row))
        rows.sort(key=lambda pair:pair[0]); page=rows[:limit]
        return dict(records=[row for _,row in page],next_cursor=page[-1][0] if len(rows)>len(page) else None)
