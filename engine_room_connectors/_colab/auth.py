"""Explicit controller-owned Colab OAuth records. No ADC, environment or cache discovery."""
import json
import math
import re
import threading
import time

from .http import bearer,ColabHTTP

SCOPES=frozenset({"openid","https://www.googleapis.com/auth/userinfo.email","https://www.googleapis.com/auth/colaboratory"})
FIELDS=frozenset({"type","client_id","client_secret","refresh_token","token","expires_at","scopes"})


def scopes(value):
    if isinstance(value,str): value=value.split()
    if not isinstance(value,list) or any(not isinstance(item,str) for item in value): raise ValueError("Invalid OAuth scopes")
    result={"https://www.googleapis.com/auth/userinfo.email" if item=="email" else item for item in value}
    if result!=SCOPES: raise ValueError("Use the explicit minimal Colab OAuth scopes; broader grants are not imported.")
    return sorted(result)


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError("Duplicate OAuth field")
        result[key]=value
    return result


def record(raw):
    try:
        data=json.loads(raw,object_pairs_hook=_unique)
        if not isinstance(data,dict) or set(data)!=FIELDS or data["type"]!="colab-oauth-v1": raise ValueError()
        if not isinstance(data["client_id"],str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com",data["client_id"]): raise ValueError()
        for key in ("client_secret","refresh_token","token"): bearer(data[key])
        if type(data["expires_at"]) not in (int,float) or not math.isfinite(data["expires_at"]) or data["expires_at"]<=0: raise ValueError()
        data["scopes"]=scopes(data["scopes"])
        return data
    except Exception:
        raise ValueError("The selected Colab OAuth record is invalid. Authenticate explicitly on the controller; no other account will be used.") from None


class OAuthTokens:
    def __init__(self,credentials,http=None,now=time.time):
        self.credentials=credentials; self.http=http if http is not None else ColabHTTP(); self.now=now
        self.lock=threading.Lock()
    def access(self,reference):
        with self.lock:
            raw=self.credentials.read(reference); data=record(raw)
            if data["expires_at"]>self.now()+60: return data["token"]
            response=self.http.refresh({key:data[key] for key in ("client_id","client_secret","refresh_token")} | {"grant_type":"refresh_token"})
            if not isinstance(response,dict) or response.get("token_type","").lower()!="bearer": raise ValueError("Colab token refresh failed.")
            expires=response.get("expires_in")
            if type(expires) not in (int,float) or not math.isfinite(expires) or not 60<expires<=86400: raise ValueError("Colab token expiry could not be verified.")
            updated={**data,"token":bearer(response.get("access_token")),"expires_at":self.now()+expires}
            if "scope" in response: updated["scopes"]=scopes(response["scope"])
            if "refresh_token" in response: updated["refresh_token"]=bearer(response["refresh_token"])
            value=json.dumps(updated,sort_keys=True,allow_nan=False)
            record(value)
            self.credentials.replace_if(reference,raw,value)
            return updated["token"]



def login_flow():
    """Construct only the explicit reduced-scope flow from the pinned public client."""
    from importlib import metadata,resources
    from pathlib import Path
    from google_auth_oauthlib.flow import InstalledAppFlow
    manifest=json.loads((Path(__file__).resolve().parents[2]/"controller/colab-source.json").read_text(encoding="utf-8"))
    if metadata.version("google-colab-cli")!=manifest["version"]:
        raise ValueError("Install the pinned optional Colab dependencies first.")
    config=json.loads(resources.files("colab_cli").joinpath("oauth_config.json").read_text())
    installed=config.get("installed",{})
    if (installed.get("auth_uri") not in {"https://accounts.google.com/o/oauth2/auth","https://accounts.google.com/o/oauth2/v2/auth"}
            or installed.get("token_uri")!="https://oauth2.googleapis.com/token"):
        raise ValueError("The pinned public Google OAuth client endpoints changed.")
    flow=InstalledAppFlow.from_client_config(config,sorted(SCOPES),autogenerate_code_verifier=True)
    flow.redirect_uri="https://sdk.cloud.google.com/applicationdefaultauthcode.html"
    return flow


def login(credentials,reference,*,overwrite=False,flow_factory=login_flow):
    import datetime
    import getpass
    import sys
    import warnings
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError("Authenticate directly in an interactive controller terminal.")
    if credentials.exists(reference) and not overwrite:
        raise ValueError("This credential reference exists. Choose a new reference or explicitly replace it.")
    try:
        flow=flow_factory()
        url,_=flow.authorization_url(access_type="offline",prompt="consent",token_usage="remote",include_granted_scopes="false")
        from urllib.parse import urlsplit
        parsed=urlsplit(url)
        if parsed.scheme!="https" or parsed.hostname!="accounts.google.com" or parsed.username or parsed.password:
            raise ValueError("Unexpected consent endpoint")
        print("Sign in using this Google authorization URL. Verify the account and requested permissions:",file=sys.stderr)
        print(url,file=sys.stderr)
        with warnings.catch_warnings():
            warnings.simplefilter("error",getpass.GetPassWarning)
            code=getpass.getpass("Google authorization code (hidden): ")
        bearer(code)
        flow.fetch_token(code=code)
        selected=scopes(flow.oauth2session.token.get("scope",list(SCOPES)))
        credential=flow.credentials
        expiry=credential.expiry
        if not isinstance(expiry,datetime.datetime): raise ValueError("Token expiry unavailable")
        if expiry.tzinfo is None: expiry=expiry.replace(tzinfo=datetime.timezone.utc)
        value=json.dumps(dict(type="colab-oauth-v1",client_id=credential.client_id,client_secret=credential.client_secret,
            refresh_token=credential.refresh_token,token=credential.token,expires_at=expiry.timestamp(),scopes=selected),sort_keys=True)
        record(value)
        credentials.save(reference,value,overwrite=overwrite)
    except Exception:
        raise ValueError("Colab authorization did not finish with the required narrow permissions. No ambient account or broader-scope fallback was used.") from None


def main():
    import argparse
    import sys
    from engine_room.controller_service import private_root
    from engine_room.credentials import Credentials
    parser=argparse.ArgumentParser(description="Direct controller Colab login; host and credential setup require owner approval.")
    parser.add_argument("--root",required=True); parser.add_argument("--reference",required=True)
    parser.add_argument("--replace",action="store_true")
    args=parser.parse_args()
    try:
        root=private_root(args.root)
        login(Credentials(root/"credentials"),args.reference,overwrite=args.replace)
        print("Colab authorization saved only for this controller reference. Add and verify its named connection next.")
        return 0
    except Exception:
        print("Colab authorization failed. Check the pinned optional dependencies, explicit account, narrow permissions and owner-only storage.",file=sys.stderr)
        return 1


if __name__=="__main__":
    import sys
    sys.exit(main())
