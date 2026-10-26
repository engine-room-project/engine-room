"""Conservative storage planning; unverified existing files never count as reusable cache."""
from dataclasses import dataclass


@dataclass(frozen=True)
class StoragePlan:
    required_bytes: int
    available_bytes: int
    disk_gb: int
    cached_bytes: int

    @property
    def fits(self):
        return self.available_bytes >= self.required_bytes


def plan_storage(file_sizes, available_bytes, install_bytes, cached_bytes=0, reserve_bytes=1024**3):
    values=list(file_sizes)
    if not values or any(type(n) is not int or n <= 0 for n in values):
        raise ValueError("Published sizes for every selected model file are required.")
    for n in (available_bytes,install_bytes,cached_bytes,reserve_bytes):
        if type(n) is not int or n < 0:
            raise ValueError("Verified storage capacity and nonnegative installation/cache sizes are required.")
    total=sum(values)
    if cached_bytes>total:
        raise ValueError("Verified cache size exceeds the selected model.")
    # Reserve one largest-file staging copy plus installation and filesystem headroom.
    required=total-cached_bytes+max(values)+install_bytes+reserve_bytes
    return StoragePlan(required,available_bytes,(required+10**9-1)//10**9,cached_bytes)
