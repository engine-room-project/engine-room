from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from engine_room.connections import Connection
from engine_room.lifecycle import Health,Quote
from engine_room.private_endpoint import ModelEndpoint
from engine_room.recovery import Observation
from engine_room_connectors.runpod import RunPodConnector
from engine_room_connectors._runpod.pricing import StoragePrices
from engine_room_connectors._runpod.runtime import Runtime
from test_records import rental


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.api=Mock(); self.runtime=Mock(); self.prices=Mock(); self.credentials=Mock()
        self.connector=RunPodConnector(self.temp.name,api=self.api,runtime=self.runtime,prices=self.prices,credentials=self.credentials,now=lambda:1000)
        self.connection=Connection("connection1","runpod","synthetic-account","Synthetic","chosen")
        self.record=replace(rental(),connector_id="runpod",state="active",resource_id="owned",protection_id="controller")
        self.selection=dict(gpu_id="Synthetic GPU",cloud="SECURE",disk_gb=200,engine="llama.cpp")
        self.api.market.return_value={"account_id":"synthetic-account","balance":10,"observed_at":1000,"offers":[{"gpu_id":"Synthetic GPU","gpu_hourly_rate":0.5,"memory_gb":48}]}
        self.prices.read.return_value={"container_usd_per_gb_month":0.1,"network_usd_per_gb_month_under_1tb":0.07,"source":"https://docs.runpod.io/pods/pricing.md","observed_at":1000}
    def test_storage_form_has_explicit_tier_location_and_bounded_size(self):
        form=self.connector.form("storage",self.connection)
        fields={item["name"]:item for item in form["fields"]}
        self.assertEqual({"size_gb","data_center","storage_type"},set(fields))
        self.assertEqual(999,fields["size_gb"]["maximum"])
        self.assertEqual([dict(value="STANDARD",label="Standard")],fields["storage_type"]["choices"])
        self.assertIn("continue",form["help"])
        self.api.market.assert_not_called()

    def test_quote_has_fresh_separate_storage_costs_and_no_cache_capacity_credit(self):
        quote=self.connector.quote(self.connection,self.selection)
        self.assertEqual(0.5,quote.price); self.assertEqual(200*10**9,quote.storage_available_bytes)
        self.assertEqual(0.1,quote.cost_details["container_usd_per_gb_month"])
        self.assertIn("separately billed",quote.cost_details["rate_scope"])
        self.assertEqual("12.8",self.api.market.call_args.kwargs["minimum_cuda"])
        self.assertEqual(quote,quote.validate(1000))
    def test_market_memory_is_required_and_confirmation_bound(self):
        first=self.connector.quote(self.connection,self.selection)
        self.assertEqual(48*1024**3,first.cost_details["gpu_memory_bytes"])
        self.api.market.return_value["offers"][0]["memory_gb"]=24
        self.assertNotEqual(first.confirmation_key(),self.connector.quote(self.connection,self.selection).confirmation_key())
        self.api.market.return_value["offers"][0].pop("memory_gb")
        with self.assertRaises(ValueError): self.connector.quote(self.connection,self.selection)
    def test_storage_rate_change_invalidates_confirmation_key(self):
        first=self.connector.quote(self.connection,self.selection)
        self.prices.read.return_value["container_usd_per_gb_month"]=0.2
        second=self.connector.quote(self.connection,self.selection)
        self.assertNotEqual(first.confirmation_key(),second.confirmation_key())
    def test_saved_volume_is_explicit_verified_and_separately_billed(self):
        self.api.volume_rest.return_value={"id":"chosen-volume","dataCenter":"CA-MTL-1","size":100,"type":"STANDARD"}
        quote=self.connector.quote(self.connection,{**self.selection,"volume_id":"chosen-volume","data_center":"CA-MTL-1"})
        self.assertEqual(200*10**9,quote.storage_available_bytes)
        self.assertTrue(quote.cost_details["network_storage_persists"])
        self.assertEqual(100,quote.cost_details["network_volume_gb"])
        self.assertFalse(any(c.args[1]=="DELETE" for c in self.api.rest.call_args_list))
    def test_unknown_or_premium_storage_tier_never_uses_standard_price(self):
        for tier in (None,"HIGH_PERFORMANCE"):
            self.api.volume_rest.return_value=dict(id="chosen-volume",dataCenter="CA-MTL-1",size=100,type=tier)
            with self.assertRaisesRegex(ValueError,"Standard storage"):
                self.connector.quote(self.connection,{**self.selection,"volume_id":"chosen-volume","data_center":"CA-MTL-1"})
        self.api.create.assert_not_called()
    def test_storage_creation_quote_has_exact_monthly_standard_price_and_no_hourly_guess(self):
        selection=dict(size_gb=50,data_center="TEST-1",storage_type="STANDARD")
        quote=self.connector.storage_quote(self.connection,selection)
        self.assertEqual(3.5,quote.monthly_usd); self.assertEqual("STANDARD",quote.storage_type)
        self.api.verified_account.assert_called_once_with(self.connection)
        with self.assertRaises(ValueError): self.connector.storage_quote(self.connection,{**selection,"storage_type":"HIGH_PERFORMANCE"})
    def test_community_cannot_silently_attach_saved_storage(self):
        with self.assertRaisesRegex(ValueError,"Secure-cloud"):
            self.connector.quote(self.connection,{**self.selection,"cloud":"COMMUNITY","volume_id":"v","data_center":"CA-MTL-1"})
        self.api.market.assert_not_called()
    def test_missing_fresh_storage_prices_refuses_quote(self):
        self.prices.read.side_effect=ValueError("Current storage prices unavailable")
        with self.assertRaises(ValueError): self.connector.quote(self.connection,self.selection)
        self.api.create.assert_not_called()
    def test_different_prepared_selection_cannot_allocate(self):
        self.runtime.payload.return_value={"gpuTypeIds":["Other GPU"],"containerDiskInGb":200,"cloudType":"SECURE"}
        with self.assertRaisesRegex(ValueError,"differs"): self.connector.allocate(self.connection,self.record,self.selection,submit_gate=lambda:None)
        self.api.create.assert_not_called()
    def test_terminal_tunnel_or_model_failure_is_preserved_by_health(self):
        self.api.get_owned.return_value={"desiredStatus":"RUNNING","costPerHr":"0.51"}
        self.runtime.status.return_value={"status":"failed","sampled_at":1000,"progress":"private-tunnel-exited"}
        health=self.connector.health(self.connection,self.record)
        self.assertEqual("failed",health.status); self.assertEqual(0.51,health.rate)
    def test_unconfirmed_delete_does_not_discard_recovery_keys(self):
        self.connector.terminate(self.connection,self.record)
        self.runtime.close.assert_called_once_with(self.record)
        self.runtime.close.reset_mock()
        self.api.observe.return_value=Observation("synthetic-account","owned","op1","absent")
        self.connector.observe(self.connection,self.record)
        self.runtime.close.assert_called_once_with(self.record,discard=True)


