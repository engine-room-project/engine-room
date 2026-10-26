"""Small declarative connector forms; labels/data never become executable UI markup."""
import re


def field(name,label,kind,*,required=True,choices=None,minimum=None,maximum=None):
    result=dict(name=name,label=label,kind=kind,required=required)
    if choices is not None: result["choices"]=[dict(value=value,label=label) for value,label in choices]
    if minimum is not None: result["minimum"]=minimum
    if maximum is not None: result["maximum"]=maximum
    return result


def validate(form):
    if (not isinstance(form,dict) or set(form)!={"schema","fields","help"} or type(form["schema"]) is not int or form["schema"]!=1
            or not isinstance(form["help"],str) or len(form["help"])>2000
            or not isinstance(form["fields"],list) or len(form["fields"])>24):
        raise ValueError("The installed connector form is invalid.")
    names=set()
    for item in form["fields"]:
        if (not isinstance(item,dict) or not {"name","label","kind","required"}.issubset(item)
                or set(item)-{"name","label","kind","required","choices","minimum","maximum"}
                or not isinstance(item["name"],str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,49}",item["name"])
                or item["name"] in names or not isinstance(item["label"],str) or not 1<=len(item["label"])<=200
                or any(ord(c)<32 for c in item["label"])
                or not isinstance(item["kind"],str) or item["kind"] not in {"text","integer","boolean","choice","credential_ref"} or type(item["required"]) is not bool):
            raise ValueError("The installed connector field is invalid.")
        names.add(item["name"])
        for key in ("minimum","maximum"):
            if key in item and (item["kind"]!="integer" or type(item[key]) is not int): raise ValueError("Invalid integer field bound.")
        if item.get("minimum",0)>item.get("maximum",2**63): raise ValueError("Invalid field range.")
        choices=item.get("choices")
        if item["kind"]=="choice":
            if not isinstance(choices,list) or len(choices)>512: raise ValueError("Invalid choice field.")
            seen=set()
            for choice in choices:
                if (not isinstance(choice,dict) or set(choice)!={"value","label"}
                        or any(not isinstance(choice[k],str) or not 1<=len(choice[k])<=200 or any(ord(c)<32 for c in choice[k]) for k in choice)
                        or choice["value"] in seen): raise ValueError("Invalid connector choice.")
                seen.add(choice["value"])
        elif choices is not None: raise ValueError("Unexpected connector choices.")
    return form


def model_fields():
    return [field("engine","Model runtime","choice",choices=[("llama.cpp","GGUF (llama.cpp)"),("vLLM","Safetensors (vLLM)")])]


def connection_form():
    return validate(dict(schema=1,fields=[field("hf_credential_ref","Saved model access credential (optional)","credential_ref",required=False)],
        help="Credentials stay on the independent controller. Choose saved references explicitly; leave model access blank for public models."))
