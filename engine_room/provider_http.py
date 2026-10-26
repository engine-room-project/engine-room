"""Bounded JSON provider HTTP. Credentials stay in headers, never URLs or errors."""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class ProviderError(RuntimeError):
    def __init__(self,status=None):
        self.status=status
        super().__init__("The provider request failed. Check credentials, connectivity and provider status.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ProviderError()


def private_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())


def read_bounded(response,limit,deadline,clock):
    """A steady trickle must not keep a lifecycle API call alive indefinitely."""
    chunks=[]; total=0
    while True:
        if clock()>=deadline: raise ProviderError()
        chunk=response.read1(min(65536,limit+1-total))
        if clock()>=deadline: raise ProviderError()
        total+=len(chunk)
        if total>limit: raise ProviderError()
        if not chunk: return b"".join(chunks)
        chunks.append(chunk)


class JsonHTTP:
    allowed_hosts=frozenset({"api.runpod.io","rest.runpod.io"})
    max_response_bytes=2*1024*1024

    def __init__(self,opener=None,clock=time.monotonic):
        self.opener=opener if opener is not None else private_opener(); self.clock=clock

    def request(self,method,url,credential,body=None,*,allow_missing=False):
        parsed=urlsplit(url)
        if (parsed.scheme!="https" or parsed.hostname not in self.allowed_hosts or parsed.port not in (None,443)
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Invalid provider API endpoint.")
        if not isinstance(credential,str) or not credential or any(ord(c)<33 or ord(c)>126 for c in credential):
            raise ValueError("The selected provider credential is invalid.")
        if method not in {"GET","POST","DELETE","PATCH"}:
            raise ValueError("Invalid provider operation.")
        payload=None if body is None else json.dumps(body,allow_nan=False).encode("utf-8")
        request=urllib.request.Request(url,data=payload,method=method,headers={
            "Authorization":"Bearer "+credential,"Content-Type":"application/json","User-Agent":"EngineRoom/0.1"})
        try:
            # No automatic retry: an uncertain allocation POST must be reconciled.
            deadline=self.clock()+15
            with self.opener.open(request,timeout=15) as response:
                status=response.status
                if not 200<=status<300:
                    raise ProviderError(status)
                raw=read_bounded(response,self.max_response_bytes,deadline,self.clock)
                return None if not raw else json.loads(raw)
        except urllib.error.HTTPError as error:
            if method=="GET" and allow_missing and error.code==404:
                return None
            raise ProviderError(error.code) from None
        except (urllib.error.URLError,OSError,ValueError):
            raise ProviderError() from None
