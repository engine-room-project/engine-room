from dataclasses import replace
import http.server
import json
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

from engine_room.private_endpoint import ModelEndpoint,EndpointHTTP,address
from engine_room.ssh import PinnedSSH
from test_records import rental


class AddressTests(unittest.TestCase):
    def test_endpoint_refuses_port_fallback_extra_fields_wrong_scope_and_resource(self):
        with tempfile.TemporaryDirectory() as root:
            target=ModelEndpoint(str(Path(root)/"m.sock"),"a"*64,"owned",1,2,3)
            self.assertEqual(target,ModelEndpoint.read(target.data(),root,"a"*64))
            for data in (18000,{"port":18000},target.data()|{"unexpected":True},target.data()|{"operation_key":"b"*64}):
                with self.assertRaises(ValueError): ModelEndpoint.read(data,root,"a"*64)
            with self.assertRaises(ValueError): target.validate(root,"a"*64,"unrelated")
            with self.assertRaises(ValueError): address(Path(root)/("x"*110)/"m.sock",root)
            with self.assertRaises(ValueError): address(Path(root).parent/"outside.sock",root)


@unittest.skipUnless(sys.platform.startswith("linux"),"Actual private Unix sockets require Linux peer credentials")
class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.root.chmod(0o700); self.path=self.root/"m.sock"
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); self.server.bind(str(self.path)); self.path.chmod(0o600); self.server.listen(8)
        self.addCleanup(self.server.close); info=self.path.stat()
        self.endpoint=ModelEndpoint(str(self.path),"a"*64,"owned",info.st_dev,info.st_ino,os.getpid())
    def test_actual_owner_and_peer_process_connect(self):
        with self.endpoint.connect(self.root,"a"*64) as peer:
            accepted,_=self.server.accept()
            with accepted: peer.sendall(b"private"); self.assertEqual(b"private",accepted.recv(20))
        with self.assertRaises(ValueError): replace(self.endpoint,pid=os.getpid()+1).connect(self.root,"a"*64)
    def test_replaced_socket_broad_modes_and_links_refuse_without_adoption(self):
        self.path.chmod(0o666)
        with self.assertRaises(ValueError): self.endpoint.connect(self.root,"a"*64)
        self.path.chmod(0o600); self.root.chmod(0o755)
        with self.assertRaises(ValueError): self.endpoint.connect(self.root,"a"*64)
        self.root.chmod(0o700); self.path.unlink(); self.path.write_text("unrelated file")
        with self.assertRaises(ValueError): self.endpoint.connect(self.root,"a"*64)
        self.assertEqual("unrelated file",self.path.read_text())
        self.path.unlink(); other=self.root/"other.sock"; self.path.symlink_to(other)
        with self.assertRaises(ValueError): self.endpoint.connect(self.root,"a"*64)
    def test_actual_unix_http_status_json(self):
        def server():
            peer,_=self.server.accept()
            with peer:
                peer.recv(4096)
                peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 14\r\nConnection: close\r\n\r\n{"ready":true}')
        backend=threading.Thread(target=server); backend.start()
        try:
            self.assertEqual({"ready":True},EndpointHTTP(self.endpoint,self.root,"a"*64).json())
        finally: backend.join(timeout=2)

    def test_unix_http_status_upgrade_trickle_is_bounded(self):
        stop=threading.Event(); outcome=[]
        def server():
            peer,_=self.server.accept()
            with peer:
                try:
                    peer.recv(4096)
                    while not stop.wait(0.05): peer.sendall(b"H")
                except OSError: pass
        backend=threading.Thread(target=server); backend.start()
        def query():
            try: EndpointHTTP(self.endpoint,self.root,"a"*64,timeout=0.3).json(); outcome.append("unsafe success")
            except Exception: outcome.append("bounded refusal")
        client=threading.Thread(target=query); client.start()
        try:
            client.join(timeout=2); self.assertFalse(client.is_alive()); self.assertEqual(["bounded refusal"],outcome)
        finally: stop.set(); client.join(timeout=2); backend.join(timeout=2)


