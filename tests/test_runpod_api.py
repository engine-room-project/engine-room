from dataclasses import replace
import unittest
from unittest.mock import Mock

from engine_room.connections import Connection
from engine_room_connectors._runpod.api import RunPodAPI
from test_records import rental


class RunPodAPITests(unittest.TestCase):
    def setUp(self):
        self.credentials=Mock(); self.credentials.read.return_value="synthetic-key"
        self.http=Mock(); self.api=RunPodAPI(self.credentials,self.http,now=lambda:1000)
        self.connection=Connection("connection1","runpod","synthetic-account","Synthetic","chosen-credential")
        self.record=replace(rental(),connector_id="runpod",state="active",resource_id="owned-pod",protection_id="controller",allocation_submitted=True)
        self.account={"data":{"myself":{"id":"synthetic-account","clientBalance":10}}}
        self.pod={"id":"owned-pod","name":self.api.operation_name(self.record),"env":self.api.markers(self.record),"volumeInGb":0}
    def respond(self,*responses): self.http.request.side_effect=list(responses)
    def allocation(self):
        record=replace(self.record,state="allocating",resource_id=None,created_at=1000,deadline=2000)
        payload=dict(name=self.api.operation_name(record),volumeInGb=0,gpuCount=1,computeType="GPU",ports=["22/tcp"],interruptible=False,imageName="example/runtime@sha256:"+"a"*64,env=self.api.markers(record))
        return record,payload
    def test_partial_create_response_retains_identity_without_claiming_ownership(self):
        record,payload=self.allocation(); self.respond(self.account,{"id":"new-pod"})
        result=self.api.create(self.connection,record,payload,submit_gate=lambda:None)
        self.assertEqual("new-pod",result.resource_id); self.assertFalse(result.owned)
        self.assertEqual(1,sum(c.args[0]=="POST" and c.args[1].endswith("/pods") for c in self.http.request.call_args_list))
    def test_gate_refusal_after_account_verification_never_posts(self):
        record,payload=self.allocation(); self.respond(self.account)
        gate=Mock(side_effect=ValueError("Stopped before POST"))
        with self.assertRaises(ValueError): self.api.create(self.connection,record,payload,submit_gate=gate)
        self.assertEqual(1,self.http.request.call_count); gate.assert_called_once()

    def test_failed_create_is_never_retried(self):
        record,payload=self.allocation(); self.respond(self.account,TimeoutError("synthetic timeout"))
        with self.assertRaises(TimeoutError): self.api.create(self.connection,record,payload,submit_gate=lambda:None)
        self.assertEqual(2,self.http.request.call_count)
    def test_secret_environment_and_expired_protection_refuse_allocation(self):
        record,payload=self.allocation(); payload["env"]["HF_TOKEN"]="synthetic"
        with self.assertRaises(ValueError): self.api.create(self.connection,record,payload,submit_gate=lambda:None)
        self.http.request.assert_not_called()
        record,payload=self.allocation()
        with self.assertRaises(ValueError): self.api.create(self.connection,replace(record,deadline=1000),payload,submit_gate=lambda:None)
        self.http.request.assert_not_called()

    def test_identity_query_requests_no_personal_account_profile(self):
        self.respond(self.account)
        self.assertEqual("synthetic-account",self.api.account("chosen-credential")["id"])
        query=self.http.request.call_args.args[3]["query"]
        self.assertIn("id clientBalance",query)
        self.assertNotIn("email",query)
        self.credentials.read.assert_called_with("chosen-credential")
    def test_changed_account_cannot_interpret_resource_404_or_delete(self):
        self.respond({"data":{"myself":{"id":"other-account","clientBalance":5}}})
        with self.assertRaisesRegex(ValueError,"another account"): self.api.observe(self.connection,self.record)
        self.assertEqual(1,self.http.request.call_count)
    def test_owned_delete_is_scoped_to_one_identified_pod(self):
        self.respond(self.account,self.pod,None)
        self.api.terminate(self.connection,self.record)
        calls=self.http.request.call_args_list
        self.assertEqual("DELETE",calls[-1].args[0])
        self.assertEqual("https://rest.runpod.io/v1/pods/owned-pod",calls[-1].args[1])
        self.assertEqual(3,len(calls))
    def test_one_credential_snapshot_binds_account_check_and_resource_calls(self):
        self.credentials.read.side_effect=["synthetic-original-key","synthetic-replacement-key"]
        self.respond(self.account,self.pod,None)
        self.api.terminate(self.connection,self.record)
        self.credentials.read.assert_called_once_with("chosen-credential")
        self.assertTrue(all(c.args[2]=="synthetic-original-key" for c in self.http.request.call_args_list))

    def test_receipt_from_another_connection_is_rejected_before_any_request(self):
        with self.assertRaisesRegex(ValueError,"original connection"):
            self.api.observe(replace(self.connection,account_id="other-account"),self.record)
        self.http.request.assert_not_called()
        self.credentials.read.assert_not_called()

    def test_market_filters_unknown_stock_and_prices_and_is_account_bound(self):
        data={"data":{"myself":{"id":"synthetic-account","clientBalance":7},"gpuTypes":[
            {"id":"Synthetic GPU","memoryInGb":48,"lowestPrice":{"stockStatus":"High","uninterruptablePrice":0.5}},
            {"id":"Unavailable","memoryInGb":48,"lowestPrice":{"stockStatus":None,"uninterruptablePrice":0.2}},
            {"id":"No price","memoryInGb":48,"lowestPrice":{"stockStatus":"Low","uninterruptablePrice":None}}]}}
        self.respond(data)
        market=self.api.market(self.connection,cloud="COMMUNITY",disk_gb=160)
        self.assertEqual(["Synthetic GPU"],[o["gpu_id"] for o in market["offers"]])
        self.assertEqual("gpu_only",market["offers"][0]["charge_scope"])
        self.assertEqual(1000,market["observed_at"])
        self.assertEqual(7,market["balance"])
        variables=self.http.request.call_args.args[3]["variables"]["pricing"]
        self.assertFalse(variables["secureCloud"])
        self.assertEqual(160,variables["totalDisk"])
        self.credentials.read.assert_called_once_with("chosen-credential")

    def test_market_honors_selected_storage_data_center_and_refuses_other_account(self):
        self.respond({"data":{"myself":{"id":"other-account","clientBalance":5},"gpuTypes":[]}})
        with self.assertRaisesRegex(ValueError,"account differs"):
            self.api.market(self.connection,cloud="SECURE",disk_gb=100,data_center="CA-MTL-1")
        self.assertEqual("CA-MTL-1",self.http.request.call_args.args[3]["variables"]["pricing"]["dataCenterId"])

    def test_same_name_is_insufficient_ownership(self):
        unrelated={**self.pod,"env":{}}
        self.respond(self.account,unrelated)
        with self.assertRaisesRegex(ValueError,"ownership"): self.api.terminate(self.connection,self.record)
        self.assertFalse(any(c.args[0]=="DELETE" for c in self.http.request.call_args_list))
    def test_attachments_and_changed_persistent_storage_are_not_deleted(self):
        attachment=replace(self.record,mode="attachment",deadline=None)
        self.respond(self.account)
        with self.assertRaisesRegex(ValueError,"disposable"): self.api.terminate(self.connection,attachment)
        self.http.request.reset_mock()
        self.respond(self.account,{**self.pod,"volumeInGb":10})
        with self.assertRaisesRegex(ValueError,"storage changed"): self.api.terminate(self.connection,self.record)
        self.assertFalse(any(c.args[0]=="DELETE" for c in self.http.request.call_args_list))
    def test_known_absence_requires_same_account_confirmation(self):
        self.respond(self.account,None)
        self.assertEqual("absent",self.api.observe(self.connection,self.record).status)
        self.assertTrue(self.http.request.call_args.kwargs["allow_missing"])
    def test_pending_no_match_stays_unknown_and_unrelated_resources_coexist(self):
        pending=replace(self.record,resource_id=None,state="allocating")
        unrelated={"id":"unrelated-pod","name":"other-work","env":{}}
        self.respond(self.account,[unrelated])
        result=self.api.reconcile(self.connection,pending)
        self.assertEqual("unknown",result.status)
        self.assertFalse(any(c.args[0]=="DELETE" for c in self.http.request.call_args_list))
    def test_positive_markers_reconcile_lost_allocation_response(self):
        pending=replace(self.record,resource_id=None,state="allocating")
        self.respond(self.account,[self.pod])
        result=self.api.reconcile(self.connection,pending)
        self.assertEqual("owned-pod",result.resource_id); self.assertTrue(result.owned)
    def test_ambiguous_matches_preserve_record_for_manual_reconciliation(self):
        pending=replace(self.record,resource_id=None,state="allocating")
        self.respond(self.account,[self.pod,{**self.pod,"id":"second-owned-pod"}])
        with self.assertRaisesRegex(ValueError,"More than one"): self.api.reconcile(self.connection,pending)


if __name__=="__main__": unittest.main()
