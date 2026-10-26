from dataclasses import asdict,replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from engine_room.attachment_client import ForwardClient
from engine_room.connections import Connection
from engine_room.records import Receipt,Store,atomic_json
from engine_room.controller_protocol import encode
from test_attachment_forward import FIXTURE

IDENTITY_SOURCE=FIXTURE.split("class Identity:",1)[1].split("r=Receipt(",1)[0]
CLIENT_FIXTURE="""import sys,os,time,pathlib
sys.path.insert(0,sys.argv[1])
from engine_room import attachment_identity
from engine_room.attachment_forward import main
from engine_room import attachment_forward
_original=attachment_forward.ForwardSupervisor
import subprocess
def owned_child(*args,**kwargs):
 (pathlib.Path(sys.argv[2])/'child-started').write_text('synthetic')
 return subprocess.Popen(*args,**kwargs)
attachment_forward.ForwardSupervisor=lambda *args,**kwargs:_original(*args,**kwargs,popen=owned_child,lease_seconds=float(os.environ.get("FIXTURE_FORWARD_LEASE","60")))
class Identity:
"""+IDENTITY_SOURCE+"""
def load_identity(*args):
 from dataclasses import replace
 from engine_room.records import Store
 store=Store(pathlib.Path(sys.argv[2])/'receipts')
 if os.environ.get('FIXTURE_IDENTITY_FAILURE')=='1': raise ValueError('synthetic credential failure')
 if os.environ.get('FIXTURE_DETACH_DURING_LOAD')=='1':
  store.save(replace(store.load('attached'),state='detached'))
 if os.environ.get('FIXTURE_CHANGE_RESOURCE')=='1':
  store.save(replace(store.load('attached'),resource_id='changed-model'))
 return Identity()
attachment_identity.Identity.load=staticmethod(load_identity)
raise SystemExit(main(sys.argv[2]))
"""


