from dataclasses import asdict,replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.desktop_attachment import Attachment
from engine_room.records import Receipt


class DesktopAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.client=Mock(); self.client.endpoint.controller_id="controller"; self.client.endpoint.client_host_id="b"*64
        self.target=dict(account_id="account",resource_id="existing-model",model_id="chosen")
        self.request=dict(connection_id="connection",approved_target=self.target,context=8192)
        self.remote=None; self.session=Mock(); self.factory=Mock(side_effect=self.make_session)
        self.access=Attachment(self.client,self.temp.name,session_factory=self.factory,clock=lambda:100,now=lambda:1000)
        self.client.call.side_effect=self.call
    def call(self,method,params=None):
        if method=="connections": return [dict(id="connection",account_id="account",connector_id="existing")]
        if method=="attach":
            self.remote=Receipt(params["operation_id"],"connection","existing","account","attachment","active",1000,resource_id="existing-model",protection_id="controller")
            return asdict(self.remote)
        if method=="status": return dict(records=[asdict(self.remote)])
        if method in {"disconnect_attachment","abandon_attachment"}:
            if self.remote is None: return dict(cancelled_before_start=True)
            self.remote=replace(self.remote,state="detached",cancel_requested=True); return asdict(self.remote)
        if method=="session_status": return dict(operation_id=self.remote.operation_id,operation_key=self.remote.operation_key(),phase="ready",ready=True,sampled_at=1000)
        raise AssertionError("Unexpected rental or other operation: "+method)
    def make_session(self,client,receipt,root,**kwargs):
        self.session.close.side_effect=lambda:self.finish(receipt)
        return self.session
    def finish(self,receipt):
        self.remote=replace(receipt,state="detached",cancel_requested=True); self.access.receipts.save(self.remote)
        return self.remote
    def begin(self,**kwargs):
        return self.access.begin(self.request,confirmed=True,ui_touch=100,is_closed=lambda:False,**kwargs)
    def test_confirmed_target_is_durable_and_session_uses_exact_model(self):
        receipt=self.begin(); proof=self.access.proof(receipt.operation_id)
        self.assertEqual("chosen",proof["model_id"]); self.assertEqual("chosen",self.factory.call_args.kwargs["selected_model"])
        self.assertTrue(self.access.view()["ready"])
        self.assertEqual("detached",self.access.stop().state)
        self.assertFalse(any(row.args[0] in {"info","request","heartbeat","cancel"} for row in self.client.call.call_args_list))
    def test_missing_confirmation_or_stale_ui_refuses_before_rpc(self):
        with self.assertRaises(ValueError): self.access.begin(self.request,confirmed=False,ui_touch=100,is_closed=lambda:False)
        with self.assertRaises(ValueError): self.access.begin(self.request,confirmed=True,ui_touch=1,is_closed=lambda:False)
        self.client.call.assert_not_called()
    def test_lost_start_reply_keeps_intent_and_abandons_without_replay(self):
        original=self.client.call.side_effect
        def lost(method,params=None):
            if method=="attach": raise RuntimeError("synthetic lost reply")
            return original(method,params)
        self.client.call.side_effect=lost
        with self.assertRaises(RuntimeError): self.begin()
        self.assertTrue(self.access.intents.path(self.access.pending_operation).exists()); self.factory.assert_not_called()
        self.assertEqual("cancelled-before-submission",self.access.stop()["state"])
        self.assertEqual(1,len([row for row in self.client.call.call_args_list if row.args[0]=="attach"]))
    def test_closed_ui_after_reply_disconnects_without_starting_session(self):
        original=self.client.call.side_effect; closed=[False]
        def reply(method,params=None):
            result=original(method,params)
            if method=="attach": closed[0]=True
            return result
        self.client.call.side_effect=reply
        with self.assertRaises(ValueError): self.access.begin(self.request,confirmed=True,ui_touch=100,is_closed=lambda:closed[0])
        self.factory.assert_not_called(); self.assertEqual("detached",self.access.receipt.state)
    def test_changed_controller_reply_preserves_intent_and_never_opens_relay(self):
        original=self.client.call.side_effect
        def reply(method,params=None):
            result=original(method,params)
            return {**result,"resource_id":"other"} if method=="attach" else result
        self.client.call.side_effect=reply
        with self.assertRaises(ValueError): self.begin()
        self.factory.assert_not_called(); self.assertTrue(any(self.access.intents.root.glob("*.json")))
    def test_recovery_does_not_overwrite_local_detached_with_late_active(self):
        receipt=self.begin(); self.access.receipts.save(replace(receipt,state="detached",cancel_requested=True))
        self.assertEqual("detached",self.access.refresh(receipt.operation_id).state)
        self.assertFalse(self.access.intents.path(receipt.operation_id).exists())

    def test_desktop_bridge_lists_and_disconnects_attachment_without_rental_recovery(self):
        from engine_room.desktop_bridge import Bridge
        self.access=Attachment(self.client,Path(self.temp.name)/"attachments",session_factory=self.factory,clock=lambda:100,now=lambda:1000)
        receipt=self.begin()
        factory=Mock(); factory.read.return_value=self.client
        bridge=Bridge(self.temp.name,client_type=factory)
        rows=bridge.dispatch(dict(action="recovery_list"))["records"]
        self.assertEqual("attachment",rows[0]["mode"]); self.assertFalse(rows[0]["shutdown_confirmed"])
        result=bridge.dispatch(dict(action="recover",params=dict(operation_id=receipt.operation_id,mode="attachment",cancel=True,confirmed=True)))
        self.assertEqual("detached",result["state"]); self.assertTrue(result["disconnected_confirmed"])
        self.assertFalse(result["shutdown_confirmed"])
        self.assertFalse(any(row.args[0] in {"cancel","abandon_request","request"} for row in self.client.call.call_args_list))


