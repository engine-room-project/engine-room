"""Explicit session-owned tool handoff; relay secrets never cross the UI pipe."""
import re
from .controller_protocol import fields
from .tools import prepare,prepare_existing,launch


def request(value):
    fields(value,("action","request_id","tool","executable","working_directory","desktop_idle","confirmed"))
    if (value["action"]!="tool_launch" or value["confirmed"] is not True
            or not isinstance(value["request_id"],str) or not re.fullmatch(r"[a-f0-9]{32}",value["request_id"])
            or value["tool"] not in {"opencode","codex"} or type(value["desktop_idle"]) is not bool):
        raise ValueError("Explicit supported tool confirmation is required.")
    for key in ("executable","working_directory"):
        text=value[key]
        if not isinstance(text,str) or not 1<=len(text)<=1024 or any(ord(c)<32 for c in text):
            raise ValueError("Choose an explicit native tool and project folder.")
    return value


class SessionTools:
    def __init__(self,rental,model_plan,inactive,*,launcher=launch,preparer=prepare,existing_preparer=prepare_existing):
        self.rental=rental; self.model_plan=model_plan; self.inactive=inactive
        self.launcher=launcher; self.preparer=preparer; self.existing_preparer=existing_preparer; self.seen=set()
    def open(self,value):
        request(value)
        identity=value["request_id"]
        if identity in self.seen or len(self.seen)>=16: raise ValueError("This tool request cannot be repeated.")
        self.seen.add(identity)
        session=self.rental.session
        def authorize():
            if self.inactive() or session is None or session is not self.rental.session or session.stopped.is_set() or session.relay.closed:
                raise ValueError("The session is no longer live.")
        authorize()
        if self.rental.view().get("ready") is not True: raise ValueError("The model is not ready.")
        authorize()
        if self.rental.receipt.mode=="attachment":
            if self.model_plan.get("id")!=session.relay.selected_model: raise ValueError("The selected served model changed.")
            overlay=self.existing_preparer(value["tool"],session.relay.url,session.relay.token,self.model_plan["id"],self.model_plan["context"])
        else: overlay=self.preparer(value["tool"],session.relay.url,session.relay.token,self.model_plan)
        authorize()
        self.launcher(value["executable"],overlay,value["working_directory"],desktop_idle=value["desktop_idle"])
        return dict(event="tool_result",request_id=identity,opened=True,
            message="The selected tool was opened with session-only settings. Compatibility is experimental; keep this window open.")
