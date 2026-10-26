from dataclasses import replace
import unittest
from unittest.mock import Mock

from engine_room.connections import Connection
from engine_room.lifecycle import Quote
from engine_room_connectors._colab.pricing import quote
import test_lifecycle as fixture


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.connection=Connection("connection1","colab","synthetic-account","Example","explicit-ref",{})
        self.api=Mock(); self.api.usage.return_value=dict(account_id=self.connection.account_id,balance=10,
            account_rate=5,assignments_count=2,rate_scope="account_total",unit="CCU",observed_at=1000)
        self.selection={"accelerator":"A100","engine":"vLLM","high_mem":True}
    def quote(self): return quote(self.api,self.connection,self.selection,now=lambda:1000)
    def test_account_consumption_is_not_a_rental_price_or_disk_estimate(self):
        result=self.quote(); self.assertIsNone(result.price); self.assertEqual("account",result.rate_scope)
        self.assertIsNone(result.available); self.assertIsNone(result.storage_available_bytes)
        self.assertEqual(5,result.cost_details["account_rate"]); self.assertEqual(2,result.cost_details["assignments_count"])
        self.assertEqual("before-installation",result.cost_details["storage_validation"])
        self.assertEqual("unknown-before-allocation",result.cost_details["selected_rental_price"])
    def test_stale_wrong_account_unit_scope_or_unknown_balance_refuse(self):
        original=self.api.usage.return_value.copy()
        for change in ({"observed_at":879},{"account_id":"unrelated"},{"unit":"USD"},{"rate_scope":"rental"},
                {"balance":None},{"balance":0},{"account_rate":float("nan")},{"assignments_count":True}):
            self.api.usage.return_value=original|change
            with self.assertRaises(ValueError): self.quote()
    def test_unknown_disk_contract_is_explicit_and_confirmation_bound(self):
        result=self.quote()
        with self.assertRaises(ValueError): replace(result,cost_details={"observed_at":1000}).validate(1000)
        self.assertNotEqual(result.confirmation_key(),replace(result,storage_available_bytes=10**12).confirmation_key())
        with self.assertRaises(ValueError): replace(result,install_bytes=-1).validate(1000)
        with self.assertRaises(ValueError): replace(result,storage_available_bytes=True).validate(1000)


class DeferredStorageControllerTests(unittest.TestCase):
    setUp=fixture.ControllerTests.setUp
    tearDown=fixture.ControllerTests.tearDown
    request=fixture.ControllerTests.request
    wait_worker=fixture.ControllerTests.wait_worker
    def test_unknown_capacity_requires_contract_but_preserves_owned_setup_failure_cleanup(self):
        self.provider.free_bytes=None; original=self.provider.quote
        with self.assertRaises(ValueError): self.request()
        self.assertEqual(0,self.provider.allocations)
        self.provider.quote=lambda *a:replace(original(*a),cost_details={"observed_at":self.clock(),"storage_validation":"before-installation","gpu_validation":"before-installation"})
        self.provider.fail_setup=True
        self.request(); self.wait_worker()
        record=self.controller.store.load("operation1")
        self.assertEqual("off",record.state); self.assertEqual(["pod-operation1"],self.provider.deletions)
    def test_unknown_capacity_does_not_accept_invalid_published_file_sizes(self):
        self.provider.free_bytes=None; original=self.provider.quote
        self.provider.quote=lambda *a:replace(original(*a),cost_details={"observed_at":self.clock(),"storage_validation":"before-installation","gpu_validation":"before-installation"})
        self.plan["fileSizes"]={"model.gguf":0}
        with self.assertRaises(ValueError): self.request()
        self.assertEqual(0,self.provider.allocations)
