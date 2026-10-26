"""Optional RunPod connector: account-bound disposable rentals through an independent controller."""
import math
from decimal import Decimal
import os
from pathlib import Path
import re
import shutil
import time

from engine_room.connectors import Descriptor
from engine_room.credentials import Credentials
from engine_room.forms import field,model_fields,connection_form,validate
from engine_room.lifecycle import Health,Quote,selection_key
from engine_room.paths import state_root
from engine_room.payload import runtime_profile
from ._runpod.api import RunPodAPI
from ._runpod.pricing import StoragePrices
from ._runpod.runtime import Runtime
from ._runpod.volumes import Volumes
from engine_room.volume_records import StorageQuote


class RunPodConnector:
    descriptor=Descriptor("runpod","RunPod","An explicitly saved RunPod API key",("rental",),capabilities=("persistent_storage",))

    def __init__(self,root,*,credentials=None,api=None,runtime=None,prices=None,now=time.time):
        self.root=Path(root); self.now=now
        self.credentials=credentials if credentials is not None else Credentials(self.root/"credentials")
        self.api=api if api is not None else RunPodAPI(self.credentials,now=now)
        self.runtime=runtime if runtime is not None else Runtime(self.root/"runpod-operations",self.credentials,forward_root=self.root/"s",now=now)
        self.prices=prices if prices is not None else StoragePrices(now=now)
        self.volumes=Volumes(self.api)

    def form(self,purpose,connection=None,values=None):
        if purpose=="connection": return connection_form()
        if purpose=="storage" and connection is not None:
            return validate(dict(schema=1,fields=[
                field("size_gb","Saved storage size (GB)","integer",minimum=1,maximum=999),
                field("data_center","Storage data center ID","text"),
                field("storage_type","Storage tier","choice",choices=[("STANDARD","Standard")])],
                help="Choose Standard storage below 1 TB in an explicit data center. Storage charges continue after rentals stop. Review a fresh monthly estimate before creation; removal is manual in the provider account."))
        if purpose!="selection" or connection is None: raise ValueError("Choose a named connection first.")
        values={} if values is None else values
        choices=[]
        if all(name in values for name in ("engine","cloud","disk_gb")):
            partial={k:v for k,v in values.items() if k in {"engine","cloud","disk_gb","volume_id","data_center"}}
            self.selection({**partial,"gpu_id":"pending-choice"})
            profile=runtime_profile(values["engine"])
            market=self.api.market(connection,cloud=values["cloud"],disk_gb=values["disk_gb"],
                data_center=values.get("data_center"),minimum_cuda=profile["minimum_cuda"])
            choices=[(offer["gpu_id"],offer["gpu_id"]) for offer in market["offers"]]
        return validate(dict(schema=1,fields=model_fields()+[
            field("cloud","Cloud tier","choice",choices=[("SECURE","Secure"),("COMMUNITY","Community")]),
            field("disk_gb","Disposable disk size (GB)","integer",minimum=1,maximum=2**31-1),
            field("volume_id","Existing saved volume ID (optional)","text",required=False),
            field("data_center","Saved volume data center (optional)","text",required=False),
            field("gpu_id","Available GPU offer","choice",choices=choices)],
            help="Choose runtime, cloud tier and disk size, then refresh GPU offers. Saved volume and data center must be selected together. Storage is billed separately; the final quote rechecks price and availability."))

    def preflight(self,credential_ref,settings):
        if os.name!="posix": raise ValueError("Configure RunPod on the independently hosted Linux controller.")
        if not shutil.which("ssh") or not shutil.which("ssh-keygen"):
            raise ValueError("Install OpenSSH client tools on the controller before connecting RunPod.")
        if not isinstance(settings,dict) or set(settings)-{"hf_credential_ref"}:
            raise ValueError("Unrecognized RunPod connection settings.")
        if settings.get("hf_credential_ref") and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",settings["hf_credential_ref"]):
            raise ValueError("Choose an explicit saved model credential reference.")
        return {"account_id":self.api.account(credential_ref)["id"],"settings":dict(settings)}

    def account_identity(self,connection):
        return self.api.verified_account(connection)["id"]

    @staticmethod
    def selection(selection):
        required={"gpu_id","cloud","disk_gb","engine"}
        if not isinstance(selection,dict) or not required.issubset(selection) or set(selection)-required-{"volume_id","data_center"}:
            raise ValueError("Choose an explicit GPU, cloud tier, runtime and disk size.")
        if (not isinstance(selection["gpu_id"],str) or not 1<=len(selection["gpu_id"])<=200
                or any(ord(c)<32 for c in selection["gpu_id"]) or selection["cloud"] not in {"SECURE","COMMUNITY"}
                or type(selection["disk_gb"]) is not int or not 0<selection["disk_gb"]<2**31):
            raise ValueError("Invalid GPU, cloud or disk selection.")
        runtime_profile(selection["engine"])
        volume=selection.get("volume_id"); place=selection.get("data_center")
        if bool(volume)!=bool(place) or (volume and (selection["cloud"]!="SECURE" or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",volume)
                or not re.fullmatch(r"[A-Z0-9-]{2,40}",place))):
            raise ValueError("Saved storage requires an explicit Secure-cloud volume and its data center.")
        return selection

    def quote(self,connection,selection):
        self.selection(selection)
        profile=runtime_profile(selection["engine"])
        market=self.api.market(connection,cloud=selection["cloud"],disk_gb=selection["disk_gb"],
            data_center=selection.get("data_center"),minimum_cuda=profile["minimum_cuda"])
        offers=[o for o in market["offers"] if o["gpu_id"]==selection["gpu_id"]]
        if len(offers)!=1: raise ValueError("That GPU has no verified current offer for this cloud, disk and runtime.")
        memory=offers[0].get("memory_gb")
        if type(memory) not in (int,float) or not math.isfinite(memory) or memory<=0:
            raise ValueError("The provider did not verify the offered GPU memory.")
        tariffs=self.prices.read()
        details={"gpu_memory_bytes":int(memory*1024**3),"gpu_validation":"before-installation","rate_scope":"GPU hourly rate plus separately billed storage","container_disk_gb":selection["disk_gb"],
            "container_usd_per_gb_month":tariffs["container_usd_per_gb_month"],"storage_source":tariffs["source"],
            "observed_at":tariffs["observed_at"],"runtime_validation":profile["validation"]}
        if selection.get("volume_id"):
            # No volume free-space credit. Its identity is selected explicitly and never auto-deleted.
            key=self.credentials.read(connection.credential_ref)
            self.api.verified_account(connection,_credential=key)
            volume=self.api.volume_rest(connection.credential_ref,"GET",selection["volume_id"],_credential=key)
            if not isinstance(volume,dict) or volume.get("id")!=selection["volume_id"] or volume.get("dataCenter")!=selection["data_center"]:
                raise ValueError("The selected saved storage could not be verified in this account and data center.")
            if volume.get("type")!="STANDARD":
                raise ValueError("Choose verified Standard storage. Premium or unknown storage-tier prices are not supported by this quote.")
            size=volume.get("size")
            if type(size) is not int or not 0<size<1000:
                raise ValueError("This saved-storage size needs a separately verified pricing tier.")
            details.update(network_volume_id=volume["id"],network_volume_gb=size,
                network_usd_per_gb_month=tariffs["network_usd_per_gb_month_under_1tb"],network_storage_persists=True,network_storage_type="STANDARD")
        return Quote(connection.account_id,selection_key(selection),offers[0]["gpu_hourly_rate"],"USD",market["balance"],
            market["observed_at"],True,selection["disk_gb"]*10**9,profile["installation_reserve_bytes"],details)

    def storage_quote(self,connection,selection):
        if (not isinstance(selection,dict) or set(selection)!={"size_gb","data_center","storage_type"}
                or type(selection["size_gb"]) is not int or not 1<=selection["size_gb"]<1000 or selection["storage_type"]!="STANDARD"
                or not isinstance(selection["data_center"],str) or not re.fullmatch(r"[A-Z0-9-]{2,40}",selection["data_center"])):
            raise ValueError("Choose an explicit Standard volume below 1 TB and its data center.")
        self.api.verified_account(connection)
        rates=self.prices.read()
        return StorageQuote(connection.account_id,selection["size_gb"],selection["data_center"],selection["storage_type"],
            float(Decimal(selection["size_gb"])*Decimal(str(rates["network_usd_per_gb_month_under_1tb"]))),rates["observed_at"],rates["source"]).validate(self.now())
    def storage_inventory(self,connection): return self.volumes.inventory(connection)
    def storage_create(self,connection,intent,*,submit_gate): return self.volumes.create(connection,intent,submit_gate=submit_gate)
    def storage_reconcile(self,connection,intent): return self.volumes.reconcile(connection,intent)
    def storage_identify(self,connection,intent,resource_id,*,confirmed): return self.volumes.confirm_manual(connection,intent,resource_id,confirmed=confirmed)

    def prepare(self,connection,receipt,selection,plan):
        self.selection(selection)
        self.runtime.prepare(connection,receipt,selection,plan)

    def allocate(self,connection,receipt,selection,*,submit_gate):
        self.selection(selection)
        payload=self.runtime.payload(receipt)
        if (payload.get("gpuTypeIds")!=[selection["gpu_id"]] or payload.get("containerDiskInGb")!=selection["disk_gb"]
                or payload.get("cloudType")!=selection["cloud"] or payload.get("networkVolumeId")!=selection.get("volume_id")):
            raise ValueError("Prepared allocation differs from the confirmed selection.")
        return self.api.create(connection,receipt,payload,submit_gate=submit_gate)

    def setup(self,connection,receipt,plan,cancel):
        return self.runtime.setup(connection,receipt,plan,cancel,self.api)

    def observe(self,connection,receipt):
        observed=self.api.observe(connection,receipt)
        if observed.status=="absent": self.runtime.close(receipt,discard=True)
        return observed

    def reconcile(self,connection,receipt):
        return self.api.reconcile(connection,receipt)

    def terminate(self,connection,receipt):
        self.api.terminate(connection,receipt)
        self.runtime.close(receipt)

    def health(self,connection,receipt):
        pod=self.api.get_owned(connection,receipt)
        if pod is None or pod.get("desiredStatus") in {"EXITED","TERMINATED"}:
            return Health("failed",self.now(),"provider-stopped",None,"USD")
        value=pod.get("costPerHr")
        try:
            if isinstance(value,bool): raise ValueError("Invalid rate")
            rate=float(value)
            if not math.isfinite(rate) or rate<0: rate=None
        except (ValueError,TypeError): rate=None
        try:
            status=self.runtime.status(receipt)
            return Health(status["status"],status["sampled_at"],status.get("progress",""),rate,"USD")
        except Exception:
            return Health("unknown",self.now(),"private-status-unavailable",rate,"USD")

    def model_endpoint(self,connection,receipt):
        if (connection.id!=receipt.connection_id or connection.account_id!=receipt.account_id
                or receipt.connector_id!=self.descriptor.id):
            raise ValueError("The original session identity is required.")
        return self.runtime.model_endpoint(receipt)

    def disconnect(self,connection,receipt):
        if receipt.mode!="attachment": raise ValueError("Managed rentals require verified termination.")
        self.runtime.close(receipt)


def create_connector():
    return RunPodConnector(state_root())
