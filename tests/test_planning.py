from dataclasses import replace
import unittest
from engine_room.lifecycle import Quote
from engine_room.planning import offer_plan

class OfferPlanningTests(unittest.TestCase):
    def setUp(self):
        self.plan=dict(context=8192,weightBytes=10**9,overheadBytes=10**9,kvBytesPerToken=1024,fileSizes={"model.gguf":10**9})
        self.quote=Quote("account","a"*64,1,"USD",10,1000,True,10**12,10**9,dict(observed_at=1000,gpu_memory_bytes=80*1024**3))
    def test_known_capacity_and_storage_are_checked_without_cache_credit(self):
        result=offer_plan(self.plan,self.quote)
        self.assertGreater(result["required_gpu_bytes"],2*10**9)
        self.assertEqual(3*10**9+1024**3,result["required_storage_bytes"])
        self.assertFalse(result["gpu_check_deferred"])
        for changed in (dict(gpu_memory_bytes=10**9),dict(gpu_memory_bytes=True),{}):
            with self.assertRaises(ValueError): offer_plan(self.plan,replace(self.quote,cost_details=changed))
        with self.assertRaises(ValueError): offer_plan(self.plan,replace(self.quote,storage_available_bytes=10**9))
    def test_unknown_capacity_requires_explicit_deferred_contract(self):
        quote=replace(self.quote,storage_available_bytes=None,cost_details=dict(observed_at=1000,storage_validation="before-installation",gpu_validation="before-installation"))
        result=offer_plan(self.plan,quote)
        self.assertTrue(result["gpu_check_deferred"]); self.assertTrue(result["storage_check_deferred"])
        self.assertNotEqual(self.quote.confirmation_key(),replace(self.quote,cost_details=dict(observed_at=1000,gpu_memory_bytes=40*1024**3)).confirmation_key())
    def test_missing_or_invalid_model_estimates_refuse(self):
        for value in (None,False,0,float("inf")):
            with self.assertRaises(ValueError): offer_plan(self.plan|dict(kvBytesPerToken=value),self.quote)


import test_lifecycle as fixture

class ControllerCapacityTests(unittest.TestCase):
    setUp=fixture.ControllerTests.setUp
    tearDown=fixture.ControllerTests.tearDown
    request=fixture.ControllerTests.request
    def test_small_gpu_refuses_before_any_provider_allocation(self):
        original=self.provider.quote
        self.provider.quote=lambda *args:replace(original(*args),cost_details=dict(observed_at=self.clock(),gpu_memory_bytes=1024))
        with self.assertRaises(ValueError): self.request()
        self.assertEqual(0,self.provider.allocations); self.assertEqual([],self.controller.store.scan())
    def test_missing_model_estimate_refuses_before_allocation(self):
        self.plan.pop("kvBytesPerToken")
        with self.assertRaises(ValueError): self.request()
        self.assertEqual(0,self.provider.allocations)
