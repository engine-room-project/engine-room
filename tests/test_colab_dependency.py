"""Optional pinned dependency smoke; no authentication or provider network calls."""
from importlib import metadata
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
import uuid
import socket
import struct
import threading
import time
import base64
import hashlib

from engine_room_connectors._colab.auth import SCOPES,login_flow
from engine_room_connectors._colab.api import notebook
from test_records import rental

try:
    pinned=metadata.version("google-colab-cli")==json.loads((Path(__file__).resolve().parents[1]/"controller/colab-source.json").read_text())["version"]
except metadata.PackageNotFoundError:
    pinned=False


@unittest.skipUnless(pinned,"Pinned optional Colab transport is not installed in this core environment")
class ColabDependencyTests(unittest.TestCase):
    def test_pinned_kernel_state_and_reduced_scope_pkce_construct_offline(self):
        with patch("requests.sessions.Session.request",side_effect=AssertionError("Dependency smoke must stay offline")) as network:
            from colab_cli.client import uuid_to_web_safe_base64
            from colab_cli.runtime import ColabRuntime
            from colab_cli.state import StateStore
            flow=login_flow()
            url,_=flow.authorization_url(access_type="offline",prompt="consent",token_usage="remote",include_granted_scopes="false")
            query=parse_qs(urlsplit(url).query)
            self.assertEqual(SCOPES,set(query["scope"][0].split()))
            self.assertEqual(["S256"],query["code_challenge_method"])
            encoded=notebook(rental())
            self.assertEqual(encoded,uuid_to_web_safe_base64(uuid.UUID(encoded[:36].replace("_","-"))))
            with tempfile.TemporaryDirectory() as root:
                self.assertEqual({},StateStore(str(Path(root)/"sessions.json")).list())
            network.assert_not_called()


