"""Owned rental kernel startup without shared CLI state or adopting existing kernels."""
import json
import re
import time
import datetime
import uuid

from engine_room.records import Store,atomic_json
from .http import ColabHTTP
from .proxy import ProxyAccess,access


KERNEL_ID=re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\Z")


def kernel_id(value):
    if not isinstance(value,str) or not KERNEL_ID.fullmatch(value):
        raise ValueError("The Colab kernel identity is invalid. Preserve the rental recovery record.")
    return value


class KernelHTTP:
    def __init__(self,http=None,now=time.time):
        self.http=http if http is not None else ColabHTTP(); self.now=now

    def request(self,lease,method,path,body=None):
        if not isinstance(lease,ProxyAccess): raise ValueError("Verified runtime access is required.")
        now=self.now(); lease.require_current(now)
        # Revalidate at use, including directly constructed or replaced lease objects.
        access(lease.resource_id,dict(url=lease.url,token=lease.token,tokenExpiresInSeconds=1),now)
        valid=(path=="/api/kernels" and method in {"GET","POST"})
        if not valid: raise ValueError("Unsupported Colab kernel operation.")
        if (method=="GET" and body is not None) or (method=="POST" and body!={"name":"python3"}):
            raise ValueError("Unsupported Colab kernel request.")
        data=None if body is None else json.dumps(body,allow_nan=False).encode()
        return self.http._send(method,lease.url.rstrip("/")+path,
            {"X-Colab-Runtime-Proxy-Token":lease.token,"X-Colab-Client-Agent":"colab-cli",
             "Content-Type":"application/json","Accept":"application/json"},data)


class KernelSession:
    def __init__(self,api,root,http=None,now=time.time):
        self.api=api; self.store=Store(root); self.http=http if http is not None else KernelHTTP(now=now); self.now=now

    @staticmethod
    def allowed(receipt,now):
        receipt.validate()
        if (receipt.mode!="rental" or receipt.connector_id!="colab" or not receipt.resource_id
                or receipt.state not in {"allocating","active"} or receipt.cancel_requested
                or not receipt.protection_id or now>=receipt.deadline):
            raise ValueError("An authorized ongoing Colab rental is required for kernel startup.")

    def start(self,connection,receipt,*,authorize):
        self.allowed(receipt,self.now())
        lease=self.api.runtime_access(connection,receipt)
        if lease.resource_id!=receipt.resource_id: raise ValueError("The runtime differs from the selected rental.")
        with self.store.allocation_lock():
            path=self.store.path(receipt.operation_id)
            if path.exists():
                raise ValueError("Kernel startup was already attempted. Recover the rental without repeating it.")
            baseline=self.http.request(lease,"GET","/api/kernels")
            if not isinstance(baseline,list) or len(baseline)>1000:
                raise ValueError("The existing Colab kernels could not be verified.")
            ids=[kernel_id(row.get("id")) for row in baseline if isinstance(row,dict)]
            if len(ids)!=len(baseline) or len(set(ids))!=len(ids):
                raise ValueError("The existing Colab kernels are ambiguous.")
            self.allowed(receipt,self.now()); lease.require_current(self.now())
            proof=dict(operation_key=receipt.operation_key(),resource_id=receipt.resource_id,
                account_id=receipt.account_id,connection_id=receipt.connection_id,
                state="submitted",kernel_id=None,submitted_at=self.now())
            atomic_json(path,proof)
            try: authorize()
            except Exception:
                atomic_json(path,{**proof,"state":"cancelled"})
                raise
            # A timeout leaves submitted state; no second kernel POST is authorized.
            result=self.http.request(lease,"POST","/api/kernels",{"name":"python3"})
            identity=kernel_id(result.get("id") if isinstance(result,dict) else None)
            if identity in ids:
                atomic_json(path,{**proof,"state":"unresolved","candidate_kernel_id":identity})
                raise ValueError("The provider returned a pre-existing kernel. It was not adopted or changed.")
            atomic_json(path,{**proof,"state":"ready","kernel_id":identity})
            return identity

    def execute(self,connection,receipt,code,*,authorize,cancel,timeout=60,channel_factory=None):
        """Bootstrap code only: callers must not embed account/model credentials in code."""
        if not isinstance(code,str) or not code or len(code.encode())>262144:
            raise ValueError("Use bounded runtime bootstrap code.")
        self.allowed(receipt,self.now())
        if cancel.is_set(): raise ValueError("Runtime setup was stopped.")
        with self.store.allocation_lock():
            path=self.store.path(receipt.operation_id)
            if path.is_symlink() or path.stat().st_size>8192: raise ValueError("Kernel proof is invalid.")
            proof=json.loads(path.read_text(encoding="utf-8"))
            expected=dict(operation_key=receipt.operation_key(),resource_id=receipt.resource_id,
                account_id=receipt.account_id,connection_id=receipt.connection_id,state="ready")
            if not isinstance(proof,dict) or any(proof.get(k)!=v for k,v in expected.items()):
                raise ValueError("The owned kernel proof is missing, busy or uncertain. Recover the rental.")
            identity=kernel_id(proof.get("kernel_id"))
            lease=self.api.runtime_access(connection,receipt)
            if lease.resource_id!=receipt.resource_id: raise ValueError("Runtime identity changed.")
            message_id=uuid.uuid4().hex; session_id=uuid.uuid4().hex
            message=dict(header=dict(msg_id=message_id,username="engine-room",session=session_id,
                date=datetime.datetime.now(datetime.timezone.utc).isoformat(),msg_type="execute_request",version="5.3"),
                parent_header={},metadata={},channel="shell",buffers=[],
                content=dict(code=code,silent=False,store_history=False,user_expressions={},allow_stdin=False,stop_on_error=True))
            if channel_factory is None:
                from .channel import connect
                channel_factory=connect
            # A failed/uncertain execution must not replay destructive bootstrap steps.
            active={**proof,"state":"executing","message_id":message_id}
            atomic_json(path,active)
            output=[]; size=0; reply=False; idle=False
            try:
                with channel_factory(lease,identity,session_id,cancel=cancel,timeout=timeout,now=self.now) as channel:
                    self.allowed(receipt,self.now())
                    if cancel.is_set(): raise ValueError("Runtime setup was stopped.")
                    authorize(); channel.send(message)
                    for _ in range(4096):
                        result=channel.receive()
                        if result.get("parent_header",{}).get("msg_id")!=message_id: continue
                        kind=result.get("header",{}).get("msg_type"); content=result.get("content",{})
                        if not isinstance(content,dict): raise ValueError("Invalid kernel reply.")
                        if kind=="execute_reply":
                            if content.get("status")!="ok": raise RuntimeError("Runtime bootstrap failed.")
                            reply=True
                        elif kind=="status" and content.get("execution_state")=="idle": idle=True
                        elif kind=="stream":
                            text=content.get("text")
                            if not isinstance(text,str): raise ValueError("Invalid kernel output.")
                            size+=len(text.encode())
                            if size>65536: raise RuntimeError("Runtime bootstrap output exceeds its transfer limit.")
                            output.append(text)
                        elif kind in {"error","input_request"}: raise RuntimeError("Runtime bootstrap failed or requested input.")
                        if reply and idle:
                            atomic_json(path,proof)
                            return "".join(output)
                    raise RuntimeError("Runtime bootstrap did not finish within its message limit.")
            except Exception:
                # Leave executing proof for recovery; timeout is not proof code stopped.
                raise RuntimeError("Colab bootstrap did not complete with confirmation. Recover the rental; code may still be running.") from None
