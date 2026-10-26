import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine_room.model_validation import gguf_files
from engine_room.model_server import command, download, check_storage
from engine_room.storage import plan_storage


class ModelTests(unittest.TestCase):
    def settings(self,files=None):
        return dict(id="example/model",revision="a"*40,context=65536,engine="llama.cpp",files=files or ["model.gguf"],mmproj="")

    def test_valid_split_model_is_sorted_and_loaded_from_first_shard(self):
        settings=self.settings(["m-00002-of-00002.gguf","m-00001-of-00002.gguf"])
        args=command(settings,"/work/weights")
        self.assertEqual("/work/weights/m-00001-of-00002.gguf",args[args.index("-m")+1])
        self.assertEqual("127.0.0.1",args[args.index("--host")+1])

    def test_shard_validation_rejects_missing_out_of_range_duplicate_and_mixed_totals(self):
        cases=[["m-00002-of-00002.gguf","m-00003-of-00002.gguf"],
               ["m-00001-of-00002.gguf"], ["m-00001-of-00002.gguf"]*2,
               ["m-00001-of-00002.gguf","m-00002-of-00003.gguf"],
               ["m-00000-of-00001.gguf"],["m.gguf","another.gguf"]]
        for files in cases:
            with self.subTest(files=files),self.assertRaises(ValueError): command(self.settings(files))

    def test_unsafe_model_and_projector_names_are_rejected(self):
        for name in ["model Q4.gguf","../model.gguf","a/../../x.gguf","bad;cmd.gguf","/absolute.gguf","model.GGUF"]:
            with self.subTest(name=name),self.assertRaises(ValueError): command(self.settings([name]))
            with self.subTest(projector=name),self.assertRaises(ValueError): command({**self.settings(),"mmproj":name})

    def test_unknown_engine_revision_and_injected_parser_fail_before_execution(self):
        for change in [{"engine":"unknown"},{"revision":"main"},{"context":True},{"id":"a/b;command"}]:
            with self.subTest(change=change),self.assertRaises(ValueError): command({**self.settings(),**change})
        args=command(dict(id="example/model",revision="b"*40,engine="vLLM",context=262144,dtype="bfloat16",tool="hermes",reasoning=""))
        self.assertEqual("262144",args[args.index("--max-model-len")+1])
        self.assertNotIn("--trust-remote-code",args)

    def test_oversized_download_does_not_fit_fixed_small_disk(self):
        plan=plan_storage([60*10**9],40*10**9,5*10**9)
        self.assertFalse(plan.fits)
        self.assertGreater(plan.disk_gb,120)

    def test_only_verified_cache_reduces_space_requirement(self):
        uncached=plan_storage([10,20],1000,5,reserve_bytes=1)
        cached=plan_storage([10,20],1000,5,cached_bytes=30,reserve_bytes=1)
        self.assertEqual(56,uncached.required_bytes)
        self.assertEqual(26,cached.required_bytes)
        for values in [([],100,0),([True],100,0),([1],None,0),([1],100,-1)]:
            with self.assertRaises(ValueError): plan_storage(*values)

    def test_remote_full_disk_refuses_before_importing_downloader(self):
        with tempfile.TemporaryDirectory() as folder:
            settings={**self.settings(),"fileSizes":{"model.gguf":100}}
            with patch("engine_room.model_server.shutil.disk_usage",return_value=SimpleNamespace(free=1)),self.assertRaisesRegex(ValueError,"Not enough model storage"):
                download(settings,folder)
            self.assertEqual([],list(Path(folder).iterdir()))

    def test_safetensors_validation_happens_before_rental_not_only_on_remote_disk(self):
        settings=dict(id="example/model",revision="a"*40,context=8192,engine="vLLM",dtype="float16",fileSizes={"model unsafe.safetensors":100})
        with self.assertRaisesRegex(ValueError,"filename"): command(settings)
        settings["fileSizes"]={"model.safetensors":100}
        self.assertEqual("vllm",command(settings)[0])

    def test_vllm_checks_actual_disk_before_implicit_download(self):
        settings=dict(id="example/model",revision="a"*40,fileSizes={"model.safetensors":100})
        with tempfile.TemporaryDirectory() as folder:
            with patch("engine_room.model_server.shutil.disk_usage",return_value=SimpleNamespace(free=1)),self.assertRaisesRegex(ValueError,"Not enough model storage"):
                check_storage(settings,folder,["model.safetensors"],snapshot_cache=True)

    def test_vllm_cache_reuse_requires_correct_snapshot_and_hash(self):
        content=b"synthetic safetensors"
        settings=dict(id="example/model",revision="a"*40,fileSizes={"model.safetensors":len(content)},fileHashes={"model.safetensors":hashlib.sha256(content).hexdigest()})
        with tempfile.TemporaryDirectory() as folder:
            snapshot=Path(folder)/"hub"/"models--example--model"/"snapshots"/("a"*40)
            snapshot.mkdir(parents=True)
            (snapshot/"model.safetensors").write_bytes(content)
            with patch("engine_room.model_server.shutil.disk_usage",return_value=SimpleNamespace(free=1024**3+len(content))):
                plan=check_storage(settings,folder,["model.safetensors"],snapshot_cache=True)
            self.assertEqual(len(content),plan.cached_bytes)
            self.assertEqual(content,(snapshot/"model.safetensors").read_bytes())

    def test_hash_verified_cache_and_pinned_download(self):
        with tempfile.TemporaryDirectory() as folder:
            content=b"synthetic GGUF fixture"
            Path(folder,"model.gguf").write_bytes(content)
            settings={**self.settings(),"fileSizes":{"model.gguf":len(content)},"fileHashes":{"model.gguf":hashlib.sha256(content).hexdigest()}}
            calls=[]
            fake=SimpleNamespace(hf_hub_download=lambda *a,**k:calls.append((a,k)))
            with patch.dict("sys.modules",{"huggingface_hub":fake}),patch("engine_room.model_server.shutil.disk_usage",return_value=SimpleNamespace(free=1024**3+len(content))):
                download(settings,folder)
            self.assertEqual("a"*40,calls[0][1]["revision"])
            self.assertEqual(content,Path(folder,"model.gguf").read_bytes())


if __name__=="__main__": unittest.main()