@unittest.skipUnless(pinned,"Pinned optional Colab transport is not installed")
class BoundedChannelTests(unittest.TestCase):
    def setUp(self):
        from engine_room_connectors._colab.channel import bounded_websocket,Channel
        self.cancel=threading.Event(); self.deadline=time.monotonic()+3
        self.ws=bounded_websocket(self.deadline,self.cancel)
        client,self.peer=socket.socketpair(); self.ws.sock=client; self.ws.connected=True
        self.channel=Channel(self.ws,self.deadline,self.cancel)
        self.addCleanup(self.channel.close); self.addCleanup(self.peer.close)
    def test_actual_frames_reassemble_bounded_text_and_handle_ping(self):
        # Real unmasked server frames; the client must mask its pong.
        self.peer.sendall(b'\x89\x01p\x01\x05{"ok"\x80\x06:true}')
        self.assertEqual({"ok":True},self.channel.receive())
    def test_announced_oversized_frame_refuses_before_waiting_for_payload(self):
        from engine_room_connectors._colab.channel import MAX_MESSAGE
        self.peer.sendall(b"\x81\x7f"+struct.pack("!Q",MAX_MESSAGE+1))
        with self.assertRaisesRegex(RuntimeError,"transfer limit"): self.channel.receive()
    def test_cancelled_or_expired_channel_does_not_wait_for_peer(self):
        self.cancel.set()
        with self.assertRaises(RuntimeError): self.channel.receive()
        self.cancel.clear(); self.channel.deadline=time.monotonic()-1
        with self.assertRaises(RuntimeError): self.channel.receive()
    def test_binary_and_masked_server_messages_are_refused(self):
        self.peer.sendall(b"\x82\x02{}")
        with self.assertRaises(RuntimeError): self.channel.receive()
        self.peer.sendall(b"\x81\x82\x00\x00\x00\x00{}")
        with self.assertRaises(RuntimeError): self.channel.receive()
    def test_trace_mode_refuses_before_any_private_transfer(self):
        import websocket
        with patch.object(websocket,"isEnabledForTrace",return_value=True):
            with self.assertRaises(RuntimeError): self.channel.send({"private":"synthetic"})
    def test_direct_tls_connection_uses_no_proxy_or_redirect_and_only_runtime_header(self):
        from engine_room_connectors._colab.channel import connect
        from engine_room_connectors._colab.proxy import access
        from unittest.mock import Mock
        lease=access("owned",dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-proxy-credential",tokenExpiresInSeconds=60),1000)
        ws=Mock(); ws.sock=None
        raw=Mock(); tls=Mock(); context=Mock(); context.wrap_socket.return_value=tls
        with patch("engine_room_connectors._colab.channel.bounded_websocket",return_value=ws), \
                patch("socket.create_connection",return_value=raw) as tcp, \
                patch("ssl.create_default_context",return_value=context):
            channel=connect(lease,"11111111-1111-4111-8111-111111111111",uuid.uuid4().hex,cancel=self.cancel,now=lambda:1000)
            args=ws.connect.call_args
            self.assertIs(tls,args.kwargs["socket"]); self.assertEqual(0,args.kwargs["redirect_limit"])
            self.assertEqual("synthetic-proxy-credential",args.kwargs["header"]["X-Colab-Runtime-Proxy-Token"])
            self.assertNotIn("Authorization",args.kwargs["header"])
            self.assertNotIn(lease.token,args.args[0]); self.assertEqual(443,tcp.call_args.args[0][1])
            channel.close(); tls.close.assert_called_once()

    def test_fragment_aggregate_is_bounded_even_when_each_frame_fits(self):
        from websocket import ABNF
        from engine_room_connectors._colab.channel import MAX_MESSAGE
        frames=[ABNF(fin=0,opcode=1,mask_value=0,data=b"x"*MAX_MESSAGE),
            ABNF(fin=1,opcode=0,mask_value=0,data=b"x")]
        with patch.object(self.ws,"recv_frame",side_effect=frames):
            with self.assertRaisesRegex(RuntimeError,"transfer limit"): self.channel.receive()

    def test_partial_payload_timeout_and_cancel_are_checked_during_read(self):
        self.peer.sendall(b"\x81\x7e\x01\x00x")
        timer=threading.Timer(0.02,self.cancel.set); timer.start()
        try:
            with self.assertRaises(RuntimeError): self.channel.receive()
        finally: timer.join()

    def test_real_upgrade_handshake_has_no_account_or_query_credential(self):
        from engine_room_connectors._colab.channel import connect
        from engine_room_connectors._colab.proxy import access
        from unittest.mock import Mock
        lease=access("owned",dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-private-proxy",tokenExpiresInSeconds=60),1000)
        client,peer=socket.socketpair(); captured=[]; errors=[]
        def provider():
            try:
                peer.settimeout(3); request=b""
                while b"\r\n\r\n" not in request: request+=peer.recv(4096)
                captured.append(request)
                headers=dict(line.split(b": ",1) for line in request.split(b"\r\n")[1:] if b": " in line)
                digest=base64.b64encode(hashlib.sha1(headers[b"Sec-WebSocket-Key"]+b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
                peer.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "+digest+b"\r\n\r\n\x81\x0b{\"ok\":true}")
            except Exception as error: errors.append(error)
        thread=threading.Thread(target=provider); thread.start()
        context=Mock(); context.wrap_socket.return_value=client
        try:
            with patch("socket.create_connection",return_value=client),patch("ssl.create_default_context",return_value=context):
                with connect(lease,"11111111-1111-4111-8111-111111111111",uuid.uuid4().hex,cancel=self.cancel,now=lambda:1000) as channel:
                    self.assertEqual({"ok":True},channel.receive())
            thread.join(timeout=3); self.assertFalse(thread.is_alive()); self.assertEqual([],errors)
            request=captured[0]
            self.assertIn(b"X-Colab-Runtime-Proxy-Token: synthetic-private-proxy",request)
            self.assertNotIn(b"Authorization:",request)
            self.assertNotIn(lease.token.encode(),request.split(b"\r\n",1)[0])
        finally:
            peer.close(); client.close(); thread.join(timeout=3)

    def test_native_ssh_binary_frames_are_preserved_without_json_or_text_coercion(self):
        payload=b"\x00\xffSSH-native\x00"
        self.peer.sendall(bytes([0x82,len(payload)])+payload)
        self.assertEqual(payload,self.channel.receive_bytes())

    def test_native_ssh_upgrade_uses_runtime_and_public_key_headers_not_credential_url(self):
        from engine_room_connectors._colab.channel import connect_ssh
        from engine_room_connectors._colab.proxy import access
        from test_colab_ssh_proxy import KEY
        from unittest.mock import Mock
        lease=access("owned",dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-private-runtime",tokenExpiresInSeconds=60),1000)
        ws=Mock(); ws.sock=None; raw=Mock(); tls=Mock(); context=Mock(); context.wrap_socket.return_value=tls
        with patch("engine_room_connectors._colab.channel.bounded_websocket",return_value=ws), \
                patch("socket.create_connection",return_value=raw),patch("ssl.create_default_context",return_value=context):
            channel=connect_ssh(lease,KEY,2000,cancel=self.cancel,now=lambda:1000)
            call=ws.connect.call_args
            self.assertTrue(call.args[0].endswith("/colab/ssh")); self.assertNotIn(lease.token,call.args[0])
            self.assertEqual(KEY,call.kwargs["header"]["X-Colab-Ssh-Pubkey"])
            self.assertEqual(0,call.kwargs["redirect_limit"]); self.assertNotIn("Authorization",call.kwargs["header"])
            channel.close(); tls.close.assert_called_once()

    def test_upgrade_trickle_cannot_extend_handshake_indefinitely(self):
        from engine_room_connectors._colab.channel import connect_ssh
        from engine_room_connectors._colab.proxy import access
        from test_colab_ssh_proxy import KEY
        from unittest.mock import Mock
        lease=access("owned",dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-private-runtime",tokenExpiresInSeconds=60),1000)
        client,peer=socket.socketpair(); stop=threading.Event(); result=[]
        def provider():
            try:
                peer.settimeout(2); request=b""
                while b"\r\n\r\n" not in request: request+=peer.recv(4096)
                while not stop.wait(0.05): peer.sendall(b"H")
            except OSError: pass
        server=threading.Thread(target=provider); server.start()
        context=Mock(); context.wrap_socket.return_value=client
        def connection():
            try:
                with patch("socket.create_connection",return_value=client),patch("ssl.create_default_context",return_value=context):
                    connect_ssh(lease,KEY,1000.3,cancel=self.cancel,now=lambda:1000)
                result.append("unexpected success")
            except RuntimeError: result.append("bounded refusal")
        worker=threading.Thread(target=connection); worker.start()
        try:
            worker.join(timeout=2); self.assertFalse(worker.is_alive())
            self.assertEqual(["bounded refusal"],result)
        finally:
            stop.set(); peer.close(); client.close(); worker.join(timeout=2); server.join(timeout=2)
