from dataclasses import replace
import hashlib
import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from engine_room.connections import Connection
from engine_room.credentials import Credentials
from engine_room.provider_http import ProviderError
from engine_room_connectors._colab.api import ColabAPI,notebook
from engine_room_connectors._colab.auth import OAuthTokens,SCOPES,record,login
from engine_room_connectors._colab.http import ColabHTTP
from test_records import rental


def oauth(**changes):
    return json.dumps(dict(type="colab-oauth-v1",client_id="synthetic.apps.googleusercontent.com",client_secret="synthetic-public-client",refresh_token="synthetic-refresh",token="synthetic-access",expires_at=2000,scopes=sorted(SCOPES))|changes)


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.credentials=Credentials(Path(self.temp.name)/"credentials")
        self.http=Mock(); self.tokens=OAuthTokens(self.credentials,self.http,now=lambda:1000)
    def test_only_explicit_reference_is_used_and_valid_token_needs_no_refresh(self):
        self.credentials.save("chosen",oauth())
        self.assertEqual("synthetic-access",self.tokens.access("chosen")); self.http.refresh.assert_not_called()
        with self.assertRaises(ValueError): self.tokens.access("missing")
    def test_direct_login_needs_interactive_terminal_and_explicit_replacement(self):
        flow=Mock()
        with patch("sys.stdin.isatty",return_value=False):
            with self.assertRaises(ValueError): login(self.credentials,"chosen",flow_factory=flow)
        flow.assert_not_called()
        self.credentials.save("chosen",oauth())
        with patch("sys.stdin.isatty",return_value=True),patch("sys.stderr.isatty",return_value=True):
            with self.assertRaisesRegex(ValueError,"exists"): login(self.credentials,"chosen",flow_factory=flow)
        flow.assert_not_called()
    def test_direct_login_stores_only_selected_scoped_record_without_email_or_cache(self):
        flow=Mock(); flow.authorization_url.return_value=("https://accounts.google.com/o/oauth2/auth?synthetic=true","state")
        flow.oauth2session.token=dict(scope=" ".join(sorted(SCOPES)))
        flow.credentials=Mock(client_id="synthetic.apps.googleusercontent.com",client_secret="synthetic-client",refresh_token="synthetic-refresh",token="synthetic-new",expiry=datetime.datetime(2030,1,1),account="synthetic@example.invalid")
        with patch("sys.stdin.isatty",return_value=True),patch("sys.stderr.isatty",return_value=True),patch("getpass.getpass",return_value="synthetic-authorization-code"),patch("sys.stderr",new=io.StringIO()) as output:
            output.isatty=lambda:True
            login(self.credentials,"chosen",flow_factory=lambda:flow)
            self.assertNotIn("synthetic-new",output.getvalue()); self.assertNotIn("synthetic-refresh",output.getvalue())
        saved=self.credentials.read("chosen")
        self.assertEqual("synthetic-new",record(saved)["token"]); self.assertNotIn("synthetic@example.invalid",saved)
        self.assertEqual(datetime.datetime(2030,1,1,tzinfo=datetime.timezone.utc).timestamp(),record(saved)["expires_at"])
        self.assertEqual("false",flow.authorization_url.call_args.kwargs["include_granted_scopes"])

    def test_refresh_rotates_only_selected_record(self):
        self.credentials.save("chosen",oauth(expires_at=1010)); self.credentials.save("other",oauth(token="synthetic-other"))
        self.http.refresh.return_value=dict(token_type="Bearer",access_token="synthetic-new",expires_in=3600,scope=" ".join(sorted(SCOPES)))
        self.assertEqual("synthetic-new",self.tokens.access("chosen"))
        self.assertEqual("synthetic-other",record(self.credentials.read("other"))["token"])
        self.assertEqual(4600,record(self.credentials.read("chosen"))["expires_at"])
    def test_explicit_rotation_during_refresh_cannot_be_overwritten(self):
        self.credentials.save("chosen",oauth(expires_at=1010))
        def changed(fields):
            self.credentials.save("chosen",oauth(token="synthetic-replacement"),overwrite=True)
            return dict(token_type="Bearer",access_token="synthetic-stale-refresh",expires_in=3600)
        self.http.refresh.side_effect=changed
        with self.assertRaisesRegex(ValueError,"changed"): self.tokens.access("chosen")
        self.assertEqual("synthetic-replacement",record(self.credentials.read("chosen"))["token"])
    def test_broader_scopes_and_corrupt_tokens_are_not_imported(self):
        for raw in (oauth(scopes=[*SCOPES,"https://www.googleapis.com/auth/drive.file"]),oauth(token="unsafe\nvalue"),oauth(expires_at=True),"synthetic-private-invalid-json"):
            with self.assertRaises(ValueError) as error: record(raw)
            self.assertNotIn("synthetic-private-invalid-json",str(error.exception))
    def test_broader_refresh_grant_is_refused_without_saving_or_revoking_other_access(self):
        initial=oauth(expires_at=1010); self.credentials.save("chosen",initial)
        self.http.refresh.return_value=dict(token_type="Bearer",access_token="synthetic-new",expires_in=3600,scope=" ".join([*SCOPES,"https://www.googleapis.com/auth/cloud-platform"]))
        with self.assertRaises(ValueError): self.tokens.access("chosen")
        self.assertEqual(initial,self.credentials.read("chosen"))


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.tokens=Mock(); self.tokens.access.return_value="synthetic-access"
        self.http=Mock(); self.http.identity.return_value=dict(sub="synthetic-subject",email="synthetic@example.invalid")
        self.api=ColabAPI(self.tokens,self.temp.name,self.http,now=lambda:1000)
        account="google-"+hashlib.sha256(b"synthetic-subject").hexdigest()
        self.connection=Connection("connection1","colab",account,"Synthetic Colab","chosen")
        self.receipt=replace(rental(),connector_id="colab",account_id=account,created_at=1000,deadline=2000,state="allocating",allocation_submitted=True,protection_id="controller")
        self.preflight=dict(nbh=notebook(self.receipt),variant="GPU",acc="A100",token="synthetic-xsrf")
        self.assigned=dict(endpoint="synthetic-owned",variant=1,accelerator="A100")
        self.gate=Mock()
    def allocate(self):
        self.http.session.side_effect=[self.preflight,self.assigned]
        return self.api.allocate(self.connection,self.receipt,"A100",submit_gate=self.gate)
    def active(self):
        self.allocate(); self.http.session.reset_mock()
        return replace(self.receipt,state="active",resource_id="synthetic-owned")
    def test_single_post_has_durable_proof_and_uses_one_account_token_snapshot(self):
        def response(method,path,token,**kwargs):
            self.assertEqual("synthetic-access",token)
            if method=="GET": return self.preflight
            self.assertEqual(1,self.gate.call_count)
            self.assertTrue(self.api._proof(self.receipt)["submitted"])
            return self.assigned
        self.http.session.side_effect=response
        result=self.api.allocate(self.connection,self.receipt,"A100",submit_gate=self.gate)
        self.assertTrue(result.owned); self.assertEqual("synthetic-owned",result.resource_id)
        self.tokens.access.assert_called_once_with("chosen")
        self.assertNotIn("synthetic@example.invalid",self.api.store.path("op1").read_text())
    def test_preexisting_assignment_is_never_adopted_or_modified(self):
        self.http.session.return_value=self.assigned
        with self.assertRaisesRegex(ValueError,"pre-existing"): self.api.allocate(self.connection,self.receipt,"A100",submit_gate=self.gate)
        self.assertEqual(1,self.http.session.call_count); self.gate.assert_not_called()
        self.assertFalse(self.api.store.path("op1").exists())
    def test_post_timeout_keeps_proof_and_is_reconciled_without_repeat(self):
        self.http.session.side_effect=[self.preflight,TimeoutError("synthetic timeout")]
        with self.assertRaises(TimeoutError): self.api.allocate(self.connection,self.receipt,"A100",submit_gate=self.gate)
        self.assertTrue(self.api.store.path("op1").exists())
        self.http.session.side_effect=[self.assigned,dict(assignments=[dict(endpoint="synthetic-owned"),dict(endpoint="unrelated")])]
        self.assertTrue(self.api.reconcile(self.connection,self.receipt).owned)
        before=self.http.session.call_count
        with self.assertRaisesRegex(ValueError,"already"): self.api.allocate(self.connection,self.receipt,"A100",submit_gate=self.gate)
        self.assertEqual(before,self.http.session.call_count)
    def test_reconciliation_keeps_candidate_when_listing_is_temporarily_unavailable(self):
        self.allocate()
        self.http.session.side_effect=[self.assigned,TimeoutError("synthetic listing timeout")]
        result=self.api.reconcile(self.connection,self.receipt)
        self.assertEqual("synthetic-owned",result.resource_id)
        self.assertEqual("unknown",result.status); self.assertFalse(result.owned)

    def test_runtime_proxy_requires_original_account_mapping_and_exact_listing(self):
        receipt=self.active()
        proxy=dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-runtime-only",tokenExpiresInSeconds=60)
        rows=dict(assignments=[dict(endpoint=receipt.resource_id,runtimeProxyInfo=proxy)])
        self.http.session.side_effect=[self.assigned,rows]
        lease=self.api.runtime_access(self.connection,receipt)
        self.assertEqual((receipt.resource_id,1060),(lease.resource_id,lease.expires_at))
        self.assertNotIn(proxy["token"],repr(lease)); self.assertNotIn(proxy["url"],repr(lease))
        self.assertIs(lease,lease.require_current(1059))
        with self.assertRaises(ValueError): lease.require_current(1060)
        self.assertTrue(all(call.args[0]=="GET" for call in self.http.session.call_args_list))
        for mapping,listing in ((dict(endpoint="unrelated"),rows),(self.assigned,dict(assignments=[])),
                (self.assigned,dict(assignments=rows["assignments"]*2))):
            self.http.session.side_effect=[mapping,listing]
            with self.assertRaises(ValueError): self.api.runtime_access(self.connection,receipt)
        self.http.identity.return_value=dict(sub="other-subject"); self.http.session.reset_mock()
        with self.assertRaises(ValueError): self.api.runtime_access(self.connection,receipt)
        self.http.session.assert_not_called()

    def test_runtime_proxy_refuses_stopped_expired_and_attached_records_before_account_access(self):
        receipt=self.active()
        for changed in (replace(receipt,cancel_requested=True),replace(receipt,deadline=1000,created_at=999),
                replace(receipt,state="stopping"),replace(receipt,mode="attachment",deadline=None,protection_id=None)):
            self.http.identity.reset_mock(); self.http.session.reset_mock()
            with self.assertRaises(ValueError): self.api.runtime_access(self.connection,changed)
            self.http.identity.assert_not_called(); self.http.session.assert_not_called()

    def test_runtime_proxy_rejects_unsupported_origins_and_invalid_expiry_without_leaking_tokens(self):
        from engine_room_connectors._colab.proxy import access
        base=dict(url="https://synthetic-runtime.region.prod.colab.dev/",token="synthetic-runtime-only",tokenExpiresInSeconds=60)
        urls=("http://synthetic.prod.colab.dev/","https://prod.colab.dev/","https://prod.colab.dev.attacker.invalid/",
            "https://synthetic.prod.colab.dev@attacker.invalid/","https://synthetic.prod.colab.dev:443/",
            "https://synthetic.prod.colab.dev/?token=synthetic-runtime-only","https://synthetic.prod.colab.dev/#fragment",
            "https://127.0.0.1/","https://synthetic.googleusercontent.com/","https://synthetic.prod.colab.dev/path",
            "https://synthetic.prod.colab.dev/\n")
        for changes in [*({"url":url} for url in urls),*({"tokenExpiresInSeconds":v} for v in (True,0,-1,86401,1.5)),{"token":"unsafe\nvalue"}]:
            with self.assertRaises(ValueError) as error: access("synthetic-owned",base|changes,1000)
            self.assertNotIn(base["token"],str(error.exception))

    def test_gate_refusal_after_preflight_prevents_post(self):
        self.http.session.return_value=self.preflight; self.gate.side_effect=ValueError("Stopped")
        with self.assertRaises(ValueError): self.api.allocate(self.connection,self.receipt,"A100",submit_gate=self.gate)
        self.assertEqual(1,self.http.session.call_count)
        self.assertFalse(json.loads(self.api.store.path("op1").read_text())["submitted"])
    def test_other_account_cannot_query_or_stop_original_resource(self):
        receipt=self.active(); self.http.identity.return_value=dict(sub="other-subject")
        with self.assertRaisesRegex(ValueError,"differs"): self.api.observe(self.connection,receipt)
        self.http.session.assert_not_called()
    def test_provider_absence_requires_mapping_and_listing_not_usage_counts(self):
        receipt=self.active()
        self.http.session.side_effect=[self.assigned,dict(assignments=[])]
        self.assertEqual("unknown",self.api.observe(self.connection,receipt).status)
        self.http.session.side_effect=[self.preflight,dict(assignments=[dict(endpoint="unrelated",accelerator="future-unknown")])]
        self.assertEqual("absent",self.api.observe(self.connection,receipt).status)
        self.assertFalse(any(c.args[1]=="ccu-info" for c in self.http.session.call_args_list))
    def test_termination_only_targets_correlated_assignment_and_needs_later_confirmation(self):
        receipt=self.active()
        self.http.session.side_effect=[self.assigned,dict(assignments=[dict(endpoint="synthetic-owned"),dict(endpoint="unrelated")]),dict(token="synthetic-stop-xsrf"),None]
        self.assertIsNone(self.api.terminate(self.connection,receipt))
        posts=[c for c in self.http.session.call_args_list if c.args[0]=="POST"]
        self.assertEqual(1,len(posts)); self.assertEqual("unassign/synthetic-owned",posts[0].args[1])
    def test_attachments_missing_proof_and_changed_mapping_are_not_deleted(self):
        self.http.session.reset_mock()
        with self.assertRaises(ValueError): self.api.terminate(self.connection,replace(self.receipt,mode="attachment",deadline=None,resource_id="existing"))
        self.http.session.assert_not_called()
        receipt=self.active(); self.http.session.side_effect=[dict(endpoint="different"),dict(assignments=[dict(endpoint="synthetic-owned"),dict(endpoint="different")])]
        with self.assertRaisesRegex(ValueError,"uncertain"): self.api.terminate(self.connection,receipt)
        self.assertFalse(any(c.args[0]=="POST" for c in self.http.session.call_args_list))
    def test_account_usage_is_never_labelled_as_this_rentals_price(self):
        self.http.session.return_value=dict(currentBalance=10,consumptionRateHourly=12,assignmentsCount=2)
        usage=self.api.usage(self.connection)
        self.assertEqual("account_total",usage["rate_scope"]); self.assertNotIn("rental_rate",usage)
    def test_notebook_identity_is_stable_and_account_connection_operation_bound(self):
        first=notebook(self.receipt); self.assertEqual(44,len(first))
        for changes in (dict(account_id="other"),dict(connection_id="other"),dict(operation_id="other")):
            self.assertNotEqual(first,notebook(replace(self.receipt,**changes)))


