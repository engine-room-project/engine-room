from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from engine_room_connectors._colab.kernel import KernelHTTP,KernelSession
from engine_room_connectors._colab.proxy import access,ProxyAccess
from engine_room_connectors._colab.http import ColabHTTP
from engine_room.provider_http import ProviderError
from test_records import rental


IDENTITY="11111111-1111-4111-8111-111111111111"
EXISTING="22222222-2222-4222-8222-222222222222"


def lease():
    return access("owned",dict(url="https://synthetic-runtime.region.prod.colab.dev/",
        token="synthetic-runtime-access",tokenExpiresInSeconds=60),1000)


class Response(io.BytesIO):
    status=200
    def read1(self,n): return self.read(n)


class KernelHTTPTests(unittest.TestCase):
    def setUp(self):
        self.opener=Mock(); self.opener.open.return_value=Response(b'[]')
        self.http=KernelHTTP(ColabHTTP(self.opener),now=lambda:1000)
    def test_runtime_token_is_only_in_header_no_google_account_authorization(self):
        self.assertEqual([],self.http.request(lease(),"GET","/api/kernels"))
        request=self.opener.open.call_args.args[0]
        self.assertEqual("https://synthetic-runtime.region.prod.colab.dev/api/kernels",request.full_url)
        self.assertEqual("synthetic-runtime-access",request.get_header("X-colab-runtime-proxy-token"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertNotIn(lease().token,request.full_url)
        self.assertEqual(15,self.opener.open.call_args.kwargs["timeout"])
    def test_expired_forged_and_arbitrary_paths_refuse_before_transport(self):
        cases=((replace(lease(),expires_at=1000),"GET","/api/kernels",None),
            (replace(lease(),url="https://attacker.invalid/"),"GET","/api/kernels",None),
            (lease(),"DELETE","/api/kernels/"+EXISTING,None),
            (lease(),"GET","/api/kernels?token=synthetic",None),
            (lease(),"POST","/api/kernels",{"name":"other"}))
        for args in cases:
            with self.assertRaises(ValueError): self.http.request(*args)
        self.opener.open.assert_not_called()
    def test_failed_post_is_one_attempt_and_errors_hide_private_body(self):
        self.opener.open.side_effect=TimeoutError("synthetic-runtime-access private-error")
        with self.assertRaises(ProviderError) as error:
            self.http.request(lease(),"POST","/api/kernels",{"name":"python3"})
        self.assertNotIn("private-error",str(error.exception)); self.assertNotIn(lease().token,str(error.exception))
        self.opener.open.assert_called_once()


class KernelStartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.api=Mock(); self.api.runtime_access.return_value=lease(); self.http=Mock()
        self.http.request.side_effect=[[{"id":EXISTING}],{"id":IDENTITY}]
        self.session=KernelSession(self.api,self.temp.name,self.http,now=lambda:1000)
        self.receipt=replace(rental(),connector_id="colab",resource_id="owned",state="active",created_at=999,deadline=2000,protection_id="proof")
        self.connection=Mock(); self.authorize=Mock()
    def start(self): return self.session.start(self.connection,self.receipt,authorize=self.authorize)
    def proof(self): return json.loads(self.session.store.path(self.receipt.operation_id).read_text())
    def test_durable_proof_and_final_authority_precede_single_create(self):
        def request(lease,method,path,body=None):
            if method=="GET": return [{"id":EXISTING}]
            self.assertEqual("submitted",self.proof()["state"])
            self.authorize.assert_called_once_with()
            return {"id":IDENTITY}
        self.http.request.side_effect=request
        self.assertEqual(IDENTITY,self.start())
        self.assertEqual("ready",self.proof()["state"])
        self.assertEqual(self.receipt.operation_key(),self.proof()["operation_key"])
        self.assertNotIn(lease().token,json.dumps(self.proof()))
        with self.assertRaisesRegex(ValueError,"already attempted"): self.start()
        self.assertEqual(2,self.http.request.call_count)
    def test_lost_post_and_malformed_reply_preserve_uncertainty_without_retry(self):
        for reply in (TimeoutError("lost private response"),{"id":"unsafe/kernel"}):
            with self.subTest(reply=type(reply).__name__):
                self.session.store.path(self.receipt.operation_id).unlink(missing_ok=True)
                self.http.request.side_effect=[[],reply]
                with self.assertRaises((TimeoutError,ValueError)): self.start()
                self.assertEqual("submitted",self.proof()["state"])
                before=self.http.request.call_count
                with self.assertRaises(ValueError): self.start()
                self.assertEqual(before,self.http.request.call_count)
    def test_baseline_kernel_is_never_adopted_or_modified(self):
        self.http.request.side_effect=[[{"id":EXISTING}],{"id":EXISTING}]
        with self.assertRaisesRegex(ValueError,"pre-existing"): self.start()
        self.assertEqual("unresolved",self.proof()["state"])
        self.assertIsNone(self.proof()["kernel_id"])
        self.assertEqual(EXISTING,self.proof()["candidate_kernel_id"])
        self.assertEqual(["GET","POST"],[c.args[1] for c in self.http.request.call_args_list])
    def test_stop_at_final_gate_prevents_create(self):
        self.authorize.side_effect=ValueError("Stopped")
        with self.assertRaises(ValueError): self.start()
        self.assertEqual("cancelled",self.proof()["state"])
        self.assertEqual(1,self.http.request.call_count)
    def test_failed_durable_write_prevents_create(self):
        from unittest.mock import patch
        with patch("engine_room_connectors._colab.kernel.atomic_json",side_effect=OSError("Disk failure")):
            with self.assertRaises(OSError): self.start()
        self.authorize.assert_not_called(); self.assertEqual(1,self.http.request.call_count)
    def test_expired_cancelled_wrong_runtime_and_ambiguous_baseline_refuse(self):
        for receipt in (replace(self.receipt,cancel_requested=True),replace(self.receipt,deadline=1000)):
            with self.assertRaises(ValueError): self.session.start(self.connection,receipt,authorize=self.authorize)
        self.api.runtime_access.assert_not_called()
        self.api.runtime_access.return_value=replace(lease(),resource_id="unrelated")
        with self.assertRaises(ValueError): self.start()
        self.http.request.assert_not_called()
        self.api.runtime_access.return_value=lease(); self.http.request.side_effect=[[{"id":EXISTING}]*2]
        with self.assertRaises(ValueError): self.start()
        self.authorize.assert_not_called()


class ExecutionChannel:
    def __init__(self,events): self.events=events; self.sent=[]; self.closed=False
    def __enter__(self): return self
    def __exit__(self,*args): self.closed=True
    def send(self,message): self.sent.append(message)
    def receive(self):
        event=self.events.pop(0)
        if isinstance(event,Exception): raise event
        kind,content,parent=event
        return dict(header=dict(msg_type=kind),parent_header=dict(msg_id=self.sent[0]["header"]["msg_id"] if parent else "unrelated"),content=content)


class KernelExecutionTests(unittest.TestCase):
    start=KernelStartTests.start
    proof=KernelStartTests.proof
    def setUp(self):
        KernelStartTests.setUp(self); self.start(); self.cancel=threading.Event()
        self.channel=ExecutionChannel([("stream",{"text":"owned-result"},True),
            ("execute_reply",{"status":"ok"},True),("status",{"execution_state":"idle"},True)])
        self.factory=Mock(return_value=self.channel); self.authorize.reset_mock()
    def execute(self,code="print('synthetic bootstrap')"):
        return self.session.execute(self.connection,self.receipt,code,authorize=self.authorize,
            cancel=self.cancel,channel_factory=self.factory)
    # Startup fixtures are inherited only for setup, not a second copy of startup tests.
    def test_execution_requires_both_correlated_reply_and_idle_without_storing_code(self):
        self.channel.events.insert(0,("stream",{"text":"unrelated"},False))
        self.assertEqual("owned-result",self.execute())
        self.assertEqual("ready",self.proof()["state"]); self.assertTrue(self.channel.closed)
        message=self.channel.sent[0]
        self.assertFalse(message["content"]["store_history"]); self.assertFalse(message["content"]["allow_stdin"])
        self.assertNotIn("synthetic bootstrap",json.dumps(self.proof()))
        self.authorize.assert_called_once_with()
    def test_uncertain_execution_never_replays_and_errors_hide_runtime_content(self):
        self.channel.events=[TimeoutError("synthetic private kernel content")]
        with self.assertRaises(RuntimeError) as error: self.execute()
        self.assertNotIn("private kernel content",str(error.exception))
        self.assertEqual("executing",self.proof()["state"]); self.assertTrue(self.channel.closed)
        before=self.factory.call_count
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(before,self.factory.call_count)
    def test_output_limit_failure_preserves_execution_uncertainty(self):
        self.channel.events=[("stream",{"text":"x"*65537},True)]
        with self.assertRaises(RuntimeError): self.execute()
        self.assertEqual("executing",self.proof()["state"])
    def test_final_execution_gate_refusal_sends_no_code(self):
        self.authorize.side_effect=ValueError("Stopped")
        with self.assertRaises(RuntimeError): self.execute()
        self.assertEqual([],self.channel.sent); self.assertTrue(self.channel.closed)
    def test_cancelled_or_different_proof_cannot_open_channel(self):
        self.cancel.set()
        with self.assertRaises(ValueError): self.execute()
        self.factory.assert_not_called()
        self.cancel.clear(); self.receipt=replace(self.receipt,account_id="changed-account")
        with self.assertRaises(ValueError): self.execute()
        self.factory.assert_not_called()
