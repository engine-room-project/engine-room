import io
import importlib.metadata
import sys
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch

from engine_room.remote_agent import child_environment,model_identity,start_model,status


class RemoteAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    @unittest.skipIf(os.name=="nt","Remote supervisor uses POSIX private-file permissions")
    def test_credential_is_consumed_before_model_start_and_not_put_in_arguments(self):
        secret=self.root/".hfkey"; secret.write_text("synthetic-explicit-hf-token"); secret.chmod(0o600)
        def launched(args,**kwargs):
            self.assertFalse(secret.exists())
            self.assertNotIn("synthetic-explicit-hf-token",repr(args))
            self.assertEqual("synthetic-explicit-hf-token",kwargs["env"]["HF_TOKEN"])
            self.assertEqual(subprocess.DEVNULL,kwargs["stdout"])
            self.assertEqual(subprocess.DEVNULL,kwargs["stderr"])
            return Mock()
        with patch("engine_room.remote_agent.subprocess.Popen",side_effect=launched): start_model(self.root)
    def test_ambient_account_token_is_not_inherited(self):
        with patch.dict(os.environ,{"HF_TOKEN":"synthetic-other-app-token","HF_ENDPOINT":"https://other.invalid"}):
            env=child_environment(self.root)
        self.assertNotIn("HF_TOKEN",env)
        self.assertEqual("https://huggingface.co",env["HF_ENDPOINT"])
        self.assertEqual(self.root,Path(env["HF_HOME"]).parent)
        self.assertTrue(Path(env["HF_HOME"]).name.startswith(".hub-auth-"))
        self.assertEqual("1",env["HF_HUB_DISABLE_IMPLICIT_TOKEN"])
        self.assertFalse(Path(env["HF_TOKEN_PATH"]).exists())
    def test_legacy_oidc_and_token_file_settings_are_removed_from_child(self):
        cached=self.root/"ambient-token"; cached.write_text("synthetic-unselected-token")
        ambient={"HUGGING_FACE_HUB_TOKEN":"synthetic-legacy-token","HF_TOKEN_PATH":str(cached),
            "HF_OIDC_RESOURCE":"synthetic-oidc","HF_HOME":str(self.root),"HF_HUB_DISABLE_IMPLICIT_TOKEN":"0"}
        with patch.dict(os.environ,ambient): env=child_environment(self.root)
        self.assertNotIn("HUGGING_FACE_HUB_TOKEN",env); self.assertNotIn("HF_OIDC_RESOURCE",env)
        self.assertNotEqual(str(cached),env["HF_TOKEN_PATH"])
        self.assertEqual("1",env["HF_HUB_DISABLE_IMPLICIT_TOKEN"])
        self.assertEqual("synthetic-unselected-token",cached.read_text())

    @unittest.skipUnless(os.name=="posix","Pinned remote Linux Hub authentication")
    def test_pinned_hub_ignores_ambient_cache_legacy_and_oidc_but_accepts_selected_credential(self):
        try: version=importlib.metadata.version("huggingface-hub")
        except importlib.metadata.PackageNotFoundError: self.skipTest("Optional pinned Hub dependency")
        if version!="2.3.0": self.skipTest("Exact pinned Hub2.3.0 required")
        ambient=self.root/"ambient"; ambient.mkdir(); (ambient/"token").write_text("synthetic-cached-token")
        model_cache=self.root/"model-cache"; model_cache.mkdir(); (model_cache/"token").write_text("synthetic-cache-token")
        for selected in (False,True):
            with self.subTest(selected=selected):
                if selected:
                    secret=self.root/".hfkey"; secret.write_text("synthetic-selected-token"); secret.chmod(0o600)
                with patch.dict(os.environ,{"HF_HOME":str(ambient),"HF_TOKEN_PATH":str(ambient/"token"),
                        "HF_TOKEN":"synthetic-ambient-token","HUGGING_FACE_HUB_TOKEN":"synthetic-legacy-token",
                        "HF_OIDC_RESOURCE":"synthetic-oidc-resource","ENGINE_ROOM_WEIGHTS":str(model_cache)}):
                    env=child_environment(self.root)
                expected="'synthetic-selected-token'" if selected else "None"
                code="from huggingface_hub import get_token; from huggingface_hub.utils import build_hf_headers; assert get_token()=="+expected+"; headers=build_hf_headers(); assert headers.get('authorization')=="+("'Bearer synthetic-selected-token'" if selected else "None")
                result=subprocess.run([sys.executable,"-I","-c",code],env=env,capture_output=True,text=True,timeout=15)
                self.assertEqual(0,result.returncode,result.stderr)
                self.assertNotEqual(str(model_cache),env["HF_HOME"])
        self.assertEqual("synthetic-cached-token",(ambient/"token").read_text())
        self.assertEqual("synthetic-cache-token",(model_cache/"token").read_text())

    def test_oversized_secret_is_refused_without_model_execution(self):
        secret=self.root/".hfkey"; secret.write_text("x"*16385); secret.chmod(0o600)
        with self.assertRaises(ValueError): child_environment(self.root)
        self.assertTrue(secret.exists())
    def test_ready_requires_both_model_identities(self):
        opener=Mock()
        response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=None)
        opener.open.return_value=response
        response.read.return_value=json.dumps({"data":[{"id":"engine-room"}]}).encode()
        self.assertFalse(model_identity("example/model",opener))
        response.read.return_value=json.dumps({"data":[{"id":"engine-room"},{"id":"example/model"}]}).encode()
        self.assertTrue(model_identity("example/model",opener))
    def test_model_exit_is_terminal_and_does_not_expose_raw_logs(self):
        process=Mock(); process.poll.return_value=1
        (self.root/"model.log").write_text("synthetic-sensitive-log")
        result=status(self.root,process,{"id":"example/model"},identity=lambda _:True)
        self.assertEqual("failed",result["status"])
        self.assertNotIn("sensitive",json.dumps(result))
    def test_wrong_or_unreachable_model_never_reports_ready(self):
        process=Mock(); process.poll.return_value=None
        self.assertEqual("starting",status(self.root,process,{"id":"example/model"},identity=lambda _:False)["status"])
        self.assertEqual("ready",status(self.root,process,{"id":"example/model"},identity=lambda _:True)["status"])


if __name__=="__main__": unittest.main()