class Response(io.BytesIO):
    status=200
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


class HTTPTests(unittest.TestCase):
    def test_xssi_json_is_parsed_and_both_tokens_stay_out_of_url(self):
        opener=Mock(); opener.open.return_value=Response(b")]}'\n{\"endpoint\":\"synthetic\"}")
        http=ColabHTTP(opener)
        self.assertEqual(dict(endpoint="synthetic"),http.session("POST","assign","synthetic-access",params=dict(nbh="synthetic-notebook"),xsrf="synthetic-xsrf"))
        request=opener.open.call_args.args[0]
        self.assertNotIn("synthetic-access",request.full_url); self.assertNotIn("synthetic-xsrf",request.full_url)
        self.assertEqual("Bearer synthetic-access",request.get_header("Authorization"))
    def test_oversized_or_slow_body_fails_without_exposing_content(self):
        opener=Mock(); opener.open.return_value=Response(b"synthetic-private-data")
        http=ColabHTTP(opener); http.limit=4
        with self.assertRaises(ProviderError) as error: http.identity("synthetic-access")
        self.assertNotIn("private-data",str(error.exception))
        ticks=iter((0,0,20)); opener.open.return_value=Response(b"{}")
        http=ColabHTTP(opener,clock=lambda:next(ticks))
        with self.assertRaises(ProviderError): http.identity("synthetic-access")
    def test_refresh_uses_fixed_token_endpoint_and_form_body(self):
        opener=Mock(); opener.open.return_value=Response(b'{"access_token":"synthetic-new"}')
        http=ColabHTTP(opener)
        http.refresh(dict(client_id="synthetic",client_secret="synthetic-client",refresh_token="synthetic-refresh",grant_type="refresh_token"))
        request=opener.open.call_args.args[0]
        self.assertEqual("https://oauth2.googleapis.com/token",request.full_url)
        self.assertIn(b"synthetic-refresh",request.data)
        self.assertNotIn("synthetic-refresh",request.full_url)
