from dataclasses import replace
import unittest
from unittest.mock import Mock

from engine_room.connections import Connection
from engine_room.volume_records import VolumeIntent
from engine_room_connectors._runpod.api import RunPodAPI
from engine_room_connectors._runpod.volumes import Volumes


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.credentials=Mock(); self.credentials.read.return_value="synthetic-key"
        self.http=Mock(); self.api=RunPodAPI(self.credentials,self.http); self.volumes=Volumes(self.api)
        self.connection=Connection("connection","runpod","account","Storage account","explicit")
        self.intent=VolumeIntent("operation","connection","runpod","account",50,"TEST-1",1000,"a"*32,("existing",),"submitting")
        self.account=dict(data=dict(myself=dict(id="account",clientBalance=10)))
        self.old=dict(id="existing",name="unrelated",size=50,dataCenter="TEST-1",type="STANDARD")
        self.created=dict(id="new",name=self.intent.marker(),size=50,dataCenter="TEST-1",type="STANDARD")
    def page(self,rows): return dict(networkVolumes=rows,pagination=dict(nextCursor=None,hasNextPage=False))
    def test_one_post_uses_one_account_credential_snapshot_after_final_gate(self):
        self.http.request.side_effect=[self.account,self.page([self.old]),self.created]
        def gate(): self.assertFalse(any(call.args[0]=="POST" and call.args[1].endswith("network-volumes") for call in self.http.request.call_args_list))
        result=self.volumes.create(self.connection,self.intent,submit_gate=gate)
        self.assertTrue(result["verified"]); self.assertEqual("new",result["resource_id"])
        self.credentials.read.assert_called_once_with("explicit")
        self.assertTrue(all(call.args[2]=="synthetic-key" for call in self.http.request.call_args_list))
        posts=[call for call in self.http.request.call_args_list if call.args[1].endswith("network-volumes") and call.args[0]=="POST"]
        self.assertEqual(1,len(posts)); self.assertEqual(dict(name=self.intent.marker(),size=50,dataCenter="TEST-1",type="STANDARD"),posts[0].args[3])
    def test_lost_response_is_not_retried_and_partial_identity_is_retained(self):
        self.http.request.side_effect=[self.account,self.page([self.old]),TimeoutError("synthetic lost reply")]
        with self.assertRaises(TimeoutError): self.volumes.create(self.connection,self.intent,submit_gate=lambda:None)
        self.assertEqual(3,self.http.request.call_count)
        self.http.request.side_effect=[self.account,self.page([self.old]),dict(id="new")]
        result=self.volumes.create(self.connection,self.intent,submit_gate=lambda:None)
        self.assertEqual(dict(resource_id="new",verified=False,source="creation-response"),result)
    def test_gate_or_changed_inventory_refuses_before_billable_post(self):
        for rows in ([self.old],[self.old,self.created]):
            self.http.request.reset_mock(); self.http.request.side_effect=[self.account,self.page(rows)]
            gate=Mock(side_effect=ValueError("synthetic stop"))
            with self.assertRaises(ValueError): self.volumes.create(self.connection,self.intent,submit_gate=gate)
            self.assertEqual(2,self.http.request.call_count)
    def test_reconciliation_never_adopts_single_or_duplicate_name_candidates(self):
        for rows in ([self.old,self.created],[self.old,self.created,{**self.created,"id":"another"}]):
            self.http.request.side_effect=[self.account,self.page(rows)]
            result=self.volumes.reconcile(self.connection,replace(self.intent,state="unresolved"))
            self.assertEqual("unresolved",result["status"]); self.assertIsNone(result["resource_id"])
            self.assertEqual(len(rows)-1,len(result["candidates"]))
    def test_different_account_cannot_interpret_absence_or_identify_a_volume(self):
        self.http.request.side_effect=[dict(data=dict(myself=dict(id="other",clientBalance=10)))]
        with self.assertRaises(ValueError): self.volumes.reconcile(self.connection,replace(self.intent,resource_id="new"))
        self.assertEqual(1,self.http.request.call_count)
    def test_manual_identification_requires_explicit_scope_and_never_deletes(self):
        with self.assertRaises(ValueError): self.volumes.confirm_manual(self.connection,self.intent,"new",confirmed=False)
        self.http.request.assert_not_called()
        self.http.request.side_effect=[self.account,self.created]
        self.assertTrue(self.volumes.confirm_manual(self.connection,self.intent,"new",confirmed=True)["verified"])
        self.assertFalse(any(call.args[0]=="DELETE" for call in self.http.request.call_args_list))
        self.http.request.side_effect=[self.account,self.old]
        with self.assertRaises(ValueError): self.volumes.confirm_manual(self.connection,self.intent,"existing",confirmed=True)
    def test_known_volume_identity_is_not_substituted_and_absence_needs_same_account(self):
        intent=replace(self.intent,resource_id="new",state="known")
        self.http.request.side_effect=[self.account,None]
        self.assertEqual("absent",self.volumes.reconcile(self.connection,intent)["status"])
        self.http.request.side_effect=[self.account,{**self.created,"id":"other"}]
        with self.assertRaises(ValueError): self.volumes.reconcile(self.connection,intent)
    def test_invalid_intents_refuse_before_any_api_call(self):
        for change in (dict(state="intent"),dict(size_gb=True),dict(size_gb=0),dict(resource_id="existing"),dict(nonce="wrong")):
            with self.assertRaises(ValueError): self.volumes.create(self.connection,replace(self.intent,**change),submit_gate=lambda:None)
        self.http.request.assert_not_called()

    def test_inventory_follows_pagination_and_refuses_cycles(self):
        first=dict(networkVolumes=[self.old],pagination=dict(nextCursor="next token",hasNextPage=True))
        self.http.request.side_effect=[self.account,first,self.page([self.created])]
        self.assertEqual(2,len(self.volumes.inventory(self.connection)))
        self.assertIn("cursor=next+token",self.http.request.call_args.args[1])
        self.http.request.side_effect=[self.account,first,first]
        with self.assertRaises(ValueError): self.volumes.inventory(self.connection)
    def test_tier_mismatch_never_confirms_creation_or_manual_recovery(self):
        self.http.request.side_effect=[self.account,self.page([self.old]),{**self.created,"type":"HIGH_PERFORMANCE"}]
        self.assertFalse(self.volumes.create(self.connection,self.intent,submit_gate=lambda:None)["verified"])
        self.http.request.side_effect=[self.account,{**self.created,"type":"HIGH_PERFORMANCE"}]
        with self.assertRaises(ValueError): self.volumes.confirm_manual(self.connection,self.intent,"new",confirmed=True)
