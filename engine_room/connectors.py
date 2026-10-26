"""Discovery of trusted installed connector modules; configuration never names executable paths."""
from dataclasses import dataclass
import importlib
import pkgutil
import re


@dataclass(frozen=True)
class Descriptor:
    id: str
    name: str
    credential_label: str
    modes: tuple[str, ...] = ("rental",)
    contract_version: int = 1
    capabilities: tuple[str,...] = ()

    def validate(self):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", self.id):
            raise ValueError("Invalid installed connector identity.")
        if self.contract_version != 1 or not self.name or not self.credential_label:
            raise ValueError("Unsupported or incomplete connector descriptor.")
        if not self.modes or any(m not in {"rental", "attachment"} for m in self.modes):
            raise ValueError("Invalid connector lifecycle modes.")
        if not isinstance(self.capabilities,tuple) or any(value!="persistent_storage" for value in self.capabilities):
            raise ValueError("Unsupported connector capability.")
        return self


class Registry:
    def __init__(self):
        self._items = {}
        self.errors = {}

    def register(self, connector):
        descriptor = connector.descriptor.validate()
        if descriptor.id in self._items:
            raise ValueError("Duplicate connector identity.")
        for method in ("preflight", "account_identity", "observe", "reconcile", "terminate", "disconnect"):
            if not callable(getattr(connector, method, None)):
                raise ValueError("Installed connector does not implement the lifecycle contract.")
        if "attachment" in descriptor.modes:
            for method in ("attachment_target","attach","pulse","model_endpoint"):
                if not callable(getattr(connector,method,None)):
                    raise ValueError("Installed connector does not implement existing-machine access.")
        if "persistent_storage" in descriptor.capabilities:
            for method in ("storage_quote","storage_inventory","storage_create","storage_reconcile","storage_identify"):
                if not callable(getattr(connector,method,None)):
                    raise ValueError("Installed connector does not implement persistent storage recovery.")
        self._items[descriptor.id] = connector

    def discover(self, package="engine_room_connectors"):
        # Installing a connector is installing trusted code. Never download or import
        # modules selected by a model page, receipt or connection configuration.
        namespace = importlib.import_module(package)
        for module in sorted(pkgutil.iter_modules(namespace.__path__), key=lambda m: m.name):
            if module.name.startswith("_"):
                continue
            try:
                connector = importlib.import_module(package + "." + module.name).create_connector()
                self.register(connector)
            except Exception:
                self.errors[module.name] = "This connector could not load. Check its installation and prerequisites."
        return self

    def __getitem__(self, connector_id):
        try:
            return self._items[connector_id]
        except KeyError:
            raise ValueError("Install the connector for this named connection first.") from None

    def descriptors(self):
        return [c.descriptor for c in self._items.values()]
