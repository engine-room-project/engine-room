import copy
import json
import threading
import types
import unittest
from unittest.mock import Mock

from engine_room.session_tools import SessionTools,request
from engine_room.tools import prepare,prepare_existing


class SessionToolTests(unittest.TestCase):
    def setUp(self):
        self.session=types.SimpleNamespace(stopped=threading.Event(),relay=types.SimpleNamespace(closed=False,url="http://127.0.0.1:18000/v1",token="synthetic_token_"+"x"*32))
        self.rental=Mock(); self.rental.session=self.session; self.rental.view.return_value=dict(ready=True)
        self.inactive=False; self.launcher=Mock()
        self.environment=dict(OPENCODE_CONFIG_CONTENT='{"theme":"preserved","provider":{"existing":{"kept":true}}}',CODEX_HOME="preserved-home")
        self.plan=dict(id="example/model",revision="a"*40,engine="vLLM",dtype="bfloat16",context=32768,tool="hermes")
        self.tools=SessionTools(self.rental,self.plan,lambda:self.inactive,launcher=self.launcher,
            preparer=lambda tool,url,token,model:prepare(tool,url,token,model,environment=self.environment))
        self.command=dict(action="tool_launch",request_id="c"*32,tool="opencode",executable="C:/synthetic/opencode.exe",working_directory="C:/synthetic/project",desktop_idle=True,confirmed=True)
    def test_launch_uses_only_child_overlay_and_never_echoes_relay_secret(self):
        before=copy.deepcopy(self.environment)
        result=self.tools.open(self.command)
        self.assertTrue(result["opened"]); self.assertEqual(before,self.environment)
        self.assertNotIn(self.session.relay.token,json.dumps(result)); self.assertNotIn("synthetic/project",json.dumps(result))
        args=self.launcher.call_args.args
        self.assertEqual(self.command["executable"],args[0]); self.assertEqual(self.command["working_directory"],args[2])
        content=json.loads(args[1].environment["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual("preserved",content["theme"]); self.assertTrue(content["provider"]["existing"]["kept"])
        self.assertEqual("preserved-home",args[1].environment["CODEX_HOME"])
        self.assertEqual(True,self.launcher.call_args.kwargs["desktop_idle"])
        with self.assertRaises(ValueError): self.tools.open(self.command)
        self.assertEqual(1,self.launcher.call_count)
    def test_inactive_unready_or_closed_session_never_launches(self):
        for cause in ("inactive","unready","stopped","relay"):
            self.tools.seen.clear(); self.inactive=cause=="inactive"
            self.rental.view.return_value=dict(ready=cause!="unready")
            self.session.stopped.clear(); self.session.relay.closed=cause=="relay"
            if cause=="stopped": self.session.stopped.set()
            with self.assertRaises(ValueError): self.tools.open(self.command)
        self.launcher.assert_not_called()
    def test_stop_during_readiness_rpc_prevents_launch(self):
        def close_during_status():
            self.session.stopped.set(); return dict(ready=True)
        self.rental.view.side_effect=close_during_status
        with self.assertRaises(ValueError): self.tools.open(self.command)
        self.launcher.assert_not_called()
    def test_unconfirmed_extra_args_and_bad_ids_refuse_before_status(self):
        for change in (dict(confirmed=False),dict(args=["untrusted"]),dict(request_id="../bad"),dict(tool="shell"),dict(desktop_idle="true")):
            with self.assertRaises((ValueError,TypeError)): self.tools.open(self.command|change)
        self.rental.view.assert_not_called(); self.launcher.assert_not_called()

    def test_attachment_handoff_uses_only_selected_served_model_and_declared_limit(self):
        self.rental.receipt=types.SimpleNamespace(mode="attachment")
        self.session.relay.selected_model="served-alias"
        existing=lambda tool,url,token,model,context:prepare_existing(tool,url,token,model,context,environment=self.environment)
        tools=SessionTools(self.rental,dict(id="served-alias",context=8192),lambda:False,launcher=self.launcher,existing_preparer=existing)
        self.assertTrue(tools.open(self.command)["opened"])
        content=json.loads(self.launcher.call_args.args[1].environment["OPENCODE_CONFIG_CONTENT"])
        self.assertTrue(content["model"].endswith("/served-alias"))
        self.launcher.reset_mock()
        tools=SessionTools(self.rental,dict(id="different",context=8192),lambda:False,launcher=self.launcher,existing_preparer=existing)
        with self.assertRaises(ValueError): tools.open(self.command)
        self.launcher.assert_not_called()
