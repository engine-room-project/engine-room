from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from engine_room.controller_protocol import Dispatcher
from engine_room.desktop_bridge import Bridge
from engine_room.desktop_storage import DesktopStorage
from engine_room.lifecycle import Controller
import test_persistent_storage as storage_fixture


class DesktopStorageTests(unittest.TestCase):
    submit=storage_fixture.StorageTests.submit
    def setUp(self):
        storage_fixture.StorageTests.setUp(self)
        self.controller=Controller(self.root,self.registry,self.enrollment,actual_host_id="a"*64,now=lambda:1000,interval=60)
        self.controller.start(); self.addCleanup(self.controller.close)
        self.dispatcher=Dispatcher(self.controller); self.calls=[]
        self.client=SimpleNamespace(endpoint=SimpleNamespace(controller_id="controller",client_host_id="b"*64),call=self.call)
        self.access=DesktopStorage(self.client,self.root/"desktop",now=lambda:1000)
        self.request=dict(connection_id="connection",selection=self.selection,approved_quote=asdict(self.quote),continuing_costs_confirmed=True)
        self.connector.storage_reconcile.side_effect=lambda connection,intent:dict(status="observed" if intent.resource_id else "unresolved",resource_id=intent.resource_id,candidates=[])
    def call(self,method,params=None):
        self.calls.append((method,params))
        if method=="storage_create":
            paths=list(self.access.operations.root.glob("*.json")); self.assertEqual(1,len(paths))
            proof=self.access.load(paths[0].stem); self.assertEqual("submitted",proof["state"]); self.assertIsNone(proof["record"])
        response=self.dispatcher.dispatch(dict(schema=1,request_id="c"*32,controller_id="controller",client_host_id="b"*64,method=method,params=params or {}))
        if not response["ok"]: raise RuntimeError("Synthetic controller refusal")
        return response["result"]
    def begin(self): return self.access.begin(self.request,confirmed=True)
    def operation(self): return next(self.access.operations.root.glob("*.json")).stem
    def test_actual_core_submission_links_exact_reviewed_quote_and_records_history(self):
        record=self.begin(); proof=self.access.load(record["operation_id"])
        self.assertEqual("known",proof["state"]); self.assertEqual(record,proof["record"])
        self.assertEqual(self.quote.key(),self.manager.read(record["operation_id"])[3].key())
        result=self.access.recover(record["operation_id"])
        self.assertEqual("observed",result["observation"]["status"])
        self.assertFalse(result["record"]["fresh_provider_observation"])
        self.connector.storage_create.assert_called_once(); self.connector.terminate.assert_not_called()
    def test_no_confirmation_or_stale_quote_cannot_submit(self):
        with self.assertRaises(ValueError): self.access.begin(self.request,confirmed=False)
        bad=deepcopy(self.request); bad["continuing_costs_confirmed"]=False
        with self.assertRaises(ValueError): self.access.begin(bad,confirmed=True)
        bad=deepcopy(self.request); bad["approved_quote"]["observed_at"]=1
        with self.assertRaises(ValueError): self.access.begin(bad,confirmed=True)
        self.assertEqual([],self.calls); self.assertEqual([],list(self.access.operations.root.glob("*.json")))
    def test_lost_reply_after_creation_finds_original_record_without_replay(self):
        original=self.call
        def lost(method,params=None):
            result=original(method,params)
            if method=="storage_create": raise RuntimeError("Synthetic lost reply")
            return result
        self.client.call=lost
        with self.assertRaises(RuntimeError): self.begin()
        operation=self.operation(); self.assertIsNone(self.access.load(operation)["record"])
        with self.assertRaises(ValueError): self.begin()
        self.client.call=original
        result=self.access.recover(operation)
        self.assertEqual("known",result["record"]["state"])
        self.connector.storage_create.assert_called_once()
    def test_missing_controller_journal_stays_pending_until_explicit_start_denial(self):
        original=self.call
        def lost(method,params=None):
            if method=="storage_create": raise RuntimeError("Synthetic undelivered request")
            return original(method,params)
        self.client.call=lost
        with self.assertRaises(RuntimeError): self.begin()
        operation=self.operation(); self.client.call=original
        with self.assertRaises(ValueError): self.access.recover(operation)
        self.assertEqual("submitted",self.access.load(operation)["state"])
        result=self.access.abandon(operation,confirmed=True)
        self.assertFalse(result["creation_may_complete"]); self.assertEqual("closed",self.access.load(operation)["state"])
        self.connector.storage_create.assert_not_called()
        with self.assertRaises(ValueError): self.manager.create(operation,"connection",self.selection,self.quote,"b"*64,continuing_costs_confirmed=True)
    def test_manual_candidate_selection_is_explicit_and_never_automatic(self):
        def lost(connection,intent,*,submit_gate): submit_gate(); raise TimeoutError()
        self.connector.storage_create.side_effect=lost
        record=self.begin(); operation=record["operation_id"]
        self.connector.storage_reconcile.side_effect=None
        self.connector.storage_reconcile.return_value=dict(status="unresolved",resource_id=None,candidates=[dict(id="candidate")])
        result=self.access.recover(operation)
        self.assertIsNone(result["record"]["resource_id"])
        before=len(self.calls)
        with self.assertRaises(ValueError): self.access.recover(operation,resource_id="candidate",confirmed=False)
        self.assertEqual(before,len(self.calls))
        self.connector.storage_identify.return_value=dict(resource_id="candidate",verified=True,source="explicit-manual-identification")
        result=self.access.recover(operation,resource_id="candidate",confirmed=True)
        self.assertEqual("known",result["record"]["state"]); self.assertEqual("candidate",result["record"]["resource_id"])
        self.connector.terminate.assert_not_called()
    def test_changed_reply_preserves_pending_intent_without_accepting_new_price(self):
        original=self.call
        def changed(method,params=None):
            result=original(method,params)
            if method=="storage_create": result["quote"]["monthly_usd"]=999
            return result
        self.client.call=changed
        with self.assertRaises(ValueError): self.begin()
        self.assertEqual("submitted",self.access.load(self.operation())["state"])
        self.assertIsNone(self.access.load(self.operation())["record"])
    def test_contradictory_provider_observation_cannot_replace_saved_evidence(self):
        record=self.begin(); original=self.call
        def changed(method,params=None):
            result=original(method,params)
            if method=="storage_recover": result["observation"]["resource_id"]="unrelated"
            return result
        self.client.call=changed
        with self.assertRaises(ValueError): self.access.recover(record["operation_id"])
        self.assertEqual(record,self.access.load(record["operation_id"])["record"])
        self.connector.storage_create.assert_called_once()

    def test_other_controller_cannot_recover_original_local_intent(self):
        record=self.begin(); before=len(self.calls)
        self.client.endpoint.controller_id="different"
        with self.assertRaises(ValueError): self.access.recover(record["operation_id"])
        self.assertEqual(before,len(self.calls))
    def test_late_unresolved_reply_cannot_erase_known_resource_identity(self):
        record=self.begin(); old=deepcopy(record)
        old.update(state="unresolved",resource_id=None,confirmation_source=None)
        result=self.access.apply(record["operation_id"],old)
        self.assertEqual("known",result["state"]); self.assertEqual("new-volume",result["resource_id"])
    def test_local_index_is_paged_and_damage_does_not_hide_valid_history(self):
        self.begin(); self.access.operations.path("damaged").write_text("damaged",encoding="utf-8")
        first=self.access.listing(limit=1); second=self.access.listing(after=first["next_cursor"],limit=1)
        rows=first["records"]+second["records"]
        self.assertEqual(1,len([row for row in rows if row.get("damaged")]))
        self.assertEqual(1,len([row for row in rows if row.get("state")=="known"]))
    def test_bridge_creation_requires_dedicated_durable_action_and_keeps_raw_rpc_blocked(self):
        factory=Mock(); factory.read.return_value=self.client
        bridge=Bridge(self.root,client_type=factory)
        self.access=DesktopStorage(self.client,self.root/"storage",now=lambda:1000)
        from unittest.mock import patch
        with self.assertRaises(ValueError):
            bridge.dispatch(dict(action="controller",params=dict(method="storage_create")))
        self.assertEqual([],self.calls)
        with patch("engine_room.desktop_bridge.DesktopStorage",return_value=self.access):
            record=bridge.dispatch(dict(action="storage_begin",params=dict(request=self.request,confirmed=True)))
            self.assertEqual("known",record["state"])
            page=bridge.dispatch(dict(action="storage_local_records",params={}))
            self.assertEqual(record,page["records"][0]["record"])
            recovered=bridge.dispatch(dict(action="storage_recover_local",params=dict(operation_id=record["operation_id"])))
            self.assertEqual("observed",recovered["observation"]["status"])
        self.connector.storage_create.assert_called_once()
