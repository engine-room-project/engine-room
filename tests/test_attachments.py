from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from engine_room.attachments import Attachments
from engine_room.connections import Connection,Connections
from engine_room.connectors import Descriptor,Registry
from engine_room.private_endpoint import ModelEndpoint
from engine_room.protection import Enrollment
from engine_room.records import atomic_json


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.connector=Mock(); self.connector.descriptor=Descriptor("existing","Synthetic existing machine","Dedicated identity",("attachment",))
        self.connector.attachment_target.return_value=dict(account_id="account",resource_id="machine-model",model_id="chosen")
        self.registry=Registry(); self.registry.register(self.connector)
        self.connections=Connections(self.root,self.registry)
        self.connection=Connection("connection","existing","account","Existing model","explicit",{})
        self.connections._save({self.connection.id:self.connection})
        self.enrollment=Enrollment("controller","a"*64,"b"*64,True)
        self.manager=Attachments(self.connections,self.registry,self.enrollment,"a"*64,now=lambda:1000)
        self.client="b"*64
    def attach(self): return self.manager.attach("operation","connection",self.client,approved_target=dict(account_id="account",resource_id="machine-model",model_id="chosen"))
    def endpoint(self,connection,receipt):
        return ModelEndpoint(str(self.root/"m.sock"),receipt.operation_key(),receipt.resource_id,1,2,3)
    def test_durable_state_precedes_start_and_lost_reply_never_replays(self):
        def start(connection,receipt):
            self.assertEqual(receipt,self.manager.store.load(receipt.operation_id))
            self.assertTrue(self.manager.journal.path(receipt.operation_id).exists())
        self.connector.attach.side_effect=start
        receipt=self.attach(); self.assertEqual(receipt,self.attach())
        self.connector.attach.assert_called_once(); self.connector.allocate.assert_not_called()
        self.assertIsNone(receipt.deadline); self.assertEqual("attachment",receipt.mode)
        self.connector.model_endpoint.side_effect=self.endpoint
        self.assertEqual("chosen",self.manager.stream_scope("operation",self.client)["selected_model"])
        self.manager.pulse("operation",self.client); self.connector.pulse.assert_called_once()
    def test_failed_start_detaches_only_after_explicit_connector_confirmation(self):
        self.connector.attach.side_effect=ValueError("synthetic failure")
        self.assertEqual("detached",self.attach().state)
        self.connector.disconnect.assert_called_once(); self.connector.terminate.assert_not_called()
        self.connector.attach.reset_mock(); self.attach(); self.connector.attach.assert_not_called()
    def test_uncertain_disconnect_preserves_unresolved_and_blocks_access(self):
        self.attach(); self.connector.disconnect.side_effect=ValueError("no local confirmation")
        result=self.manager.disconnect("operation","connection",self.client)
        self.assertEqual("unresolved",result.state); self.assertTrue(result.cancel_requested)
        self.assertTrue(self.manager.pending())
        for method in (self.manager.pulse,self.manager.stream_scope):
            with self.assertRaises(ValueError): method("operation",self.client)
        self.connector.terminate.assert_not_called()
    def test_abandon_before_start_prevents_late_attach(self):
        self.assertIsNone(self.manager.disconnect("operation","connection",self.client))
        with self.assertRaises(ValueError): self.attach()
        self.connector.attach.assert_not_called()
    def test_rotation_does_not_prevent_closing_original_local_access(self):
        receipt=self.attach(); self.connector.attachment_target.side_effect=ValueError("rotated credential")
        self.connector.account_identity.side_effect=ValueError("rotated credential")
        changed=replace(self.connection,credential_ref="rotated")
        self.connections._save({changed.id:changed})
        result=self.manager.disconnect("operation","connection",self.client)
        self.assertEqual("detached",result.state)
        self.connector.disconnect.assert_called_once_with(self.connection,replace(receipt,cancel_requested=True))
        self.connector.account_identity.assert_not_called()
    def test_restart_reconciles_local_evidence_and_never_reconnects(self):
        self.attach(); self.connector.attach.reset_mock()
        restarted=Attachments(self.connections,self.registry,self.enrollment,"a"*64)
        results=restarted.recover(); self.assertEqual("detached",results[0].state)
        self.connector.attach.assert_not_called(); self.connector.terminate.assert_not_called()
    def test_interrupted_journal_recovery_never_replays_connect(self):
        self.attach(); self.manager.store.path("operation").unlink(); self.connector.attach.reset_mock()
        results=self.manager.recover(); self.assertEqual("detached",results[0].state)
        self.connector.attach.assert_not_called()
    def test_wrong_host_or_scope_refuses_without_remote_action(self):
        with self.assertRaises(ValueError): self.manager.attach("operation","connection","c"*64,approved_target={})
        self.connector.attach.assert_not_called()
        self.attach()
        with self.assertRaises(ValueError): self.manager.disconnect("operation","different",self.client)
        self.connector.disconnect.assert_not_called()
    def test_changed_connection_revokes_access_and_close_prevents_new_start(self):
        self.attach(); self.connections._save({"connection":replace(self.connection,settings={"changed":True})})
        with self.assertRaises(ValueError): self.manager.stream_scope("operation",self.client)
        self.manager.close()
        with self.assertRaises(ValueError): self.manager.attach("another","connection",self.client,approved_target={})
        self.connector.terminate.assert_not_called()
    def test_disconnect_during_start_is_durable_before_waiting_for_start(self):
        entered=threading.Event(); release=threading.Event(); results=[]; errors=[]
        def start(*args): entered.set(); self.assertTrue(release.wait(3))
        self.connector.attach.side_effect=start
        def connect():
            try: results.append(self.attach())
            except Exception as error: errors.append(error)
        def close():
            try: results.append(self.manager.disconnect("operation","connection",self.client))
            except Exception as error: errors.append(error)
        worker=threading.Thread(target=connect); closer=threading.Thread(target=close)
        worker.start(); self.assertTrue(entered.wait(2)); closer.start()
        try:
            until=time.monotonic()+2
            while time.monotonic()<until and not self.manager.store.load("operation").cancel_requested: time.sleep(0.01)
            self.assertTrue(self.manager.store.load("operation").cancel_requested)
        finally:
            release.set(); worker.join(3); closer.join(3)
        self.assertFalse(worker.is_alive()); self.assertFalse(closer.is_alive()); self.assertEqual([],errors)
        self.assertTrue(all(result.state=="detached" for result in results))
        self.connector.attach.assert_called_once(); self.connector.terminate.assert_not_called()

    def test_controller_rpc_keeps_attachment_model_scope_and_rejects_wrong_operation(self):
        from engine_room.lifecycle import Controller
        from engine_room.controller_protocol import Dispatcher
        controller=Controller(self.root,self.registry,self.enrollment,actual_host_id="a"*64,now=lambda:1000,interval=60)
        controller.start(); self.addCleanup(controller.close)
        dispatcher=Dispatcher(controller)
        def call(method,params):
            return dispatcher.dispatch(dict(schema=1,request_id="c"*32,controller_id="controller",client_host_id=self.client,method=method,params=params))
        attached=call("attach",dict(operation_id="operation",connection_id="connection",approved_target=controller.attachments.preview("connection",self.client)))
        self.assertTrue(attached["ok"])
        receipt=controller.store.load("operation"); scope=dict(operation_id="operation",operation_key=receipt.operation_key())
        self.connector.model_endpoint.side_effect=self.endpoint
        result=call("model_stream",scope)
        self.assertTrue(result["ok"]); self.assertEqual("chosen",result["result"]["selected_model"])
        for method in ("attachment_pulse","disconnect_attachment","model_stream"):
            self.assertFalse(call(method,dict(scope,operation_key="0"*64))["ok"])
        self.assertTrue(call("attachment_pulse",scope)["ok"])
        self.assertEqual("detached",call("disconnect_attachment",scope)["result"]["state"])
        self.assertFalse(call("model_stream",scope)["ok"])
        self.connector.terminate.assert_not_called(); self.connector.allocate.assert_not_called()

    def test_changed_resource_record_cannot_reuse_original_journal(self):
        receipt=self.attach()
        self.manager.store.save(replace(receipt,resource_id="different-machine"))
        with self.assertRaises(ValueError): self.manager.stream_scope("operation",self.client)
        with self.assertRaises(ValueError): self.manager.disconnect("operation","connection",self.client)
        self.connector.disconnect.assert_not_called(); self.connector.terminate.assert_not_called()

    def test_damaged_journal_is_preserved_and_cannot_replay(self):
        self.attach(); path=self.manager.journal.path("operation"); path.write_text("damaged",encoding="utf-8")
        with self.assertRaises(ValueError): self.attach()
        self.assertEqual("damaged",path.read_text(encoding="utf-8"))
        self.assertEqual(1,self.connector.attach.call_count)

    def test_orphan_damaged_journal_remains_a_reported_recovery_problem(self):
        path=self.manager.journal.path("operation"); path.write_text("damaged",encoding="utf-8")
        self.assertEqual([],self.manager.recover()); self.assertTrue(self.manager.pending())
        with self.assertRaises(ValueError): self.attach()
        self.connector.attach.assert_not_called()

    def test_changed_preview_requires_fresh_confirmation_before_any_start(self):
        preview=self.manager.preview("connection",self.client)
        self.connector.attachment_target.return_value={**preview,"model_id":"changed"}
        with self.assertRaises(ValueError): self.manager.attach("operation","connection",self.client,approved_target=preview)
        self.connector.attach.assert_not_called(); self.assertFalse(self.manager.store.path("operation").exists())
