from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import Mock,patch

from engine_room.payload import ROOT,source_payload,payload_files
from engine_room_connectors._colab.bootstrap import install_code
import test_colab_bootstrap as staging
from test_colab_upload import native_plan
from test_colab_model_start import receipt


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    target=importlib.util.module_from_spec(spec); spec.loader.exec_module(target); return target


class NativeVllmTests(unittest.TestCase):
    def setUp(self):
        self.fixture=staging.StagingTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.fixture.payload=source_payload(native_plan(),native=True)
        self.fixture.names=payload_files(native_plan(),native=True); self.fixture.stage()
        self.root=self.fixture.root; self.key=self.fixture.key; self.digest=self.fixture.payload["sha256"]
        self.verifier=module("verify_vllm_candidate",ROOT/"remote/verify_vllm.py")
        self.torch=Mock(); self.torch.version.cuda="13.0"; self.torch.cuda.is_available.return_value=True
        self.torch.cuda.device_count.return_value=1; self.torch.cuda.get_device_capability.return_value=(8,0)
        self.load=Mock(side_effect=lambda name:self.torch if name=="torch" else Mock())
        self.version=lambda name:{"vllm":"0.32.0","torch":"2.13.0+cu130"}[name]
    def verify(self): return self.verifier.verify(self.root,load=self.load,version=self.version)
    def test_exact_packages_extension_and_actual_gpu_checks_produce_fixed_proof(self):
        proof=self.verify(); self.assertEqual("vLLM",proof["engine"]); self.assertEqual([8,0],proof["gpu_capability"])
        self.assertIn("vllm._C",[call.args[0] for call in self.load.call_args_list])
        self.assertFalse((self.root/"native-runtime.json").exists())
    def test_incompatible_cuda_missing_multiple_or_old_gpu_refuse(self):
        self.torch.version.cuda="12.9"
        with self.assertRaises(ValueError): self.verify()
        self.torch.version.cuda="13.0"; self.torch.cuda.is_available.return_value=False
        with self.assertRaises(ValueError): self.verify()
        self.torch.cuda.is_available.return_value=True; self.torch.cuda.device_count.return_value=2
        with self.assertRaises(ValueError): self.verify()
        self.torch.cuda.device_count.return_value=1; self.torch.cuda.get_device_capability.return_value=(7,0)
        with self.assertRaises(ValueError): self.verify()
    def test_changed_lock_versions_or_missing_native_extension_refuse(self):
        self.version=lambda name:"unrelated"
        with self.assertRaises(ValueError): self.verify()
        self.version=lambda name:{"vllm":"0.32.0","torch":"2.13.0"}[name]
        self.load.side_effect=ImportError("synthetic missing native library")
        with self.assertRaises(ImportError): self.verify()
        (self.root/"remote/requirements-vllm.lock").write_text("uninspected dependency")
        with self.assertRaises(ValueError): self.verify()
    def test_installer_status_requires_matching_native_proof_and_successful_process(self):
        observer=module("native_installer_observer",ROOT/"remote/install_status.py")
        (self.root/"install-start.json").write_text(json.dumps(dict(source_sha256=self.digest,state="submitted")))
        (self.root/"runtime-ready").write_text("installed")
        python=self.root/"venv/bin/python"; python.parent.mkdir(parents=True); python.write_text("synthetic")
        (self.root/"python-path").write_text(str(python)); process=Mock(); process.poll.return_value=0
        handle=dict(operation_key=self.key,root=str(self.root),source_sha256=self.digest,process=process)
        def status(): return observer.collect(str(self.root),self.key,self.digest,handle)
        self.assertNotEqual("installed",status()["state"])
        proof=self.verify(); (self.root/"native-runtime.json").write_text(json.dumps(proof))
        self.assertEqual("installed",status()["state"])
        process.poll.return_value=5; self.assertEqual("failed",status()["state"])
        process.poll.return_value=0; (self.root/"native-runtime.json").write_text(json.dumps(proof|{"version":"unrelated"}))
        self.assertNotEqual("installed",status()["state"])
    def test_large_native_payload_generates_bounded_launcher_without_single_message_stage(self):
        r=receipt(); payload=source_payload(native_plan(),native=True)
        code=install_code(r,native_plan(),dict(root="/content/engine-room-"+r.operation_key()[:32],source_sha256=payload["sha256"],state="staged"))
        self.assertLess(len(code.encode()),262144); compile(code,"native-launcher","exec")
        self.assertIn("remote/install-colab.sh",code); self.assertNotIn("HF_TOKEN",code)
