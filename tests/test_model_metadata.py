import json
import unittest
import urllib.error
from unittest.mock import Mock
from engine_room.model_metadata import ModelMetadata

class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.credentials=Mock(); self.credentials.read.return_value="synthetic-explicit-token"
        self.opener=Mock(); self.head=Mock()
        self.plan=dict(id="example/model",revision="a"*40,context=8192,engine="llama.cpp",files=["model.gguf"],fileSizes={"model.gguf":100})
        self.info=dict(sha="a"*40,siblings=[dict(rfilename="model.gguf",size=100)])
        self.verifier=ModelMetadata(self.credentials,self.opener,self.head)
    def response(self):
        response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps(self.info).encode(); self.opener.open.return_value=response
        head=Mock(); head.status=200; head.__enter__=Mock(return_value=head); head.__exit__=Mock(return_value=False)
        self.head.open.return_value=head
    def test_public_model_never_reads_an_ambient_credential(self):
        self.response(); self.verifier.verify(self.plan)
        self.credentials.read.assert_not_called()
        self.assertNotIn("Authorization",self.head.open.call_args.args[0].headers)
    def test_visible_gated_metadata_does_not_prove_download_access(self):
        self.info["gated"]=True; self.response()
        self.head.open.side_effect=urllib.error.HTTPError("https://huggingface.co",403,"synthetic secret text",{},None)
        with self.assertRaisesRegex(ValueError,"before renting") as error: self.verifier.verify(self.plan,"chosen")
        self.assertNotIn("synthetic secret",str(error.exception))
        self.credentials.read.assert_called_once_with("chosen")
    def test_changed_sizes_refuse_before_download_probe(self):
        self.info["siblings"][0]["size"]=101; self.response()
        with self.assertRaises(ValueError): self.verifier.verify(self.plan)
        self.head.open.assert_not_called()
    def test_signed_https_redirect_is_not_followed(self):
        self.response(); self.head.open.side_effect=urllib.error.HTTPError("https://huggingface.co",302,"redirect",{"Location":"https://cdn.example/model?synthetic-signature"},None)
        self.verifier.verify(self.plan,"chosen")
        self.assertEqual(1,self.head.open.call_count)