class DesktopCoreAttachmentTests(unittest.TestCase):
    def test_real_desktop_session_and_controller_protocol_disconnect_only_local_access(self):
        import threading
        import time
        from types import SimpleNamespace
        from engine_room.connections import Connection
        from engine_room.connectors import Descriptor,Registry
        from engine_room.controller_protocol import Dispatcher
        from engine_room.desktop_session import DesktopSession
        from engine_room.lifecycle import Controller
        from engine_room.private_endpoint import ModelEndpoint
        from engine_room.protection import Enrollment
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); connector=Mock()
            connector.descriptor=Descriptor("existing","Synthetic existing model","Explicit identity",("attachment",))
            target=dict(account_id="account",resource_id="model",model_id="chosen")
            connector.attachment_target.return_value=target
            registry=Registry(); registry.register(connector)
            controller=Controller(root/"controller",registry,Enrollment("controller","a"*64,"b"*64,True),actual_host_id="a"*64,now=lambda:1000,interval=60)
            controller.connections._save({"connection":Connection("connection","existing","account","Existing model","explicit",{})})
            controller.start(); dispatcher=Dispatcher(controller); methods=[]; pulsed=threading.Event()
            connector.pulse.side_effect=lambda *args:pulsed.set()
            connector.model_endpoint.side_effect=lambda connection,receipt:ModelEndpoint(str(root/"controller"/"m.sock"),receipt.operation_key(),receipt.resource_id,1,2,3)
            def call(method,params=None):
                methods.append(method)
                response=dispatcher.dispatch(dict(schema=1,request_id="c"*32,controller_id="controller",client_host_id="b"*64,method=method,params=params or {}))
                if not response["ok"]: raise RuntimeError("Synthetic protocol refusal")
                return response["result"]
            client=SimpleNamespace(endpoint=SimpleNamespace(controller_id="controller",client_host_id="b"*64),call=call)
            def session(*args,**kwargs): return DesktopSession(*args,**kwargs,relay_factory=Mock(),interval=0.01)
            access=Attachment(client,root/"desktop",session_factory=session,now=lambda:1000)
            try:
                receipt=access.begin(dict(connection_id="connection",approved_target=target,context=8192),confirmed=True,ui_touch=time.monotonic(),is_closed=lambda:False)
                self.assertTrue(pulsed.wait(2)); self.assertTrue(access.view()["ready"])
                self.assertEqual("detached",access.stop().state)
                self.assertEqual("detached",controller.store.load(receipt.operation_id).state)
                self.assertFalse(any(method in {"request","heartbeat","cancel"} for method in methods))
                connector.terminate.assert_not_called(); connector.allocate.assert_not_called()
            finally:
                access.stop(); controller.close()
