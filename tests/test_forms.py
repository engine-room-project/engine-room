from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.forms import connection_form,field,validate
from engine_room.connections import Connection
from engine_room_connectors.colab import ColabConnector
from engine_room_connectors.runpod import RunPodConnector
import test_controller_transport as protocol


class FormTests(unittest.TestCase):
    def test_fields_are_bounded_data_not_markup_or_callbacks(self):
        original=connection_form()
        for change in ({"script":"synthetic"},{"fields":[field("bad name","Label","text")]},
                {"fields":[field("one","Label","script")]},{"fields":[field("one","Label","choice",choices=[("a","A"),("a","Again")])]},
                {"fields":[field("one","Label","integer",minimum=10,maximum=1)]}):
            with self.assertRaises(ValueError): validate(original|change)
        malicious=deepcopy(original); malicious["fields"][0]["onclick"]="synthetic"
        with self.assertRaises(ValueError): validate(malicious)
    def test_connector_connection_forms_need_no_credentials_or_provider_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            for kind in (ColabConnector,RunPodConnector):
                api=Mock(); connector=kind(Path(folder),api=api,runtime=Mock(),credentials=Mock())
                result=connector.form("connection"); self.assertEqual("credential_ref",result["fields"][0]["kind"])
                self.assertFalse(result["fields"][0]["required"]); self.assertEqual([],api.mock_calls)
    def test_runpod_gpu_choices_only_load_after_explicit_shape_and_preserve_final_quote_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            api=Mock(); api.market.return_value={"offers":[{"gpu_id":"Synthetic GPU"}]}
            connector=RunPodConnector(folder,api=api,runtime=Mock(),credentials=Mock())
            connection=Connection("connection1","runpod","synthetic-account","Example","explicit-ref",{})
            initial=connector.form("selection",connection,{})
            self.assertEqual([],initial["fields"][-1]["choices"]); api.market.assert_not_called()
            result=connector.form("selection",connection,{"engine":"llama.cpp","cloud":"SECURE","disk_gb":100})
            self.assertEqual([{"value":"Synthetic GPU","label":"Synthetic GPU"}],result["fields"][-1]["choices"])
            self.assertEqual("12.8",api.market.call_args.kwargs["minimum_cuda"])
    def test_colab_fields_keep_unknown_cost_and_account_total_scope_explanation(self):
        with tempfile.TemporaryDirectory() as folder:
            api=Mock(); connector=ColabConnector(folder,api=api,runtime=Mock(),credentials=Mock())
            connection=Connection("connection1","colab","synthetic-account","Example","explicit-ref",{})
            result=connector.form("selection",connection,{})
            self.assertEqual({"engine","accelerator","high_mem"},{item["name"] for item in result["fields"]})
            self.assertIn("all assignments",result["help"]); self.assertEqual([],api.mock_calls)


class FormProtocolTests(unittest.TestCase):
    setUp=protocol.ProtocolTests.setUp
    tearDown=protocol.ProtocolTests.tearDown
    call=protocol.ProtocolTests.call
    def test_another_installed_connector_exposes_forms_without_core_id_branch(self):
        self.provider.form=lambda purpose,connection,values:dict(schema=1,fields=[field("region","Region","choice",choices=[("region-one","Example region")])],help="Synthetic connector field")
        result=self.call("connector_form",dict(connector_id="test",purpose="selection",connection_id=self.connection.id))
        self.assertTrue(result["ok"]); self.assertEqual("region",result["result"]["fields"][0]["name"])
        self.assertEqual(0,self.provider.allocations)
        self.provider.account="unrelated"
        self.assertFalse(self.call("connector_form",dict(connector_id="test",purpose="selection",connection_id=self.connection.id))["ok"])
