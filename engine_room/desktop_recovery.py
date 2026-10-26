"""Read-only local recovery index; actions retain original enrollment and request scope."""
import json
from pathlib import Path
import re

from .desktop_rental import Rental
from .desktop_attachment import Attachment
from .records import Receipt

IDENTITY=re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")


def listing(root,mode="rental"):
    if mode not in {"rental","attachment"}: raise ValueError("Invalid recovery mode.")
    root=Path(root)
    if root.is_symlink(): raise ValueError("Linked recovery directory.")
    records={}
    damaged=0
    for name in ("requests","receipts"):
        directory=root/name
        if directory.is_symlink(): raise ValueError("Linked recovery directory.")
        paths=list(directory.glob("*.json"))
        if len(paths)>512: raise ValueError("Recovery index needs reconciliation.")
        for path in sorted(paths):
            try:
                operation=path.stem
                if not IDENTITY.fullmatch(operation) or path.is_symlink() or path.stat().st_size>16384: raise ValueError()
                value=json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value,dict) or value.get("operation_id")!=operation: raise ValueError()
                row=records.setdefault(operation,dict(operation_id=operation,state="pending",mode=mode,can_recover=False,shutdown_confirmed=False))
                if name=="requests":
                    if value.get("schema")!=1 or value.get("state") not in {"submitted","linked"}: raise ValueError()
                    if value.get("mode","rental")!=mode: raise ValueError()
                    row["can_recover"]=True
                else:
                    receipt=Receipt(**value).validate()
                    if receipt.mode!=mode: raise ValueError()
                    row["state"]=receipt.state
            except (OSError,ValueError,TypeError,UnicodeError):
                damaged+=1
    return dict(records=list(records.values()),damaged_records=damaged)


def recover(client,root,operation,*,cancel=False,mode="rental"):
    if mode not in {"rental","attachment"}: raise ValueError("Invalid recovery mode.")
    if not isinstance(operation,str) or not IDENTITY.fullmatch(operation): raise ValueError("Invalid recovery identity.")
    rental=(Attachment if mode=="attachment" else Rental)(client,root)
    result=rental.abandon(operation) if cancel else rental.refresh(operation)
    if isinstance(result,dict):
        return dict(operation_id=operation,state=result["state"],shutdown_confirmed=False)
    return dict(operation_id=result.operation_id,state=result.state,mode=mode,
        shutdown_confirmed=mode=="rental" and result.state=="off",
        disconnected_confirmed=mode=="attachment" and result.state=="detached")
