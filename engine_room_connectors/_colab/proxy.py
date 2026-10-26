"""Short-lived runtime access from an owned Colab assignment, never account OAuth."""
from dataclasses import dataclass,field
import math
import re
from urllib.parse import urlsplit

from .http import bearer


@dataclass(frozen=True)
class ProxyAccess:
    resource_id: str
    url: str = field(repr=False)
    token: str = field(repr=False)
    expires_at: float

    def require_current(self,now):
        if type(now) not in (int,float) or not math.isfinite(now) or not now<self.expires_at:
            raise ValueError("The Colab runtime access expired. Refresh ownership before connecting.")
        return self


def access(resource_id,data,now):
    try:
        if not isinstance(data,dict): raise ValueError()
        url=data["url"]; token=bearer(data["token"]); ttl=data["tokenExpiresInSeconds"]
        if (not isinstance(url,str) or len(url)>2048 or any(ord(c)<33 or ord(c)>126 for c in url)
                or type(ttl) is not int or not 1<=ttl<=86400
                or type(now) not in (int,float) or not math.isfinite(now) or now<0): raise ValueError()
        parsed=urlsplit(url)
        # Current native runtime origin, not arbitrary Google-hosted user content.
        if (parsed.scheme!="https" or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.path not in ("","/") or parsed.query or parsed.fragment
                or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+prod\.colab\.dev",parsed.netloc)):
            raise ValueError()
        return ProxyAccess(resource_id,"https://"+parsed.netloc+"/",token,now+ttl)
    except Exception:
        raise ValueError("The owned Colab runtime returned invalid or unsupported private access details.") from None
