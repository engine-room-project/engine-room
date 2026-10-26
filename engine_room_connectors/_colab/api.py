"""Account-bound Colab assignment protocol; no shared CLI state or retrying POSTs.

Protocol adapted from google-colab-cli, Google LLC (Apache-2.0). See provenance.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid

from engine_room.records import Store,atomic_json
from engine_room.recovery import Observation
from .http import bearer,ColabHTTP

ACCELERATORS=frozenset({"T4","L4","A100","H100","G4"})


def endpoint(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.~-]{0,199}",value):
        raise ValueError("The provider assignment identity is invalid.")
    return value


def notebook(receipt):
    value=json.dumps([receipt.account_id,receipt.connection_id,receipt.operation_id],separators=(",",":"))
    return str(uuid.uuid5(uuid.NAMESPACE_URL,"Engine Room Colab "+value)).replace("-","_")+"."*8


class ColabAPI:
    def __init__(self,tokens,root,http=None,now=time.time):
        self.tokens=tokens; self.store=Store(root); self.http=http if http is not None else ColabHTTP(); self.now=now
    def account(self,reference,*,_token=None):
        token=self.tokens.access(reference) if _token is None else _token
        data=self.http.identity(token)
        subject=data.get("sub") if isinstance(data,dict) else None
        if not isinstance(subject,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.~-]{0,199}",subject):
            raise ValueError("The Colab account identity could not be verified.")
        return "google-"+hashlib.sha256(subject.encode()).hexdigest()
    def _bound(self,connection,receipt=None):
        if connection.connector_id!="colab" or (receipt is not None and (
                receipt.connector_id!="colab" or receipt.connection_id!=connection.id or receipt.account_id!=connection.account_id)):
            raise ValueError("The original Colab connection is required.")
        token=self.tokens.access(connection.credential_ref)
        if self.account(connection.credential_ref,_token=token)!=connection.account_id:
            raise ValueError("The authenticated Google account differs. Preserve the original recovery records.")
        return token
    def usage(self,connection):
        token=self._bound(connection)
        data=self.http.session("GET","ccu-info",token)
        if not isinstance(data,dict): raise ValueError("Colab usage is unavailable.")
        balance=data.get("currentBalance"); rate=data.get("consumptionRateHourly"); count=data.get("assignmentsCount")
        if (any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (balance,rate))
                or type(count) is not int or count<0):
            raise ValueError("Colab usage is incomplete.")
        return dict(account_id=connection.account_id,balance=balance,account_rate=rate,
            assignments_count=count,rate_scope="account_total",unit="CCU",observed_at=self.now())
    @staticmethod
    def _params(receipt,accelerator=None,high_mem=False):
        if accelerator is not None and accelerator not in ACCELERATORS: raise ValueError("Choose a supported GPU explicitly.")
        if type(high_mem) is not bool: raise ValueError("Choose the memory shape explicitly.")
        params={"nbh":notebook(receipt)}
        if accelerator:
            params.update(variant="GPU",accelerator=accelerator)
            if high_mem and accelerator!="L4": params["shape"]="hm"
        return params
    def _proof(self,receipt):
        path=self.store.path(receipt.operation_id)
        try:
            if path.is_symlink() or path.stat().st_size>4096: raise ValueError()
            data=json.loads(path.read_text(encoding="utf-8"))
            expected=dict(account_id=receipt.account_id,connection_id=receipt.connection_id,
                operation_id=receipt.operation_id,notebook=notebook(receipt),submitted=True)
            if not isinstance(data,dict) or set(data)!=set(expected)|{"submitted_at"}: raise ValueError()
            if any(type(data[k]) is not type(v) or data[k]!=v for k,v in expected.items()): raise ValueError()
            stamp=data["submitted_at"]
            if type(stamp) not in (int,float) or not math.isfinite(stamp) or not receipt.created_at<=stamp<receipt.deadline: raise ValueError()
            return data
        except Exception:
            raise ValueError("Durable Colab allocation proof is missing or damaged. Nothing was changed.") from None
    def allocate(self,connection,receipt,accelerator,*,submit_gate,high_mem=False):
        receipt.validate()
        if (receipt.mode!="rental" or receipt.state!="allocating" or not receipt.allocation_submitted
                or not receipt.protection_id or self.now()>=receipt.deadline):
            raise ValueError("A protected, durably submitted rental operation is required.")
        params=self._params(receipt,accelerator,high_mem)
        token=self._bound(connection,receipt)
        with self.store.allocation_lock():
            if self.store.path(receipt.operation_id).exists():
                raise ValueError("An allocation may already have been submitted. Reconcile without repeating it.")
            preflight=self.http.session("GET","assign",token,params=params)
            if (not isinstance(preflight,dict) or preflight.get("endpoint") or preflight.get("nbh")!=notebook(receipt)
                    or preflight.get("variant")!="GPU" or preflight.get("acc")!=accelerator):
                raise ValueError("A pre-existing or unexpected assignment was returned. It was not adopted or modified.")
            xsrf=bearer(preflight.get("token"))
            stamp=self.now()
            if not receipt.created_at<=stamp<receipt.deadline: raise ValueError("The protected allocation clock or deadline changed.")
            proof=dict(account_id=receipt.account_id,connection_id=receipt.connection_id,operation_id=receipt.operation_id,
                notebook=notebook(receipt),submitted=True,submitted_at=stamp)
            atomic_json(self.store.path(receipt.operation_id),proof)
            try: submit_gate()
            except Exception:
                proof["submitted"]=False
                atomic_json(self.store.path(receipt.operation_id),proof)
                raise
            result=self.http.session("POST","assign",token,params=params,xsrf=xsrf)
        if not isinstance(result,dict): raise ValueError("Allocation remains uncertain; reconcile this operation.")
        identity=endpoint(result.get("endpoint"))
        owned=type(result.get("variant")) is int and result["variant"]==1 and result.get("accelerator") in ACCELERATORS
        return Observation(receipt.account_id,identity,receipt.operation_id,"active",owned)
    def _query(self,token,receipt):
        self._proof(receipt)
        result=self.http.session("GET","assign",token,params=self._params(receipt))
        if not isinstance(result,dict): raise ValueError("Assignment lookup is unavailable.")
        identity=result.get("endpoint")
        if identity is not None: return endpoint(identity)
        if result.get("nbh")!=notebook(receipt) or not isinstance(result.get("token"),str):
            raise ValueError("Assignment lookup is incomplete.")
        return None
    def _listed(self,token):
        result=self.http.session("GET","assignments",token)
        if not isinstance(result,dict) or not isinstance(result.get("assignments"),list): raise ValueError("Assignment listing is unavailable.")
        identities=[endpoint(row.get("endpoint")) for row in result["assignments"] if isinstance(row,dict)]
        if len(identities)!=len(result["assignments"]) or len(set(identities))!=len(identities): raise ValueError("Assignment listing is ambiguous.")
        return set(identities)
    def _observe(self,token,receipt):
        mapped=self._query(token,receipt); listed=self._listed(token)
        if receipt.resource_id in listed and mapped==receipt.resource_id:
            return Observation(receipt.account_id,receipt.resource_id,receipt.operation_id,"active",True)
        if receipt.resource_id not in listed and mapped is None:
            return Observation(receipt.account_id,receipt.resource_id,receipt.operation_id,"absent",False)
        return Observation(receipt.account_id,receipt.resource_id,receipt.operation_id,"unknown",False)
    def observe(self,connection,receipt):
        if not receipt.resource_id: raise ValueError("A known assignment is required for absence confirmation.")
        return self._observe(self._bound(connection,receipt),receipt)
    def reconcile(self,connection,receipt):
        token=self._bound(connection,receipt)
        identity=self._query(token,receipt)
        if identity is None: return Observation(receipt.account_id,None,receipt.operation_id,"unknown",False)
        try: present=identity in self._listed(token)
        except Exception: present=False
        return Observation(receipt.account_id,identity,receipt.operation_id,"active" if present else "unknown",present)
    def runtime_access(self,connection,receipt):
        # One account token snapshot and two provider ownership observations; no creation.
        receipt.validate()
        if (receipt.mode!="rental" or not receipt.resource_id or receipt.state not in {"allocating","active"}
                or receipt.cancel_requested or self.now()>=receipt.deadline):
            raise ValueError("An owned active rental is required for runtime access.")
        token=self._bound(connection,receipt)
        if self._query(token,receipt)!=receipt.resource_id:
            raise ValueError("Colab runtime ownership could not be verified.")
        result=self.http.session("GET","assignments",token)
        rows=result.get("assignments") if isinstance(result,dict) else None
        if not isinstance(rows,list) or len(rows)>1000:
            raise ValueError("Colab runtime ownership could not be verified.")
        identities=[endpoint(row.get("endpoint")) for row in rows if isinstance(row,dict)]
        if len(identities)!=len(rows) or len(set(identities))!=len(identities) or receipt.resource_id not in identities:
            raise ValueError("Colab runtime ownership could not be verified.")
        row=rows[identities.index(receipt.resource_id)]
        from .proxy import access
        return access(receipt.resource_id,row.get("runtimeProxyInfo"),self.now())

    def terminate(self,connection,receipt):
        if receipt.mode!="rental" or not receipt.resource_id: raise ValueError("An existing machine is never terminated by rental cleanup.")
        token=self._bound(connection,receipt)
        observed=self._observe(token,receipt)
        if observed.status=="absent": return
        if observed.status!="active" or not observed.owned: raise ValueError("Assignment ownership is uncertain. Nothing was deleted.")
        path="unassign/"+endpoint(receipt.resource_id)
        result=self.http.session("GET",path,token)
        if not isinstance(result,dict): raise ValueError("Shutdown authorization is unavailable.")
        self.http.session("POST",path,token,xsrf=bearer(result.get("token")))
        # Only a later same-account provider observation can establish off.
