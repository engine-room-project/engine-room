"""Read current published storage tariffs without provider account credentials."""
import re
import time
import urllib.request

from engine_room.provider_http import NoRedirect

URL="https://docs.runpod.io/pods/pricing.md"


class StoragePrices:
    def __init__(self,opener=None,now=time.time):
        self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        self.now=now

    def read(self):
        try:
            with self.opener.open(URL,timeout=15) as response:
                raw=response.read(512*1024+1)
            if len(raw)>512*1024: raise ValueError("Pricing document too large")
            text=raw.decode("utf-8")
            container=re.search(r"\|\s*\*\*Container disk\*\*\s*\|\s*\\?\$([0-9]+(?:\.[0-9]+)?)/GB/month",text)
            network=re.search(r"\|\s*\*\*Network volume\*\*\s*\|\s*\\?\$([0-9]+(?:\.[0-9]+)?)/GB/month",text)
            if not container or not network: raise ValueError("Storage tariff format changed")
            return {"container_usd_per_gb_month":float(container[1]),"network_usd_per_gb_month_under_1tb":float(network[1]),
                    "source":URL,"observed_at":self.now()}
        except Exception:
            raise ValueError("Current RunPod storage prices could not be verified. Refresh pricing before renting.") from None
