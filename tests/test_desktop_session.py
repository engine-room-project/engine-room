from dataclasses import asdict,replace
import http.client
import http.server
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from engine_room.controller_protocol import decode,encode
from engine_room.desktop_session import DesktopSession,ModelRelay,ModelStream
from engine_room.private_endpoint import ModelEndpoint
from test_records import rental
import test_lifecycle as lifecycle_fixture


class EndpointTests(unittest.TestCase):
    setUp=lifecycle_fixture.ControllerTests.setUp
    tearDown=lifecycle_fixture.ControllerTests.tearDown
    request=lifecycle_fixture.ControllerTests.request
    wait_worker=lifecycle_fixture.ControllerTests.wait_worker
    def test_endpoint_requires_fresh_health_and_active_authorized_operation(self):
        self.request(); self.wait_worker()
        receipt=self.controller.store.load("operation1")
        endpoint=ModelEndpoint(str(Path(self.temp.name)/"model.sock"),receipt.operation_key(),receipt.resource_id,1,2,3)
        self.provider.model_endpoint=Mock(return_value=endpoint)
        with self.assertRaisesRegex(ValueError,"fresh"): self.controller.model_endpoint("operation1","b"*64)
        self.controller.tick()
        self.assertEqual(endpoint,self.controller.model_endpoint("operation1","b"*64))
        self.clock.advance(31)
        with self.assertRaises(ValueError): self.controller.model_endpoint("operation1","b"*64)
    def test_wrong_resource_endpoint_cannot_reuse_previous_model_health(self):
        self.request(); self.wait_worker(); self.controller.tick()
        receipt=self.controller.store.load("operation1")
        target=ModelEndpoint(str(Path(self.temp.name)/"model.sock"),receipt.operation_key(),"unrelated-resource",1,2,3)
        self.provider.model_endpoint=Mock(return_value=target)
        with self.assertRaises(ValueError): self.controller.model_endpoint("operation1","b"*64)

    def test_expired_or_cancelled_operations_cannot_open_model_streams(self):
        self.request(); self.wait_worker(); self.controller.tick()
        receipt=self.controller.store.load("operation1")
        endpoint=ModelEndpoint(str(Path(self.temp.name)/"model.sock"),receipt.operation_key(),receipt.resource_id,1,2,3)
        self.provider.model_endpoint=Mock(return_value=endpoint)
        self.clock.advance(121)
        with self.assertRaises(ValueError): self.controller.model_endpoint("operation1","b"*64)
        self.provider.model_endpoint.assert_not_called()



