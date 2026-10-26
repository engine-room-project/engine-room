"""Account-bound volume creation boundary; names identify candidates, never ownership."""
import re

from engine_room.volume_records import VolumeIntent


class Volumes:
    def __init__(self,api): self.api=api
    @staticmethod
    def volume(value):
        if (not isinstance(value,dict) or not isinstance(value.get("id"),str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",value["id"])
                or not isinstance(value.get("name"),str) or not 1<=len(value["name"])<=200 or any(ord(c)<32 for c in value["name"])
                or type(value.get("size")) is not int or not 1<=value["size"]<=4000 or not isinstance(value.get("dataCenter"),str)
                or not re.fullmatch(r"[A-Z0-9-]{2,40}",value["dataCenter"]) or value.get("type") not in {"STANDARD","HIGH_PERFORMANCE"}):
            raise ValueError("The storage observation is incomplete.")
        return {name:value[name] for name in ("id","name","size","dataCenter","type")}
    def inventory(self,connection,*,key=None):
        if key is None:
            key=self.api.credentials.read(connection.credential_ref); self.api.verified_account(connection,_credential=key)
        result=[]; cursor=None; seen=set()
        while True:
            page=self.api.volume_rest(connection.credential_ref,"GET",_credential=key,cursor=cursor)
            if not isinstance(page,dict) or not isinstance(page.get("networkVolumes"),list) or not isinstance(page.get("pagination"),dict):
                raise ValueError("The storage inventory is incomplete.")
            result.extend(self.volume(row) for row in page["networkVolumes"])
            if len(result)>512: raise ValueError("The storage inventory exceeds the supported bound.")
            pagination=page["pagination"]
            if pagination.get("hasNextPage") is False and pagination.get("nextCursor") is None: break
            cursor=pagination.get("nextCursor")
            if pagination.get("hasNextPage") is not True or not isinstance(cursor,str) or not cursor or cursor in seen or len(seen)>=4:
                raise ValueError("The storage inventory pagination is incomplete.")
            seen.add(cursor)
        if len({row["id"] for row in result})!=len(result): raise ValueError("Duplicate storage identities.")
        return result
    @staticmethod
    def matches(value,intent):
        return value["name"]==intent.marker() and value["size"]==intent.size_gb and value["dataCenter"]==intent.data_center and value["type"]==intent.storage_type and value["id"] not in intent.baseline_ids
    def bound(self,connection,intent):
        if not isinstance(intent,VolumeIntent): raise ValueError("Use the original durable storage intent.")
        intent.validate()
        return self.api._bound_credential(connection,intent)
    def create(self,connection,intent,*,submit_gate):
        if not isinstance(intent,VolumeIntent) or intent.state!="submitting" or intent.resource_id is not None or not callable(submit_gate):
            raise ValueError("A durably submitted storage intent and final gate are required.")
        key=self.bound(connection,intent)
        rows=self.inventory(connection,key=key)
        if {row["id"] for row in rows}!=set(intent.baseline_ids) or any(row["name"]==intent.marker() for row in rows):
            raise ValueError("Storage inventory changed; reconcile before any creation request.")
        submit_gate()  # Core persists one-submit authority before this one POST; never retry here.
        value=self.api.volume_rest(connection.credential_ref,"POST",body=dict(name=intent.marker(),size=intent.size_gb,dataCenter=intent.data_center,type=intent.storage_type),_credential=key)
        if not isinstance(value,dict) or not isinstance(value.get("id"),str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",value["id"]):
            raise ValueError("Volume creation remains uncertain; preserve the original intent.")
        if value["id"] in intent.baseline_ids: raise ValueError("The returned volume was already present before creation.")
        verified=False
        try: verified=self.matches(self.volume(value),intent)
        except ValueError: pass
        return dict(resource_id=value["id"],verified=verified,source="creation-response")
    def reconcile(self,connection,intent):
        key=self.bound(connection,intent)
        if intent.resource_id is not None:
            value=self.api.volume_rest(connection.credential_ref,"GET",intent.resource_id,allow_missing=True,_credential=key)
            if value is None: return dict(status="absent",resource_id=intent.resource_id,candidates=[])
            value=self.volume(value)
            if value["id"]!=intent.resource_id or not self.matches(value,intent): raise ValueError("The original volume scope changed.")
            return dict(status="observed",resource_id=value["id"],candidates=[])
        rows=self.inventory(connection,key=key)
        # Even a single exact marker match is only a candidate: provider names are not unique.
        candidates=[row for row in rows if self.matches(row,intent)]
        return dict(status="unresolved",resource_id=None,candidates=candidates)
    def confirm_manual(self,connection,intent,resource_id,*,confirmed):
        if confirmed is not True or not isinstance(resource_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",resource_id):
            raise ValueError("Explicit manual volume identification is required.")
        key=self.bound(connection,intent)
        if resource_id in intent.baseline_ids or (intent.resource_id is not None and intent.resource_id!=resource_id):
            raise ValueError("This volume differs from the original creation operation.")
        value=self.volume(self.api.volume_rest(connection.credential_ref,"GET",resource_id,_credential=key))
        if value["id"]!=resource_id or not self.matches(value,intent): raise ValueError("The selected volume does not match the original intent.")
        return dict(resource_id=resource_id,verified=True,source="explicit-manual-identification")
