import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import select
import tempfile
import threading
import unittest
from unittest.mock import Mock

from engine_room_connectors._colab.channel import public_key
from engine_room_connectors._colab.proxy import access
from engine_room_connectors._colab.ssh_proxy import bridge,load_access,save_access,validate
from test_records import rental

KEY="ssh-ed25519 "+base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"+b"x"*32).decode()


def scoped():
    return access("owned",dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-private-runtime",tokenExpiresInSeconds=60),1000)


class KeyTests(unittest.TestCase):
    def test_public_key_wire_format_rejects_injection_and_wrong_algorithms(self):
        self.assertEqual(KEY,public_key(KEY))
        for key in (KEY+"\nInjected: value",KEY+" comment",KEY.replace("ssh-ed25519 ","ssh-rsa "),"ssh-ed25519 eA=="):
            with self.assertRaises(ValueError): public_key(key)


@unittest.skipUnless(os.name=="posix","Native SSH proxy runs on the Linux controller")
class PrivateAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name); self.directory.chmod(0o700)
        self.receipt=replace(rental(),connector_id="colab",resource_id="owned",state="active",protection_id="controller",created_at=999,deadline=2000)
        self.authorize=Mock()
    def save(self): return save_access(self.directory,self.receipt,scoped(),KEY,authorize=self.authorize,now=lambda:1000)
    def test_runtime_only_file_is_private_bound_and_repr_hides_token(self):
        path=self.save(); self.authorize.assert_called_once_with()
        result=load_access(path,self.receipt.operation_key(),now=lambda:1000)
        self.assertEqual(scoped().token,result.lease.token)
        self.assertNotIn(scoped().token,repr(result)); self.assertEqual(0o600,path.stat().st_mode&0o777)
        self.assertEqual({"schema","resource_id","url","token","expires_at","deadline","operation_key","public_key"},set(json.loads(path.read_text())))
        for scope,now in (("b"*64,1000),(self.receipt.operation_key(),1060)):
            with self.assertRaises(ValueError): load_access(path,scope,now=lambda:now)
    def test_cancelled_gate_or_wrong_resource_never_writes(self):
        self.authorize.side_effect=ValueError("Stopped")
        with self.assertRaises(ValueError): self.save()
        self.assertFalse((self.directory/"ssh-access.json").exists())
        self.authorize.reset_mock(); self.receipt=replace(self.receipt,resource_id="unrelated")
        with self.assertRaises(ValueError): self.save()
        self.authorize.assert_not_called()
    def test_broad_permissions_symlinks_and_arbitrary_files_refuse(self):
        path=self.save(); path.chmod(0o644)
        with self.assertRaises(ValueError): load_access(path,self.receipt.operation_key(),now=lambda:1000)
        path.chmod(0o600); self.directory.chmod(0o755)
        with self.assertRaises(ValueError): load_access(path,self.receipt.operation_key(),now=lambda:1000)
        self.directory.chmod(0o700)
        target=self.directory/"elsewhere.json"; path.rename(target); path.symlink_to(target)
        with self.assertRaises(OSError): load_access(path,self.receipt.operation_key(),now=lambda:1000)
        with self.assertRaises(ValueError): load_access(target,self.receipt.operation_key(),now=lambda:1000)


class FakeChannel:
    def __init__(self,cancel): self.cancel=cancel; self.sent=[]; self.received=False; self.input=threading.Event(); self.closed=False
    def check(self):
        if self.cancel.is_set(): raise RuntimeError("Closed")
    def send_bytes(self,data): self.sent.append(data); self.input.set()
    def receive_bytes(self):
        while not self.input.wait(0.1): self.check()
        if not self.received:
            self.received=True; return b"synthetic-server-ssh"
        self.cancel.wait(3); self.check(); raise RuntimeError("No data")
    def close(self): self.closed=True; self.cancel.set(); self.input.set()


@unittest.skipUnless(os.name=="posix","Native stdio bridge uses Linux descriptors")
class BridgeTests(unittest.TestCase):
    def test_real_pipes_deliver_both_directions_and_parent_eof_stops_proxy(self):
        incoming,writer=os.pipe(); reader,outgoing=os.pipe()
        cancel=threading.Event(); channel=FakeChannel(cancel); result=[]
        thread=threading.Thread(target=lambda:result.append(bridge(channel,incoming,outgoing,cancel=cancel)))
        thread.start()
        try:
            os.write(writer,b"synthetic-client-ssh")
            ready,_,_=select.select([reader],[],[],3); self.assertTrue(ready)
            self.assertEqual(b"synthetic-server-ssh",os.read(reader,4096))
            self.assertEqual(b"synthetic-client-ssh",b"".join(channel.sent))
            os.close(writer); writer=None
            thread.join(timeout=3); self.assertFalse(thread.is_alive()); self.assertEqual([0],result)
            self.assertTrue(channel.closed)
        finally:
            cancel.set(); channel.close(); thread.join(timeout=3)
            for fd in (incoming,writer,reader,outgoing):
                if fd is not None: os.close(fd)
