import json
import unittest
import urllib.error
from unittest.mock import Mock,patch

from engine_room.model_discovery import Discovery
import test_controller_transport as protocol


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.credentials=Mock(); self.credentials.read.return_value="synthetic-token"
        self.opener=Mock(); self.discovery=Discovery(self.credentials,self.opener)
        self.config=dict(model_type="llama",max_position_embeddings=8192,num_hidden_layers=2,num_key_value_heads=2,head_dim=64,author="private-author")
        self.info=dict(sha="a"*40,siblings=[dict(rfilename="model.safetensors",size=100)],author="private-author",cardData=dict(email="private-email"))
    def response(self,value):
        response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps(value).encode(); return response
    def replies(self):
        self.opener.open.side_effect=[self.response(self.info),self.response(self.info),self.response(self.config)]
    def test_public_metadata_is_refetched_at_sha_and_projects_only_planner_fields(self):
        self.replies(); result=self.discovery.discover("example/model")
        self.credentials.read.assert_not_called()
        urls=[call.args[0].full_url for call in self.opener.open.call_args_list]
        self.assertIn("/revision/"+"a"*40,urls[1]); self.assertIn("/resolve/"+"a"*40,urls[2])
        self.assertNotIn("private-",json.dumps(result)); self.assertIn("Experimental",result["warning"])
        self.assertEqual(8192,result["config"]["max_position_embeddings"])
    def test_only_explicit_credential_is_used_and_foreign_redirect_is_not_followed(self):
        self.opener.open.side_effect=urllib.error.HTTPError("https://huggingface.co",302,"redirect",{"Location":"https://unrelated.invalid/config"},None)
        with self.assertRaises(ValueError): self.discovery.discover("example/model","chosen")
        self.credentials.read.assert_called_once_with("chosen"); self.assertEqual(1,self.opener.open.call_count)
        self.assertEqual("Bearer synthetic-token",self.opener.open.call_args.args[0].get_header("Authorization"))
    def test_same_origin_config_redirect_preserves_pinning(self):
        redirect=urllib.error.HTTPError("https://huggingface.co",307,"redirect",{"Location":"/api/resolve-cache/models/example/model/"+"a"*40+"/config.json"},None)
        self.opener.open.side_effect=[self.response(self.info),self.response(self.info),redirect,self.response(self.config)]
        result=self.discovery.discover("example/model","chosen")
        self.assertEqual("a"*40,result["info"]["sha"]); self.assertEqual(4,self.opener.open.call_count)
        self.assertEqual("Bearer synthetic-token",self.opener.open.call_args.args[0].get_header("Authorization"))
    def test_same_origin_redirect_to_another_revision_is_refused(self):
        redirect=urllib.error.HTTPError("https://huggingface.co",307,"redirect",{"Location":"/example/model/resolve/main/config.json"},None)
        self.opener.open.side_effect=[self.response(self.info),self.response(self.info),redirect]
        with self.assertRaisesRegex(ValueError,"pinned revision"): self.discovery.discover("example/model")
        self.assertEqual(3,self.opener.open.call_count)
    def test_invalid_identifier_revision_size_or_uncredentialed_private_refuses(self):
        for model in ("../private","https://other.invalid/model","example/model?token=secret"):
            with self.assertRaises(ValueError): self.discovery.discover(model)
        self.opener.open.assert_not_called()
        self.opener.open.side_effect=[self.response(self.info),self.response(self.info|dict(sha="b"*40))]
        with self.assertRaises(ValueError): self.discovery.discover("example/model")
        response=self.response({}); response.read.return_value=b"x"*(2*1024*1024+1); self.opener.open.side_effect=[response]
        with self.assertRaises(ValueError): self.discovery.discover("example/model")
        self.info["private"]=True; self.replies()
        with self.assertRaises(ValueError): self.discovery.discover("example/model")
    def test_gguf_base_config_is_resolved_independently_to_an_immutable_revision(self):
        info=self.info|dict(siblings=[dict(rfilename="model.gguf",size=100)],cardData=dict(base_model="example/base"))
        missing=urllib.error.HTTPError("https://huggingface.co",404,"missing",{},None)
        base=self.info|dict(sha="b"*40)
        self.opener.open.side_effect=[self.response(info),self.response(info),missing,self.response(base),self.response(base),self.response(self.config)]
        result=self.discovery.discover("example/model")
        self.assertEqual("example/base",result["base_model"]); self.assertEqual("b"*40,result["base_revision"])
        self.assertEqual(8192,result["base_config"]["max_position_embeddings"])


class DiscoveryProtocolTests(unittest.TestCase):
    setUp=protocol.ProtocolTests.setUp
    tearDown=protocol.ProtocolTests.tearDown
    call=protocol.ProtocolTests.call
    def test_named_account_is_verified_before_read_only_discovery(self):
        with patch("engine_room.controller_protocol.Discovery") as factory:
            factory.return_value.discover.return_value={"synthetic":True}
            result=self.call("model_discover",dict(connection_id=self.connection.id,model_id="example/model"))
            self.assertTrue(result["ok"]); factory.return_value.discover.assert_called_once_with("example/model",None,None)
            self.assertEqual(0,self.provider.allocations)
            factory.reset_mock(); self.provider.account="changed"
            self.assertFalse(self.call("model_discover",dict(connection_id=self.connection.id,model_id="example/model"))["ok"])
            factory.assert_not_called()
