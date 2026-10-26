"""Fresh account telemetry without inventing per-rental prices or storage capacity."""
import math

from engine_room.lifecycle import Quote,selection_key
from engine_room.payload import runtime_profile


def telemetry(api,connection,*,now):
    usage=api.usage(connection)
    if (not isinstance(usage,dict) or usage.get("account_id")!=connection.account_id
            or usage.get("unit")!="CCU" or usage.get("rate_scope")!="account_total"
            or type(usage.get("assignments_count")) is not int or usage["assignments_count"]<0):
        raise ValueError("The original account's compute-unit telemetry is unavailable.")
    for name in ("balance","account_rate","observed_at"):
        value=usage.get(name)
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError("Fresh Colab account telemetry is incomplete.")
    stamp=usage["observed_at"]
    if not 0<=now()-stamp<=120: raise ValueError("Refresh Colab account telemetry before confirming.")
    return usage


def quote(api,connection,selection,*,now):
    profile=runtime_profile(selection["engine"])
    usage=telemetry(api,connection,now=now); stamp=usage["observed_at"]
    details=dict(observed_at=stamp,gpu_validation="before-installation",selected_rental_price="unknown-before-allocation",
        rate_scope="All Colab assignments in this account; not this rental's individual price",
        account_rate=usage["account_rate"],assignments_count=usage["assignments_count"],
        availability="unconfirmed-before-allocation",storage_capacity="unknown-before-allocation",
        storage_validation="before-installation",runtime_validation=profile["validation"],
        installation_reserve_validation="planning-reserve-not-measured")
    return Quote(connection.account_id,selection_key(selection),None,"CCU",usage["balance"],stamp,None,None,
        profile["installation_reserve_bytes"],details,rate_scope="account",balance_required=True).validate(now())
