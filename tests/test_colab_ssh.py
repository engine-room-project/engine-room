from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock

from engine_room_connectors._colab.ssh import ColabSSH,scan_authenticated
from test_colab_ssh_proxy import KEY,scoped
from test_records import rental


@unittest.skipUnless(os.name=="posix","Colab OpenSSH runs on the Linux controller")
class ColabSSHTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name); self.directory.chmod(0o700)
        self.receipt=replace(rental(),connector_id="colab",resource_id="owned",state="active",protection_id="controller",created_at=999,deadline=2000)
        self.authorize=Mock(); self.supplier=Mock(return_value=scoped()); self.commands=[]
        def runner(args,**kwargs):
            self.commands.append(args)
            if args[0]=="ssh-keygen":
                path=Path(args[args.index("-f")+1]); path.write_text("synthetic operation key"); path.with_suffix(".pub").write_text(KEY)
            return subprocess.CompletedProcess(args,0,b"",b"")
        self.runner=runner; self.scanner=Mock(return_value=KEY)
        self.ssh=ColabSSH(self.directory,self.receipt,self.supplier,self.authorize,now=lambda:1000,runner=runner,scanner=self.scanner)
    def enroll(self): return self.ssh.enroll(cancel=threading.Event())
    def test_enrollment_records_pending_before_authenticated_scan_and_never_replaces_key(self):
        def scan(*args,**kwargs):
            proof=json.loads(self.ssh.identity.read_text())
            self.assertEqual("pending",proof["state"])
            self.assertEqual(self.receipt.operation_key(),proof["operation_key"])
            return KEY
        self.scanner.side_effect=scan
        self.assertEqual(KEY,self.enroll())
        original=self.ssh.known.read_bytes(); self.scanner.reset_mock()
        self.assertEqual(KEY,self.enroll()); self.scanner.assert_not_called()
        self.assertEqual(original,self.ssh.known.read_bytes())
        self.ssh.known.write_text("unrelated changed host")
        with self.assertRaises(ValueError): self.ssh.args()
        self.assertEqual("unrelated changed host",self.ssh.known.read_text())
    def test_uncertain_scan_cannot_be_repeated_or_used_for_connection(self):
        self.scanner.side_effect=RuntimeError("Synthetic lost native response")
        with self.assertRaises(RuntimeError): self.enroll()
        self.assertEqual("pending",json.loads(self.ssh.identity.read_text())["state"])
        self.scanner.reset_mock()
        with self.assertRaises(ValueError): self.enroll()
        self.scanner.assert_not_called()
        with self.assertRaises(ValueError): self.ssh.args()
    def test_strict_args_use_only_operation_identity_and_no_token_command_argument(self):
        self.enroll(); args=self.ssh.args(); text=" ".join(args)
        for item in ("StrictHostKeyChecking=yes","IdentityAgent=none","IdentitiesOnly=yes","CertificateFile=none","PasswordAuthentication=no","KbdInteractiveAuthentication=no","ForwardAgent=no"):
            self.assertIn(item,args)
        self.assertIn("none",args); self.assertIn(str(self.ssh.key),args)
        self.assertNotIn(scoped().token,text); self.assertNotIn("colab_cli",text)
        self.assertIn("-I",text); self.assertIn("ssh_proxy.py",text)
    def test_cleanup_preserves_unowned_host_files_and_only_stops_own_handle(self):
        self.ssh.generate(); foreign=self.ssh.known; foreign.write_text("unrelated")
        with self.assertRaises(ValueError): self.ssh.discard_keys()
        self.assertEqual("unrelated",foreign.read_text()); self.assertTrue(self.ssh.key.exists())
        foreign.unlink(); self.enroll()
        unrelated=self.directory/"unrelated.txt"; unrelated.write_text("keep")
        self.ssh.discard_keys(); self.assertEqual("keep",unrelated.read_text())
        self.assertFalse(self.ssh.key.exists()); self.assertFalse(self.ssh.identity.exists())
    def test_a_native_tunnel_prevents_second_command_without_closing_other_sessions(self):
        self.enroll(); tunnel=Mock(); tunnel.poll.return_value=None; self.ssh.tunnel=tunnel
        count=len(self.commands)
        with self.assertRaises(RuntimeError): self.ssh.run("true")
        self.assertEqual(count,len(self.commands)); tunnel.terminate.assert_not_called()
        self.ssh.tunnel=None
    def test_existing_unowned_key_is_not_adopted(self):
        self.ssh.key.write_text("unrelated")
        with self.assertRaises(ValueError): self.ssh.generate()
        self.assertEqual("unrelated",self.ssh.key.read_text()); self.assertEqual([],self.commands)
    @unittest.skipUnless(shutil.which("ssh"),"OpenSSH client is required for actual option parsing")
    def test_actual_openssh_parses_isolated_strict_configuration_without_connecting(self):
        self.enroll()
        result=subprocess.run(self.ssh.args()+["-G","root@colab-runtime"],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(0,result.returncode,result.stderr.decode())
        config=result.stdout.decode()
        self.assertIn("identityagent none",config); self.assertIn("passwordauthentication no",config)
        self.assertIn("stricthostkeychecking true",config); self.assertNotIn(scoped().token,config)


class EnrollmentChannel:
    def __init__(self,cancel): self.cancel=cancel; self.input=threading.Event(); self.sent=False
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def check(self):
        if self.cancel.is_set(): raise RuntimeError("Closed")
    def send_bytes(self,data): self.input.set()
    def receive_bytes(self):
        while not self.input.wait(0.1): self.check()
        if not self.sent: self.sent=True; return KEY.encode()+b"\n"
        self.cancel.wait(3); self.check(); raise RuntimeError("No data")
    def close(self): self.cancel.set(); self.input.set()


@unittest.skipUnless(os.name=="posix","Authenticated local enrollment bridge uses Linux descriptors")
class EnrollmentBridgeTests(unittest.TestCase):
    def test_scanner_reads_key_only_through_the_selected_authenticated_bridge(self):
        calls=[]
        def channel(lease,key,deadline,**kwargs):
            self.assertEqual(scoped(),lease); self.assertEqual(KEY,key)
            calls.append(deadline); return EnrollmentChannel(kwargs["cancel"])
        def runner(args,**kwargs):
            port=int(args[args.index("-p")+1])
            with socket.create_connection(("127.0.0.1",port),timeout=3) as peer:
                peer.sendall(b"synthetic-keyscan")
                data=b""
                while not data.endswith(b"\n"): data+=peer.recv(4096)
            return subprocess.CompletedProcess(args,0,f"[127.0.0.1]:{port} ".encode()+data,b"")
        actual=scan_authenticated(scoped(),KEY,2000,cancel=threading.Event(),runner=runner,channel_factory=channel,now=lambda:1000)
        self.assertEqual(KEY,actual); self.assertEqual([1030],calls)
    def test_cached_keyscan_output_without_authenticated_connection_cannot_enroll(self):
        runner=Mock(return_value=subprocess.CompletedProcess([],0,b"synthetic fabricated keyscan",b""))
        with self.assertRaises((ValueError,RuntimeError)):
            scan_authenticated(scoped(),KEY,2000,cancel=threading.Event(),runner=runner,channel_factory=Mock(),now=lambda:1000)
