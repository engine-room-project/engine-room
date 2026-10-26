import base64
from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.attachment_identity import Identity,key_file


def public(marker=b"a"):
    return "ssh-ed25519 "+base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"+marker*32).decode()


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.key=self.root/"dedicated-key"; self.key.write_text("synthetic private identity"); self.key.chmod(0o600)
        self.credentials=Mock(); self.credentials.read.return_value=str(self.key)
        self.runner=Mock(return_value=Mock(returncode=0,stdout=public().encode()))
        self.settings=dict(host="10.0.0.1",port=22,username="modeluser",host_key=public(b"h"),model_port=8000,model_id="example/model")
    def load(self,**changes): return Identity.load(self.settings|changes,"explicit-path",self.credentials,runner=self.runner)
    def test_explicit_saved_identity_binds_host_account_and_model_without_network(self):
        identity=self.load(); self.credentials.read.assert_called_once_with("explicit-path")
        self.runner.assert_called_once()
        self.assertEqual(["ssh-keygen","-y","-P","","-f",str(self.key)],self.runner.call_args.args[0])
        self.assertNotIn(str(self.key),repr(identity))
        for change in (dict(username="different"),dict(host_key=public(b"k")),dict(host="10.0.0.2")):
            self.assertNotEqual(identity.account_id,self.load(**change).account_id)
        self.assertNotEqual(identity.resource_id,self.load(model_port=8001).resource_id)
        self.runner.return_value.stdout=public(b"b").encode()
        self.assertNotEqual(identity.account_id,self.load().account_id)
    def test_invalid_target_key_and_expansion_refuse_before_key_derivation(self):
        for change in (dict(host="8.8.8.8"),dict(host="127.0.0.1"),dict(port=True),dict(model_port=22),dict(username="bad;command"),dict(host_key="ssh-ed25519 bad"),dict(model_id="bad model")):
            with self.assertRaises(ValueError): self.load(**change)
        self.runner.assert_not_called(); self.credentials.read.assert_not_called()
        self.credentials.read.return_value=str(self.root/"key%h")
        with self.assertRaises(ValueError): self.load()
        self.runner.assert_not_called()
    @unittest.skipIf(os.name=="nt","POSIX owner permissions")
    def test_nonprivate_or_linked_key_is_preserved_and_refused(self):
        self.key.chmod(0o644)
        with self.assertRaises(ValueError): self.load()
        self.assertEqual(0o644,self.key.stat().st_mode&0o777)
        self.key.chmod(0o600); link=self.root/"linked"; link.symlink_to(self.key)
        self.credentials.read.return_value=str(link)
        with self.assertRaises(ValueError): self.load()
        self.runner.assert_not_called()
    @unittest.skipUnless(sys.platform.startswith("linux"),"Linux private Unix forwarding")
    def test_forward_is_single_pinned_loopback_read_only_and_preserves_existing_state(self):
        identity=self.load(); trust=self.root/"trust"; target=trust/"model.sock"
        args=identity.forward_args(trust,target)
        self.assertIn("-N",args); self.assertEqual(1,args.count("-L")); self.assertNotIn("-R",args)
        self.assertEqual(str(target)+":127.0.0.1:8000",args[args.index("-L")+1])
        self.assertEqual("modeluser@10.0.0.1",args[-1]); self.assertEqual(0o600,(trust/"known-hosts").stat().st_mode&0o777)
        for option in ("BatchMode=yes","IdentityAgent=none","ProxyCommand=none","PermitLocalCommand=no","StreamLocalBindUnlink=no"):
            self.assertIn(option,args)
        before=(trust/"known-hosts").read_bytes()
        with self.assertRaises(FileExistsError): identity.forward_args(trust,target)
        self.assertEqual(before,(trust/"known-hosts").read_bytes())
        target.write_text("unrelated existing path")
        with self.assertRaises(ValueError): identity.forward_args(trust,target)
        self.assertEqual("unrelated existing path",target.read_text())
    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("ssh"),"Read-only actual OpenSSH config parser")
    def test_actual_ssh_parser_accepts_forward_without_connecting(self):
        identity=self.load(); trust=self.root/"parse"; args=identity.forward_args(trust,trust/"m.sock")
        result=subprocess.run([args[0],"-G",*args[1:]],stdin=subprocess.DEVNULL,capture_output=True,timeout=10)
        self.assertEqual(0,result.returncode,result.stderr.decode())
        output=result.stdout.decode()
        for value in ("identityagent none","certificatefile none","permitlocalcommand no","sessiontype none"):
            self.assertIn(value,output)
        self.assertFalse((trust/"m.sock").exists())
