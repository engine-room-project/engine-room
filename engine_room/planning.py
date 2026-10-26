"""Connector-neutral pre-allocation memory and storage checks."""
import math
from .storage import plan_storage


def offer_plan(plan,quote):
    values=[plan.get(name) for name in ("weightBytes","overheadBytes","kvBytesPerToken")]
    if any(type(value) not in (int,float) or not math.isfinite(value) or value<=0 for value in values):
        raise ValueError("A checked model memory plan is required before renting.")
    required=math.ceil((values[0]+values[1]+values[2]*plan["context"])/0.92)
    details=quote.cost_details or {}
    capacity=details.get("gpu_memory_bytes")
    if capacity is None:
        if details.get("gpu_validation")!="before-installation":
            raise ValueError("Unknown GPU capacity requires an explicit check before installation.")
    elif type(capacity) is not int or capacity<=0 or required>capacity:
        raise ValueError("The offered GPU cannot hold this model, conversation cache and headroom.")
    sizes=plan.get("fileSizes")
    if not isinstance(sizes,dict) or not sizes: raise ValueError("Published file sizes are required.")
    storage=plan_storage(sizes.values(),quote.storage_available_bytes or 0,quote.install_bytes)
    if quote.storage_available_bytes is not None and not storage.fits:
        raise ValueError("The selected disk cannot hold this model, installation and download headroom.")
    return dict(required_gpu_bytes=required,gpu_memory_bytes=capacity,required_storage_bytes=storage.required_bytes,
                storage_available_bytes=quote.storage_available_bytes,gpu_check_deferred=capacity is None,
                storage_check_deferred=quote.storage_available_bytes is None)
