import hashlib
import base64
import io
import json
from pathlib import Path
import re
import tarfile
import subprocess
import sys
import tempfile
import unittest

from engine_room.payload import FILES,ROOT,bootstrap_script,runtime_profile,source_payload


class PayloadTests(unittest.TestCase):
    def plan(self): return dict(id="example/model",revision="a"*40,context=8192,engine="llama.cpp",files=["model.gguf"],fileSizes={"model.gguf":10})
    def test_source_payload_is_deterministic_and_explicitly_allowlisted(self):
        first=source_payload(self.plan()); second=source_payload(self.plan())
        self.assertEqual(first,second)
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(first["base64"])),mode="r:gz") as archive:
            self.assertEqual(set(FILES)|{"model.json"},set(archive.getnames()))
            self.assertTrue(all(m.isfile() and not m.issym() and m.mtime==0 for m in archive.getmembers()))
            for name in archive.getnames():
                self.assertNotIn("..",name); self.assertFalse(name.startswith("/"))
            self.assertNotIn(".git",archive.getnames())
    def test_actual_extracted_payload_imports_without_source_checkout(self):
        payload=source_payload(self.plan())
        with tempfile.TemporaryDirectory() as folder:
            with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload["base64"])),mode="r:gz") as archive:
                archive.extractall(folder,filter="data")
            # Isolated interpreter excludes the checkout and environment PYTHONPATH.
            result=subprocess.run([sys.executable,"-I","-c",
                "import sys; sys.path.insert(0,sys.argv[1]); import engine_room.remote_agent; import engine_room.records",
                folder],cwd=folder,capture_output=True,text=True,timeout=20)
            self.assertEqual(0,result.returncode,result.stderr)

    def test_credentials_and_unknown_fields_cannot_enter_generated_model_settings(self):
        plan={**self.plan(),"account_key":"synthetic-sensitive-provider-key","hf_key":"synthetic-sensitive-hf-key"}
        payload=source_payload(plan)
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload["base64"])),mode="r:gz") as archive:
            model=json.load(archive.extractfile("model.json"))
        self.assertNotIn("account_key",model); self.assertNotIn("hf_key",model)
    def test_runtime_profiles_use_digest_not_floating_tags(self):
        for engine in ("llama.cpp","vLLM"):
            profile=runtime_profile(engine)
            self.assertRegex(profile["image"],r"@sha256:[a-f0-9]{64}$")
            self.assertNotIn(":latest",profile["image"])
        with self.assertRaises(ValueError): runtime_profile("unsupported")
    def test_bootstrap_uses_manifest_snapshot_and_preserves_credential_start_boundary(self):
        source=bootstrap_script()
        self.assertNotIn("@UBUNTU_SNAPSHOT@",source)
        self.assertIn("20261025T000000Z",source)
        self.assertIn("--require-hashes",source)
        self.assertIn("exec sleep infinity",source)
        self.assertNotIn("engine_room.model_server",source)
        self.assertNotIn("HF_TOKEN",source)
        self.assertNotIn("--allow-unauthenticated",source)
        self.assertNotIn("trusted=yes",source)
    def test_native_vllm_lock_matches_manifest_and_has_only_exact_hashed_packages(self):
        metadata=json.loads((ROOT/"remote/vllm-native.json").read_text())
        raw=(ROOT/"remote/requirements-vllm.lock").read_text().encode()
        self.assertEqual(metadata["lock_sha256"],hashlib.sha256(raw).hexdigest())
        entries=[line for line in raw.decode().replace("\\\n"," ").splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual(metadata["resolved_packages"],len(entries))
        for line in entries:
            self.assertRegex(line,r"^[A-Za-z0-9_-]+==[A-Za-z0-9_.+]+(?: +--hash=sha256:[a-f0-9]{64})+ *$")
        self.assertIn("vllm=="+metadata["version"],raw.decode())
        self.assertEqual("v"+metadata["version"],runtime_profile("vLLM")["source_tag"])
        self.assertEqual(runtime_profile("vLLM")["source_commit"],metadata["source_commit"])

    def test_all_dependency_lock_entries_are_exact_and_hashed(self):
        text=(ROOT/"remote/requirements.lock").read_text()
        blocks=text.replace("\\\n", " ").splitlines()
        requirements=[s for s in blocks if s.strip() and not s.startswith("#")]
        self.assertGreater(len(requirements),1)
        for entry in requirements:
            self.assertRegex(entry,r"^[A-Za-z0-9_-]+==[A-Za-z0-9_.+]+")
            self.assertRegex(entry,r"--hash=sha256:[a-f0-9]{64}")
        self.assertIn("huggingface-hub==2.3.0",text)


if __name__=="__main__": unittest.main()
