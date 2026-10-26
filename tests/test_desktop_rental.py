from dataclasses import asdict,replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.connections import Connection
from engine_room.desktop_rental import Rental
from engine_room.desktop_bridge import Bridge
from engine_room.lifecycle import Quote,selection_key
from engine_room.records import Receipt


class RentalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.client=Mock(); self.client.endpoint.controller_id="controller"; self.client.endpoint.client_host_id="b"*64
        self.connection=Connection("connection1","test","synthetic-account","Example","explicit-ref",{})
        self.selection={"gpu":"synthetic"}; self.quote=Quote(self.connection.account_id,selection_key(self.selection),1,"USD",10,1000,True,10**12,10**9,dict(observed_at=1000,gpu_memory_bytes=80*1024**3))
        self.request=dict(connection_id=self.connection.id,selection=self.selection,plan=dict(id="example/model",revision="a"*40,context=8192,engine="vLLM",dtype="float16",fileSizes={"model.safetensors":10**9},weightBytes=10**9,overheadBytes=10**9,kvBytesPerToken=1024),approved_quote=asdict(self.quote),rate_ceiling=2,duration_seconds=600)
        self.closed=False; self.submissions=0; self.remote=None; self.factory=Mock(); self.session=Mock(); self.factory.return_value=self.session
        self.client.call.side_effect=self.call
        self.rental=Rental(self.client,self.root,session_factory=self.factory,now=lambda:1000,clock=lambda:100)
    def call(self,method,params=None):
        if method=="info": return {"protection_healthy":True}
        if method=="connections": return [asdict(self.connection)]
        if method=="request":
            self.submissions+=1
            path=self.rental.intents.path(params["operation_id"])
            self.assertTrue(path.exists())
            self.remote=Receipt(params["operation_id"],self.connection.id,"test",self.connection.account_id,"rental","intent",1000,1600,
                protection_id="controller",lease_expires_at=1120,rate_ceiling=2,rate_unit="USD",quote_key=self.quote.confirmation_key())
            return asdict(self.remote)
        if method=="cancel": return []
        if method=="status": return {"records":[asdict(self.remote)]}
        raise AssertionError(method)
    def begin(self,request=None):
        return self.rental.begin(request or self.request,confirmed=True,ui_touch=90,is_closed=lambda:self.closed)
    def test_intent_precedes_submission_and_real_ui_timestamp_reaches_session(self):
        receipt=self.begin(); self.assertEqual(1,self.submissions)
        self.assertEqual(90,self.factory.call_args.kwargs["initial_touch"])
        self.assertEqual(receipt,self.rental.receipts.load(receipt.operation_id))
        self.rental.touch(); self.session.touch.assert_called_once()
        self.session.close.return_value=replace(receipt,cancel_requested=True)
        self.rental.stop(); self.session.close.assert_called_once()
        self.assertTrue(self.rental.receipt.cancel_requested)
    def test_lost_response_preserves_intent_and_second_begin_does_not_replay(self):
        original=self.call
        def lost(method,params=None):
            result=original(method,params)
            if method=="request": raise TimeoutError("synthetic lost response")
            return result
        self.client.call.side_effect=lost
        with self.assertRaises(TimeoutError): self.begin()
        with self.assertRaises(ValueError): self.begin()
        self.assertEqual(1,self.submissions); self.factory.assert_not_called()
        self.assertEqual(1,len(list(self.rental.intents.root.glob("*.json"))))
    def test_abandoned_unknown_request_archives_denial_without_claiming_provider_off(self):
        original=self.call
        def lost(method,params=None):
            if method=="abandon_request":
                return dict(operation_id=params["operation_id"],connection_id=self.connection.id,future_start_forbidden=True,receipt_exists=False)
            result=original(method,params)
            if method=="request": raise TimeoutError("synthetic lost request")
            return result
        self.client.call.side_effect=lost
        with self.assertRaises(TimeoutError): self.begin()
        result=self.rental.stop()
        self.assertEqual("cancelled-before-submission",result["state"])
        self.assertEqual([],list(self.rental.intents.root.glob("*.json")))
        self.assertEqual(1,len(list((self.root/"finished-requests").glob("*.json"))))
        self.assertIsNone(self.rental.stop())
    def test_missing_server_receipt_cannot_erase_a_known_local_rental(self):
        receipt=self.begin(); original=self.call
        def missing(method,params=None):
            if method=="abandon_request": return dict(operation_id=receipt.operation_id,connection_id=self.connection.id,future_start_forbidden=True,receipt_exists=False)
            return original(method,params)
        self.client.call.side_effect=missing
        with self.assertRaises(ValueError): self.rental.abandon(receipt.operation_id)
        self.assertTrue(self.rental.intents.path(receipt.operation_id).exists())
        self.assertTrue(self.rental.receipts.path(receipt.operation_id).exists())
    def test_delayed_initial_reply_cannot_overwrite_terminal_cancellation_evidence(self):
        original=self.call
        def abandoned(method,params=None):
            if method=="abandon_request": return dict(operation_id=params["operation_id"],connection_id=self.connection.id,future_start_forbidden=True,receipt_exists=True)
            result=original(method,params)
            if method=="request":
                self.remote=replace(self.remote,state="cancelled",cancel_requested=True)
                self.rental.abandon(self.remote.operation_id)
            return result
        self.client.call.side_effect=abandoned
        with self.assertRaises(ValueError): self.begin()
        self.factory.assert_not_called()
        self.assertEqual("cancelled",self.rental.receipts.load(self.remote.operation_id).state)

    def test_closing_during_request_requests_owned_cleanup_without_false_off(self):
        original=self.call
        def closed(method,params=None):
            result=original(method,params)
            if method=="request": self.closed=True
            return result
        self.client.call.side_effect=closed
        with self.assertRaises(ValueError): self.begin()
        self.factory.assert_not_called(); self.assertTrue(self.rental.receipt.cancel_requested)
        self.assertNotEqual("off",self.rental.receipt.state)
        self.assertIn("cancel",[call.args[0] for call in self.client.call.call_args_list])
    def test_unknown_model_fields_never_reach_controller_or_intent(self):
        with self.assertRaises(ValueError): self.begin(self.request|{"plan":self.request["plan"]|{"account_key":"synthetic-sensitive"}})
        self.client.call.assert_not_called(); self.assertEqual([],list(self.rental.intents.root.glob("*.json")))

    def test_confirmation_stale_pulse_wrong_selection_or_account_refuse_before_submission(self):
        with self.assertRaises(ValueError): self.rental.begin(self.request,confirmed=False,ui_touch=90,is_closed=lambda:False)
        with self.assertRaises(ValueError): self.rental.begin(self.request,confirmed=True,ui_touch=1,is_closed=lambda:False)
        with self.assertRaises(ValueError): self.begin(self.request|{"selection":{"gpu":"unrelated"}})
        self.connection=replace(self.connection,account_id="unrelated")
        with self.assertRaises(ValueError): self.begin()
        self.assertEqual(0,self.submissions)
    def test_fresh_terminal_scope_clears_intent_but_changed_resource_or_account_refuses(self):
        receipt=self.begin(); identity=receipt.operation_id
        self.remote=replace(receipt,state="active",resource_id="owned")
        self.rental.refresh(identity)
        self.remote=replace(self.remote,state="off",resource_id="unrelated")
        with self.assertRaises(ValueError): self.rental.refresh(identity)
        self.assertTrue(self.rental.intents.path(identity).exists())
        self.remote=replace(self.remote,resource_id="owned",account_id="unrelated")
        with self.assertRaises(ValueError): self.rental.refresh(identity)
        self.remote=replace(self.remote,account_id=receipt.account_id)
        result=self.rental.refresh(identity); self.assertEqual("off",result.state); self.assertFalse(self.rental.intents.path(identity).exists())

    def test_bridge_recovery_reopens_original_request_without_replay(self):
        self.rental=Rental(self.client,self.root/"rentals",session_factory=self.factory,now=lambda:1000,clock=lambda:100)
        receipt=self.begin()
        factory=Mock(); factory.read.return_value=self.client
        bridge=Bridge(self.root,client_type=factory)
        rows=bridge.dispatch(dict(action="recovery_list"))["records"]
        self.assertEqual(receipt.operation_id,rows[0]["operation_id"])
        self.assertTrue(rows[0]["can_recover"]); self.assertFalse(rows[0]["shutdown_confirmed"])
        self.remote=replace(receipt,state="off",resource_id="owned")
        result=bridge.dispatch(dict(action="recover",params=dict(operation_id=receipt.operation_id,cancel=False,confirmed=True)))
        self.assertTrue(result["shutdown_confirmed"]); self.assertEqual(1,self.submissions)
        rows=bridge.dispatch(dict(action="recovery_list"))["records"]
        self.assertFalse(rows[0]["can_recover"]); self.assertFalse(rows[0]["shutdown_confirmed"])
        factory.read.assert_called_once_with(self.root)
    def test_bridge_recovery_refuses_changed_enrollment_without_remote_action(self):
        self.rental=Rental(self.client,self.root/"rentals",session_factory=self.factory,now=lambda:1000,clock=lambda:100)
        receipt=self.begin(); self.client.endpoint.controller_id="changed"
        self.client.call.reset_mock(); factory=Mock(); factory.read.return_value=self.client
        bridge=Bridge(self.root,client_type=factory)
        with self.assertRaises(ValueError):
            bridge.dispatch(dict(action="recover",params=dict(operation_id=receipt.operation_id,cancel=True,confirmed=True)))
        self.client.call.assert_not_called()
        self.assertTrue(self.rental.intents.path(receipt.operation_id).exists())

    def test_session_view_refuses_stale_wrong_scope_and_inconsistent_ready(self):
        receipt=self.begin(); original=self.call
        response=dict(operation_id=receipt.operation_id,operation_key=receipt.operation_key(),phase="ready",ready=True,sampled_at=1000)
        def status(method,params=None):
            if method=="session_status": return response.copy()
            return original(method,params)
        self.client.call.side_effect=status
        self.assertEqual(dict(phase="ready",ready=True),self.rental.view())
        for changed in (dict(sampled_at=969),dict(operation_key="0"*64),dict(ready="true"),dict(phase="starting")):
            previous=response.copy(); response.update(changed)
            with self.assertRaises(ValueError): self.rental.view()
            response.clear(); response.update(previous)
