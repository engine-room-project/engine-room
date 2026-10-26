from dataclasses import asdict
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.controller_client import Endpoint
from engine_room.desktop_bridge import Bridge
from engine_room.records import atomic_json


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.base=Path(self.temp.name)
        self.root=self.base/"desktop"; self.factory=Mock(); self.client=Mock(); self.factory.return_value=self.client
        self.client.call.return_value=dict(controller_host_id="a"*64,client_host_id="b"*64,protection_healthy=True)
        self.bridge=Bridge(self.root,client_type=self.factory,identity=lambda:"b"*64,which=lambda name:None)
        key=self.base/"identity"; key.write_text("synthetic private identity")
        public="ssh-ed25519 "+base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"+b"a"*32).decode()
        self.endpoint=Endpoint("10.0.0.1",22,"controller",public,str(key),"controller1","a"*64,"b"*64,True)
    def enroll(self):
        values=asdict(self.endpoint); values.pop("client_host_id")
        return self.bridge.dispatch(dict(action="enroll_controller",params=dict(endpoint=values)))
    def test_missing_first_start_has_no_provider_and_no_files_or_network(self):
        state=self.bridge.dispatch(dict(action="startup"))
        self.assertEqual("missing",state["controller_state"]); self.assertFalse(state["provider_configured"])
        self.assertFalse(state["ssh_ready"]); self.assertFalse(self.root.exists()); self.factory.assert_not_called()
    def test_bad_or_changed_host_configuration_is_preserved_without_repair(self):
        self.root.mkdir(); path=self.root/"controller.json"; path.write_text("synthetic damaged state")
        state=self.bridge.dispatch(dict(action="startup")); self.assertEqual("damaged",state["controller_state"])
        self.assertEqual("synthetic damaged state",path.read_text())
        atomic_json(path,asdict(self.endpoint)); state=self.bridge.dispatch(dict(action="startup"))
        self.assertEqual("configured",state["controller_state"]); self.assertIsNone(state["provider_configured"])
        self.assertFalse((self.root/"controller-known-hosts").exists())
    def test_enrollment_verifies_independent_controller_before_persistent_save(self):
        self.assertEqual(dict(saved=True,protection_healthy=True),self.enroll())
        self.assertEqual(2,self.factory.call_count); self.client.call.assert_called_once_with("info"); self.client.save.assert_called_once()
        self.assertEqual([],list(self.root.iterdir())) # temporary trust removed; fake save creates no file
    def test_bad_remote_identity_or_existing_controller_never_saves(self):
        self.client.call.return_value["controller_host_id"]="unrelated"
        with self.assertRaises(ValueError): self.enroll()
        self.client.save.assert_not_called(); self.assertFalse((self.root/"controller.json").exists())
        (self.root/"controller.json").write_text("preserve existing")
        with self.assertRaises(ValueError): self.enroll()
        self.assertEqual("preserve existing",(self.root/"controller.json").read_text())
    def test_recovery_index_is_read_only_without_controller_or_network(self):
        self.assertEqual(dict(records=[],damaged_records=0),self.bridge.dispatch(dict(action="recovery_list")))
        self.assertFalse(self.root.exists()); self.factory.read.assert_not_called()
        directory=self.root/"rentals"/"requests"; directory.mkdir(parents=True)
        (directory/"damaged.json").write_text("synthetic damaged private content")
        result=self.bridge.dispatch(dict(action="recovery_list"))
        self.assertEqual(1,result["damaged_records"]); self.assertNotIn("private",json.dumps(result))
        self.assertEqual("synthetic damaged private content",(directory/"damaged.json").read_text())
    def test_recovery_requires_confirmation_before_reading_controller(self):
        for confirmed,cancel in ((False,True),(True,"true")):
            with self.assertRaises(ValueError):
                self.bridge.dispatch(dict(action="recover",params=dict(operation_id="example",cancel=cancel,confirmed=confirmed)))
        self.factory.read.assert_not_called()

    def test_one_shot_bridge_refuses_rental_shell_and_stream_before_reading_trust(self):
        for method in ("request","heartbeat","cancel","model_stream","storage_create","exec"):
            with self.assertRaises(ValueError): self.bridge.dispatch(dict(action="controller",params=dict(method=method)))
        self.factory.read.assert_not_called()
        self.factory.read.return_value.call.return_value=[]
        self.assertEqual([],self.bridge.dispatch(dict(action="controller",params=dict(method="connections"))))
        self.factory.read.return_value.call.assert_called_once_with("connections",{})


class ActualBridgeProcessTests(unittest.TestCase):
    def run_bridge(self,raw):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            code="import sys; sys.path.insert(0,sys.argv[1]); from engine_room.desktop_bridge import main; raise SystemExit(main())"
            result=subprocess.run([sys.executable,"-I","-c",code,str(root)],input=raw,capture_output=True,timeout=15,
                env={**os.environ,"ENGINE_ROOM_DATA_DIR":folder})
            self.assertEqual([],list(Path(folder).iterdir()))
        self.assertEqual(b"",result.stderr); return result,json.loads(result.stdout)
    def test_isolated_startup_has_bounded_json_and_no_personal_paths(self):
        result,data=self.run_bridge(b'{"action":"startup"}\n')
        self.assertEqual(0,result.returncode); self.assertTrue(data["ok"])
        self.assertEqual("missing",data["result"]["controller_state"]); self.assertNotIn("Users",result.stdout.decode())
    def test_duplicate_extra_oversized_or_secret_errors_never_echo_input(self):
        for raw in (b'{"action":"startup","action":"secret-synthetic"}\n',b'{"action":"secret-synthetic"}\n',
                b'{"action":"startup"}\nextra',b"x"*262145):
            result,data=self.run_bridge(raw); self.assertEqual(1,result.returncode); self.assertFalse(data["ok"])
            self.assertNotIn(b"secret-synthetic",result.stdout)
