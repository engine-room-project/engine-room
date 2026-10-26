import os
import io
from types import SimpleNamespace
from unittest.mock import Mock,patch
import socket
import sys
import threading
import unittest

from engine_room.model_request import guarded_request,validate_body
from engine_room.streaming import duplex


class BodyTests(unittest.TestCase):
    def test_exact_model_and_unambiguous_json(self):
        validate_body(b'{"model":"chosen","stream":true}',"chosen")
        for body in (b'{}',b'[]',b'{"model":"other"}',b'{"model":"other","model":"chosen"}',b'{"model":"chosen","x":NaN}',b'\xff'):
            with self.assertRaises((ValueError,UnicodeError)): validate_body(body,"chosen")


@unittest.skipUnless(sys.platform.startswith("linux"),"Linux descriptor stream boundary")
class GuardTests(unittest.TestCase):
    def parse(self,data,authorized=lambda:True):
        reader,writer=os.pipe()
        try:
            os.write(writer,data); os.close(writer); writer=None
            return guarded_request(reader,"chosen",authorized,seconds=0.2)
        finally:
            os.close(reader)
            if writer is not None: os.close(writer)
    def request(self,body=b'{"model":"chosen"}',extra=b'',path=b'/v1/chat/completions'):
        return b'POST '+path+b' HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n'+extra+b'\r\n'+body
    def test_canonical_request_discards_credentials_and_pipelined_request(self):
        body=b'{"model":"chosen"}'
        first=self.request(body,b'Authorization: Bearer synthetic\r\n')
        result=self.parse(first+self.request(b'{"model":"other"}'))
        self.assertTrue(result.endswith(body)); self.assertNotIn(b'synthetic',result)
        self.assertEqual(1,result.count(b'POST ')); self.assertIn(b'Connection: close',result)
    def test_ambiguous_framing_other_models_and_routes_are_refused(self):
        for request in (self.request(extra=b'Content-Length: 18\r\n'),self.request(extra=b'Transfer-Encoding: chunked\r\n'),
                        self.request(b'{"model":"other"}'),self.request(path=b'/load_model'),self.request()[:-2],
                        self.request(extra=b' Upgrade: websocket\r\n'),b'GET /v1/models?x=1 HTTP/1.1\r\n\r\n'):
            with self.assertRaises(ValueError): self.parse(request)
    def test_revoked_authority_prevents_forwarding(self):
        with self.assertRaises(ValueError): self.parse(self.request(),lambda:False)
    def test_fixed_request_duplex_never_reads_extra_input(self):
        peer,server=socket.socketpair(); reader,writer=os.pipe(); out_reader,out_writer=os.pipe()
        errors=[]; received=[]; server.settimeout(3)
        checked=b'checked request'*30000
        def upstream():
            try:
                data=b''
                while True:
                    chunk=server.recv(65536)
                    if not chunk: break
                    data+=chunk
                received.append(data); server.sendall(b'synthetic response')
            finally: server.close()
        def run():
            try: duplex(peer,reader,out_writer,lambda:True,request=checked)
            except Exception as error: errors.append(error)
            finally: os.close(out_writer)
        producer=threading.Thread(target=upstream); worker=threading.Thread(target=run)
        try:
            os.write(writer,b'unchecked second request'); producer.start(); worker.start()
            self.assertEqual(b'synthetic response',os.read(out_reader,100))
            worker.join(timeout=2); producer.join(timeout=2)
            self.assertFalse(worker.is_alive()); self.assertFalse(producer.is_alive())
            self.assertEqual([],errors); self.assertEqual([checked],received)
        finally:
            peer.close(); os.close(reader); os.close(writer); os.close(out_reader)

    def test_controller_bridge_checks_model_before_connecting_upstream(self):
        from engine_room import controller_service
        from engine_room.controller_protocol import encode
        scope=dict(endpoint={"synthetic":"descriptor"},selected_model="chosen")
        message=dict(method="model_stream",params=dict(operation_key="a"*64))
        reader,writer=os.pipe(); out_reader,out_writer=os.pipe()
        fake_in=SimpleNamespace(buffer=io.BytesIO(encode(message)),fileno=lambda:reader)
        fake_out=SimpleNamespace(buffer=io.BytesIO(),fileno=lambda:out_writer)
        target=Mock()
        try:
            os.write(writer,self.request(b'{"model":"other"}')); os.close(writer); writer=None
            with patch.object(controller_service,"local_call",return_value=dict(ok=True,result=scope)),patch.object(controller_service.ModelEndpoint,"read",return_value=target),patch.object(controller_service.sys,"stdin",fake_in),patch.object(controller_service.sys,"stdout",fake_out):
                with self.assertRaises(ValueError): controller_service.bridge("synthetic-root")
            target.connect.assert_not_called()
        finally:
            os.close(reader); os.close(out_reader); os.close(out_writer)
            if writer is not None: os.close(writer)
