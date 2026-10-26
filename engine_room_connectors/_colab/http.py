"""Fixed-origin Colab protocol HTTP; account credentials never enter URLs or errors.

Wire format follows google-colab-cli (Google LLC, Apache-2.0); see notices/provenance.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from engine_room.provider_http import ProviderError,private_opener,read_bounded


def bearer(value):
    if not isinstance(value,str) or not 1<=len(value)<=8192 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise ValueError("The explicitly selected Colab token is invalid.")
    return value


class ColabHTTP:
    limit=2*1024*1024
    def __init__(self,opener=None,clock=time.monotonic):
        self.opener=opener if opener is not None else private_opener(); self.clock=clock
    def _send(self,method,url,headers,data=None):
        request=urllib.request.Request(url,data=data,method=method,headers={"User-Agent":"EngineRoom/0.1",**headers})
        try:
            deadline=self.clock()+15
            with self.opener.open(request,timeout=15) as response:
                if not 200<=response.status<300: raise ProviderError(response.status)
                raw=read_bounded(response,self.limit,deadline,self.clock)
            if raw.startswith(b")]}'\n"): raw=raw[5:]
            return None if not raw else json.loads(raw)
        except urllib.error.HTTPError as error: raise ProviderError(error.code) from None
        except Exception: raise ProviderError() from None
    def session(self,method,path,token,*,params=None,xsrf=None):
        if method not in {"GET","POST"} or not (path in {"assign","assignments","ccu-info"} or re.fullmatch(r"unassign/[A-Za-z0-9][A-Za-z0-9_.~-]{0,199}",path)):
            raise ValueError("Invalid Colab operation.")
        if params is not None and (not isinstance(params,dict) or set(params)-{"nbh","variant","accelerator","shape"}):
            raise ValueError("Unexpected Colab request parameters.")
        query=urllib.parse.urlencode({**(params or {}),"authuser":"0"})
        headers={"Authorization":"Bearer "+bearer(token),"Accept":"application/json","X-Colab-Client-Agent":"colab-cli"}
        if xsrf is not None: headers["X-Goog-Colab-Token"]=bearer(xsrf)
        return self._send(method,"https://colab.research.google.com/tun/m/"+path+"?"+query,headers,b"" if method=="POST" else None)
    def identity(self,token):
        return self._send("GET","https://openidconnect.googleapis.com/v1/userinfo",{"Authorization":"Bearer "+bearer(token),"Accept":"application/json"})
    def refresh(self,fields):
        if not isinstance(fields,dict) or set(fields)!={"client_id","client_secret","refresh_token","grant_type"} or fields["grant_type"]!="refresh_token":
            raise ValueError("Invalid OAuth refresh request.")
        return self._send("POST","https://oauth2.googleapis.com/token",{"Content-Type":"application/x-www-form-urlencoded"},urllib.parse.urlencode(fields).encode())
