"""Explicit independent-host enrollment. Never infer independence from a second process."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re


def host_identity():
    """Return a one-way machine identity; do not publish the underlying OS identifier."""
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value=winreg.QueryValueEx(key,"MachineGuid")[0]
        raw=value.encode("utf-8")
    else:
        raw=Path("/etc/machine-id").read_bytes().strip()
    if not raw:
        raise ValueError("The controller host identity could not be verified.")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Enrollment:
    controller_id: str
    controller_host_id: str
    client_host_id: str
    independent_host_confirmed: bool

    def verify(self, actual_host_id, client_host_id):
        if not isinstance(self.controller_id,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}",self.controller_id):
            raise ValueError("Invalid controller enrollment.")
        if any(not isinstance(s,str) or not re.fullmatch(r"[a-f0-9]{64}",s) for s in (self.controller_host_id,self.client_host_id)):
            raise ValueError("Controller and client host identities are required.")
        if (self.independent_host_confirmed is not True or self.controller_host_id!=actual_host_id
                or self.client_host_id!=client_host_id or self.controller_host_id==self.client_host_id):
            raise ValueError("Enroll an independently hosted controller before requesting a managed rental.")
        return self

    @classmethod
    def read(cls,path):
        try:
            source=Path(path)
            if source.is_symlink() or source.stat().st_size>4096:
                raise ValueError("Unsafe enrollment record.")
            return cls(**json.loads(source.read_text(encoding="utf-8")))
        except (OSError,ValueError,TypeError):
            raise ValueError("Independent controller enrollment is missing or damaged.") from None
