import os
import unittest
from unittest.mock import Mock

from engine_room.desktop_planner import plan
from engine_room.controller_protocol import encode


class PlannerBoundaryTests(unittest.TestCase):
    def test_unknown_fields_and_missing_runtime_refuse_without_execution(self):
        runner=Mock()
        with self.assertRaises(ValueError): plan(dict(mode="plan",discovery={},script="untrusted"),runner=runner)
        with self.assertRaises(ValueError): plan(dict(mode="plan",discovery={}),runner=runner,which=lambda value:None)
        runner.assert_not_called()

    def test_non_numeric_memory_estimate_is_refused(self):
        full=dict(id="example/model",revision="a"*40,context=8192,engine="vLLM",dtype="bfloat16",fileSizes={"model.safetensors":1000},weightBytes=1000,overheadBytes=1000,kvBytesPerToken=1000)
        runner=Mock(return_value=Mock(returncode=0,stderr=b"",stdout=encode(dict(ok=True,result=dict(plan=full,estimated_memory_bytes="Infinity")))))
        with self.assertRaisesRegex(ValueError,"memory estimate"):
            plan(dict(mode="plan",discovery={}),runner=runner,which=lambda name:"powershell.exe")


@unittest.skipUnless(os.name=="nt","Actual Windows PowerShell planner")
class ActualPlannerTests(unittest.TestCase):
    def discovery(self,gguf=False):
        config=dict(model_type="unknown_family",torch_dtype="bfloat16",max_position_embeddings=32768,
                    num_hidden_layers=4,num_key_value_heads=2,head_dim=64)
        return dict(model_id="example/model",info=dict(sha="a"*40,pipeline_tag="text-generation",siblings=[dict(rfilename="model.gguf" if gguf else "model.safetensors",size=1000)]),config=config,base_config=config)
    def test_safetensors_plan_preserves_precision_context_and_experimental_label(self):
        result=plan(dict(mode="plan",discovery=self.discovery(),engine="vLLM",context=8192))
        self.assertEqual("bfloat16",result["plan"]["dtype"]); self.assertEqual(8192,result["plan"]["context"])
        self.assertEqual(32768,result["native_context"]); self.assertIn("Experimental",result["warning"])
        self.assertGreater(result["estimated_memory_bytes"],result["plan"]["weightBytes"])
        self.assertNotIn("nativeContext",result["plan"]); self.assertNotIn("warning",result["plan"])
    def test_gguf_requires_explicit_variant_and_uses_shared_shard_validation(self):
        data=self.discovery(True)
        description=plan(dict(mode="describe",discovery=data))
        self.assertEqual("model.gguf",description["variants"][0]["name"])
        result=plan(dict(mode="plan",discovery=data,engine="llama.cpp",variant="model.gguf",context=8192))
        self.assertEqual(["model.gguf"],result["plan"]["files"])
        self.assertIn("Experimental",result["warning"])
        for variant in (None,"missing.gguf"):
            with self.assertRaises(ValueError): plan(dict(mode="plan",discovery=data,engine="llama.cpp",variant=variant))
        data["info"]["siblings"][0]["rfilename"]="../model.gguf"
        with self.assertRaises(ValueError): plan(dict(mode="plan",discovery=data,engine="llama.cpp",variant="../model.gguf"))
    def test_published_context_limit_and_explicit_engine_are_enforced(self):
        for fields in (dict(engine="vLLM",context=32769),dict(engine="vLLM",context=8191),dict(engine="unselected")):
            with self.assertRaises(ValueError): plan(dict(mode="plan",discovery=self.discovery(),**fields))