@unittest.skipUnless(sys.platform.startswith("linux"),"Actual parent/helper private Unix control")
class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        (self.root/"bin").mkdir(mode=0o700); (self.root/"bin"/"ssh").symlink_to(sys.executable)
        (self.root/"s").mkdir(mode=0o700)
        self.receipt=Receipt("attached","connection","ssh","fixture-account","attachment","active",1000,resource_id="fixture-model")
        Store(self.root/"receipts").save(self.receipt)
        self.connection=Connection("connection","ssh","fixture-account","Synthetic existing model","chosen-path",{})
        self.save(self.connection)
        self.processes=[]; self.lease=60; self.detach_during_load=False; self.change_resource=False; self.identity_failure=False
        self.client=ForwardClient(self.root,self.receipt,popen=self.spawn)
        self.addCleanup(self.cleanup)
    def save(self,connection): atomic_json(self.root/"connections.json",dict(schema=1,connections=[asdict(connection)]))
    def spawn(self,command,**kwargs):
        self.assertIn("engine_room.attachment_forward",command[3])
        process=subprocess.Popen([sys.executable,"-I","-c",CLIENT_FIXTURE,command[-2],command[-1]],
            env={**os.environ,"PATH":str(self.root/"bin")+os.pathsep+os.environ.get("PATH",""),"FIXTURE_FORWARD_LEASE":str(self.lease),"FIXTURE_IDENTITY_FAILURE":"1" if self.identity_failure else "0","FIXTURE_DETACH_DURING_LOAD":"1" if self.detach_during_load else "0","FIXTURE_CHANGE_RESOURCE":"1" if self.change_resource else "0"},**kwargs)
        self.processes.append(process); return process
    def cleanup(self):
        self.client.close()
        for process in self.processes:
            if process.poll() is None: process.kill(); process.wait(timeout=3)
    def test_saved_scope_starts_private_endpoint_and_explicit_close_is_confirmed(self):
        endpoint=self.client.start()
        self.assertEqual(self.receipt.operation_key(),endpoint.operation_key)
        self.assertEqual("fixture-model",endpoint.resource_id)
        self.client.pulse()
        with self.assertRaises(ValueError): self.client.start()
        self.assertEqual(1,len(self.processes))
        self.assertTrue(self.client.close()); self.assertTrue(self.client.close())
        self.assertFalse(Path(endpoint.path).exists())
        with self.assertRaises(ValueError): self.client.pulse()
    def test_changed_saved_account_refuses_before_forward_or_credential_import(self):
        self.save(Connection("connection","ssh","different-account","Synthetic","chosen-path",{}))
        with self.assertRaises(ValueError): self.client.start()
        self.assertEqual([],list((self.root/"s").iterdir()))
        self.assertFalse((self.root/"credentials").exists())
    def test_helper_loss_is_not_disconnect_confirmation(self):
        endpoint=self.client.start()
        self.client.process.kill(); self.client.process.wait(timeout=3)
        self.assertFalse(self.client.close())
        self.assertTrue(Path(endpoint.path).exists()) # unknown/stale path is preserved, never adopted

    def test_no_background_pulses_keep_an_unattended_helper_alive(self):
        self.lease=3
        endpoint=self.client.start()
        self.client.process.wait(timeout=6)
        self.assertTrue(self.client.close())
        self.assertFalse(Path(endpoint.path).exists())
    def test_start_pipe_cannot_override_saved_connection_or_echo_input(self):
        command=[sys.executable,"-I","-c","engine_room.attachment_forward",str(Path(__file__).resolve().parents[1]),str(self.root)]
        process=self.spawn(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        raw=encode(dict(operation_id=self.receipt.operation_id,operation_key=self.receipt.operation_key(),connection={"secret":"synthetic-do-not-echo"}))
        output,error=process.communicate(raw,timeout=6)
        self.assertEqual(b"",error); self.assertEqual(1,process.returncode)
        self.assertNotIn(b"synthetic-do-not-echo",output)
        self.assertFalse((self.root/"credentials").exists())

    def test_saved_detached_receipt_refuses_before_credential_access(self):
        Store(self.root/"receipts").save(replace(self.receipt,state="detached"))
        with self.assertRaises(ValueError): self.client.start()
        self.assertFalse((self.root/"credentials").exists())
        self.assertEqual([],list((self.root/"s").iterdir()))

    def test_disconnect_during_identity_check_prevents_forward_start(self):
        self.detach_during_load=True
        with self.assertRaises(ValueError): self.client.start()
        state_root=self.root/"s"/self.receipt.operation_key()[:16]
        proof=__import__("json").loads((state_root/"forward.json").read_text())
        self.assertEqual("closed",proof["state"]); self.assertTrue(proof["disconnected"])
        self.assertIsNone(proof["endpoint"]); self.assertFalse((state_root/"m.sock").exists())
    def test_pulse_after_account_change_revokes_only_the_owned_forward(self):
        endpoint=self.client.start()
        self.save(Connection("connection","ssh","different-account","Synthetic","chosen-path",{}))
        self.client.pulse(); self.client.process.wait(timeout=6)
        self.assertTrue(self.client.close()); self.assertFalse(Path(endpoint.path).exists())
        self.assertEqual("active",Store(self.root/"receipts").load("attached").state)

    def test_changed_resource_during_identity_check_prevents_forward(self):
        self.change_resource=True
        with self.assertRaises(ValueError): self.client.start()
        state_root=self.root/"s"/self.receipt.operation_key()[:16]
        self.assertFalse((state_root/"m.sock").exists())
        self.assertEqual("changed-model",Store(self.root/"receipts").load("attached").resource_id)

    def test_parent_eof_before_start_never_launches_ssh_child(self):
        command=[sys.executable,"-I","-c","engine_room.attachment_forward",str(Path(__file__).resolve().parents[1]),str(self.root)]
        process=self.spawn(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        output,error=process.communicate(encode(dict(operation_id=self.receipt.operation_id,operation_key=self.receipt.operation_key())),timeout=8)
        self.assertEqual(b"",error); self.assertEqual(0,process.returncode)
        result=__import__("json").loads(output)
        self.assertEqual("parent-ended",result["reason"]); self.assertTrue(result["disconnected"])
        self.assertFalse((self.root/"child-started").exists())

    def test_identity_failure_confirms_no_child_and_preserves_acknowledgement(self):
        self.identity_failure=True
        with self.assertRaises(ValueError): self.client.start()
        self.assertTrue(self.client.close())
        self.assertFalse((self.root/"child-started").exists())
        proof=__import__("json").loads((self.root/"s"/self.receipt.operation_key()[:16]/"forward.json").read_text())
        self.assertEqual("closed",proof["state"]); self.assertTrue(proof["disconnected"])
        self.assertIsNone(proof["endpoint"])

    def test_identity_failure_never_overwrites_prior_operation_evidence(self):
        self.identity_failure=True
        directory=self.root/"s"/self.receipt.operation_key()[:16]; directory.mkdir(mode=0o700)
        proof=directory/"forward.json"; proof.write_text('original evidence',encoding="utf-8")
        with self.assertRaises(ValueError): self.client.start()
        self.assertFalse(self.client.close())
        self.assertEqual('original evidence',proof.read_text(encoding="utf-8"))
        self.assertFalse((self.root/"child-started").exists())
