import io
import json
import unittest
import urllib.error
from unittest.mock import Mock

from engine_room.provider_http import JsonHTTP,NoRedirect,ProviderError


class Response:
    status=200
    def __init__(self,raw): self.raw=io.BytesIO(raw)
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read1(self,limit): return self.raw.read(limit)


class HttpTests(unittest.TestCase):
    def setUp(self): self.opener=Mock(); self.http=JsonHTTP(self.opener)
    def test_credential_only_in_header_and_single_bounded_request(self):
        self.opener.open.return_value=Response(b'{"id":"synthetic"}')
        result=self.http.request("POST","https://rest.runpod.io/v1/pods","synthetic-key",{"name":"test"})
        self.assertEqual("synthetic",result["id"])
        request=self.opener.open.call_args.args[0]
        self.assertNotIn("synthetic-key",request.full_url)
        self.assertNotIn(b"synthetic-key",request.data)
        self.assertEqual("Bearer synthetic-key",request.get_header("Authorization"))
        self.opener.open.assert_called_once()
        self.assertEqual(15,self.opener.open.call_args.kwargs["timeout"])
    def test_lost_post_response_is_not_retried_or_reported_as_absent(self):
        self.opener.open.side_effect=TimeoutError("synthetic-sensitive-error")
        with self.assertRaises(ProviderError) as error: self.http.request("POST","https://rest.runpod.io/v1/pods","synthetic-key",{})
        self.assertNotIn("sensitive",str(error.exception))
        self.opener.open.assert_called_once()
    def test_404_only_means_absence_when_explicit_get_allows_it(self):
        self.opener.open.side_effect=urllib.error.HTTPError("https://rest.runpod.io/v1/pods/pod",404,"synthetic",{},None)
        self.assertIsNone(self.http.request("GET","https://rest.runpod.io/v1/pods/pod","synthetic-key",allow_missing=True))
        for method in ("GET","POST","DELETE"):
            with self.subTest(method=method),self.assertRaises(ProviderError): self.http.request(method,"https://rest.runpod.io/v1/pods/pod","synthetic-key")
    def test_redirect_or_arbitrary_endpoint_refused(self):
        with self.assertRaises(ProviderError): NoRedirect().redirect_request(None,None,None,None,None,None)
        for url in ("http://rest.runpod.io/v1/pods","https://evil.invalid/v1/pods","https://rest.runpod.io/v1/pods?api_key=synthetic"):
            with self.subTest(url=url),self.assertRaises(ValueError): self.http.request("GET",url,"synthetic-key")
        self.opener.open.assert_not_called()
    def test_slow_trickle_and_late_final_chunk_cannot_extend_lifecycle_request(self):
        for values in ((0,0,1,16),(0,0,16)):
            ticks=iter(values)
            self.opener.open.return_value=Response(b"{}")
            self.http=JsonHTTP(self.opener,clock=lambda:next(ticks))
            with self.assertRaises(ProviderError):
                self.http.request("GET","https://rest.runpod.io/v1/pods","synthetic-key")
        self.assertEqual(2,self.opener.open.call_count)

    def test_oversized_or_malformed_json_fails_safely(self):
        for raw in (b'{"secret":"synthetic-sensitive"',b" "*(self.http.max_response_bytes+1)):
            self.opener.open.return_value=Response(raw)
            with self.assertRaises(ProviderError) as error: self.http.request("GET","https://rest.runpod.io/v1/pods","synthetic-key")
            self.assertNotIn("sensitive",str(error.exception))


if __name__=="__main__": unittest.main()
