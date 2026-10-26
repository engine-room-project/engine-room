"""RunPod account and positively owned-resource API, extracted from the development runtime."""
import hashlib
import json
import math
import re
import time
from urllib.parse import urlencode

from engine_room.provider_http import JsonHTTP,ProviderError
from engine_room.recovery import Observation


class RunPodAPI:
    def __init__(self,credentials,http=None,now=time.time):
        self.credentials=credentials
        self.http=http if http is not None else JsonHTTP()
        self.now=now

    def graphql(self,reference,query,variables=None,*,_credential=None):
        body={"query":query}
        if variables is not None: body["variables"]=variables
        result=self.http.request("POST","https://api.runpod.io/graphql",self.credentials.read(reference) if _credential is None else _credential,body)
        if not isinstance(result,dict) or result.get("errors") or not isinstance(result.get("data"),dict):
            raise ProviderError()
        return result["data"]

    def account(self,reference,*,_credential=None):
        account=self.graphql(reference,"query { myself { id clientBalance } }",_credential=_credential).get("myself")
        if not isinstance(account,dict) or not isinstance(account.get("id"),str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}",account["id"]):
            raise ValueError("The provider account identity could not be verified.")
        balance=account.get("clientBalance")
        if type(balance) not in (float,int) or not math.isfinite(balance) or balance<0:
            raise ValueError("The provider balance could not be verified.")
        return {"id":account["id"],"balance":balance,"observed_at":self.now()}

    def market(self,connection,*,cloud,disk_gb,data_center=None,minimum_cuda=None):
        """Fresh account-bound GPU offers. This rate is GPU-only, not a storage tariff."""
        if cloud not in {"SECURE","COMMUNITY"} or type(disk_gb) is not int or not 0<disk_gb<2**31:
            raise ValueError("Choose the cloud tier and a positive disk size explicitly.")
        if data_center is not None and (not isinstance(data_center,str) or not re.fullmatch(r"[A-Z0-9-]{2,40}",data_center)):
            raise ValueError("Invalid selected storage data center.")
        pricing={"gpuCount":1,"secureCloud":cloud=="SECURE","supportPublicIp":True,"totalDisk":disk_gb}
        if data_center is not None: pricing["dataCenterId"]=data_center
        if minimum_cuda is not None:
            if not isinstance(minimum_cuda,str) or not re.fullmatch(r"[0-9]+\.[0-9]+",minimum_cuda):
                raise ValueError("Invalid runtime CUDA requirement.")
            pricing["minCudaVersion"]=minimum_cuda
        key=self.credentials.read(connection.credential_ref)
        data=self.graphql(connection.credential_ref,
            "query Market($pricing: GpuLowestPriceInput!) { myself { id clientBalance } gpuTypes { id memoryInGb lowestPrice(input: $pricing) { stockStatus uninterruptablePrice } } }",
            {"pricing":pricing},_credential=key)
        account=data.get("myself")
        if not isinstance(account,dict) or account.get("id")!=connection.account_id:
            raise ValueError("The provider account differs from this connection.")
        balance=account.get("clientBalance")
        if type(balance) not in (int,float) or not math.isfinite(balance) or balance<0:
            raise ValueError("A fresh provider balance is required.")
        if not isinstance(data.get("gpuTypes"),list): raise ProviderError()
        offers=[]
        for gpu in data["gpuTypes"]:
            if not isinstance(gpu,dict): continue
            price=gpu.get("lowestPrice")
            if not isinstance(price,dict) or str(price.get("stockStatus","")).casefold() not in {"high","medium","low"}: continue
            rate=price.get("uninterruptablePrice"); memory=gpu.get("memoryInGb"); name=gpu.get("id")
            if (type(rate) not in (int,float) or not math.isfinite(rate) or rate<=0
                    or type(memory) not in (int,float) or not math.isfinite(memory) or memory<=0
                    or not isinstance(name,str) or not 1<=len(name)<=200 or any(ord(c)<32 for c in name)):
                continue
            offers.append({"gpu_id":name,"memory_gb":memory,"gpu_hourly_rate":rate,
                "unit":"USD","charge_scope":"gpu_only","stock":price["stockStatus"]})
        return {"account_id":connection.account_id,"balance":balance,"observed_at":self.now(),
            "cloud":cloud,"disk_gb":disk_gb,"data_center":data_center,"offers":offers}

    def verified_account(self,connection,*,_credential=None):
        account=self.account(connection.credential_ref,_credential=_credential)
        if account["id"]!=connection.account_id:
            raise ValueError("This credential belongs to another account. Preserve the original recovery records.")
        return account

    def _bound_credential(self,connection,receipt):
        if (connection.id!=receipt.connection_id or connection.account_id!=receipt.account_id
                or connection.connector_id!="runpod" or receipt.connector_id!="runpod"):
            raise ValueError("The original connection and provider account are required.")
        key=self.credentials.read(connection.credential_ref)
        self.verified_account(connection,_credential=key)
        return key

    def rest(self,reference,method,path,body=None,*,allow_missing=False,_credential=None):
        if not re.fullmatch(r"(?:pods|networkvolumes)(?:/[A-Za-z0-9_-]{1,100})?",path):
            raise ValueError("Invalid RunPod resource path.")
        return self.http.request(method,"https://rest.runpod.io/v1/"+path,self.credentials.read(reference) if _credential is None else _credential,body,allow_missing=allow_missing)

    def volume_rest(self,reference,method,resource_id=None,body=None,*,allow_missing=False,_credential=None,cursor=None):
        if method not in {"GET","POST"} or (resource_id is not None and (not isinstance(resource_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",resource_id))):
            raise ValueError("Unsupported storage API operation.")
        if method=="POST" and resource_id is not None: raise ValueError("Creation requires a new storage operation.")
        if cursor is not None and (method!="GET" or resource_id is not None or not isinstance(cursor,str) or not 1<=len(cursor)<=2048 or any(ord(c)<32 for c in cursor)):
            raise ValueError("Invalid bounded storage cursor.")
        path="https://api.runpod.io/v2/network-volumes"+("/"+resource_id if resource_id is not None else "")
        if method=="GET" and resource_id is None: path+="?"+urlencode(dict(limit=128,**({"cursor":cursor} if cursor is not None else {})))
        return self.http.request(method,path,self.credentials.read(reference) if _credential is None else _credential,body,allow_missing=allow_missing)

    @staticmethod
    def operation_name(receipt):
        data=json.dumps([receipt.account_id,receipt.connection_id,receipt.operation_id],separators=(",",":")).encode()
        return "engine-room-"+hashlib.sha256(data).hexdigest()[:32]

    @classmethod
    def markers(cls,receipt):
        return {"ENGINE_ROOM_OPERATION":receipt.operation_id,"ENGINE_ROOM_CONNECTION":receipt.connection_id,"ENGINE_ROOM_ACCOUNT":receipt.account_id}

    @classmethod
    def owned(cls,pod,receipt):
        if not isinstance(pod,dict) or pod.get("name")!=cls.operation_name(receipt): return False
        if receipt.resource_id and pod.get("id")!=receipt.resource_id: return False
        if not isinstance(pod.get("id"),str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",pod["id"]): return False
        if pod.get("volumeInGb",0)!=0: return False
        env=pod.get("env")
        return isinstance(env,dict) and all(env.get(k)==v for k,v in cls.markers(receipt).items())

    def observe(self,connection,receipt):
        key=self._bound_credential(connection,receipt)
        if not receipt.resource_id:
            raise ValueError("A known resource identity is required for absence confirmation.")
        pod=self.rest(connection.credential_ref,"GET","pods/"+receipt.resource_id,allow_missing=True,_credential=key)
        if pod is None:
            return Observation(receipt.account_id,receipt.resource_id,receipt.operation_id,"absent",False)
        return Observation(receipt.account_id,receipt.resource_id,receipt.operation_id,"active",self.owned(pod,receipt))

    def reconcile(self,connection,receipt):
        key=self._bound_credential(connection,receipt)
        pods=self.rest(connection.credential_ref,"GET","pods",_credential=key)
        if not isinstance(pods,list): raise ProviderError()
        matches=[p for p in pods if self.owned(p,receipt)]
        if len(matches)>1:
            raise ValueError("More than one owned resource matches this operation. Keep the record for manual reconciliation.")
        if not matches:
            # No match does not prove a delayed allocation cannot still appear.
            return Observation(receipt.account_id,None,receipt.operation_id,"unknown",False)
        return Observation(receipt.account_id,matches[0]["id"],receipt.operation_id,"active",True)

    def terminate(self,connection,receipt):
        key=self._bound_credential(connection,receipt)
        if receipt.mode!="rental" or not receipt.resource_id:
            raise ValueError("Only this operation's identified disposable rental may be terminated.")
        pod=self.rest(connection.credential_ref,"GET","pods/"+receipt.resource_id,allow_missing=True,_credential=key)
        if pod is None: return
        if not self.owned(pod,receipt):
            raise ValueError("Resource ownership or disposable storage changed. Nothing was deleted.")
        self.rest(connection.credential_ref,"DELETE","pods/"+receipt.resource_id,_credential=key)
        # The caller still needs a fresh same-account absence observation before off.

    def get_owned(self,connection,receipt):
        key=self._bound_credential(connection,receipt)
        if not receipt.resource_id: raise ValueError("Resource identity is required.")
        pod=self.rest(connection.credential_ref,"GET","pods/"+receipt.resource_id,allow_missing=True,_credential=key)
        if pod is None: return None
        if not self.owned(pod,receipt):
            raise ValueError("Resource ownership changed. Nothing was modified.")
        return pod

    def create(self,connection,receipt,payload,*,submit_gate):
        if (receipt.mode!="rental" or receipt.state!="allocating" or not receipt.allocation_submitted
                or not receipt.protection_id or receipt.deadline is None or self.now()>=receipt.deadline):
            raise ValueError("A protected, durably submitted rental operation is required.")
        receipt.validate()
        if (payload.get("name")!=self.operation_name(receipt) or payload.get("volumeInGb")!=0
                or payload.get("gpuCount")!=1 or payload.get("computeType")!="GPU"
                or payload.get("ports")!=["22/tcp"] or payload.get("interruptible") is not False
                or not re.fullmatch(r"[a-z0-9./_-]+@sha256:[a-f0-9]{64}",payload.get("imageName",""))
                or not isinstance(payload.get("env"),dict)
                or any(payload["env"].get(k)!=v for k,v in self.markers(receipt).items())):
            raise ValueError("The allocation payload differs from the owned disposable rental plan.")
        for name in payload["env"]:
            if name not in {*self.markers(receipt),"SESSION_SSH_PUB","SESSION_HOST_KEY","SESSION_SOURCE",
                            "SESSION_SOURCE_SHA256","ENGINE_ROOM_ENGINE","ENGINE_ROOM_WEIGHTS"}:
                raise ValueError("Unexpected allocation environment entry; credentials must not enter provider settings.")
        key=self._bound_credential(connection,receipt)
        submit_gate()
        pod=self.rest(connection.credential_ref,"POST","pods",payload,_credential=key)
        if not isinstance(pod,dict) or not isinstance(pod.get("id"),str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",pod["id"]):
            raise ValueError("Allocation response is uncertain. Reconcile before trying again.")
        return Observation(receipt.account_id,pod["id"],receipt.operation_id,"active",self.owned(pod,receipt))
