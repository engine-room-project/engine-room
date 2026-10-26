"""Durable storage-operation scope, separate from disposable rental shutdown receipts."""
from dataclasses import dataclass
import hashlib
import json
import math
import re


@dataclass(frozen=True)
class VolumeIntent:
    operation_id: str
    connection_id: str
    connector_id: str
    account_id: str
    size_gb: int
    data_center: str
    created_at: float
    nonce: str
    baseline_ids: tuple[str,...] = ()
    state: str = "intent"
    resource_id: str | None = None
    schema: int = 1
    storage_type: str = "STANDARD"

    def validate(self):
        for value in (self.operation_id,self.connection_id,self.connector_id):
            if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",value): raise ValueError("Invalid storage operation identity.")
        if not isinstance(self.account_id,str) or not 1<=len(self.account_id)<=200 or any(ord(c)<32 for c in self.account_id):
            raise ValueError("The original storage account is required.")
        if (type(self.size_gb) is not int or not 1<=self.size_gb<=4000 or not isinstance(self.data_center,str)
                or not re.fullmatch(r"[A-Z0-9-]{2,40}",self.data_center) or not isinstance(self.nonce,str) or not re.fullmatch(r"[a-f0-9]{32}",self.nonce)
                or type(self.created_at) not in (int,float) or not math.isfinite(self.created_at) or self.created_at<=0
                or type(self.schema) is not int or self.schema!=1 or self.state not in {"intent","submitting","known","unresolved"} or self.storage_type not in {"STANDARD","HIGH_PERFORMANCE"}):
            raise ValueError("Invalid durable storage intent.")
        if not isinstance(self.baseline_ids,tuple) or len(self.baseline_ids)>512:
            raise ValueError("A bounded original storage inventory is required.")
        for value in self.baseline_ids+((self.resource_id,) if self.resource_id is not None else ()):
            if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",value): raise ValueError("Invalid saved volume identity.")
        if len(set(self.baseline_ids))!=len(self.baseline_ids): raise ValueError("Duplicate baseline identities.")
        if self.state=="known" and self.resource_id is None: raise ValueError("Known storage requires a verified resource ID.")
        if self.resource_id is not None and self.resource_id in self.baseline_ids: raise ValueError("Existing unrelated storage cannot become a created resource.")
        return self
    def operation_key(self):
        self.validate()
        scope=(self.account_id,self.connection_id,self.operation_id,self.size_gb,self.data_center,self.created_at,self.nonce,self.storage_type)
        return hashlib.sha256(json.dumps(scope,separators=(",",":")).encode()).hexdigest()
    def marker(self): return "engine-room-storage-"+self.operation_key()[:32]


@dataclass(frozen=True)
class StorageQuote:
    account_id: str
    size_gb: int
    data_center: str
    storage_type: str
    monthly_usd: float
    observed_at: float
    source: str

    def validate(self,now=None):
        if (not isinstance(self.account_id,str) or not 1<=len(self.account_id)<=200 or any(ord(c)<32 for c in self.account_id)
                or type(self.size_gb) is not int or not 1<=self.size_gb<1000 or not isinstance(self.data_center,str)
                or not re.fullmatch(r"[A-Z0-9-]{2,40}",self.data_center) or self.storage_type!="STANDARD"
                or type(self.monthly_usd) not in (int,float) or not math.isfinite(self.monthly_usd) or self.monthly_usd<=0
                or type(self.observed_at) not in (int,float) or not math.isfinite(self.observed_at) or self.observed_at<=0
                or not isinstance(self.source,str) or not self.source.startswith("https://") or len(self.source)>1024
                or any(ord(c)<32 for c in self.source)):
            raise ValueError("A verified Standard-storage monthly quote is required.")
        if now is not None and not 0<=now-self.observed_at<=120: raise ValueError("Refresh storage pricing before approval.")
        return self
    def key(self):
        self.validate()
        return hashlib.sha256(json.dumps((self.account_id,self.size_gb,self.data_center,self.storage_type,float(self.monthly_usd),self.source),separators=(",",":")).encode()).hexdigest()