class SyntheticStream:
    def __init__(self,client,operation_id,operation_key):
        self.client=client; self.operation_id=operation_id; self.closed=False; self.closed_event=threading.Event()
        self.process=Mock(); self.process.stdin=io.BytesIO()
        self.process.stdout=io.BufferedReader(io.BytesIO(client.response))
        client.streams.append(self)
    def connect(self): return self
    def close(self): self.closed=True; self.closed_event.set()


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock(); self.client.response=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 11\r\n\r\n{"ok":true}'
        self.client.streams=[]
        self.relay=ModelRelay(self.client,replace(rental(),operation_id="synthetic-operation"),stream_factory=SyntheticStream)
        self.addCleanup(self.relay.close)
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection("127.0.0.1",self.relay.port,timeout=3)
        self.addCleanup(connection.close)
        selected={"Authorization":"Bearer "+self.relay.token,**(headers or {})}
        connection.request(method,path,body,selected)
        response=connection.getresponse(); return response.status,response.read()
    def test_loopback_endpoint_requires_session_token_and_rejects_origins(self):
        self.assertEqual("127.0.0.1",self.relay.server.server_address[0])
        for headers,expected in (({"Authorization":"Bearer wrong"},401),({"Origin":"https://synthetic.invalid"},403),({"Host":"synthetic.invalid"},403)):
            self.assertEqual(expected,self.request("GET","/v1/models",headers=headers)[0])
        self.assertEqual([],self.client.streams)
    def test_proxy_preserves_json_without_forwarding_token_or_tool_settings(self):
        body=b'{"messages":[{"role":"user","content":"synthetic private prompt"}]}'
        self.assertEqual((200,b'{"ok":true}'),self.request("POST","/v1/chat/completions",body,{"Content-Type":"application/json","X-Tool-Private":"synthetic-setting"}))
        stream=self.client.streams[0]; sent=stream.process.stdin.getvalue()
        self.assertTrue(sent.endswith(body)); self.assertNotIn(self.relay.token.encode(),sent)
        self.assertNotIn(b"synthetic-setting",sent); self.assertEqual("synthetic-operation",stream.operation_id)
        self.assertTrue(stream.closed_event.wait(timeout=2)); self.assertTrue(stream.closed)
    def test_chunked_upstream_sse_is_streamed_without_chunk_framing(self):
        self.client.response=b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n9\r\ndata: a\n\n\r\nb\r\ndata: end\n\n\r\n0\r\n\r\n'
        status,body=self.request("POST","/v1/chat/completions",b"{}",{"Content-Type":"application/json"})
        self.assertEqual(200,status); self.assertEqual(b"data: a\n\ndata: end\n\n",body)
    def test_other_routes_query_keys_and_ambiguous_framing_are_refused(self):
        for path in ("/load_lora_adapter","/v1/models?api_key=synthetic","http://synthetic.invalid/v1/models"):
            self.assertIn(self.request("GET",path)[0],(403,404))
        self.assertEqual(400,self.request("POST","/v1/chat/completions",b"{}",{"Content-Type":"application/json","Transfer-Encoding":"chunked"})[0])
        self.assertEqual(413,self.request("POST","/v1/chat/completions",None,{"Content-Type":"application/json","Content-Length":str(64*1024*1024+1)})[0])
        self.assertEqual([],self.client.streams)
    def test_rejected_body_does_not_erase_response_or_wait_for_missing_bytes(self):
        with socket.create_connection(("127.0.0.1",self.relay.port),timeout=1) as connection:
            header=("POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:"+str(self.relay.port)+
                "\r\nAuthorization: Bearer "+self.relay.token+
                "\r\nTransfer-Encoding: chunked\r\nContent-Length: 999999\r\n\r\n{}")
            connection.sendall(header.encode())
            response=http.client.HTTPResponse(connection); response.begin()
            self.assertEqual(400,response.status)
            self.assertIn(b"explicit content length",response.read())
        self.assertEqual([],self.client.streams)

    def test_failed_stream_close_does_not_skip_other_streams_or_listener(self):
        broken=self.relay.new_stream(); good=self.relay.new_stream()
        broken.close=Mock(side_effect=OSError("synthetic process error"))
        with self.assertRaises(RuntimeError): self.relay.close()
        self.assertTrue(good.closed); self.assertFalse(self.relay.thread.is_alive())

    def test_close_terminates_only_its_owned_streams(self):
        other=ModelRelay(self.client,replace(rental(),operation_id="other-operation"),stream_factory=SyntheticStream)
        self.addCleanup(other.close)
        stream=self.relay.new_stream(); unrelated=other.new_stream()
        self.assertNotEqual(self.relay.token,other.token)
        self.relay.close(); self.assertTrue(stream.closed); self.assertFalse(unrelated.closed)
        self.assertFalse(self.relay.thread.is_alive()); self.assertTrue(other.thread.is_alive())
        with self.assertRaises(RuntimeError): self.relay.new_stream()


class SelectedModelRelayTests(unittest.TestCase):
    request=RelayTests.request
    def setUp(self):
        self.client=Mock(); self.client.response=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'; self.client.streams=[]
        self.relay=ModelRelay(self.client,replace(rental(),mode="attachment",deadline=None,protection_id=None),stream_factory=SyntheticStream,selected_model="chosen-model")
        self.addCleanup(self.relay.close)
    # Exercise selected-model behavior separately; general relay tests use rentals.
    def test_selected_model_rejects_ambiguous_or_other_requests_before_stream(self):
        for body in (b'{}',b'{"model":"other"}',b'{"model":"chosen-model","model":"other"}',
                     b'{"model":"other","model":"chosen-model"}',b'[]',b'{"model":"chosen-model","x":NaN}',b'not-json'):
            self.assertEqual(400,self.request("POST","/v1/chat/completions",body,{"Content-Type":"application/json"})[0])
        self.assertEqual([],self.client.streams)
    def test_selected_model_applies_to_every_supported_inference_route(self):
        for route in ("/v1/chat/completions","/v1/completions","/v1/embeddings","/v1/responses"):
            self.assertEqual(400,self.request("POST",route,b'{"model":"different"}',{"Content-Type":"application/json"})[0])
        self.assertEqual([],self.client.streams)
    def test_selected_model_preserves_valid_body_and_streaming(self):
        body=b'{"model":"chosen-model","messages":[],"stream":true}'
        self.assertEqual(200,self.request("POST","/v1/chat/completions",body,{"Content-Type":"application/json"})[0])
        self.assertTrue(self.client.streams[0].process.stdin.getvalue().endswith(body))
    def test_attachment_requires_explicit_model_before_binding_listener(self):
        with self.assertRaises(ValueError):
            ModelRelay(self.client,replace(rental(),mode="attachment",deadline=None,protection_id=None),stream_factory=SyntheticStream)