@unittest.skipUnless(sys.platform.startswith("linux"),"Private SSH socket forwards require Linux")
class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.root.chmod(0o700)
        self.receipt=replace(rental(),state="active",resource_id="owned",protection_id="controller")
        self.commands=[]; self.children=[]
        def popen(args,**kwargs):
            self.commands.append(args)
            paths=[args[i+1].split(":127.0.0.1:")[0] for i,v in enumerate(args) if v=="-L"]
            code="""import socket,sys,os,select
servers=[]
for path in sys.argv[1:]:
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.bind(path); os.chmod(path,0o600); s.listen(8); servers.append(s)
while True:
 ready,_,_=select.select(servers,[],[],1)
 for server in ready:
  peer,_=server.accept(); peer.close()
"""
            child=subprocess.Popen([sys.executable,"-I","-c",code,*paths],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.children.append(child); return child
        self.ssh=PinnedSSH(self.root,popen=popen); self.ssh.host="synthetic-host"; self.ssh.args=Mock(return_value=["ssh"])
    def tearDown(self):
        self.ssh.close(self.receipt)
        for child in self.children:
            if child.poll() is None: child.kill(); child.wait(timeout=5)
    def test_actual_owned_child_socket_instances_and_scope_are_used(self):
        self.ssh.forward(self.receipt)
        target=self.ssh.forward_endpoint("model",self.receipt)
        self.assertEqual(self.ssh.tunnel.pid,target.pid)
        with target.connect(self.root,self.receipt.operation_key()): pass
        self.assertIn("StreamLocalBindUnlink=no",self.commands[0]); self.assertIn("StreamLocalBindMask=0177",self.commands[0])
        self.assertTrue(all("127.0.0.1:0" not in value for value in self.commands[0]))
        with self.assertRaises(ValueError): self.ssh.forward_endpoint("model",replace(self.receipt,resource_id="other"))
        self.ssh.close(self.receipt); self.assertFalse(Path(target.path).exists())
    def test_existing_path_refuses_before_any_process_and_is_preserved(self):
        self.ssh.model_socket.write_text("unrelated")
        with self.assertRaises(ValueError): self.ssh.forward(self.receipt)
        self.assertEqual([],self.commands); self.assertEqual("unrelated",self.ssh.model_socket.read_text())
    def test_replaced_owned_path_cannot_receive_traffic_or_be_deleted(self):
        self.ssh.forward(self.receipt); target=self.ssh.forward_endpoint("model",self.receipt)
        self.ssh.model_socket.unlink(); self.ssh.model_socket.write_text("replacement")
        with self.assertRaises(ValueError): target.connect(self.root,self.receipt.operation_key())
        self.ssh.close(self.receipt)
        self.assertEqual("replacement",self.ssh.model_socket.read_text()); self.assertFalse(self.ssh.status_socket.exists())
        self.assertEqual(["model"],json.loads(self.ssh.forward_state.read_text())["preserved_unknown_paths"])
    def test_overlong_socket_path_refuses_before_directory_or_process_creation(self):
        target=self.root/("x"*100)
        with self.assertRaises(ValueError): PinnedSSH(target,popen=Mock())
        self.assertFalse(target.exists())
    @unittest.skipUnless(shutil.which("ssh-keygen"),"Installed OpenSSH key generator")
    def test_long_artifact_names_keep_short_private_socket_paths(self):
        artifact=self.root/("operation-"+"x"*100)
        namespace=self.root/"s"; namespace.mkdir(mode=0o700)
        helper=PinnedSSH(artifact,forward_directory=namespace/("a"*16))
        helper.generate()
        self.assertTrue(helper.key.exists()); self.assertLess(len(os.fsencode(helper.model_socket)),100)
        self.assertTrue(helper.key.with_suffix(".pub").read_text().strip().endswith("engine-room-operation"))

    @unittest.skipUnless(shutil.which("ssh"),"Installed OpenSSH option parser")
    def test_actual_openssh_accepts_private_forward_syntax_and_permissions(self):
        self.ssh.forward(self.receipt)
        # -G parses configuration without connecting or opening another forward.
        args=self.commands[0]
        result=subprocess.run(args[:-1]+["-G",args[-1]],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(0,result.returncode,result.stderr.decode())
        self.assertIn(str(self.ssh.model_socket),result.stdout.decode())
        self.assertIn("streamlocalbindunlink no",result.stdout.decode())
