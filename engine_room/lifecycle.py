"""Connector-neutral independent-controller allocation and deadline monitoring."""
from dataclasses import asdict,dataclass,replace
import hashlib
import json
import math
import threading
import time

from .billing import valid_scope,valid_unit
from .attachments import Attachments
from .persistent_storage import PersistentStorage
from .connections import Connections
from .model_server import command
from .protection import host_identity
from .private_endpoint import ModelEndpoint
from .records import DamagedRecord,Receipt,Store,atomic_json
from .recovery import Observation, Recovery
from .planning import offer_plan


@dataclass(frozen=True)
class Quote:
    account_id: str
    selection_key: str
    price: float | None
    unit: str
    balance: float | None
    observed_at: float
    available: bool | None
    storage_available_bytes: int | None
    install_bytes: int
    cost_details: dict | None = None
    rate_scope: str = "rental"
    balance_required: bool = True

    def validate(self, now):
        if (not valid_unit(self.unit) or not valid_scope(self.rate_scope) or type(self.balance_required) is not bool
                or self.available is False or type(self.available) not in (bool,type(None))):
            raise ValueError("This provider offer is unavailable or invalid.")
        if (type(self.install_bytes) is not int or self.install_bytes<0
                or (self.storage_available_bytes is not None and (type(self.storage_available_bytes) is not int or self.storage_available_bytes<0))):
            raise ValueError("The provider storage plan is invalid.")
        if self.storage_available_bytes is None and (not isinstance(self.cost_details,dict)
                or self.cost_details.get("storage_validation")!="before-installation"):
            raise ValueError("Unknown disk capacity requires explicit verification before installation.")
        if self.balance is not None and (type(self.balance) not in (int,float) or not math.isfinite(self.balance) or self.balance<0):
            raise ValueError("The reported provider balance is invalid.")
        for value in (self.observed_at,):
            if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                raise ValueError("The provider quote is incomplete.")
        if not 0 <= now-self.observed_at <= 120:
            raise ValueError("Refresh the provider quote before confirming a rental.")
        if self.price is not None and (type(self.price) not in (int,float) or not math.isfinite(self.price) or self.price<0):
            raise ValueError("The provider price is invalid.")
        if self.balance_required and (self.balance is None or self.balance<=0):
            raise ValueError("This connector requires a verified positive prepaid balance.")
        if self.cost_details is not None:
            stamp=self.cost_details.get("observed_at") if isinstance(self.cost_details,dict) else None
            if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<=120:
                raise ValueError("Refresh the separate storage price before confirming a rental.")
        return self

    def confirmation_key(self):
        # Age is verified separately. Price, currency, disk and account changes need review.
        details=None if self.cost_details is None else {k:v for k,v in self.cost_details.items() if k!="observed_at"}
        fields=(self.account_id,self.selection_key,self.price,self.unit,self.balance,self.available,self.storage_available_bytes,self.install_bytes,details,self.rate_scope,self.balance_required)
        return hashlib.sha256(json.dumps(fields,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Health:
    status: str
    observed_at: float
    progress: str = ""
    rate: float | None = None
    unit: str | None = None
    rate_scope: str = "rental"


def selection_key(selection):
    return hashlib.sha256(json.dumps(selection,sort_keys=True,allow_nan=False).encode()).hexdigest()


class Controller:
    """Runs on an enrolled host independent of the desktop, not on the rented GPU.

    Enrollment requires explicit host confirmation; matching/different machine IDs alone
    cannot prove physical power independence. SSH transport/service validation is also a
    release gate. Connectors must bound API requests and make allocation a single POST.
    """
    lease_seconds=120
    health_loss_seconds=90
    setup_stall_seconds=300
    setup_limit_seconds=2700

    def __init__(self,root,registry,enrollment, *, actual_host_id=None, now=time.time, monotonic=time.monotonic, interval=5):
        self.connections=Connections(root,registry)
        self.store=self.connections.receipts
        self.start_denials=Store(self.connections.root/"start-denials")
        self.request_journal=Store(self.connections.root/"request-journal")
        self.registry=registry
        self.enrollment=enrollment
        self.host_id=actual_host_id if actual_host_id is not None else host_identity()
        self.now=now
        self.monotonic=monotonic
        self.interval=interval
        self._stop=threading.Event()
        self._monitor=None
        self._workers={}
        self._cancels={}
        self._timing={}
        self._health={}
        self._tick_lock=threading.Lock()
        self._fault=False
        self._last_tick=None
        self._ownership_store=Store(self.connections.root / "controller-owner")
        self._ownership=None
        self.attachments=Attachments(self.connections,registry,enrollment,self.host_id,now=now)
        self.storage=PersistentStorage(self.connections,registry,enrollment,self.host_id,now=now)

    def _recovery(self):
        return Recovery(self.store,self.connections.read(),self.registry)

    def start(self):
        if self._monitor is not None:
            raise ValueError("The controller has already started.")
        self.enrollment.verify(self.host_id,self.enrollment.client_host_id)
        # A second daemon must not mistake a live controller's rental for abandoned work.
        ownership=self._ownership_store.allocation_lock(timeout=0)
        ownership.__enter__()
        self._ownership=ownership
        try:
            # Restart recovers outstanding rentals, rather than silently resuming paid work.
            self._recovery().recover()
            self.attachments.recover()
            self._last_tick=self.monotonic()
            self._monitor=threading.Thread(target=self._loop,name="engine-room-deadline-monitor",daemon=True)
            self._monitor.start()
        except Exception:
            self._ownership.__exit__(None,None,None)
            self._ownership=None
            raise

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:
                self._fault=True
                # Persisted receipts survive monitor/storage/provider errors. New allocation
                # is refused and a later tick retries cleanup; never report unverified off.

    def _protection(self,client_host_id):
        self.enrollment.verify(self.host_id,client_host_id)
        if (self._monitor is None or not self._monitor.is_alive() or self._stop.is_set()
                or self._fault or self._last_tick is None
                or self.monotonic()-self._last_tick>max(60,2*self.interval)):
            raise ValueError("Independent shutdown protection is not healthy. No rental was requested.")

    def request(self,operation_id,connection_id,selection,plan,approved_quote,rate_ceiling,duration_seconds,client_host_id):
        self._protection(client_host_id)
        if type(duration_seconds) is not int or duration_seconds<=0:
            raise ValueError("Choose a finite rental duration before starting.")
        if type(rate_ceiling) not in (int,float) or not math.isfinite(rate_ceiling) or rate_ceiling<=0:
            raise ValueError("Confirm a positive maximum hourly rate.")
        command(plan)  # Same launch validation used remotely, before any billable request.
        sizes=plan.get("fileSizes")
        if not isinstance(sizes,dict) or not sizes:
            raise ValueError("Published model download sizes are required before renting.")
        if plan.get("engine")=="llama.cpp":
            from .model_validation import gguf_files
            files,projector=gguf_files(plan)
            if set(sizes)!=set(files+([projector] if projector else [])):
                raise ValueError("Download sizes do not match the selected model files.")
        with self.store.allocation_lock():
            if self.store.path(operation_id).exists():
                old=self.store.load(operation_id)
                if old.connection_id!=connection_id:
                    raise ValueError("Operation identity belongs to another connection.")
                return old  # Retrying a lost desktop response never creates a second rental.
            if self.start_denials.path(operation_id).exists() or self.start_denials.path(operation_id).is_symlink():
                raise ValueError("This request was abandoned. Its operation identity cannot allocate again.")
            if any(not self.store.path(path.stem).exists() for path in self.request_journal.root.glob("*.json")):
                raise ValueError("Recover the interrupted request journal before allocating.")
            if self.store.blockers():
                raise ValueError("Recover outstanding operations before requesting another rental.")
            connection=self.connections.read()[connection_id]
            connector=self.registry[connection.connector_id]
            if "rental" not in connector.descriptor.modes:
                raise ValueError("This connector cannot rent machines.")
            if connector.account_identity(connection)!=connection.account_id:
                raise ValueError("The authenticated account differs from this connection.")
            fresh=connector.quote(connection,selection)
            if not isinstance(fresh,Quote) or not isinstance(approved_quote,Quote):
                raise ValueError("A verified provider quote is required.")
            fresh.validate(self.now()); approved_quote.validate(self.now())
            if (fresh.account_id!=connection.account_id or fresh.selection_key!=selection_key(selection)
                    or fresh.confirmation_key()!=approved_quote.confirmation_key()
                    or (fresh.price is not None and fresh.price>rate_ceiling)):
                raise ValueError("The provider offer changed. Review and confirm the fresh quote.")
            offer_plan(plan,fresh)
            self._protection(client_host_id)
            now=self.now()
            deadline=now+duration_seconds
            receipt=Receipt(operation_id,connection.id,connection.connector_id,connection.account_id,"rental","intent",now,
                deadline=deadline,protection_id=self.enrollment.controller_id,lease_expires_at=min(deadline,now+self.lease_seconds),
                rate_ceiling=rate_ceiling,rate_unit=fresh.unit,rate_scope=fresh.rate_scope,quote_key=fresh.confirmation_key(),cost_details=fresh.cost_details)
            atomic_json(self.request_journal.path(operation_id),dict(schema=1,receipt=asdict(receipt)))
            self.store.save(receipt)  # Durable before any provider allocation submission.
            self._timing[operation_id]={"deadline":self.monotonic()+duration_seconds,"lease":self.monotonic()+min(duration_seconds,self.lease_seconds)}
            cancel=threading.Event()
            self._cancels[operation_id]=cancel
            worker=threading.Thread(target=self._allocate,args=(receipt,connection,connector,selection,plan,cancel),
                name="engine-room-setup",daemon=True)
            self._workers[operation_id]=worker
            worker.start()
        return receipt

    def _allocate(self,receipt,connection,connector,selection,plan,cancel):
        try:
            with self.store.allocation_lock():
                receipt=self.store.load(receipt.operation_id)
                others=[r for r in self.store.blockers() if isinstance(r,DamagedRecord) or r.operation_id!=receipt.operation_id]
                if others or receipt.cancel_requested or self._expired(receipt) or self.start_denials.path(receipt.operation_id).exists():
                    self.store.save(replace(receipt,state="cancelled",cancel_requested=True))
                    return
                self._protection(self.enrollment.client_host_id)
                if connector.account_identity(connection)!=receipt.account_id:
                    raise ValueError("Account changed before allocation.")
                prepare=getattr(connector,"prepare",None)
                if callable(prepare):
                    prepare(connection,receipt,selection,plan)
                fresh=connector.quote(connection,selection)
                if (not isinstance(fresh,Quote) or fresh.validate(self.now()).confirmation_key()!=receipt.quote_key
                        or self._expired(receipt)):
                    raise ValueError("The final offer or rental deadline changed before allocation.")
                self._protection(self.enrollment.client_host_id)
                receipt=replace(receipt,state="allocating",allocation_submitted=True)
                self.store.save(receipt)
            observation=connector.allocate(connection,receipt,selection,submit_gate=self._submission_guard(receipt))
            Recovery._validate_observation(receipt,observation)
            if not observation.resource_id:
                raise ValueError("Allocation did not return a resource identity.")
            with self.store.allocation_lock():
                latest=self.store.load(receipt.operation_id)
                if latest.state=="off":
                    return
                if latest.resource_id and latest.resource_id!=observation.resource_id:
                    raise ValueError("Allocation identity conflicts with reconciliation.")
                receipt=replace(latest,resource_id=observation.resource_id,
                    state="active" if observation.status=="active" and observation.owned else "unresolved")
                self.store.save(receipt)
            if observation.status!="active" or not observation.owned:
                # Keep the returned identity before further I/O. A partial create response
                # must not lose a known candidate when the ownership recheck fails.
                confirmed=connector.observe(connection,receipt)
                Recovery._validate_observation(receipt,confirmed)
                if confirmed.status!="active" or not confirmed.owned:
                    raise ValueError("Allocation ownership remains uncertain.")
                with self.store.allocation_lock():
                    latest=self.store.load(receipt.operation_id)
                    if not latest.unresolved: return
                    receipt=replace(latest,state="active")
                    self.store.save(receipt)
            if receipt.cancel_requested or self._expired(receipt) or cancel.is_set():
                self.cancel(receipt.operation_id)
                return
            # The monitor runs separately even if setup/download hangs or the desktop dies.
            connector.setup(connection,receipt,plan,cancel)
        except Exception:
            try:
                with self.store.allocation_lock():
                    latest=self.store.load(receipt.operation_id)
                    if latest.unresolved:
                        state="unresolved" if latest.allocation_submitted or latest.resource_id else "cancelled"
                        self.store.save(replace(latest,state=state,cancel_requested=True))
                cancel.set()
                self._recovery().recover({receipt.operation_id})
            except Exception:
                self._fault=True

    def _submission_guard(self,receipt):
        committed=False
        def submit_gate():
            nonlocal committed
            with self.store.allocation_lock():
                if committed: raise ValueError("This operation already authorized one allocation request.")
                latest=self.store.load(receipt.operation_id)
                try:
                    if self.start_denials.path(receipt.operation_id).exists() or self.start_denials.path(receipt.operation_id).is_symlink():
                        raise ValueError("This request was abandoned before provider submission.")
                    if latest.resource_id or latest.state!="allocating" or latest.cancel_requested or self._expired(latest):
                        raise ValueError("The rental was stopped or changed before submission.")
                    if any(isinstance(r,DamagedRecord) or r.operation_id!=receipt.operation_id for r in self.store.blockers()):
                        raise ValueError("Another recovery record appeared before submission.")
                    self._protection(self.enrollment.client_host_id)
                except Exception:
                    if latest.resource_id is None:
                        # This worker has not authorized its POST. This deterministic
                        # refusal differs from a provider timeout after submission.
                        self.store.save(replace(latest,state="cancelled",cancel_requested=True,allocation_submitted=False))
                    raise
                committed=True
            # Authorization is the submission boundary. Never hold the recovery
            # lock over network I/O: a late provider result must stay recoverable.
        return submit_gate

    def _expired(self,receipt):
        now=self.now()
        timing=self._timing.get(receipt.operation_id)
        return (now>=receipt.deadline or now<receipt.created_at-5
                or (receipt.lease_expires_at is not None and now>=receipt.lease_expires_at)
                or (timing is not None and (self.monotonic()>=timing["deadline"] or self.monotonic()>=timing["lease"])))

    def heartbeat(self,operation_id,client_host_id):
        self._protection(client_host_id)
        with self.store.allocation_lock():
            receipt=self.store.load(operation_id)
            if not receipt.unresolved or receipt.cancel_requested or self._expired(receipt):
                raise ValueError("This operation cannot be extended. Recover it first.")
            self.store.save(replace(receipt,lease_expires_at=min(receipt.deadline,self.now()+self.lease_seconds)))
            self._timing[operation_id]["lease"]=min(self._timing[operation_id]["deadline"],self.monotonic()+self.lease_seconds)

    def model_scope(self,operation_id,client_host_id):
        receipt=self.store.load(operation_id)
        if receipt.mode=="attachment": return self.attachments.stream_scope(operation_id,client_host_id)
        return dict(endpoint=self.model_endpoint(operation_id,client_host_id).data())

    def model_endpoint(self,operation_id,client_host_id):
        self._protection(client_host_id)
        receipt=self.store.load(operation_id)
        if (receipt.mode!="rental" or receipt.state!="active" or receipt.cancel_requested or self._expired(receipt)):
            raise ValueError("This rental is not authorized for model access.")
        checked=self._health.get(operation_id,{})
        if not checked.get("ready") or not 0<=self.now()-checked.get("good",0)<=30:
            raise ValueError("A fresh verified model and provider health reading is required.")
        connection=self.connections.read()[receipt.connection_id]
        if connection.connector_id!=receipt.connector_id or connection.account_id!=receipt.account_id:
            raise ValueError("The original named connection and account are required.")
        connector=self.registry[receipt.connector_id]
        endpoint=getattr(connector,"model_endpoint",None)
        if not callable(endpoint): raise ValueError("This connector does not yet support private model access.")
        target=endpoint(connection,receipt)
        if not isinstance(target,ModelEndpoint): raise ValueError("The session requires a scoped private socket endpoint.")
        return target.validate(self.connections.root,receipt.operation_key(),receipt.resource_id)

    def abandon(self,operation_id,connection_id,client_host_id):
        self.enrollment.verify(self.host_id,client_host_id)
        path=self.start_denials.path(operation_id)
        self.store.path(connection_id)  # The same bounded identifier grammar.
        with self.store.allocation_lock():
            connection=self.connections.read().get(connection_id)
            if connection is None: raise ValueError("The original named connection is required.")
            expected=dict(schema=1,operation_id=operation_id,connection_id=connection_id,
                account_id=connection.account_id,connector_id=connection.connector_id,
                client_host_id=client_host_id,controller_id=self.enrollment.controller_id)
            if path.exists() or path.is_symlink():
                if path.is_symlink() or path.stat().st_size>8192 or json.loads(path.read_text())!=expected:
                    raise ValueError("The request denial belongs to another scope or is damaged.")
            journal=self.request_journal.path(operation_id)
            if not self.store.path(operation_id).exists() and (journal.exists() or journal.is_symlink()):
                if journal.is_symlink() or journal.stat().st_size>32768: raise ValueError("The request journal is damaged.")
                data=json.loads(journal.read_text())
                if not isinstance(data,dict) or set(data)!={"schema","receipt"} or data["schema"]!=1:
                    raise ValueError("The request journal is damaged.")
                recovered=Receipt(**data["receipt"]).validate()
                if (recovered.operation_id!=operation_id or recovered.connection_id!=connection_id
                        or recovered.account_id!=connection.account_id or recovered.connector_id!=connection.connector_id
                        or recovered.protection_id!=self.enrollment.controller_id or recovered.mode!="rental"):
                    raise ValueError("The original request journal scope is required.")
                self.store.save(replace(recovered,state="unresolved",allocation_submitted=True,cancel_requested=True))
            exists=self.store.path(operation_id).exists()
            if exists:
                receipt=self.store.load(operation_id)
                if (receipt.connection_id!=connection_id or receipt.account_id!=connection.account_id
                        or receipt.connector_id!=connection.connector_id or receipt.mode!="rental"
                        or receipt.protection_id!=self.enrollment.controller_id):
                    raise ValueError("The original managed rental is required.")
            atomic_json(path,expected)
        if exists:
            results=self.cancel(operation_id)
            return dict(operation_id=operation_id,connection_id=connection_id,future_start_forbidden=True,
                receipt_exists=True,recovery=[asdict(result) for result in results])
        return dict(operation_id=operation_id,connection_id=connection_id,future_start_forbidden=True,
            receipt_exists=False,recovery=[])

    def cancel(self,operation_id):
        with self.store.allocation_lock():
            receipt=self.store.load(operation_id)
            if receipt.mode!="rental":
                raise ValueError("Disconnect an attached machine without terminating it.")
            if not receipt.unresolved:
                return []
            self.store.save(replace(receipt,cancel_requested=True))
        if operation_id in self._cancels:
            self._cancels[operation_id].set()
        return self._recovery().recover({operation_id})

    def tick(self):
        with self._tick_lock:
            records=self.store.scan()
            current=self.connections.read()
            for receipt in records:
                if isinstance(receipt,DamagedRecord) or not receipt.unresolved:
                    continue
                stop=receipt.cancel_requested or self._expired(receipt) or self._fault
                if receipt.resource_id and not stop:
                    try:
                        connection=current[receipt.connection_id]
                        connector=self.registry[receipt.connector_id]
                        if connector.account_identity(connection)!=receipt.account_id:
                            raise ValueError("Provider account changed.")
                        health=connector.health(connection,receipt)
                        if (not isinstance(health,Health) or health.status not in {"starting","ready","failed","unknown"}
                                or type(health.observed_at) not in (int,float) or not math.isfinite(health.observed_at)
                                or not 0<=self.now()-health.observed_at<=30):
                            raise ValueError("The health reading is stale or invalid.")
                        if health.status=="failed":
                            stop=True  # Terminal failure cannot wait for a billing reading.
                        else:
                            if not valid_unit(health.unit) or not valid_scope(health.rate_scope):
                                raise ValueError("The provider billing unit or scope is not yet verified.")
                            if type(health.rate) not in (int,float) or not math.isfinite(health.rate) or health.rate<0:
                                raise ValueError("The actual provider rate is not yet verified.")
                            if (health.unit!=receipt.rate_unit or health.rate_scope!=receipt.rate_scope
                                    or health.rate>receipt.rate_ceiling):
                                stop=True
                        state=self._health.setdefault(receipt.operation_id,{"good":receipt.created_at,"progress_at":receipt.created_at,"progress":None,"ready":False})
                        state.update(last_status=health.status if not stop else "failed",sampled_at=health.observed_at)
                        if not stop and (health.status=="ready" or (health.status=="starting" and not state["ready"])):
                            state["good"]=self.now()
                        if health.status=="ready" and not stop: state["ready"]=True
                        if health.progress!=state["progress"]:
                            state["progress"]=health.progress; state["progress_at"]=self.now()
                        if health.status=="starting" and not state["ready"]:
                            stop=stop or self.now()-receipt.created_at>=self.setup_limit_seconds or self.now()-state["progress_at"]>=self.setup_stall_seconds
                        elif self.now()-state["good"]>=self.health_loss_seconds:
                            stop=True
                    except Exception:
                        state=self._health.setdefault(receipt.operation_id,{"good":receipt.created_at,"progress_at":receipt.created_at,"progress":None,"ready":False})
                        state.update(last_status="unknown",sampled_at=self.now())
                        stop=self.now()-state["good"]>=self.health_loss_seconds
                if stop:
                    self.cancel(receipt.operation_id)
            self._last_tick=self.monotonic()

    def close(self):
        self._stop.set()
        if self._ownership is None:
            return []  # Failed startup never authorizes cleanup of another live daemon.
        self.attachments.closed=True
        self.storage.closed=True
        for cancel in self._cancels.values(): cancel.set()
        results=self._recovery().recover()
        self.attachments.close()
        if self._monitor: self._monitor.join(timeout=2)
        if self._monitor and self._monitor.is_alive():
            raise RuntimeError("Controller monitoring is still stopping; recovery records are retained.")
        if self._ownership is not None:
            self._ownership.__exit__(None,None,None)
            self._ownership=None
        return results
