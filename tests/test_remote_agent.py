import io
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
        self.assertEqual(str(self.root/"weights"),env["HF_HOME"])
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
