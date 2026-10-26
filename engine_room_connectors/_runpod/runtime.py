"""RunPod disposable-container payload, pinned SSH and credential-before-start setup."""
import base64
import json
import math
import os
from pathlib import Path
import re
import shlex
import time

from engine_room.model_metadata import ModelMetadata
from engine_room.payload import bootstrap_script,runtime_profile,source_payload
from engine_room.private_endpoint import EndpointHTTP,address,private_parents
from engine_room.records import atomic_json
from engine_room.ssh import PinnedSSH
from .api import RunPodAPI


class Runtime:
    def __init__(self,root,credentials,*,forward_root=None,ssh_factory=PinnedSSH,metadata=None,now=time.time):
        self.root=Path(root); self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.forward_root=Path(forward_root or self.root/"s").absolute()
        self.forward_root.mkdir(mode=0o700,parents=True,exist_ok=True)
        address(self.forward_root/"m.sock",self.forward_root)
        if os.name=="posix": private_parents(self.forward_root/"m.sock",self.forward_root)
        self.credentials=credentials; self.ssh_factory=ssh_factory
        self.metadata=metadata if metadata is not None else ModelMetadata(credentials)
        self.now=now; self.sessions={}

    def directory(self,receipt):
        receipt.validate()
        return self.root/receipt.operation_id

    def forward_directory(self,receipt):
        return self.forward_root/receipt.operation_key()[:16]

    def prepare(self,connection,receipt,selection,plan):
        if selection["engine"]!=plan["engine"]: raise ValueError("The selected runtime differs from the checked model.")
        self.metadata.verify(plan,connection.settings.get("hf_credential_ref"))
        profile=runtime_profile(plan["engine"])
        fields=[plan.get("weightBytes"),plan.get("overheadBytes"),plan.get("kvBytesPerToken")]
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in fields):
            raise ValueError("The checked model memory plan is incomplete. Check the model again before renting.")
        required_gpu=fields[0]+fields[1]+fields[2]*plan["context"]
        payload=source_payload(plan)
        if len(payload["base64"])>100000:
            raise ValueError("The inspected runtime payload exceeds the provider environment limit.")
        directory=self.directory(receipt)
        forward_directory=self.forward_directory(receipt)
        address(forward_directory/"m.sock",self.forward_root); address(forward_directory/"s.sock",self.forward_root)
        directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        ssh=self.ssh_factory(directory,forward_directory=forward_directory)
        keys=ssh.generate()
        env={**RunPodAPI.markers(receipt),"SESSION_SSH_PUB":keys["public_key"],
             "SESSION_HOST_KEY":keys["host_private_b64"],"SESSION_SOURCE":payload["base64"],
             "SESSION_SOURCE_SHA256":payload["sha256"],"ENGINE_ROOM_ENGINE":plan["engine"]}
        if selection.get("volume_id"):
            # Cache directories are model/revision specific. Never overwrite another model's files.
            env["ENGINE_ROOM_WEIGHTS"]="/workspace/engine-room/"+plan["id"].replace("/","--")+"/"+plan["revision"]
        body={"name":RunPodAPI.operation_name(receipt),"imageName":profile["image"],"cloudType":selection["cloud"],
            "computeType":"GPU","gpuCount":1,"gpuTypeIds":[selection["gpu_id"]],"gpuTypePriority":"custom",
            "containerDiskInGb":selection["disk_gb"],"volumeInGb":0,"ports":["22/tcp"],
            "globalNetworking":False,"supportPublicIp":True,"interruptible":False,
            "minRAMPerGPU":32,"minVCPUPerGPU":4,"dockerEntrypoint":["/bin/bash","-lc"],
            "dockerStartCmd":[bootstrap_script()],"env":env}
        if selection.get("volume_id"):
            body.update(networkVolumeId=selection["volume_id"],dataCenterIds=[selection["data_center"]],volumeMountPath="/workspace")
        # Contains generated operation SSH keys/source, never account/HF credentials. Private state only.
        atomic_json(directory/"request.json",body)
        atomic_json(directory/"runtime.json",{"engine":plan["engine"],"minimum_cuda":profile["minimum_cuda"],
            "source_sha256":payload["sha256"],"account_id":receipt.account_id,"connection_id":receipt.connection_id,
            "required_gpu_bytes":required_gpu,"gpu_id":selection["gpu_id"]})
        self.sessions[receipt.operation_id]=ssh

    def payload(self,receipt):
        body=json.loads((self.directory(receipt)/"request.json").read_text(encoding="utf-8"))
        if body.get("name")!=RunPodAPI.operation_name(receipt): raise ValueError("Operation payload identity changed.")
        return body

    def session(self,receipt):
        if receipt.operation_id not in self.sessions:
            self.sessions[receipt.operation_id]=self.ssh_factory(self.directory(receipt),forward_directory=self.forward_directory(receipt))
        return self.sessions[receipt.operation_id]

    def connect(self,pod,receipt):
        host=pod.get("publicIp"); port=(pod.get("portMappings") or {}).get("22")
        if not host or port is None: return None
        if isinstance(port,str) and port.isdigit(): port=int(port)
        ssh=self.session(receipt); ssh.endpoint(host,port)
        return ssh

    def setup(self,connection,receipt,plan,cancel,api):
        deadline=min(receipt.deadline,receipt.created_at+600)
        ssh=None
        while self.now()<deadline and not cancel.is_set():
            pod=api.get_owned(connection,receipt)
            if pod is None: raise RuntimeError("The rental is absent during setup.")
            if pod.get("desiredStatus") in {"EXITED","TERMINATED"}: raise RuntimeError("The rental stopped during setup.")
            try:
                ssh=self.connect(pod,receipt)
                if ssh and ssh.run("test -f /opt/engine-room/runtime-ready && printf READY",timeout=12)==b"READY": break
            except RuntimeError: pass
            cancel.wait(2)
        else: raise RuntimeError("Pinned runtime setup did not finish before its deadline.")
        minimum=runtime_profile(plan["engine"])["minimum_cuda"]
        output=ssh.run("nvidia-smi",timeout=10).decode("utf-8",errors="replace")
        match=re.search(r"CUDA Version:\s*([0-9]+)\.([0-9]+)",output)
        if not match or tuple(map(int,match.groups()))<tuple(map(int,minimum.split("."))):
            raise RuntimeError("This host's GPU driver does not meet the pinned runtime requirement.")
        memory=ssh.run("nvidia-smi --query-gpu=memory.total,compute_cap --format=csv,noheader,nounits",timeout=10).decode().strip().splitlines()
        if len(memory)!=1: raise RuntimeError("The rental did not report exactly one GPU.")
        values=memory[0].split(",")
        if len(values)!=2: raise RuntimeError("GPU capacity could not be verified.")
        available,capability=map(float,values)
        recorded=json.loads((self.directory(receipt)/"runtime.json").read_text(encoding="utf-8"))
        if (not math.isfinite(available) or available<=0 or not math.isfinite(capability)
                or recorded["required_gpu_bytes"]>available*1024**2*0.92
                or (plan.get("dtype")=="bfloat16" and capability<8.0)):
            raise RuntimeError("The actual GPU cannot support the checked model memory/precision plan.")
        if cancel.is_set(): raise RuntimeError("Setup was cancelled before model start.")
        reference=connection.settings.get("hf_credential_ref")
        if reference:
            secret=self.credentials.read(reference)
            try: ssh.run("umask 077; cat > /opt/engine-room/.hfkey",data=secret.encode(),timeout=15)
            finally: secret=""
        if cancel.is_set(): raise RuntimeError("Setup was cancelled before model start.")
        ssh.run("cd /opt/engine-room && PYTHONPATH=/opt/engine-room ENGINE_ROOM_ROOT=/opt/engine-room nohup $(cat /opt/engine-room/python-path) -m engine_room.remote_agent >/dev/null 2>&1 </dev/null &",timeout=15)
        if cancel.is_set(): raise RuntimeError("Setup was cancelled before private forwarding.")
        ssh.forward(receipt)

    def status(self,receipt):
        ssh=self.sessions.get(receipt.operation_id)
        if ssh is None or ssh.tunnel is None:
            phase="runtime-setup"
            if ssh is not None and getattr(ssh,"host",None):
                try: phase=ssh.run("head -c 2048 /opt/engine-room/phase",timeout=10).decode("utf-8",errors="replace").strip()
                except RuntimeError: pass
            return {"status":"failed" if "failed" in phase.casefold() else "starting","progress":phase,"sampled_at":self.now()}
        if ssh.tunnel.poll() is not None:
            return {"status":"failed","progress":"private-tunnel-exited","sampled_at":self.now()}
        endpoint=ssh.forward_endpoint("status",receipt)
        data=EndpointHTTP(endpoint,self.forward_root,receipt.operation_key(),timeout=5).json()
        if not isinstance(data,dict) or data.get("status") not in {"starting","ready","failed"}:
            raise ValueError("Remote status is invalid.")
        return data

    def model_endpoint(self,receipt):
        ssh=self.sessions.get(receipt.operation_id)
        if (ssh is None or ssh.tunnel is None or ssh.tunnel.poll() is not None
                or self.status(receipt).get("status")!="ready"):
            raise ValueError("This session's private model connection is not ready.")
        return ssh.forward_endpoint("model",receipt)

    def close(self,receipt,*,discard=False):
        ssh=self.sessions.get(receipt.operation_id)
        if ssh is None: ssh=self.ssh_factory(self.directory(receipt),forward_directory=self.forward_directory(receipt))
        if discard:
            ssh.discard_keys(receipt)
            (self.directory(receipt)/"request.json").unlink(missing_ok=True)
        else: ssh.close(receipt)
        self.sessions.pop(receipt.operation_id,None)
