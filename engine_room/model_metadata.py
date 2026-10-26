"""Verify pinned model download metadata on the controller before spending."""
import json
import urllib.request
import urllib.error
from urllib.parse import urlsplit

from .model_server import command
from .provider_http import NoRedirect


class StopRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class ModelMetadata:
    def __init__(self,credentials,opener=None,head_opener=None):
        self.credentials=credentials
        self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        self.head_opener=head_opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),StopRedirect())

    def verify(self,plan,credential_ref=None):
        command(plan)
        headers={"User-Agent":"EngineRoom/0.1"}
        if credential_ref: headers["Authorization"]="Bearer "+self.credentials.read(credential_ref)
        request=urllib.request.Request("https://huggingface.co/api/models/"+plan["id"]+"/revision/"+plan["revision"]+"?blobs=true",headers=headers)
        try:
            with self.opener.open(request,timeout=20) as response:
                raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024: raise ValueError("Metadata too large")
            info=json.loads(raw)
            if info.get("sha")!=plan["revision"]: raise ValueError("Revision changed")
            published={item["rfilename"]:item for item in info["siblings"]}
            sizes=plan["fileSizes"]
            if (info.get("gated") or info.get("private")) and not credential_ref:
                raise ValueError("Explicit model credential required")
            if plan["engine"]=="vLLM":
                expected={name for name in published if "/" not in name and name.endswith(".safetensors") and "adapter" not in name}
                if set(sizes)!=expected: raise ValueError("Weight manifest differs")
            for name,size in sizes.items():
                if type(size) is not int or size<=0 or published[name].get("size")!=size:
                    raise ValueError("Published sizes changed")
                expected_hash=(plan.get("fileHashes") or {}).get(name)
                if expected_hash and (published[name].get("lfs") or {}).get("sha256")!=expected_hash:
                    raise ValueError("Published file hash changed")
            # Metadata may be visible for gated models even when downloads are refused.
            # Check one selected file with HEAD and never follow the credentialed redirect.
            name=next(iter(sizes))
            access=urllib.request.Request("https://huggingface.co/"+plan["id"]+"/resolve/"+plan["revision"]+"/"+name,
                headers=headers,method="HEAD")
            try:
                with self.head_opener.open(access,timeout=15) as response:
                    if response.status!=200: raise ValueError("Model download not authorized")
            except urllib.error.HTTPError as error:
                target=urlsplit(error.headers.get("Location",""))
                if error.code not in {301,302,303,307,308} or target.scheme!="https" or not target.hostname:
                    raise ValueError("Model download not authorized") from None
        except Exception:
            raise ValueError("Model access or pinned download metadata could not be verified. Check the selected model credential and licence access before renting.") from None
        return info
