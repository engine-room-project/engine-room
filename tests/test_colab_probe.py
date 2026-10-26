import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

from engine_room_connectors._colab.probe import code,validate,inspect_runtime,ROOT


def plan():
    return dict(id="example/model",revision="a"*40,context=8192,engine="llama.cpp",files=["model.gguf"],
        fileSizes={"model.gguf":10**9},weightBytes=2*10**9,overheadBytes=10**9,kvBytesPerToken=10000)


def report():
    return dict(schema=1,system="Linux",machine="x86_64",kernel_python=[3,12,15],libc=["glibc","2.39"],os={"ID":"ubuntu","VERSION_ID":"24.04"},
        root="/content",disk_free_bytes=100*1024**3,disk_total_bytes=200*1024**3,
        gpus=[dict(name="NVIDIA A100-SXM4-40GB",memory_mib=40960,free_mib=40000,compute_capability=8.0)],cuda="12.8",gpu_error=None)


class ProbeValidationTests(unittest.TestCase):
    def test_selected_capacity_storage_and_driver_accept_without_installing(self):
        result=validate(report(),plan(),"A100")
        self.assertGreater(result["storage_required_bytes"],2*10**9)
        self.assertLess(result["required_gpu_bytes"],result["available_gpu_bytes"])
    def test_notebook_python_313_does_not_change_the_isolated_model_python(self):
        result=validate(report()|{"kernel_python":[3,13,7]},plan(),"A100")
        self.assertEqual("3.12",result["runtime_python"])

    def test_actual_driver_platform_python_accelerator_or_free_memory_mismatch_refuses(self):
        changes=({"libc":["glibc","2.35"]},{"cuda":"12.7"},{"machine":"aarch64"},{"system":"Windows"},{"kernel_python":[3,11,15]},
            {"os":{"ID":"ubuntu","VERSION_ID":"22.04"}},{"root":"/different"},{"gpu_error":"Unknown"},
            {"gpus":[]},{"gpus":report()["gpus"]*2},
            {"gpus":[{**report()["gpus"][0],"name":"NVIDIA T4"}]},
            {"gpus":[{**report()["gpus"][0],"free_mib":1}]},
            {"gpus":[{**report()["gpus"][0],"memory_mib":float("nan")}]})
        for change in changes:
            with self.subTest(change=list(change)),self.assertRaises(ValueError): validate(report()|change,plan(),"A100")
    def test_missing_or_oversized_model_memory_and_disk_refuse(self):
        for changed in (plan()|{"weightBytes":None},plan()|{"weightBytes":10**12},
                plan()|{"fileSizes":{"other.gguf":1}}):
            with self.assertRaises(ValueError): validate(report(),changed,"A100")
        with self.assertRaises(ValueError): validate(report()|{"disk_free_bytes":1},plan(),"A100")
    def test_bfloat16_requires_actual_capability_not_gpu_name(self):
        selected=plan()|dict(engine="vLLM",dtype="bfloat16",fileSizes={"model.safetensors":10**9})
        actual=report()|dict(cuda="13.0",gpus=[{**report()["gpus"][0],"compute_capability":7.5}])
        with self.assertRaises(ValueError): validate(actual,selected,"A100")
    def test_probe_consumes_owned_kernel_transport_and_refuses_bad_reports_before_setup(self):
        session=Mock(); session.execute.return_value=json.dumps(report()); authority=Mock(); cancel=Mock()
        result=inspect_runtime(session,"connection","receipt",plan(),"A100",authorize=authority,cancel=cancel)
        self.assertGreater(result["capacity"]["required_gpu_bytes"],0)
        call=session.execute.call_args
        self.assertEqual(("connection","receipt"),call.args[:2])
        self.assertIs(authority,call.kwargs["authorize"]); self.assertIs(cancel,call.kwargs["cancel"])
        self.assertEqual(60,call.kwargs["timeout"])
        for raw in ("incomplete private output",json.dumps(report()|{"cuda":"12.7"})):
            session.execute.return_value=raw
            with self.assertRaises(ValueError) as error:
                inspect_runtime(session,"connection","receipt",plan(),"A100",authorize=authority,cancel=cancel)
            self.assertNotIn("private output",str(error.exception))

    def test_generated_code_is_standalone_read_only_and_rejects_arbitrary_root_code(self):
        for root in ("relative","/content/../private","/content';print('injected')"):
            with self.assertRaises(ValueError): code(root)
        with tempfile.TemporaryDirectory() as root:
            # The real generated kernel snippet runs in an isolated process, without source PYTHONPATH.
            selected=Path(root).as_posix()
            snippet=code("/content").replace(repr("/content"),repr(selected))
            result=subprocess.run([sys.executable,"-I","-c",snippet],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stderr)
            actual=json.loads(result.stdout)
            self.assertEqual(1,actual["schema"]); self.assertGreater(actual["disk_free_bytes"],0)
            self.assertEqual([],list(Path(root).iterdir()))
            self.assertNotIn("hostname",actual); self.assertNotIn("environment",actual)


class ProbeCollectionTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location("standalone_probe",ROOT/"remote/probe.py")
        self.probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.probe)
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
    def test_real_driver_parse_uses_no_shell_or_ambient_credentials(self):
        runner=Mock(side_effect=[Mock(stdout="CUDA Version: 12.8"),Mock(stdout="NVIDIA A100-SXM4-40GB, 40960, 40000, 8.0\n")])
        with patch.object(self.probe.shutil,"which",return_value="/usr/bin/nvidia-smi"):
            actual=self.probe.collect(self.temp.name,run=runner)
        self.assertEqual("12.8",actual["cuda"]); self.assertEqual(40000,actual["gpus"][0]["free_mib"])
        for call in runner.call_args_list:
            self.assertEqual({"PATH","LC_ALL"},set(call.kwargs["env"]))
            self.assertEqual(10,call.kwargs["timeout"]); self.assertNotIn("shell",call.kwargs)
    def test_unavailable_gpu_or_failed_command_returns_unknown_not_invented_capacity(self):
        runner=Mock(side_effect=RuntimeError("synthetic private error"))
        with patch.object(self.probe.shutil,"which",return_value="/usr/bin/nvidia-smi"):
            actual=self.probe.collect(self.temp.name,run=runner)
        self.assertEqual([],actual["gpus"]); self.assertIsNone(actual["cuda"])
        self.assertNotIn("private error",json.dumps(actual))
