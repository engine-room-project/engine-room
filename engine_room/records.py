"""Account-bound recovery records. No credential material belongs in this store."""
from __future__ import annotations

from .billing import valid_scope,valid_unit

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
import time

_ID = re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")
_STATES = {"intent", "allocating", "active", "stopping", "unresolved", "off", "detached", "cancelled"}


def atomic_json(target, value):
    """Flush data before same-directory replacement; never expose a partial JSON file."""
    target = Path(target)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    # Same-directory replacement keeps a partial write from replacing a healthy receipt.
    fd, name = tempfile.mkstemp(prefix=".receipt-", suffix=".tmp", dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(temp,target)
                break
            except PermissionError as error:
                # Windows readers/scanners can briefly deny delete sharing. Never
                # remove the existing receipt or weaken replacement atomicity.
                if os.name!="nt" or getattr(error,"winerror",None) not in {5,32,33} or attempt==5:
                    raise
                time.sleep(0.01*2**attempt)
        if os.name != "nt":
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


@dataclass(frozen=True)
class Receipt:
    operation_id: str
    connection_id: str
    connector_id: str
    account_id: str
    mode: str
    state: str
    created_at: float
    deadline: float | None = None
    resource_id: str | None = None
    protection_id: str | None = None
    schema: int = 1
    lease_expires_at: float | None = None
    rate_ceiling: float | None = None
    rate_unit: str | None = None
    cancel_requested: bool = False
    allocation_submitted: bool = False
    quote_key: str | None = None
    cost_details: dict | None = None
    rate_scope: str = "rental"

    def validate(self):
        for value in (self.operation_id, self.connection_id, self.connector_id):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError("Invalid recovery record identity.")
        if not isinstance(self.account_id, str) or not 1 <= len(self.account_id) <= 200:
            raise ValueError("Verified provider account identity is required.")
        if any(ord(c) < 32 for c in self.account_id):
            raise ValueError("Invalid provider account identity.")
        if self.schema != 1 or type(self.schema) is not int:
            raise ValueError("Unsupported recovery record version.")
        if self.mode not in {"rental", "attachment"} or self.state not in _STATES:
            raise ValueError("Invalid recovery record lifecycle.")
        if type(self.created_at) not in (int, float) or not math.isfinite(self.created_at) or self.created_at <= 0:
            raise ValueError("Invalid operation start time.")
        if self.quote_key is not None and (not isinstance(self.quote_key,str) or not re.fullmatch(r"[a-f0-9]{64}",self.quote_key)):
            raise ValueError("Invalid confirmed quote identity.")
        if self.cost_details is not None and not isinstance(self.cost_details,dict):
            raise ValueError("Invalid recorded cost details.")
        if type(self.cancel_requested) is not bool or type(self.allocation_submitted) is not bool:
            raise ValueError("Invalid operation flags.")
        if self.state == "cancelled" and (self.resource_id is not None or self.allocation_submitted):
            raise ValueError("Only an unsubmitted allocation may be cancelled locally.")
        if self.lease_expires_at is not None and (type(self.lease_expires_at) not in (int,float) or not math.isfinite(self.lease_expires_at) or self.deadline is None or not self.created_at < self.lease_expires_at <= self.deadline):
            raise ValueError("Invalid controller lease.")
        if self.rate_ceiling is not None and (type(self.rate_ceiling) not in (int,float) or not math.isfinite(self.rate_ceiling) or self.rate_ceiling <= 0 or not valid_unit(self.rate_unit)):
            raise ValueError("Invalid confirmed rate ceiling.")
        if not valid_scope(self.rate_scope):
            raise ValueError("Invalid confirmed billing scope.")
        if self.mode == "rental":
            if type(self.deadline) not in (int, float) or not math.isfinite(self.deadline) or self.deadline <= self.created_at:
                raise ValueError("Managed rentals require a finite deadline.")
            if self.state == "detached":
                raise ValueError("Detaching does not stop a managed rental.")
        elif self.deadline is not None or self.state == "off":
            raise ValueError("Attachment records cannot assert machine shutdown.")
        for value in (self.resource_id, self.protection_id):
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 200 or any(ord(c) < 32 for c in value)):
                raise ValueError("Invalid resource or protection identity.")
        if self.state in {"active", "stopping", "off", "detached"} and not self.resource_id:
            raise ValueError("A provider resource identity is required.")
        if self.mode == "rental" and self.state in {"allocating", "active", "stopping", "off"} and not self.protection_id:
            raise ValueError("Independent protection evidence is required.")
        return self

    def operation_key(self):
        """Stable operation scope, not authentication; resource ID can arrive later."""
        self.validate()
        fields=(self.operation_id,self.connection_id,self.connector_id,self.account_id,self.mode,
            self.created_at,self.deadline,self.protection_id,self.rate_ceiling,self.rate_unit,self.quote_key,self.rate_scope)
        return hashlib.sha256(json.dumps(fields,separators=(",",":"),allow_nan=False).encode()).hexdigest()

    @property
    def unresolved(self):
        return self.mode == "rental" and self.state not in {"off", "cancelled"}


@dataclass(frozen=True)
class DamagedRecord:
    filename: str
    message: str = "Recovery record cannot be read safely; keep it for manual reconciliation."


class Store:
    """Single-host state directory; the caller holds allocation_lock for lifecycle writes."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, operation_id):
        if not isinstance(operation_id, str) or not _ID.fullmatch(operation_id):
            raise ValueError("Invalid operation identity.")
        return self.root / (operation_id + ".json")

    def save(self, receipt):
        receipt.validate()
        target = self.path(receipt.operation_id)
        atomic_json(target, asdict(receipt))

    def scan(self):
        """A broken receipt never prevents reading later healthy receipts."""
        results = []
        for path in sorted(self.root.glob("*.json")):
            try:
                if path.is_symlink() or path.stat().st_size > 16384:
                    raise ValueError("Unsafe record file.")
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Invalid record object.")
                receipt = Receipt(**data).validate()
                if path.name != receipt.operation_id + ".json":
                    raise ValueError("Record filename and identity differ.")
                results.append(receipt)
            except (OSError, ValueError, TypeError, UnicodeError):
                # Never include raw record content or parser output in user-facing errors.
                results.append(DamagedRecord(path.name))
        return results

    def load(self, operation_id):
        expected = self.path(operation_id).name
        for record in self.scan():
            if isinstance(record, Receipt) and record.operation_id == operation_id:
                return record
            if isinstance(record, DamagedRecord) and record.filename == expected:
                raise ValueError("This recovery record is damaged; preserve it for reconciliation.")
        raise ValueError("Operation was not found.")

    def blockers(self):
        return [r for r in self.scan() if isinstance(r, DamagedRecord) or r.unresolved]

    @contextmanager
    def allocation_lock(self, timeout=5):
        """Serialize final pre-allocation checks with all writers on this host."""
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Invalid allocation lock timeout.")
        lock_path = self.root / ".allocation.lock"
        if lock_path.is_symlink():
            raise ValueError("Unsafe allocation lock file.")
        with open(lock_path, "a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            until = time.monotonic() + timeout
            acquired = False
            while not acquired:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except (BlockingIOError, OSError):
                    if time.monotonic() >= until:
                        raise TimeoutError("Another lifecycle operation is still in progress.") from None
                    time.sleep(min(0.05, max(0, until - time.monotonic())))
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
