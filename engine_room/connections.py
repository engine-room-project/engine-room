"""Explicit named connections; fresh installations contain no provider or credential."""
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import unicodedata
import uuid

from .records import DamagedRecord, Store, atomic_json


@dataclass(frozen=True)
class Connection:
    id: str
    connector_id: str
    account_id: str
    name: str = ""
    credential_ref: str = ""
    settings: dict = field(default_factory=dict)

    def validate(self):
        for value in (self.id, self.connector_id):
            if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value):
                raise ValueError("Invalid connection identity.")
        if not isinstance(self.account_id, str) or not 1 <= len(self.account_id) <= 200 or any(ord(c)<32 for c in self.account_id):
            raise ValueError("Verified provider account identity is required.")
        if not isinstance(self.name,str) or not 1 <= len(self.name.strip()) <= 80 or any(ord(c)<32 for c in self.name):
            raise ValueError("Choose a connection name of 1 to 80 readable characters.")
        if not isinstance(self.credential_ref,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", self.credential_ref):
            raise ValueError("Choose an explicit credential for this connection.")
        if not isinstance(self.settings,dict):
            raise ValueError("Invalid connector settings.")
        return self


class Connections:
    def __init__(self, root, registry):
        self.root = Path(root)
        self.path = self.root / "connections.json"
        self.receipts = Store(self.root / "receipts")
        self.registry = registry

    def read(self):
        if not self.path.exists():
            return {}
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 65536:
                raise ValueError("Unsafe connection configuration.")
            data=json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data,dict) or set(data) != {"schema", "connections"} or type(data["schema"]) is not int or data["schema"] != 1:
                raise ValueError("Unsupported connection configuration.")
            if not isinstance(data["connections"],list):
                raise ValueError("Invalid connections list.")
            result={}
            names=set()
            for item in data["connections"]:
                connection=Connection(**item).validate()
                name=unicodedata.normalize("NFC",connection.name).casefold()
                if connection.id in result or name in names:
                    raise ValueError("Duplicate connection identity or name.")
                names.add(name)
                result[connection.id]=connection
            return result
        except (OSError, ValueError, TypeError, UnicodeError):
            raise ValueError("Connection configuration is damaged. Preserve it and restore or repair it before continuing.") from None

    def _save(self, connections):
        atomic_json(self.path,{"schema":1,"connections":[asdict(c) for c in connections.values()]})

    def add(self, name, connector_id, credential_ref, settings=None):
        # Both naming and credentials are explicit. No default provider or fallback to
        # another application's account. Account changes create a distinct connection.
        connection=Connection(uuid.uuid4().hex,connector_id,"unverified",name.strip(),credential_ref,settings or {}).validate()
        connector=self.registry[connector_id]
        with self.receipts.allocation_lock():
            current=self.read()
            normalized=unicodedata.normalize("NFC",connection.name).casefold()
            if any(unicodedata.normalize("NFC",c.name).casefold()==normalized for c in current.values()):
                raise ValueError("That connection name is already in use.")
            try:
                checked=connector.preflight(credential_ref,connection.settings)
                account=checked["account_id"]
                checked_settings=checked["settings"]
                connection=Connection(connection.id,connector_id,account,connection.name,credential_ref,checked_settings).validate()
            except Exception:
                raise ValueError("Connection setup failed. Check this connector's prerequisites and the credential you explicitly selected.") from None
            current[connection.id]=connection
            self._save(current)
        return connection

    def remove(self, connection_id):
        with self.receipts.allocation_lock():
            current=self.read()
            if connection_id not in current:
                raise ValueError("Named connection was not found.")
            for receipt in self.receipts.scan():
                if isinstance(receipt,DamagedRecord) or (receipt.connection_id==connection_id and receipt.state not in {"off","detached","cancelled"}):
                    raise ValueError("Recover or disconnect the existing operation before removing this connection.")
            del current[connection_id]
            self._save(current)
        # Removing a connection never terminates a machine or deletes provider storage.
