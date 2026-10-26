from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from engine_room.connectors import Descriptor, Registry
from engine_room.lifecycle import Controller, Health, Quote, selection_key
from engine_room.protection import Enrollment
from engine_room.recovery import Observation
from test_records import rental


class Clock:
    def __init__(self): self.value=1000.0
    def __call__(self): return self.value
    def advance(self,seconds): self.value+=seconds


class Provider:
    descriptor=Descriptor("test","Synthetic provider","Explicit synthetic credential")
    def __init__(self,clock):
        self.clock=clock; self.account="synthetic-account"; self.resources={}; self.allocations=0; self.deletions=[]
        self.allocation_entered=threading.Event(); self.allocation_release=threading.Event(); self.allocation_release.set()
        self.setup_entered=threading.Event(); self.setup_release=threading.Event(); self.setup_release.set()
        self.health_status="ready"; self.progress="phase1"; self.rate=1.0; self.fail_setup=False; self.keep_after_delete=False
        self.quote_price=1.0; self.free_bytes=10**12; self.store=None
        self.unit="USD"; self.rate_scope="rental"; self.balance=10; self.balance_required=True
    def preflight(self,credential,settings): return {"account_id":self.account,"settings":{}}
    def account_identity(self,connection): return self.account
    def quote(self,connection,selection):
        return Quote(self.account,selection_key(selection),self.quote_price,self.unit,self.balance,self.clock(),True,self.free_bytes,10**9,dict(observed_at=self.clock(),gpu_memory_bytes=80*1024**3),rate_scope=self.rate_scope,balance_required=self.balance_required)
    def allocate(self,connection,receipt,selection,*,submit_gate):
        submit_gate()
        durable=self.store.load(receipt.operation_id)
        assert durable.allocation_submitted and durable.state=="allocating"
        self.allocations+=1; self.allocation_entered.set()
        if not self.allocation_release.wait(3): raise RuntimeError("Synthetic allocation fixture not released")
        pod="pod-"+receipt.operation_id
        self.resources[pod]=receipt.operation_id
        return Observation(self.account,pod,receipt.operation_id,"active",True)
    def setup(self,connection,receipt,plan,cancel):
        self.setup_entered.set()
        if not self.setup_release.wait(3): raise RuntimeError("Synthetic setup fixture not released")
        if self.fail_setup: raise RuntimeError("synthetic-sensitive-setup-error")
    def observe(self,connection,receipt):
        owned=self.resources.get(receipt.resource_id)==receipt.operation_id
        return Observation(self.account,receipt.resource_id,receipt.operation_id,"active" if owned else "absent",owned)
    def reconcile(self,connection,receipt):
        for pod,operation in list(self.resources.items()):
            if operation==receipt.operation_id: return Observation(self.account,pod,operation,"active",True)
        return Observation(self.account,None,receipt.operation_id,"unknown",False)
    def terminate(self,connection,receipt):
        assert self.resources.get(receipt.resource_id)==receipt.operation_id
        self.deletions.append(receipt.resource_id)
        if not self.keep_after_delete: self.resources.pop(receipt.resource_id)
    def health(self,connection,receipt): return Health(self.health_status,self.clock(),self.progress,self.rate,self.unit,self.rate_scope)
    def disconnect(self,connection,receipt): pass


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.clock=Clock(); self.provider=Provider(self.clock)
        self.registry=Registry(); self.registry.register(self.provider)
        self.enrollment=Enrollment("independent-controller","a"*64,"b"*64,True)
        self.controller=Controller(self.temp.name,self.registry,self.enrollment,actual_host_id="a"*64,
            now=self.clock,monotonic=self.clock,interval=60)
        self.connection=self.controller.connections.add("Test connection","test","explicit-credential")
        self.provider.store=self.controller.store
        self.controller.start()
        self.selection={"gpu":"synthetic","disk_gb":1000}
        self.plan=dict(id="example/model",revision="a"*40,context=8192,engine="vLLM",dtype="float16",fileSizes={"model.safetensors":10**9},weightBytes=10**9,overheadBytes=10**9,kvBytesPerToken=1024)
    def tearDown(self):
        self.provider.allocation_release.set(); self.provider.setup_release.set()
        for worker in self.controller._workers.values(): worker.join(timeout=2)
        self.controller.close(); self.temp.cleanup()
    def request(self,operation="operation1",duration=600,quote=None):
        quote=quote or self.provider.quote(self.connection,self.selection)
        return self.controller.request(operation,self.connection.id,self.selection,self.plan,quote,2.0,duration,"b"*64)
    def wait_worker(self,operation="operation1"):
        self.controller._workers[operation].join(timeout=2)
        self.assertFalse(self.controller._workers[operation].is_alive())

    def test_intent_is_durable_before_single_allocation_and_retry_is_idempotent(self):
        self.request(); self.wait_worker()
        self.assertEqual(1,self.provider.allocations)
        existing=self.request()
        self.assertEqual("active",existing.state)
        self.assertEqual(1,self.provider.allocations)

    def test_protection_missing_or_same_host_refuses_before_provider_allocation(self):
        self.controller.enrollment=replace(self.enrollment,controller_host_id="b"*64)
        with self.assertRaisesRegex(ValueError,"independently hosted"): self.request()
        self.assertEqual(0,self.provider.allocations)
        self.assertEqual([],self.controller.store.scan())

    def test_stop_during_provider_preflight_prevents_final_post(self):
        original=self.provider.allocate
        def stopped(connection,receipt,selection,*,submit_gate):
            self.controller.cancel(receipt.operation_id)
            return original(connection,receipt,selection,submit_gate=submit_gate)
        self.provider.allocate=stopped
        self.request(); self.wait_worker()
        self.assertEqual(0,self.provider.allocations)
        self.assertEqual("cancelled",self.controller.store.load("operation1").state)
    def test_new_recovery_record_at_final_gate_prevents_post(self):
        original=self.provider.allocate
        def late(connection,receipt,selection,*,submit_gate):
            self.controller.store.save(rental("other",state="allocating",protection_id="proof",allocation_submitted=True))
            return original(connection,receipt,selection,submit_gate=submit_gate)
        self.provider.allocate=late
        self.request(); self.wait_worker()
        self.assertEqual(0,self.provider.allocations)
        self.assertEqual("cancelled",self.controller.store.load("operation1").state)

    def test_final_submission_authorization_is_one_use(self):
        receipt=rental("guarded",connection_id=self.connection.id,state="allocating",created_at=self.clock(),deadline=self.clock()+600,protection_id=self.enrollment.controller_id,allocation_submitted=True)
        self.controller.store.save(receipt)
        guard=self.controller._submission_guard(receipt)
        guard()
        with self.assertRaisesRegex(ValueError,"one allocation"): guard()

    def test_dead_monitor_refuses_before_allocation(self):
        self.controller._stop.set(); self.controller._monitor.join(timeout=1)
        self.assertFalse(self.controller._monitor.is_alive())
        with self.assertRaisesRegex(ValueError,"not healthy"): self.request()
        self.assertEqual(0,self.provider.allocations)

    def test_expired_or_changed_quote_and_insufficient_disk_refuse_before_allocation(self):
        quote=self.provider.quote(self.connection,self.selection)
        self.provider.quote_price=1.5
        with self.assertRaisesRegex(ValueError,"offer changed"): self.request(quote=quote)
        self.provider.quote_price=1
        self.clock.advance(121); self.controller.tick()
        with self.assertRaisesRegex(ValueError,"Refresh"): self.request(quote=quote)
        self.provider.free_bytes=1
        with self.assertRaisesRegex(ValueError,"disk"): self.request()
        self.assertEqual(0,self.provider.allocations)

    def test_unknown_provider_price_requires_explicit_rate_ceiling_and_is_not_invented(self):
        self.provider.quote_price=None
        quote=self.provider.quote(self.connection,self.selection)
        self.assertIsNone(quote.price)
        with self.assertRaisesRegex(ValueError,"positive maximum"):
            self.controller.request("bad",self.connection.id,self.selection,self.plan,quote,0,600,"b"*64)
        self.request(); self.wait_worker()
        self.assertEqual(2.0,self.controller.store.load("operation1").rate_ceiling)

    def test_unresolved_receipt_at_final_worker_gate_prevents_post(self):
        enter=threading.Event(); release=threading.Event(); original=self.controller._allocate
        def delayed(*args):
            enter.set(); release.wait(2); original(*args)
        with patch.object(self.controller,"_allocate",side_effect=delayed):
            self.request(); self.assertTrue(enter.wait(1))
            self.controller.store.save(rental("other",state="allocating",protection_id="proof",allocation_submitted=True))
            release.set(); self.wait_worker()
        self.assertEqual(0,self.provider.allocations)
        self.assertEqual("cancelled",self.controller.store.load("operation1").state)

    def test_deadline_monitor_cleans_up_while_setup_remains_blocked(self):
        self.provider.setup_release.clear()
        self.request(duration=10); self.assertTrue(self.provider.setup_entered.wait(1))
        self.assertTrue(self.controller._workers["operation1"].is_alive())
        self.clock.advance(11); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)
        self.assertEqual({},self.provider.resources)
        self.assertTrue(self.controller._workers["operation1"].is_alive())
        self.provider.setup_release.set(); self.wait_worker()

    def test_late_allocation_after_deadline_is_retained_then_verified_off(self):
        self.provider.allocation_release.clear()
        self.request(duration=10); self.assertTrue(self.provider.allocation_entered.wait(1))
        self.clock.advance(11); self.controller.tick()
        pending=self.controller.store.load("operation1")
        self.assertEqual("unresolved",pending.state); self.assertTrue(pending.cancel_requested)
        self.provider.allocation_release.set(); self.wait_worker()
        self.assertEqual("off",self.controller.store.load("operation1").state)
        self.assertEqual(1,len(self.provider.deletions))
        self.assertFalse(self.provider.setup_entered.is_set())

    def test_lost_desktop_lease_causes_verified_cleanup(self):
        self.request(); self.wait_worker(); self.clock.advance(121); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_heartbeat_never_extends_absolute_deadline(self):
        self.request(duration=150); self.wait_worker()
        original=self.controller.store.load("operation1").deadline
        self.clock.advance(90); self.controller.tick(); self.controller.heartbeat("operation1","b"*64)
        self.assertEqual(original,self.controller.store.load("operation1").lease_expires_at)
        self.clock.advance(61); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_terminal_setup_failure_and_rate_overrun_trigger_verified_cleanup(self):
        self.provider.fail_setup=True
        self.request(); self.wait_worker()
        self.assertEqual("off",self.controller.store.load("operation1").state)
        self.provider.fail_setup=False
        self.request("second"); self.wait_worker("second")
        self.provider.rate=3; self.controller.tick()
        self.assertEqual("off",self.controller.store.load("second").state)

    def test_brief_health_loss_recovers_but_sustained_loss_stops(self):
        self.request(); self.wait_worker(); self.controller.tick()
        self.provider.health_status="unknown"; self.clock.advance(30); self.controller.tick()
        self.assertEqual("active",self.controller.store.load("operation1").state)
        self.provider.health_status="ready"; self.controller.tick()
        self.provider.health_status="unknown"; self.clock.advance(91); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_delete_acknowledgement_without_absence_remains_unresolved(self):
        self.request(); self.wait_worker(); self.provider.keep_after_delete=True
        results=self.controller.cancel("operation1")
        self.assertEqual("unresolved",results[0].state)
        self.assertEqual("unresolved",self.controller.store.load("operation1").state)
        self.assertEqual(1,len(self.controller.store.blockers()))
        self.provider.keep_after_delete=False

    def test_background_monitor_expires_deadline_without_desktop_calls(self):
        self.controller.close()
        self.controller=Controller(self.temp.name,self.registry,self.enrollment,actual_host_id="a"*64,now=self.clock,monotonic=self.clock,interval=0.02)
        finished=threading.Event()
        original=self.controller.tick
        def observed_tick():
            original()
            if self.controller.store.path("operation1").exists() and self.controller.store.load("operation1").state=="off":
                finished.set()
        with patch.object(self.controller,"tick",side_effect=observed_tick):
            self.controller.start()
            self.request(duration=10); self.wait_worker()
            self.clock.advance(11)
            self.assertTrue(finished.wait(2),"Live background monitor did not confirm cleanup")
        self.assertEqual({},self.provider.resources)

    def test_changed_balance_requires_review_of_fresh_quote(self):
        quote=self.provider.quote(self.connection,self.selection)
        with patch.object(self.provider,"quote",return_value=replace(quote,balance=5)):
            with self.assertRaisesRegex(ValueError,"offer changed"): self.request(quote=quote)
        self.assertEqual(0,self.provider.allocations)

    def test_size_manifest_must_match_selected_gguf_files(self):
        self.plan.update(engine="llama.cpp",files=["model.gguf"])
        with self.assertRaisesRegex(ValueError,"sizes do not match"): self.request()
        self.assertEqual(0,self.provider.allocations)

    def test_second_live_controller_cannot_recover_first_controllers_rental(self):
        self.request(); self.wait_worker()
        other=Controller(self.temp.name,self.registry,self.enrollment,actual_host_id="a"*64,now=self.clock,monotonic=self.clock,interval=60)
        with self.assertRaises(TimeoutError): other.start()
        self.assertEqual([],other.close())
        self.assertEqual("active",self.controller.store.load("operation1").state)
        self.assertEqual([],self.provider.deletions)

    def test_missing_actual_rate_cannot_keep_rental_running_indefinitely(self):
        self.request(); self.wait_worker(); self.provider.rate=None
        self.controller.tick(); self.clock.advance(91); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_third_unit_postpaid_zero_rate_keeps_protection_without_prepaid_balance(self):
        self.provider.unit="EUR"; self.provider.balance=None; self.provider.balance_required=False
        self.provider.quote_price=0; self.provider.rate=0
        self.request(); self.wait_worker()
        self.controller.tick(); self.clock.advance(91); self.controller.tick()
        receipt=self.controller.store.load("operation1")
        self.assertEqual(("active","EUR","rental"),(receipt.state,receipt.rate_unit,receipt.rate_scope))
        self.clock.advance(30); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_prepaid_unknown_or_zero_balance_refuses_without_allocation(self):
        for balance in (None,0):
            self.provider.balance=balance
            with self.assertRaisesRegex(ValueError,"prepaid balance"): self.request()
        self.assertEqual(0,self.provider.allocations)

    def test_changed_billing_unit_or_scope_stops_immediately(self):
        for operation,field,value in (("currency","unit","EUR"),("scope","rate_scope","account")):
            self.provider.unit="USD"; self.provider.rate_scope="rental"
            self.request(operation); self.wait_worker(operation)
            setattr(self.provider,field,value); self.controller.tick()
            self.assertEqual("off",self.controller.store.load(operation).state)

    def test_account_total_scope_is_preserved_and_enforced(self):
        self.provider.rate_scope="account"
        self.request(); self.wait_worker(); self.controller.tick()
        receipt=self.controller.store.load("operation1")
        self.assertEqual("account",receipt.rate_scope)
        self.assertEqual("active",receipt.state)
        self.provider.rate=3; self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_terminal_health_failure_does_not_wait_for_unknown_rate(self):
        self.request(); self.wait_worker()
        self.provider.health_status="failed"; self.provider.rate=None; self.provider.unit=None
        self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_billing_scope_and_prepaid_policy_changes_require_confirmation(self):
        quote=self.provider.quote(self.connection,self.selection)
        for change in ({"rate_scope":"account"},{"balance_required":False}):
            with patch.object(self.provider,"quote",return_value=replace(quote,**change)):
                with self.assertRaisesRegex(ValueError,"offer changed"): self.request(quote=quote)
        self.assertEqual(0,self.provider.allocations)

    def test_starting_after_ready_is_treated_as_health_loss(self):
        self.request(); self.wait_worker(); self.controller.tick()
        self.provider.health_status="starting"
        self.clock.advance(91); self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)

    def test_restart_recovers_outstanding_resource_before_new_requests(self):
        self.request(); self.wait_worker()
        self.controller._stop.set(); self.controller._monitor.join(timeout=1)
        # Simulate OS lock release at process exit, without running normal cleanup.
        self.controller._ownership.__exit__(None,None,None)
        self.controller._ownership=None
        replacement=Controller(self.temp.name,self.registry,self.enrollment,actual_host_id="a"*64,now=self.clock,monotonic=self.clock,interval=60)
        replacement.start()
        try:
            self.assertEqual("off",replacement.store.load("operation1").state)
            self.assertEqual({},self.provider.resources)
        finally: replacement.close()


if __name__=="__main__": unittest.main()
