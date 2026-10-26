import base64
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock,patch

from engine_room.payload import FILES,ROOT,source_payload
from engine_room_connectors._colab.bootstrap import stage_runtime,staging_code,install_code,start_install
from test_colab_probe import plan,report
from test_records import rental


class StagingTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location("standalone_stage",ROOT/"remote/stage.py")
        self.module=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.key="a"*64
        self.payload=source_payload(plan()); self.names=FILES+("model.json",)
        self.root=self.base/("engine-room-"+self.key[:32])
    def stage(self):
        return self.module.stage(str(self.base),self.key,self.payload["base64"],self.payload["sha256"],self.names)
    def test_actual_payload_stages_with_flushed_owner_proof_and_exact_files(self):
        result=self.stage()
        self.assertEqual("staged",result["state"])
        proof=json.loads((self.root/".engine-room-owner.json").read_text())
        self.assertEqual(self.key,proof["operation_key"]); self.assertEqual("staged",proof["state"])
        actual={p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(set(self.names)|{".engine-room-owner.json"},actual)
        self.assertEqual(plan()["revision"],json.loads((self.root/"model.json").read_text())["revision"])
    def test_existing_directory_is_never_adopted_overwritten_or_removed(self):
        self.root.mkdir(); sentinel=self.root/"unrelated.txt"; sentinel.write_text("keep")
        with self.assertRaises(FileExistsError): self.stage()
        self.assertEqual("keep",sentinel.read_text()); self.assertEqual([sentinel],list(self.root.iterdir()))
    def test_hash_failure_leaves_filesystem_untouched(self):
        self.payload["sha256"]="0"*64
        with self.assertRaises(ValueError): self.stage()
        self.assertEqual([],list(self.base.iterdir()))
    def malicious(self,members):
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode="w:gz") as archive:
            for member,data in members: archive.addfile(member,io.BytesIO(data))
        raw=output.getvalue(); self.payload=dict(base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())
    def test_link_traversal_duplicate_and_expanding_archives_refuse_before_creating_folder(self):
        for kind in ("link","traversal","duplicate","expansion"):
            member=tarfile.TarInfo("model.json")
            if kind=="link": member.type=tarfile.SYMTYPE; member.linkname="/unrelated"
            if kind=="traversal": member.name="../model.json"
            data=b"x"*(6*1024*1024) if kind=="expansion" else b"{}"
            if kind not in {"link"}: member.size=len(data)
            self.malicious([(member,data)]*(2 if kind=="duplicate" else 1))
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.module.stage(str(self.base),self.key,self.payload["base64"],self.payload["sha256"],["model.json"])
            self.assertFalse(self.root.exists())
    def test_partial_write_failure_retains_owned_state_and_unrelated_sibling(self):
        sentinel=self.base/"unrelated.txt"; sentinel.write_text("keep")
        original=self.module.owner_record
        def failed(root,proof):
            if proof["state"]=="staged": raise OSError("Synthetic flush failure")
            original(root,proof)
        with patch.object(self.module,"owner_record",side_effect=failed):
            with self.assertRaises(OSError): self.stage()
        self.assertEqual("extracting",json.loads((self.root/".engine-room-owner.json").read_text())["state"])
        self.assertEqual("keep",sentinel.read_text())
        with self.assertRaises(FileExistsError): self.stage()
    def test_generated_kernel_staging_runs_without_checkout_and_refuses_second_attempt(self):
        receipt=replace(rental(),connector_id="colab",resource_id="owned",state="active",protection_id="proof")
        snippet,payload=staging_code(receipt,plan())
        snippet=snippet.replace(repr("/content"),repr(self.base.as_posix()))
        first=subprocess.run([sys.executable,"-I","-"],input=snippet,cwd=self.base,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,first.returncode,first.stderr)
        result=json.loads(first.stdout); self.assertEqual(payload["sha256"],result["source_sha256"])
        second=subprocess.run([sys.executable,"-I","-"],input=snippet,cwd=self.base,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(0,second.returncode)
        self.assertEqual("staged",json.loads((Path(result["root"])/".engine-room-owner.json").read_text())["state"])


class BootstrapWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.receipt=replace(rental(),connector_id="colab",resource_id="owned",state="active",protection_id="proof")
        self.session=Mock(); self.authorize=Mock(); self.cancel=Mock(); self.cancel.is_set.return_value=False
        _,payload=staging_code(self.receipt,plan())
        self.ack=dict(root="/content/engine-room-"+self.receipt.operation_key()[:32],source_sha256=payload["sha256"],state="staged")
    def stage(self):
        return stage_runtime(self.session,"connection",self.receipt,plan(),"A100",authorize=self.authorize,cancel=self.cancel)
    def test_checked_inventory_precedes_staging_and_only_exact_acknowledgement_is_accepted(self):
        self.session.execute.side_effect=[json.dumps(report()),json.dumps(self.ack)]
        result=self.stage(); self.assertEqual("staged",result["state"])
        self.assertEqual(2,self.session.execute.call_count)
        for call in self.session.execute.call_args_list:
            self.assertIs(self.authorize,call.kwargs["authorize"])
            self.assertIs(self.cancel,call.kwargs["cancel"])
    def test_invalid_capacity_prevents_staging_and_bad_ack_stays_uncertain(self):
        self.session.execute.return_value=json.dumps(report()|{"disk_free_bytes":1})
        with self.assertRaises(ValueError): self.stage()
        self.assertEqual(1,self.session.execute.call_count)
        self.session.execute.side_effect=[json.dumps(report()),json.dumps(self.ack|{"source_sha256":"0"*64})]
        with self.assertRaisesRegex(ValueError,"not confirmed"): self.stage()


class NativeInstallLaunchTests(unittest.TestCase):
    stage=StagingTests.stage
    def setUp(self):
        StagingTests.setUp(self)
        self.receipt=replace(rental(),connector_id="colab",resource_id="owned",state="active",protection_id="proof",created_at=999,deadline=2000)
        self.key=self.receipt.operation_key(); self.root=self.base/("engine-room-"+self.key[:32])
        self.stage()
        self.production="/content/engine-room-"+self.key[:32]
        self.staged=dict(root=self.production,source_sha256=self.payload["sha256"],state="staged")
    def run_launcher(self):
        program=install_code(self.receipt,plan(),self.staged).replace(repr(self.production),repr(str(self.root)))
        prefix="""import subprocess,types,pathlib,json,time
time.time=lambda:1000
def fake(args,**kwargs):
    root=pathlib.Path(kwargs['cwd'])
    proof=json.loads((root/'install-start.json').read_text())
    assert proof['state']=='submitted'
    (root/'fake-launch.json').write_text(json.dumps({'args':args,'env':kwargs['env'],'detached':kwargs['start_new_session']}))
    return types.SimpleNamespace(pid=12345)
subprocess.Popen=fake
"""
        return subprocess.run([sys.executable,"-I","-"],input=prefix+program,capture_output=True,text=True,timeout=30,
            env={**os.environ,"HF_TOKEN":"synthetic-private-model-token"})
    def test_actual_launcher_records_intent_and_passes_only_isolated_environment(self):
        result=self.run_launcher(); self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual("installing",json.loads(result.stdout)["state"])
        called=json.loads((self.root/'fake-launch.json').read_text())
        self.assertEqual('/usr/bin/timeout',called['args'][0]); self.assertTrue(called['detached'])
        self.assertEqual({'PATH','HOME','LC_ALL','ENGINE_ROOM_ROOT'},set(called['env']))
        self.assertNotIn('synthetic-private-model-token',json.dumps(called))
        self.assertFalse((self.root/'runtime-ready').exists())
        repeated=self.run_launcher(); self.assertNotEqual(0,repeated.returncode)
    def test_changed_payload_refuses_before_process_or_start_marker(self):
        (self.root/'remote/install-colab.sh').write_text('uninspected source')
        result=self.run_launcher(); self.assertNotEqual(0,result.returncode)
        self.assertFalse((self.root/'fake-launch.json').exists()); self.assertFalse((self.root/'install-start.json').exists())
    def test_unconfirmed_stage_or_unprepared_engine_refuses_without_kernel_call(self):
        session=Mock()
        with self.assertRaises(ValueError):
            start_install(session,'connection',self.receipt,plan(),self.staged|{'state':'unknown'},authorize=Mock(),cancel=Mock())
        session.execute.assert_not_called()
        with self.assertRaises(ValueError):
            install_code(self.receipt,plan()|{'engine':'unsupported'},self.staged)
