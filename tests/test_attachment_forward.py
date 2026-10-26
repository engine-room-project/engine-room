import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest


FIXTURE="""import sys,os,time,pathlib
sys.path.insert(0,sys.argv[1])
from engine_room.attachment_forward import ForwardSupervisor
from engine_room.records import Receipt
class Identity:
 account_id='fixture-account'
 resource_id='fixture-model'
 def forward_args(self,root,path):
  root.mkdir(mode=0o700)
  code="import socket,sys,os,time; s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); os.chmod(sys.argv[1],0o600); s.listen(); s.settimeout(.1); end=time.monotonic()+10\\nwhile time.monotonic()<end:\\n try: c,_=s.accept(); c.close()\\n except socket.timeout: pass"
  return ['ssh','-c',code,str(path)]
r=Receipt('attached','connection','ssh','fixture-account','attachment','active',1000,resource_id='fixture-model')
raise SystemExit(ForwardSupervisor(Identity(),r,pathlib.Path(sys.argv[2]),sys.stdin.buffer,sys.stdout.buffer,lease_seconds=float(sys.argv[3])).run())
"""


@unittest.skipUnless(sys.platform.startswith("linux"),"Actual Linux supervised Unix sockets and parent-death signal")
class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        (self.root/"ssh").symlink_to(sys.executable)
        self.repo=Path(__file__).resolve().parents[1]
    def start(self,lease=60):
        target=self.root/"forward"
        process=subprocess.Popen([sys.executable,"-I","-c",FIXTURE,str(self.repo),str(target),str(lease)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,"PATH":str(self.root)+os.pathsep+os.environ.get("PATH","")})
        self.addCleanup(self.cleanup,process)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            self.assertTrue(selector.select(10),"Supervisor did not report readiness")
        raw=process.stdout.readline(4097)
        ready=json.loads(raw)
        self.assertEqual("ready",ready["event"],raw)
        self.assertFalse(ready["shutdown_confirmed"])
        return process,ready
    def cleanup(self,process):
        if process.stdin: process.stdin.close(); process.stdin=None
        if process.poll() is None:
            try: process.wait(timeout=4)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        for stream in (process.stdout,process.stderr):
            if stream: stream.close()
    def close(self,process):
        process.stdin.close(); process.stdin=None
        output,error=process.communicate(timeout=6)
        self.assertEqual(b"",error)
        return json.loads(output.splitlines()[-1])
    def test_parent_eof_closes_only_owned_forward_and_removes_verified_socket(self):
        process,ready=self.start()
        result=self.close(process)
        self.assertTrue(result["disconnected"]); self.assertFalse(result["shutdown_confirmed"])
        self.assertEqual("parent-ended",result["reason"])
        self.assertFalse(Path(ready["endpoint"]["path"]).exists())
        proof=json.loads((self.root/"forward"/"forward.json").read_text())
        self.assertEqual("closed",proof["state"]); self.assertTrue(proof["disconnected"])
    def test_unrelated_replacement_is_preserved(self):
        process,ready=self.start(); path=Path(ready["endpoint"]["path"])
        path.rename(path.with_name("old.sock")); path.write_text("unrelated")
        result=self.close(process)
        self.assertFalse(result["disconnected"]); self.assertEqual("unrelated",path.read_text())
    def test_liveness_expiry_closes_without_shutdown_claim(self):
        process,ready=self.start(2)
        process.wait(timeout=6)
        output,error=process.communicate(timeout=2)
        self.assertEqual(b"",error)
        result=json.loads(output.splitlines()[-1])
        self.assertEqual("liveness-expired",result["reason"])
        self.assertFalse(result["shutdown_confirmed"])
    def test_explicit_stop_frame_does_not_need_parent_eof(self):
        process,ready=self.start()
        process.stdin.write(b"pulse\nstop\n"); process.stdin.flush()
        process.wait(timeout=6)
        output,error=process.communicate(timeout=2)
        self.assertEqual(b"",error)
        result=json.loads(output.splitlines()[-1])
        self.assertEqual("disconnect-requested",result["reason"]); self.assertTrue(result["disconnected"])
        self.assertFalse(result["shutdown_confirmed"])
    def test_existing_forward_evidence_is_not_overwritten_or_adopted(self):
        target=self.root/"forward"; target.mkdir(mode=0o700)
        proof=target/"forward.json"; proof.write_text("unrelated existing evidence")
        result=subprocess.run([sys.executable,"-I","-c",FIXTURE,str(self.repo),str(target),"60"],input=b"",capture_output=True,timeout=6)
        self.assertEqual(1,result.returncode); self.assertEqual(b"",result.stderr)
        self.assertFalse(json.loads(result.stdout)["disconnected"])
        self.assertEqual("unrelated existing evidence",proof.read_text())
    def test_supervisor_loss_kills_only_its_retained_exec_child(self):
        process,ready=self.start(); child=ready["endpoint"]["pid"]
        process.kill(); process.wait(timeout=3)
        until=time.monotonic()+3
        live=True
        while time.monotonic()<until:
            path=Path('/proc')/str(child)/'stat'
            try: live=path.read_text().split(') ',1)[1].split()[0]!='Z'
            except FileNotFoundError: live=False
            if not live: break
            time.sleep(.02)
        self.assertFalse(live,"Owned exec child remained live after supervisor loss")
