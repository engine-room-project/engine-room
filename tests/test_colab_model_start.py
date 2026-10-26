from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from engine_room_connectors._colab.model_start import start_code,start_model
from engine_room_connectors._colab.bootstrap import staging_code
import test_colab_bootstrap as staging_fixture
from test_colab_probe import plan
from test_records import rental


def receipt():
    return replace(rental(),connector_id="colab",resource_id="owned",state="active",protection_id="proof")


class StartTests(unittest.TestCase):
    def setUp(self):
        self.r=receipt(); self.ssh=Mock(); self.ssh.receipt=self.r; self.ssh.run.return_value=b"MODEL_START_SUBMITTED\n"
        self.credentials=Mock(); self.credentials.read.return_value="synthetic-model-access"
        self.connection=Mock(); self.connection.settings={"hf_credential_ref":"explicit-ref"}
        self.authorize=Mock(); self.cancel=threading.Event()
    def start(self):
        return start_model(self.ssh,self.connection,self.r,plan(),self.credentials,authorize=self.authorize,cancel=self.cancel,now=lambda:100)
    def test_secret_only_uses_ssh_stdin_and_requires_authority(self):
        self.start(); call=self.ssh.run.call_args
        self.assertEqual(b"synthetic-model-access",call.kwargs["data"])
        self.assertNotIn("synthetic-model-access",call.args[0]); self.assertNotIn("explicit-ref",call.args[0])
        self.assertEqual(2,self.authorize.call_count); self.credentials.read.assert_called_once_with("explicit-ref")
    def test_cancel_or_bad_credentials_never_submit(self):
        self.cancel.set()
        with self.assertRaises(ValueError): self.start()
        self.credentials.read.assert_not_called(); self.ssh.run.assert_not_called()
        self.cancel.clear(); self.credentials.read.return_value="invalid\ncredential"
        with self.assertRaises(ValueError): self.start()
        self.ssh.run.assert_not_called()
    def test_wrong_ssh_resource_never_reads_or_transmits_credentials(self):
        self.ssh.receipt=replace(self.r,resource_id="unrelated")
        with self.assertRaises(ValueError): self.start()
        self.credentials.read.assert_not_called(); self.ssh.run.assert_not_called()
    def test_public_model_and_uncertain_acknowledgement(self):
        self.connection.settings={}; self.ssh.run.return_value=b"unexpected"
        with self.assertRaises(RuntimeError): self.start()
        self.credentials.read.assert_not_called(); self.assertEqual(b"",self.ssh.run.call_args.kwargs["data"])
    def test_other_resources_and_cancelled_receipts_refuse(self):
        for changed in (replace(self.r,connector_id="other"),replace(self.r,cancel_requested=True),replace(self.r,mode="attachment")):
            with self.assertRaises(ValueError): start_code(changed,plan())


@unittest.skipUnless(sys.platform.startswith("linux"),"Actual native permissions and directory fsync require Linux")
class GeneratedStartTests(unittest.TestCase):
    def setUp(self):
        self.stage=staging_fixture.StagingTests(); self.stage.setUp(); self.addCleanup(self.stage.doCleanups)
        self.r=receipt(); self.stage.key=self.r.operation_key()
        self.stage.root=self.stage.base/("engine-room-"+self.stage.key[:32]); self.stage.stage()
        self.root=self.stage.root
        (self.root/"runtime-ready").write_text("installed\n")
        (self.root/"venv/bin").mkdir(parents=True); (self.root/"venv/bin/python").write_text("synthetic executable")
        (self.root/"home").mkdir(mode=0o700)
        self.code=start_code(self.r,plan()).replace(repr("/content/engine-room-"+self.r.operation_key()[:32]),repr(str(self.root)))
    def execute(self,secret=b"synthetic-model-access"):
        stdin=io.TextIOWrapper(io.BytesIO(secret)); output=io.StringIO()
        with patch("sys.stdin",stdin),patch("sys.stdout",output),patch("time.time",return_value=100),patch("subprocess.Popen") as launch:
            exec(self.code,{})
            return launch.call_args,output.getvalue()
    def test_actual_source_private_credential_intent_and_minimal_child(self):
        call,output=self.execute(); self.assertEqual("MODEL_START_SUBMITTED\n",output)
        self.assertEqual(b"synthetic-model-access",(self.root/".hfkey").read_bytes())
        self.assertEqual(0,(self.root/".hfkey").stat().st_mode&0o077)
        self.assertEqual(self.r.resource_id,json.loads((self.root/"model-start.json").read_text())["resource_id"])
        self.assertNotIn("HF_TOKEN",call.kwargs["env"]); self.assertNotIn("synthetic-model-access",repr(call))
        self.assertEqual([str(self.root/"venv/bin/python"),"-m","engine_room.remote_agent"],call.args[0])
        with self.assertRaises(ValueError): self.execute()
    def test_changed_source_or_unknown_credentials_preserved_without_launch(self):
        f=self.root/"engine_room/remote_agent.py"; original=f.read_bytes(); f.write_bytes(b"changed")
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse((self.root/".hfkey").exists())
        f.write_bytes(original); (self.root/".hfkey").write_text("unrelated")
        with self.assertRaises(FileExistsError): self.execute()
        self.assertEqual("unrelated",(self.root/".hfkey").read_text()); self.assertFalse((self.root/"model-start.json").exists())
