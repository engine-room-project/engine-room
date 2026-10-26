from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import Mock

from engine_room.tools import LaunchPlan,inline_settings,launch,prepare,prepare_existing


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.plan=dict(id="example/model",revision="a"*40,context=32768,engine="vLLM",dtype="float16",tool="hermes",reasoning="qwen3",efforts=["low","high"])
        self.url="http://127.0.0.1:18000/v1"; self.token="synthetic_session_token_"+"x"*20
        self.env={"PATH":"synthetic-path","CODEX_HOME":"synthetic-codex-home","OPENCODE_CONFIG":"synthetic-config.jsonc","EXISTING_KEY":"synthetic-existing-key"}
    def prepare(self,tool,**kwargs): return prepare(tool,self.url,self.token,self.plan,environment=self.env,**kwargs)
    def test_jsonc_preserves_strings_comments_trailing_commas_and_refuses_duplicates(self):
        source='{"url":"https://synthetic.invalid/a//b",/* note */"array":["x,}",],// note\n"object":{},}'
        self.assertEqual(dict(url="https://synthetic.invalid/a//b",array=["x,}"],object={}),inline_settings(source))
        for raw in ('{"x":1,"x":2}',"[]",'{"secret":NaN}',"{broken"):
            with self.assertRaises(ValueError) as error: inline_settings(raw)
            self.assertNotIn(raw,str(error.exception))
    def test_opencode_keeps_existing_inline_options_and_uses_unique_provider(self):
        original=dict(model="existing/model",provider=dict(existing=dict(options=dict(apiKey="synthetic-existing"),models=dict(kept={}))),theme="kept",permission=dict(bash="ask"),mcp=dict(kept=dict(enabled=False)))
        self.env["OPENCODE_CONFIG_CONTENT"]=json.dumps(original)
        before=dict(self.env)
        result=self.prepare("opencode",effort="high"); child=json.loads(result.environment["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(before,self.env)
        for key in ("theme","permission","mcp"): self.assertEqual(original[key],child[key])
        self.assertEqual(original["provider"]["existing"],child["provider"]["existing"])
        namespace=child["model"].split("/")[0]; provider=child["provider"][namespace]
        self.assertEqual(self.url,provider["options"]["baseURL"])
        reference=provider["options"]["apiKey"]; variable=reference[5:-1]
        self.assertEqual(self.token,result.environment[variable]); self.assertNotIn(self.token,json.dumps(child))
        self.assertEqual(32768,provider["models"]["example/model"]["limit"]["output"])
        self.assertEqual("high",provider["models"]["example/model"]["options"]["reasoningEffort"])
    def test_codex_overrides_parse_as_toml_and_preserve_normal_home_and_permissions(self):
        result=self.prepare("codex",effort="low")
        config={}
        for index,value in enumerate(result.args):
            if value=="--config":
                setting=result.args[index+1]; parsed=tomllib.loads(setting)
                config.update(parsed)
                self.assertNotIn("approval_policy",setting); self.assertNotIn("sandbox",setting)
        namespace=config["model_provider"]; provider=config["model_providers"][namespace]
        self.assertEqual(self.url,provider["base_url"]); self.assertEqual("responses",provider["wire_api"])
        self.assertFalse(provider["requires_openai_auth"])
        self.assertEqual(self.token,result.environment[provider["env_key"]])
        self.assertNotIn(self.token,str(result.args)); self.assertNotIn(self.token,repr(result))
        self.assertEqual(self.env["CODEX_HOME"],result.environment["CODEX_HOME"])
        self.assertEqual("low",config["model_reasoning_effort"])
    def test_unspecified_effort_does_not_override_normal_model_preference(self):
        self.assertNotIn("model_reasoning_effort",str(self.prepare("codex").args))
        result=self.prepare("opencode"); content=json.loads(result.environment["OPENCODE_CONFIG_CONTENT"])
        namespace=content["model"].split("/")[0]
        self.assertNotIn("options",content["provider"][namespace]["models"]["example/model"])
    def test_two_sessions_keep_separate_namespaces_tokens_and_parent_environment(self):
        first=self.prepare("opencode"); second=self.prepare("opencode")
        self.assertNotEqual(first.args,second.args)
        self.assertNotIn("OPENCODE_CONFIG_CONTENT",self.env)
        self.assertEqual("synthetic-existing-key",first.environment["EXISTING_KEY"])
    def test_invalid_endpoint_effort_and_inline_config_fail_without_mutation(self):
        before=dict(self.env)
        for url in ("http://8.8.8.8:18000/v1","http://127.0.0.1:18000/v1?key=secret","http://user@127.0.0.1:18000/v1"):
            with self.assertRaises(ValueError): prepare("opencode",url,self.token,self.plan,environment=self.env)
        with self.assertRaises(ValueError): self.prepare("codex",effort="max")
        self.env["OPENCODE_CONFIG_CONTENT"]="synthetic-private-invalid-json"
        with self.assertRaises(ValueError) as error: self.prepare("opencode")
        self.assertNotIn(self.env["OPENCODE_CONFIG_CONTENT"],str(error.exception))
        self.env.pop("OPENCODE_CONFIG_CONTENT"); self.assertEqual(before,self.env)
    def test_prepare_and_remove_no_owned_files_never_edit_normal_settings(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            files={root/"config.toml":b'# normal preferences\nmodel="existing"\n',root/"opencode.jsonc":b'{// keep comment\n"theme":"normal",}'}
            for path,data in files.items(): path.write_bytes(data)
            self.env["CODEX_HOME"]=str(root); self.env["OPENCODE_CONFIG"]=str(root/"opencode.jsonc")
            self.prepare("codex"); self.prepare("opencode")
            self.assertEqual(set(files),set(root.iterdir()))
            for path,data in files.items(): self.assertEqual(data,path.read_bytes())
    def test_native_launch_uses_child_environment_and_never_mutates_parent(self):
        result=self.prepare("codex"); runner=Mock(); before=dict(os.environ)
        with tempfile.TemporaryDirectory() as folder:
            launch(Path(sys.executable).absolute(),result,folder,console=False,runner=runner)
        args=runner.call_args.args[0]
        self.assertEqual(list(result.args),args[1:]); self.assertNotIn(self.token,str(args))
        self.assertEqual(result.environment,runner.call_args.kwargs["env"])
        self.assertEqual(before,dict(os.environ))
    def test_real_child_receives_overlay_without_changing_parent_or_settings_files(self):
        result=self.prepare("opencode")
        before=dict(os.environ)
        collector="import json,os,sys; from pathlib import Path; Path('child.json').write_text(json.dumps({'args':sys.argv[1:],'inline':os.environ.get('OPENCODE_CONFIG_CONTENT'),'keys':{k:v for k,v in os.environ.items() if k.startswith('ENGINE_ROOM_SESSION_')}}))"
        def child(args,**kwargs):
            return subprocess.Popen([sys.executable,"-c",collector,*args[1:]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
        with tempfile.TemporaryDirectory(prefix="tool project ") as folder:
            normal=Path(folder)/"opencode.jsonc"; normal.write_text('{"theme":"kept",}')
            original=normal.read_bytes()
            process=launch(Path(sys.executable).absolute(),result,folder,console=False,runner=child)
            _,errors=process.communicate(timeout=5)
            self.assertEqual(0,process.returncode)
            snapshot=json.loads((Path(folder)/"child.json").read_text())
            self.assertEqual(list(result.args),snapshot["args"])
            self.assertEqual([self.token],list(snapshot["keys"].values()))
            self.assertEqual(original,normal.read_bytes())
        self.assertEqual(before,dict(os.environ))

    def test_single_instance_desktop_requires_idle_check_without_terminating_anything(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"OpenCode.exe"; target.write_bytes(b"synthetic fixture")
            runner=Mock()
            with self.assertRaisesRegex(ValueError,"closed"): launch(target,self.prepare("opencode"),folder,runner=runner)
            runner.assert_not_called()
    def test_other_tools_are_not_falsely_registered(self):
        for name in ("claude","comfyui","cursor"):
            with self.assertRaisesRegex(ValueError,"not yet validated"): self.prepare(name)

    def test_existing_model_handoff_preserves_settings_without_engine_or_capability_guesses(self):
        before=dict(self.env)
        result=prepare_existing("opencode",self.url,self.token,"served-alias",8192,environment=self.env)
        self.assertEqual(before,self.env)
        content=json.loads(result.environment["OPENCODE_CONFIG_CONTENT"])
        provider=content["provider"][content["model"].split("/")[0]]
        model=provider["models"]["served-alias"]
        self.assertEqual(8192,model["limit"]["context"])
        self.assertNotIn("tool_call",model); self.assertNotIn("reasoning",model); self.assertNotIn("attachment",model)
        self.assertTrue(any("not inferred" in warning for warning in result.warnings))
        codex=prepare_existing("codex",self.url,self.token,"served-alias",8192,environment=self.env)
        self.assertEqual("served-alias",codex.args[1]); self.assertEqual(self.env["CODEX_HOME"],codex.environment["CODEX_HOME"])
    def test_existing_model_requires_safe_exact_id_and_explicit_capacity(self):
        for model,context in (("",8192),("-flag",8192),("bad\nmodel",8192),("served",True),("served",0),("served",1048577)):
            with self.assertRaises(ValueError): prepare_existing("codex",self.url,self.token,model,context,environment=self.env)