class HandshakeTests(unittest.TestCase):
    def test_stream_uses_fixed_command_and_verifies_response_correlation(self):
        client=Mock(); client.args.return_value=["ssh","fixed-wrapper"]
        client.endpoint.controller_id="synthetic-controller"; client.endpoint.client_host_id="b"*64
        process=Mock(); process.stdin=io.BytesIO(); process.stdout=io.BytesIO(); process.poll.return_value=None
        def reply(data):
            request=decode(data)
            process.stdout=io.BytesIO(encode(dict(schema=1,request_id=request["request_id"],controller_id="synthetic-controller",ok=True,result=dict(stream=True))))
            return len(data)
        process.stdin=Mock(); process.stdin.write.side_effect=reply
        factory=Mock(return_value=process)
        stream=ModelStream(client,"operation1","a"*64,popen=factory); stream.connect()
        self.assertEqual(["ssh","fixed-wrapper"],factory.call_args.args[0]); stream.close()
        process.terminate.assert_called_once()
    def test_bad_response_closes_process_without_exposing_output(self):
        client=Mock(); client.args.return_value=["ssh"]; client.endpoint.controller_id="controller"; client.endpoint.client_host_id="b"*64
        process=Mock(); process.stdin=io.BytesIO(); process.stdout=io.BytesIO(b"synthetic-secret-response\n"); process.poll.return_value=None
        stream=ModelStream(client,"operation1","a"*64,popen=Mock(return_value=process))
        with self.assertRaises(RuntimeError) as error: stream.connect()
        self.assertNotIn("synthetic-secret-response",str(error.exception)); process.terminate.assert_called_once()


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.record=replace(rental(),state="active",resource_id="synthetic-pod",protection_id="controller",lease_expires_at=150,rate_ceiling=2,rate_unit="USD")
        self.client=Mock(); self.client.endpoint.controller_id="controller"; self.relay=Mock(); self.beats=threading.Event()
        self.remote=asdict(self.record); self.clock=lifecycle_fixture.Clock()
        def call(method,params):
            self.assertEqual(dict(operation_id="op1") if method=="status" else dict(operation_id="op1",operation_key=self.record.operation_key()),params)
            if method=="heartbeat": self.beats.set(); return dict(self.remote)
            if method=="cancel": self.remote["state"]="off"; return []
            if method=="status": return dict(records=[dict(self.remote)],next_cursor=None)
            raise AssertionError("Unexpected operation")
        self.client.call.side_effect=call
    def session(self,**kwargs):
        kwargs.setdefault("clock",self.clock)
        session=DesktopSession(self.client,self.record,self.temp.name,relay_factory=Mock(return_value=self.relay),interval=0.01,ui_timeout=0.04,**kwargs)
        self.addCleanup(session.close); return session
    def test_stale_active_reply_cannot_overwrite_terminal_durable_receipt(self):
        session=self.session(); self.assertTrue(self.beats.wait(3))
        terminal=replace(self.record,state="off",cancel_requested=True)
        with session.lock: session.store.save(terminal)
        result=session._save(asdict(self.record))
        self.assertEqual("off",result.state); self.assertEqual("off",session.store.load("op1").state)

    def test_known_provider_resource_cannot_change_during_renewal(self):
        session=self.session(); self.assertTrue(self.beats.wait(3))
        with self.assertRaises(ValueError): session._save(asdict(replace(self.record,resource_id="unrelated")))
        self.assertEqual(self.record.resource_id,session.store.load("op1").resource_id)

    def test_delayed_response_cannot_reset_an_expired_ui_pulse(self):
        relay=Mock()
        with self.assertRaises(ValueError):
            DesktopSession(self.client,self.record,self.temp.name,relay_factory=relay,clock=lambda:100,initial_touch=1)
        relay.assert_not_called(); self.client.call.assert_not_called()

    def test_missing_ui_pulses_stops_renewal_and_cancels_selected_operation(self):
        session=self.session(); self.assertTrue(self.beats.wait(3))
        self.clock.advance(0.05); session.thread.join(timeout=3)
        self.assertFalse(session.thread.is_alive()); self.assertTrue(session.stopped.is_set())
        self.assertEqual("off",session.store.load("op1").state)
        self.relay.close.assert_called()
        with self.assertRaises(ValueError): session.touch()
    def test_ui_activity_maintains_lease_until_explicit_close(self):
        session=self.session(); self.assertTrue(self.beats.wait(3))
        for _ in range(8): self.clock.advance(0.02); session.touch(); time.sleep(0.01)
        self.assertFalse(session.stopped.is_set())
        final=session.close(); self.assertEqual("off",final.state)
        self.assertTrue(all(c.args[1]["operation_id"]=="op1" for c in self.client.call.call_args_list))
    def test_network_failure_preserves_uncertainty_instead_of_off(self):
        self.client.call.side_effect=RuntimeError("synthetic private diagnostic")
        session=self.session(); session.thread.join(timeout=1)
        record=session.store.load("op1")
        self.assertNotEqual("off",record.state); self.assertTrue(record.cancel_requested)
    def test_receipt_write_failure_cannot_skip_remote_cancel(self):
        session=self.session(); self.assertTrue(self.beats.wait(3))
        session.store.save=Mock(side_effect=OSError("synthetic disk error"))
        try:
            with self.assertRaises(OSError): session.close()
            session.thread.join(timeout=1)
            self.assertTrue(any(c.args[0]=="cancel" for c in self.client.call.call_args_list))
            self.relay.close.assert_called()
        finally:
            from engine_room.records import Store
            session.store=Store(self.temp.name)

    def test_other_controller_and_existing_stop_intent_refuse_before_any_rpc(self):
        from engine_room.records import Store
        self.client.endpoint.controller_id="different-controller"
        with self.assertRaises(ValueError): self.session()
        self.client.endpoint.controller_id="controller"
        Store(self.temp.name).save(replace(self.record,cancel_requested=True))
        with self.assertRaises(ValueError): self.session()
        self.client.call.assert_not_called()

    def test_stop_intent_is_durable_while_a_heartbeat_is_still_blocked(self):
        entered=threading.Event(); release=threading.Event(); original=self.client.call.side_effect
        def blocked(method,params):
            if method=="heartbeat": entered.set(); release.wait(2)
            return original(method,params)
        self.client.call.side_effect=blocked
        session=self.session(); self.assertTrue(entered.wait(1))
        closer=threading.Thread(target=session.close); closer.start()
        try:
            until=time.monotonic()+1
            while time.monotonic()<until and not session.store.load("op1").cancel_requested: time.sleep(0.01)
            self.assertTrue(session.store.load("op1").cancel_requested)
        finally:
            release.set(); closer.join(timeout=3)
        self.assertFalse(closer.is_alive())

    def test_attachment_cannot_start_rental_heartbeat_or_termination(self):
        with self.assertRaises(ValueError): DesktopSession(self.client,replace(self.record,mode="attachment",deadline=None,lease_expires_at=None),self.temp.name)
        self.client.call.assert_not_called()