class PricingTests(unittest.TestCase):
    def test_current_document_tariffs_are_parsed_without_month_to_hour_guess(self):
        opener=Mock(); response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        response.read.return_value=b"| **Container disk** | \\$0.10/GB/month | Not charged |\n| **Network volume** | \\$0.07/GB/month (< 1TB) |"
        opener.open.return_value=response
        rates=StoragePrices(opener,now=lambda:1000).read()
        self.assertEqual(0.1,rates["container_usd_per_gb_month"]); self.assertEqual(0.07,rates["network_usd_per_gb_month_under_1tb"])
        self.assertEqual(1000,rates["observed_at"])
        self.assertNotIn("hour",rates)


class FakeSSH:
    def __init__(self,directory,*,forward_directory=None):
        self.directory=Path(directory); self.host=None; self.tunnel=None; self.calls=[]; self.forward_directory=Path(forward_directory or directory); self.status_socket=self.forward_directory/"s.sock"
    def generate(self): return {"public_key":"ssh-ed25519 QUJD","host_private_b64":"c3ludGhldGlj"}
    def endpoint(self,host,port): self.host=host
    def run(self,command,*,data=None,timeout=15):
        self.calls.append((command,data))
        if command.startswith("test -f"): return b"READY"
        if command=="nvidia-smi": return b"NVIDIA-SMI CUDA Version: 13.0"
        if command.startswith("nvidia-smi --query"): return b"81920, 8.0"
        return b""
    def forward(self,receipt): self.tunnel=Mock(); self.tunnel.poll.return_value=None; self.calls.append(("forward",None))
    def forward_endpoint(self,role,receipt):
        return ModelEndpoint(str(self.forward_directory/("m.sock" if role=="model" else "s.sock")),receipt.operation_key(),receipt.resource_id,1,2,3)
    def close(self,receipt=None): pass
    def discard_keys(self,receipt=None): pass


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.credentials=Mock(); self.credentials.read.return_value="synthetic-explicit-hf-token"
        self.metadata=Mock()
        self.runtime=Runtime(self.temp.name,self.credentials,ssh_factory=FakeSSH,metadata=self.metadata,now=lambda:1000)
        self.record=replace(rental(),connector_id="runpod",created_at=1000,deadline=2000,protection_id="controller")
        self.connection=Connection("connection1","runpod","synthetic-account","Synthetic","chosen",{"hf_credential_ref":"model-credential"})
        self.selection=dict(gpu_id="Synthetic GPU",cloud="SECURE",disk_gb=200,engine="llama.cpp")
        self.plan=dict(id="example/model",revision="a"*40,context=8192,engine="llama.cpp",files=["model.gguf"],fileSizes={"model.gguf":100},weightBytes=100,overheadBytes=1024**3,kvBytesPerToken=1024)
    def test_preparation_contains_no_account_or_model_credential_value(self):
        self.runtime.prepare(self.connection,self.record,self.selection,self.plan)
        body=self.runtime.payload(self.record)
        self.assertNotIn("synthetic-explicit-hf-token",str(body))
        self.credentials.read.assert_not_called()
        self.assertEqual(["22/tcp"],body["ports"])
        self.assertEqual(0,body["volumeInGb"])
        self.assertIn("@sha256:",body["imageName"])
        self.assertNotIn("HF_TOKEN",body["env"])
    def test_real_setup_transfers_credential_before_start_and_creates_only_local_forward(self):
        self.runtime.prepare(self.connection,self.record,self.selection,self.plan)
        record=replace(self.record,state="active",resource_id="owned")
        api=Mock(); api.get_owned.return_value={"desiredStatus":"RUNNING","publicIp":"8.8.8.8","portMappings":{"22":2222}}
        self.runtime.setup(self.connection,record,self.plan,threading.Event(),api)
        calls=self.runtime.sessions[record.operation_id].calls
        secret_index=next(i for i,(cmd,data) in enumerate(calls) if data==b"synthetic-explicit-hf-token")
        start_index=next(i for i,(cmd,data) in enumerate(calls) if "engine_room.remote_agent" in cmd)
        self.assertLess(secret_index,start_index)
        self.assertTrue(all("synthetic-explicit-hf-token" not in cmd for cmd,data in calls))
        self.assertEqual("forward",calls[-1][0])
    def test_model_endpoint_requires_this_sessions_live_ready_tunnel(self):
        ssh=Mock(); ssh.tunnel.poll.return_value=None
        target=ModelEndpoint(str(Path(self.temp.name)/"model.sock"),self.record.operation_key(),"owned",1,2,3)
        ssh.forward_endpoint.return_value=target
        self.runtime.sessions[self.record.operation_id]=ssh
        self.runtime.status=Mock(return_value=dict(status="ready"))
        self.assertEqual(target,self.runtime.model_endpoint(self.record))
        self.runtime.status.return_value=dict(status="starting")
        with self.assertRaises(ValueError): self.runtime.model_endpoint(self.record)
        self.runtime.status.return_value=dict(status="ready"); ssh.tunnel.poll.return_value=1
        with self.assertRaises(ValueError): self.runtime.model_endpoint(self.record)

    def test_dead_tunnel_is_terminal_in_real_runtime_status(self):
        self.runtime.prepare(self.connection,self.record,self.selection,self.plan)
        ssh=self.runtime.sessions[self.record.operation_id]
        ssh.tunnel=Mock(); ssh.tunnel.poll.return_value=1
        self.assertEqual("failed",self.runtime.status(self.record)["status"])
    def test_terminal_bootstrap_phase_does_not_wait_for_model_deadline(self):
        self.runtime.prepare(self.connection,self.record,self.selection,self.plan)
        ssh=self.runtime.sessions[self.record.operation_id]; ssh.host="8.8.8.8"
        ssh.run=lambda *a,**k:b"Setup failed"
        self.assertEqual("failed",self.runtime.status(self.record)["status"])


if __name__=="__main__": unittest.main()
