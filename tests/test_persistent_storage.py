from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.connections import Connection,Connections
from engine_room.connectors import Descriptor,Registry
from engine_room.persistent_storage import PersistentStorage
from engine_room.protection import Enrollment
from engine_room.volume_records import StorageQuote


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.connector=Mock(); self.connector.descriptor=Descriptor("synthetic","Synthetic storage","Explicit credential",capabilities=("persistent_storage",))
        self.registry=Registry(); self.registry.register(self.connector)
        self.connections=Connections(self.root,self.registry)
        self.connection=Connection("connection","synthetic","account","Named storage","explicit",{})
        self.connections._save({self.connection.id:self.connection})
        self.enrollment=Enrollment("controller","a"*64,"b"*64,True)
        self.manager=PersistentStorage(self.connections,self.registry,self.enrollment,"a"*64,now=lambda:1000)
        self.selection=dict(size_gb=50,data_center="TEST-1",storage_type="STANDARD")
        self.quote=StorageQuote("account",50,"TEST-1","STANDARD",3.5,1000,"https://storage.invalid/pricing")
        self.connector.storage_quote.return_value=self.quote
        self.connector.storage_inventory.return_value=[dict(id="unrelated")]
        self.connector.storage_create.side_effect=self.submit
    def submit(self,connection,intent,*,submit_gate):
        value,saved,_,_=self.manager.read(intent.operation_id)
        self.assertEqual(intent,saved); self.assertFalse(value["submission_claimed"])
        submit_gate()
        self.assertTrue(self.manager.read(intent.operation_id)[0]["submission_claimed"])
        return dict(resource_id="new-volume",verified=True,source="creation-response")
    def create(self,**kwargs):
        return self.manager.create("operation","connection",self.selection,self.quote,"b"*64,continuing_costs_confirmed=True,**kwargs)
    def test_intent_precedes_one_submission_and_retry_never_replays(self):
        result=self.create(); self.assertEqual("known",result["intent"]["state"])
        self.assertEqual(result,self.create()); self.connector.storage_create.assert_called_once()
        self.connector.terminate.assert_not_called()
    def test_lost_reply_stays_unresolved_and_name_candidates_are_not_adopted(self):
        def lost(*args,submit_gate,**kwargs): submit_gate(); raise TimeoutError("synthetic lost response")
        self.connector.storage_create.side_effect=lost
        result=self.create(); self.assertTrue(result["submission_claimed"]); self.assertIsNone(result["intent"]["resource_id"])
        self.assertEqual("unresolved",self.create()["intent"]["state"]); self.connector.storage_create.assert_called_once()
        self.connector.storage_reconcile.return_value=dict(status="unresolved",resource_id=None,candidates=[dict(id="candidate")])
        result=self.manager.recover("operation","b"*64)
        self.assertEqual("unresolved",result["journal"]["intent"]["state"]); self.assertIsNone(result["journal"]["intent"]["resource_id"])
    def test_partial_response_identity_can_be_verified_without_name_adoption(self):
        def partial(*args,submit_gate,**kwargs): submit_gate(); return dict(resource_id="new-volume",verified=False,source="creation-response")
        self.connector.storage_create.side_effect=partial; self.create()
        self.connector.storage_reconcile.return_value=dict(status="observed",resource_id="new-volume",candidates=[])
        self.assertEqual("known",self.manager.recover("operation","b"*64)["journal"]["intent"]["state"])
    def test_failed_gate_storage_write_prevents_submission_claim_and_allows_safe_abandonment(self):
        original=self.manager.save
        def save(value):
            if value["submission_claimed"]: raise OSError("synthetic disk failure")
            return original(value)
        self.manager.save=save
        result=self.create(); self.assertFalse(result["submission_claimed"])
        result=self.manager.abandon_unsubmitted("operation","b"*64); self.assertTrue(result["closed_without_submission"])
        self.create(); self.assertEqual(1,self.connector.storage_create.call_count)
    def test_submitted_storage_cannot_be_abandoned_as_if_it_never_existed(self):
        self.create()
        with self.assertRaises(ValueError): self.manager.abandon_unsubmitted("operation","b"*64)
        self.connector.terminate.assert_not_called()
    def test_price_change_or_missing_explicit_cost_approval_refuses_before_intent(self):
        self.connector.storage_quote.return_value=replace(self.quote,monthly_usd=4)
        with self.assertRaises(ValueError): self.create()
        self.assertFalse(self.manager.records.path("operation").exists())
        with self.assertRaises(ValueError): self.manager.create("operation","connection",self.selection,self.quote,"b"*64,continuing_costs_confirmed=False)
        self.connector.storage_create.assert_not_called()
    def test_restart_retains_no_replay_and_original_connection_scope(self):
        self.create(); self.connector.storage_create.reset_mock()
        restarted=PersistentStorage(self.connections,self.registry,self.enrollment,"a"*64,now=lambda:1000)
        self.assertEqual("known",restarted.create("operation","connection",self.selection,self.quote,"b"*64,continuing_costs_confirmed=True)["intent"]["state"])
        self.connector.storage_create.assert_not_called()
        self.connector.storage_reconcile.side_effect=ValueError("different account")
        with self.assertRaises(ValueError): restarted.recover("operation","b"*64)
        self.assertEqual("known",restarted.read("operation")[1].state)
    def test_explicit_manual_identification_records_verified_original_resource(self):
        def lost(*args,submit_gate,**kwargs): submit_gate(); raise TimeoutError()
        self.connector.storage_create.side_effect=lost; self.create()
        self.connector.storage_identify.return_value=dict(resource_id="selected",verified=True,source="explicit-manual-identification")
        result=self.manager.recover("operation","b"*64,resource_id="selected",confirmed=True)
        self.assertEqual("selected",result["journal"]["intent"]["resource_id"])
        self.assertEqual("known",result["journal"]["intent"]["state"])
    def test_damaged_journal_is_preserved_and_blocks_another_creation(self):
        self.create(); path=self.manager.records.path("operation"); path.write_text("damaged",encoding="utf-8")
        with self.assertRaises(ValueError): self.manager.create("another","connection",self.selection,self.quote,"b"*64,continuing_costs_confirmed=True)
        self.assertEqual("damaged",path.read_text(encoding="utf-8")); self.assertEqual(1,self.connector.storage_create.call_count)

    def test_unconfirmed_manual_recovery_or_known_id_substitution_refuses_before_provider(self):
        self.create()
        with self.assertRaises(ValueError): self.manager.recover("operation","b"*64,resource_id="new-volume",confirmed=False)
        with self.assertRaises(ValueError): self.manager.recover("operation","b"*64,resource_id="other",confirmed=True)
        self.connector.storage_identify.assert_not_called()

    def test_write_failure_after_provider_response_keeps_claim_and_never_replays(self):
        original=self.manager.save
        def save(value):
            if value["intent"]["resource_id"] is not None: raise OSError("synthetic failed response journal")
            return original(value)
        self.manager.save=save
        with self.assertRaises(OSError): self.create()
        saved=self.manager.read("operation")[0]
        self.assertTrue(saved["submission_claimed"]); self.assertIsNone(saved["intent"]["resource_id"])
        self.create(); self.connector.storage_create.assert_called_once()
    def test_changed_connection_before_final_gate_prevents_submit_claim(self):
        def changed(connection,intent,*,submit_gate):
            self.connections._save({connection.id:replace(connection,credential_ref="rotated")})
            submit_gate()
            self.fail("Gate must not authorize a changed connection")
        self.connector.storage_create.side_effect=changed
        result=self.create(); self.assertFalse(result["submission_claimed"])
        self.assertEqual("unresolved",result["intent"]["state"])

    def test_connection_change_during_quote_cannot_create_mismatched_journal(self):
        def quote(*args):
            self.connections._save({self.connection.id:replace(self.connection,credential_ref="rotated")})
            return self.quote
        self.connector.storage_quote.side_effect=quote
        with self.assertRaises(ValueError): self.create()
        self.assertFalse(self.manager.records.path("operation").exists())
        self.connector.storage_create.assert_not_called()

    def test_recovery_listing_is_paged_and_damaged_records_do_not_hide_healthy_records(self):
        self.create(); self.manager.records.path("damaged").write_text("damaged",encoding="utf-8")
        page=self.manager.listing(limit=1); self.assertEqual(1,len(page["records"]))
        second=self.manager.listing(after=page["next_cursor"],limit=1)
        rows=page["records"]+second["records"]
        self.assertEqual(1,len([row for row in rows if row.get("damaged")]))
        healthy=next(row for row in rows if not row.get("damaged"))
        self.assertEqual("known",healthy["state"]); self.assertFalse(healthy["fresh_provider_observation"])
        self.assertNotIn("connection",healthy); self.assertNotIn("credential_ref",str(healthy))
    def test_storage_form_requires_capability_and_original_account(self):
        from engine_room.lifecycle import Controller
        from engine_room.controller_protocol import Dispatcher
        controller=Controller(self.root,self.registry,self.enrollment,actual_host_id="a"*64,now=lambda:1000,interval=60)
        controller.start(); self.addCleanup(controller.close); dispatcher=Dispatcher(controller)
        params=dict(connector_id="synthetic",purpose="storage",connection_id="connection")
        self.connector.account_identity.return_value="account"
        self.connector.form.return_value=dict(schema=1,fields=[],help="Explicit storage choices")
        def call():
            return dispatcher.dispatch(dict(schema=1,request_id="c"*32,controller_id="controller",client_host_id="b"*64,method="connector_form",params=params))
        self.assertTrue(call()["ok"])
        self.connector.form.assert_called_once_with("storage",self.connection,{})
        self.connector.form.reset_mock(); self.connector.account_identity.return_value="other-account"
        self.assertFalse(call()["ok"]); self.connector.form.assert_not_called()
        self.connector.account_identity.return_value="account"
        self.connector.descriptor=replace(self.connector.descriptor,capabilities=())
        self.assertFalse(call()["ok"]); self.connector.form.assert_not_called()
        self.connector.storage_create.assert_not_called()

    def test_controller_storage_rpc_is_scoped_and_does_not_return_raw_connection_settings(self):
        from dataclasses import asdict
        from engine_room.lifecycle import Controller
        from engine_room.controller_protocol import Dispatcher
        controller=Controller(self.root,self.registry,self.enrollment,actual_host_id="a"*64,now=lambda:1000,interval=60)
        controller.start(); self.addCleanup(controller.close); dispatcher=Dispatcher(controller)
        def call(method,params):
            return dispatcher.dispatch(dict(schema=1,request_id="c"*32,controller_id="controller",client_host_id="b"*64,method=method,params=params))
        quoted=call("storage_quote",dict(connection_id="connection",selection=self.selection))
        self.assertTrue(quoted["ok"])
        response=call("storage_create",dict(operation_id="operation",connection_id="connection",selection=self.selection,approved_quote=quoted["result"],continuing_costs_confirmed=True))
        self.assertTrue(response["ok"]); result=response["result"]
        self.assertEqual("known",result["state"]); self.assertNotIn("credential_ref",str(result)); self.assertNotIn("settings",result)
        scope=dict(operation_id="operation",operation_key=result["operation_key"])
        self.assertTrue(call("storage_status",scope)["ok"])
        for method in ("storage_status","storage_recover","storage_close_unsubmitted"):
            self.assertFalse(call(method,dict(scope,operation_key="0"*64))["ok"])
        self.connector.storage_reconcile.assert_not_called()
        self.assertFalse(call("storage_close_unsubmitted",scope)["ok"])
        denial=dict(operation_id="future",connection_id="connection",confirmed=False)
        self.assertFalse(call("storage_abandon",denial)["ok"])
        self.assertFalse(controller.storage.denials.path("future").exists())
        denied=call("storage_abandon",dict(denial,confirmed=True))
        self.assertTrue(denied["ok"]); self.assertFalse(denied["result"]["creation_may_complete"])
        self.connector.terminate.assert_not_called()

    def test_abandon_before_journal_forbids_delayed_create_and_survives_restart(self):
        result=self.manager.abandon("operation","connection","b"*64)
        self.assertTrue(result["new_submissions_forbidden"]); self.assertFalse(result["creation_may_complete"])
        self.assertIsNone(result["record"])
        restarted=PersistentStorage(self.connections,self.registry,self.enrollment,"a"*64,now=lambda:1000)
        with self.assertRaises(ValueError): restarted.create("operation","connection",self.selection,self.quote,"b"*64,continuing_costs_confirmed=True)
        self.connector.storage_create.assert_not_called(); self.connector.storage_quote.assert_not_called()
    def test_abandon_during_provider_preflight_prevents_final_submission(self):
        submissions=[]
        def preflight(connection,intent,*,submit_gate):
            result=self.manager.abandon(intent.operation_id,connection.id,"b"*64)
            self.assertFalse(result["creation_may_complete"])
            submit_gate(); submissions.append("must-not-submit")
        self.connector.storage_create.side_effect=preflight
        result=self.create()
        self.assertTrue(result["closed_without_submission"]); self.assertFalse(result["submission_claimed"])
        self.assertEqual([],submissions)
    def test_abandon_after_submission_keeps_creation_uncertain_and_never_deletes(self):
        def submitted(connection,intent,*,submit_gate):
            submit_gate()
            result=self.manager.abandon(intent.operation_id,connection.id,"b"*64)
            self.assertTrue(result["creation_may_complete"]); self.assertFalse(result["record"]["closed_without_submission"])
            return dict(resource_id="new-volume",verified=True,source="creation-response")
        self.connector.storage_create.side_effect=submitted
        self.assertEqual("known",self.create()["intent"]["state"])
        self.connector.terminate.assert_not_called()
    def test_abandon_wrong_original_connection_cannot_change_known_operation(self):
        self.create()
        with self.assertRaises(ValueError): self.manager.abandon("operation","different","b"*64)
        self.assertFalse(self.manager.denials.path("operation").exists())
