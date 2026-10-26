from dataclasses import replace
import threading
import unittest

from engine_room.lifecycle import Controller
import test_lifecycle as fixture


class AbandonedRequestTests(unittest.TestCase):
    setUp=fixture.ControllerTests.setUp
    tearDown=fixture.ControllerTests.tearDown
    request=fixture.ControllerTests.request
    wait_worker=fixture.ControllerTests.wait_worker
    def abandon(self,operation="operation1",connection=None):
        return self.controller.abandon(operation,connection or self.connection.id,"b"*64)
    def test_cancel_before_request_persists_and_denies_late_request_after_restart(self):
        result=self.abandon(); self.assertTrue(result["future_start_forbidden"]); self.assertFalse(result["receipt_exists"])
        with self.assertRaises(ValueError): self.request()
        self.controller.close()
        self.controller=Controller(self.temp.name,self.registry,self.enrollment,actual_host_id="a"*64,now=self.clock,monotonic=self.clock,interval=60)
        self.controller.start()
        with self.assertRaises(ValueError): self.request()
        self.assertEqual(0,self.provider.allocations); self.assertEqual([],self.provider.deletions)
    def test_final_guard_refuses_abandonment_during_provider_preflight(self):
        entered=threading.Event(); released=threading.Event(); original=self.provider.allocate
        def preflight(*args,submit_gate):
            entered.set()
            if not released.wait(3): raise RuntimeError("Synthetic preflight not released")
            return original(*args,submit_gate=submit_gate)
        self.provider.allocate=preflight
        try:
            self.request(); self.assertTrue(entered.wait(3)); result=self.abandon()
            self.assertTrue(result["receipt_exists"]); self.assertEqual(0,self.provider.allocations)
        finally: released.set()
        self.wait_worker(); self.assertEqual(0,self.provider.allocations)
        self.assertEqual("cancelled",self.controller.store.load("operation1").state)
    def test_after_submission_stays_uncertain_until_delayed_owned_resource_is_confirmed_off(self):
        self.provider.resources["unrelated"]="another-operation"; self.provider.allocation_release.clear()
        self.request(); self.assertTrue(self.provider.allocation_entered.wait(3))
        try:
            result=self.abandon(); self.assertTrue(result["receipt_exists"])
            self.assertNotEqual("off",self.controller.store.load("operation1").state)
        finally: self.provider.allocation_release.set()
        self.wait_worker(); self.assertEqual("off",self.controller.store.load("operation1").state)
        self.assertEqual(["pod-operation1"],self.provider.deletions); self.assertIn("unrelated",self.provider.resources)
    def test_orphan_journal_is_never_reported_as_never_submitted(self):
        self.request(); self.wait_worker(); self.assertTrue(self.controller.request_journal.path("operation1").exists())
        self.controller.store.path("operation1").unlink()
        with self.assertRaises(ValueError): self.request("other-operation")
        result=self.abandon(); self.assertTrue(result["receipt_exists"])
        self.assertEqual("off",self.controller.store.load("operation1").state)
    def test_wrong_connection_or_client_cannot_deny_an_existing_rental(self):
        self.request(); self.wait_worker(); other=self.controller.connections.add("Other","test","other-credential")
        with self.assertRaises(ValueError): self.abandon(connection=other.id)
        with self.assertRaises(ValueError): self.controller.abandon("operation1",self.connection.id,"c"*64)
        self.assertFalse(self.controller.start_denials.path("operation1").exists()); self.assertEqual([],self.provider.deletions)


import test_controller_transport as protocol


class AbandonProtocolTests(unittest.TestCase):
    setUp=protocol.ProtocolTests.setUp
    tearDown=protocol.ProtocolTests.tearDown
    call=protocol.ProtocolTests.call
    request_params=protocol.ProtocolTests.request_params
    def test_authenticated_abandonment_rpc_blocks_late_request_without_false_off(self):
        result=self.call("abandon_request",dict(operation_id="operation1",connection_id=self.connection.id))
        self.assertTrue(result["ok"]); self.assertFalse(result["result"]["receipt_exists"])
        self.assertNotIn("off",result["result"])
        self.assertFalse(self.call("request",self.request_params())["ok"])
        self.assertEqual(0,self.provider.allocations)
