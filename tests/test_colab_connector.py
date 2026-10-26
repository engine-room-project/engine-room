from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from engine_room.connections import Connection,Connections
from engine_room.connectors import Registry
from engine_room.lifecycle import selection_key
from engine_room.recovery import Observation
from engine_room_connectors.colab import ColabConnector
from test_colab_model_start import receipt
from test_colab_probe import plan


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.api=Mock(); self.runtime=Mock(); self.credentials=Mock(); self.r=receipt()
        self.connection=Connection(self.r.connection_id,"colab",self.r.account_id,"Example","explicit-ref",{})
        self.selection={"accelerator":"A100","high_mem":True,"engine":"llama.cpp"}
        self.connector=ColabConnector(self.root,api=self.api,runtime=self.runtime,credentials=self.credentials,now=lambda:100)
        self.api.account.return_value=self.r.account_id
        self.api.usage.return_value=dict(account_id=self.r.account_id,balance=10,account_rate=3,assignments_count=2,
            rate_scope="account_total",unit="CCU",observed_at=100)
        self.active=Observation(self.r.account_id,self.r.resource_id,self.r.operation_id,"active",True)
        self.api.observe.return_value=self.active; self.api.allocate.return_value=self.active
        self.runtime.status.return_value=dict(status="ready",sampled_at=100,progress="ready")
        self.runtime.read.return_value=dict(state="prepared",selection_key=selection_key(self.selection))
    def test_explicit_preflight_and_rejected_settings_do_not_import_other_accounts(self):
        with patch("engine_room_connectors.colab.sys.platform","linux"),patch("engine_room_connectors.colab.shutil.which",return_value="synthetic-ssh"),patch("engine_room_connectors.colab.metadata.version",return_value="1.9.2"):
            self.assertEqual(self.r.account_id,self.connector.preflight("explicit-ref",{})["account_id"])
            self.api.account.assert_called_once_with("explicit-ref")
            with self.assertRaises(ValueError): self.connector.preflight("explicit-ref",{"implicit_account":True})
        self.credentials.read.assert_not_called()
    def test_full_selection_is_bound_before_one_allocation(self):
        gate=Mock(); self.assertEqual(self.active,self.connector.allocate(self.connection,self.r,self.selection,submit_gate=gate))
        self.api.allocate.assert_called_once_with(self.connection,self.r,"A100",submit_gate=gate,high_mem=True)
        with self.assertRaises(ValueError): self.connector.allocate(self.connection,self.r,self.selection|{"high_mem":False},submit_gate=gate)
        self.assertEqual(1,self.api.allocate.call_count)
    def test_account_telemetry_scope_is_preserved_in_quote_and_health(self):
        quote=self.connector.quote(self.connection,self.selection); self.assertIsNone(quote.price); self.assertEqual("account",quote.rate_scope)
        health=self.connector.health(self.connection,self.r)
        self.assertEqual(("ready",3,"CCU","account"),(health.status,health.rate,health.unit,health.rate_scope))
        self.api.usage.return_value["balance"]=0
        self.assertEqual("failed",self.connector.health(self.connection,self.r).status)
    def test_termination_request_is_not_off_and_only_provider_absence_discards_keys(self):
        self.connector.terminate(self.connection,self.r); self.api.terminate.assert_called_once_with(self.connection,self.r)
        self.runtime.close.assert_called_once_with(self.r); self.runtime.reset_mock()
        self.connector.observe(self.connection,self.r); self.runtime.close.assert_not_called()
        self.api.observe.return_value=replace(self.active,status="absent",owned=False)
        self.connector.observe(self.connection,self.r); self.runtime.close.assert_called_once_with(self.r,discard=True)
    def test_attachment_wrong_account_or_provider_evidence_never_deletes_or_discards(self):
        for changed in (replace(self.r,mode="attachment"),replace(self.r,account_id="unrelated"),replace(self.r,connector_id="other")):
            with self.assertRaises(ValueError): self.connector.terminate(self.connection,changed)
        self.api.terminate.assert_not_called()
        self.api.observe.return_value=replace(self.active,resource_id="unrelated")
        with self.assertRaises(ValueError): self.connector.observe(self.connection,self.r)
        self.runtime.close.assert_not_called()
    def test_unknown_ownership_or_missing_runtime_is_not_off(self):
        self.api.observe.return_value=replace(self.active,status="unknown",owned=False)
        self.assertEqual("unknown",self.connector.health(self.connection,self.r).status)
        self.runtime.status.assert_not_called(); self.api.observe.return_value=self.active
        self.runtime.status.side_effect=ValueError("synthetic missing handle")
        self.assertEqual("unknown",self.connector.health(self.connection,self.r).status)
        self.api.terminate.assert_not_called()
    def test_discovery_adds_both_connectors_without_any_default_connection_or_network(self):
        with patch("engine_room_connectors.colab.state_root",return_value=self.root),patch("engine_room_connectors.runpod.state_root",return_value=self.root),patch("engine_room_connectors.ssh.state_root",return_value=self.root):
            registry=Registry().discover()
        self.assertEqual({"colab","runpod","ssh"},{d.id for d in registry.descriptors()})
        self.assertEqual({},Connections(self.root,registry).read()); self.assertEqual({},registry.errors)
