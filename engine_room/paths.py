"""Per-user runtime state, independent of checkout location and machine-specific paths."""
import os
from pathlib import Path


def state_root():
    explicit=os.environ.get("ENGINE_ROOM_DATA_DIR")
    if explicit: return Path(explicit).expanduser().resolve()
    if os.name=="nt":
        base=os.environ.get("LOCALAPPDATA")
        if not base: raise ValueError("The Windows application-data directory is unavailable.")
        return Path(base)/"EngineRoom"
    base=os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home()/".local"/"share")/"engine-room"