class QuietHTTPServer(socketserver.ThreadingUnixStreamServer if hasattr(socketserver,"ThreadingUnixStreamServer") else http.server.ThreadingHTTPServer):
    daemon_threads=True
    def handle_error(self,*args): pass


class ModelFixture(http.server.BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def log_message(self,*args): pass
    def do_POST(self):
        body=self.rfile.read(int(self.headers["Content-Length"]))
        self.server.body_hash=hashlib.sha256(body).hexdigest()
        self.server.incoming_auth=self.headers.get("Authorization")
        self.send_response(200); self.send_header("Content-Type","text/event-stream")
        self.send_header("Transfer-Encoding","chunked"); self.send_header("Connection","close"); self.end_headers()
        self.wfile.write(b"9\r\ndata: a\n\n\r\n"); self.wfile.flush()
        self.server.first.set()
        self.server.release.wait(10)
        self.wfile.write(b"b\r\ndata: end\n\n\r\n0\r\n\r\n"); self.wfile.flush()
        self.close_connection=True


@unittest.skipUnless(sys.platform.startswith("linux"),"Actual Linux process/Unix socket/model stream")
class BridgeTests(unittest.TestCase):
    def setUp(self):
        lifecycle_fixture.ControllerTests.setUp(self)
        self.request(); self.wait_worker(); self.controller.tick()
        backend_path=Path(self.temp.name)/"backend.sock"
        self.backend=QuietHTTPServer(str(backend_path),ModelFixture); backend_path.chmod(0o600)
        self.backend.first=threading.Event(); self.backend.release=threading.Event()
        info=backend_path.stat(); receipt=self.controller.store.load("operation1")
        self.provider.model_endpoint=Mock(return_value=ModelEndpoint(str(backend_path),receipt.operation_key(),receipt.resource_id,info.st_dev,info.st_ino,os.getpid()))
        self.backend_thread=threading.Thread(target=self.backend.serve_forever,kwargs=dict(poll_interval=0.05),daemon=True); self.backend_thread.start()
        from engine_room.controller_service import LocalServer
        from engine_room.controller_protocol import Dispatcher
        self.local=LocalServer(self.temp.name,Dispatcher(self.controller))
        self.local_thread=threading.Thread(target=self.local.serve_forever,kwargs=dict(poll_interval=0.05),daemon=True); self.local_thread.start()
        client=Mock(); client.endpoint.controller_id="independent-controller"; client.endpoint.client_host_id="b"*64
        client.args.return_value=[sys.executable,"-m","engine_room.controller_service","rpc","--root",self.temp.name]
        self.relay=ModelRelay(client,self.controller.store.load("operation1"))
    request=lifecycle_fixture.ControllerTests.request
    wait_worker=lifecycle_fixture.ControllerTests.wait_worker
    def tearDown(self):
        self.backend.release.set(); self.relay.close()
        self.local.shutdown(); self.local_thread.join(timeout=2); self.local.server_close()
        self.backend.shutdown(); self.backend_thread.join(timeout=2); self.backend.server_close()
        lifecycle_fixture.ControllerTests.tearDown(self)
    def begin(self):
        body=b'{"prompt":"'+b'x'*400000+b'"}'
        connection=http.client.HTTPConnection("127.0.0.1",self.relay.port,timeout=8); self.addCleanup(connection.close)
        connection.request("POST","/v1/chat/completions",body,{"Authorization":"Bearer "+self.relay.token,"Content-Type":"application/json"})
        response=connection.getresponse(); self.assertEqual(200,response.status)
        self.assertEqual(b"data: a\n\n",response.read(9))
        self.assertEqual(hashlib.sha256(body).hexdigest(),self.backend.body_hash)
        self.assertIsNone(self.backend.incoming_auth)
        return response
    def test_actual_wrapper_and_socket_stream_large_body_and_incremental_sse(self):
        response=self.begin()
        self.assertFalse(self.backend.release.is_set())
        self.backend.release.set()
        self.assertEqual(b"data: end\n\n",response.read())
    def test_revocation_closes_an_existing_stream_even_if_backend_remains_open(self):
        response=self.begin()
        self.controller.cancel("operation1")
        self.assertEqual(b"",response.read())
        self.assertFalse(self.backend.release.is_set())


class AttachmentPulseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.record=replace(rental(),mode="attachment",state="active",resource_id="existing-model",deadline=None,protection_id="controller")
        self.client=Mock(); self.client.endpoint.controller_id="controller"; self.relay=Mock(); self.beat=threading.Event()
        self.clock=lifecycle_fixture.Clock(); self.remote=asdict(self.record)
        def call(method,params):
            if method=="attachment_pulse": self.beat.set(); return dict(self.remote)
            if method=="disconnect_attachment": self.remote.update(state="detached",cancel_requested=True); return dict(self.remote)
            if method=="status": return dict(records=[dict(self.remote)])
            raise AssertionError("Attachment must never renew or terminate a rental")
        self.client.call.side_effect=call
    def session(self):
        self.factory=Mock(return_value=self.relay)
        session=DesktopSession(self.client,self.record,self.temp.name,relay_factory=self.factory,selected_model="chosen-model",interval=0.01,ui_timeout=0.04,clock=self.clock)
        self.addCleanup(session.close); return session
    def test_ui_loss_closes_access_without_rental_heartbeat_or_termination(self):
        session=self.session(); self.assertTrue(self.beat.wait(2))
        self.factory.assert_called_once_with(self.client,self.record,selected_model="chosen-model")
        self.clock.advance(0.05); session.thread.join(timeout=2)
        self.assertFalse(session.thread.is_alive()); self.assertEqual("detached",session.store.load(self.record.operation_id).state)
        self.assertTrue(any(row.args[0]=="disconnect_attachment" for row in self.client.call.call_args_list))
        self.assertFalse(any(row.args[0] in {"heartbeat","cancel"} for row in self.client.call.call_args_list))
    def test_late_active_reply_cannot_overwrite_confirmed_local_disconnection(self):
        session=self.session(); self.assertTrue(self.beat.wait(2))
        with session.lock: session.store.save(replace(self.record,state="detached",cancel_requested=True))
        self.assertEqual("detached",session._save(asdict(self.record)).state)
    def test_network_loss_preserves_uncertainty_without_off_claim(self):
        self.client.call.side_effect=RuntimeError("synthetic transport failure")
        session=self.session(); session.thread.join(timeout=2)
        result=session.store.load(self.record.operation_id)
        self.assertEqual("active",result.state); self.assertTrue(result.cancel_requested)
        self.relay.close.assert_called()
