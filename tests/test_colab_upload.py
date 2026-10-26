from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from engine_room.payload import source_payload
from engine_room_connectors._colab.bootstrap import staging_steps,stage_runtime
from test_colab_model_start import receipt
from test_colab_probe import plan,report


def native_plan():
    return plan()|{"engine":"vLLM","dtype":"float16","files":["model.safetensors"],"fileSizes":{"model.safetensors":10**9}}


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.r=receipt(); self.steps,self.payload=staging_steps(self.r,native_plan())
        self.namespace={}
    def execute(self,code):
        output=io.StringIO()
        with redirect_stdout(output): exec(code.replace(repr("/content"),repr(str(self.base))),self.namespace)
        return json.loads(output.getvalue())
    def test_actual_large_lock_transfers_with_bounded_messages_then_exclusive_verified_stage(self):
        self.assertGreater(len(self.payload["base64"]),262144)
        self.assertGreater(len(self.steps),3)
        for index,(code,ack) in enumerate(self.steps):
            self.assertLess(len(code.encode()),262144)
            result=self.execute(code)
            if index<len(self.steps)-1:
                self.assertEqual(ack,result); self.assertEqual([],list(self.base.iterdir()))
        root=self.base/("engine-room-"+self.r.operation_key()[:32])
        self.assertEqual(str(root),result["root"])
        self.assertEqual(self.payload["sha256"],result["source_sha256"])
        self.assertEqual((Path(__file__).resolve().parents[1]/"remote/requirements-vllm.lock").read_bytes(),(root/"remote/requirements-vllm.lock").read_bytes())
        self.assertNotIn("_engine_room_upload",self.namespace)
    def test_preexisting_memory_state_wrong_scope_offset_and_corrupt_chunk_refuse(self):
        self.namespace["_engine_room_upload"]={"unrelated":"keep"}
        with self.assertRaises(ValueError): self.execute(self.steps[0][0])
        self.assertEqual({"unrelated":"keep"},self.namespace["_engine_room_upload"])
        self.namespace={}; self.execute(self.steps[0][0]); original=self.namespace["_engine_room_upload"].copy()
        for change in ({"operation_key":"b"*64},{"data":"wrong-offset"}):
            self.namespace["_engine_room_upload"]=original|change
            with self.assertRaises(ValueError): self.execute(self.steps[1][0])
        self.namespace["_engine_room_upload"]=original.copy()
        code=self.steps[1][0].replace("if len(_er_chunk)>65536", "_er_chunk='X'+_er_chunk[1:]\nif len(_er_chunk)>65536")
        with self.assertRaises(ValueError): self.execute(code)
        self.assertEqual("",self.namespace["_engine_room_upload"]["data"]); self.assertEqual([],list(self.base.iterdir()))
    def test_full_archive_digest_refuses_changed_buffer_before_creating_files(self):
        for code,_ in self.steps[:-1]: self.execute(code)
        buffer=self.namespace["_engine_room_upload"]; buffer["data"]="X"+buffer["data"][1:]
        with self.assertRaises(ValueError): self.execute(self.steps[-1][0])
        self.assertEqual([],list(self.base.iterdir()))
    def test_existing_destination_preserved_and_image_payload_does_not_include_native_lock(self):
        root=self.base/("engine-room-"+self.r.operation_key()[:32]); root.mkdir(); (root/"unrelated").write_text("keep")
        for code,_ in self.steps[:-1]: self.execute(code)
        with self.assertRaises(FileExistsError): self.execute(self.steps[-1][0])
        self.assertEqual("keep",(root/"unrelated").read_text())
        self.assertLess(len(source_payload(native_plan())["base64"]),100000)
    def test_uncertain_or_cancelled_chunk_stops_pipeline_without_replay(self):
        cancel=threading.Event(); session=Mock(); authorize=Mock()
        inventory={"capacity":{"synthetic":"checked"}}
        with patch("engine_room_connectors._colab.bootstrap.inspect_runtime",return_value=inventory):
            session.execute.side_effect=[json.dumps(self.steps[0][1]),TimeoutError("synthetic uncertain chunk")]
            with self.assertRaises(TimeoutError): stage_runtime(session,"connection",self.r,native_plan(),"A100",authorize=authorize,cancel=cancel)
            self.assertEqual(2,session.execute.call_count)
            session.reset_mock(); session.execute.side_effect=lambda *a,**k:cancel.set() or json.dumps(self.steps[0][1])
            with self.assertRaises(ValueError): stage_runtime(session,"connection",self.r,native_plan(),"A100",authorize=authorize,cancel=cancel)
            self.assertEqual(1,session.execute.call_count)
