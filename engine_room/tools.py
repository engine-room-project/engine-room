"""Coding-tool settings scoped to a child process; never edit normal tool files."""
from dataclasses import dataclass,field
import copy
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
import uuid

from .model_server import command


@dataclass(frozen=True)
class LaunchPlan:
    tool: str
    args: tuple[str,...]
    environment: dict = field(repr=False)
    warnings: tuple[str,...] = ()


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError("Duplicate setting")
        result[key]=value
    return result


def inline_settings(raw):
    """Read existing inline JSONC without rewriting or exporting it."""
    try:
        if not isinstance(raw,str) or len(raw)>65536: raise ValueError()
        token=r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/'
        clean=re.sub(token,lambda match:match[0] if match[0].startswith('"') else ' ',raw)
        clean=re.sub(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])',lambda match:match[0] if match[0].startswith('"') else '',clean)
        value=json.loads(clean,object_pairs_hook=_unique,parse_constant=lambda value:(_ for _ in ()).throw(ValueError()))
        if not isinstance(value,dict): raise ValueError()
        return value
    except Exception:
        raise ValueError("The existing inline OpenCode settings could not be read safely. They were not changed.") from None


def _string(value): return json.dumps(value,ensure_ascii=False)


def served_model_plan(model_id,context):
    if (not isinstance(model_id,str) or not model_id or model_id.startswith("-") or len(model_id)>500
            or any(ord(c)<32 for c in model_id) or type(context) is not int or not 512<=context<=1048576):
        raise ValueError("Choose the exact served model and an explicit conversation limit from its server settings.")
    return dict(id=model_id,context=context)


def prepare(tool,url,token,plan,*,environment=None,effort=None):
    command(plan)  # Use the same checked model identity/context as the runtime.
    return _prepare(tool,url,token,plan,environment=environment,effort=effort)


def prepare_existing(tool,url,token,model_id,context,*,environment=None):
    result=_prepare(tool,url,token,served_model_plan(model_id,context),environment=environment)
    return LaunchPlan(result.tool,result.args,result.environment,result.warnings+("Existing-model capacity is explicitly declared; engine and tool capabilities were not inferred.",))


def _prepare(tool,url,token,plan,*,environment=None,effort=None):
    endpoint=urlsplit(url)
    try: port=endpoint.port
    except ValueError: port=None
    if (endpoint.scheme!="http" or endpoint.hostname!="127.0.0.1" or type(port) is not int
            or not 1024<=port<=65535 or endpoint.path!="/v1" or endpoint.query or endpoint.fragment
            or endpoint.username is not None or endpoint.password is not None):
        raise ValueError("Use this session's authenticated local model address.")
    if not isinstance(token,str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}",token):
        raise ValueError("Use this session's API key explicitly.")
    if tool not in {"opencode","codex"}:
        raise ValueError("Automatic connection for this tool is not yet validated. Existing settings were kept.")
    choices=plan.get("efforts",[])
    if not isinstance(choices,(list,tuple)) or any(e not in {"minimal","low","medium","high","xhigh","max"} for e in choices):
        raise ValueError("The model's effort choices are invalid.")
    if effort is not None and effort not in ["none",*choices]:
        raise ValueError("Choose an effort supported by this model.")
    if plan.get("tool","") not in {"","hermes","qwen3_xml","llama3_json","mistral"} or plan.get("reasoning","") not in {"","qwen3"}:
        raise ValueError("Model parser metadata is invalid.")
    if "vision" in plan and type(plan["vision"]) is not bool: raise ValueError("Model vision metadata is invalid.")
    child=dict(os.environ if environment is None else environment)
    original=inline_settings(child["OPENCODE_CONFIG_CONTENT"]) if tool=="opencode" and child.get("OPENCODE_CONFIG_CONTENT") else {}
    if "provider" in original and not isinstance(original["provider"],dict):
        raise ValueError("The existing OpenCode providers are not a settings object. They were not changed.")
    # A fresh namespace avoids replacing a user-defined provider or key reference.
    for _ in range(4):
        nonce=uuid.uuid4().hex
        provider="engine_room_"+nonce
        variable="ENGINE_ROOM_SESSION_"+nonce.upper()
        if variable not in child and provider not in original.get("provider",{}): break
    else: raise ValueError("A separate tool connection namespace could not be created.")
    child[variable]=token
    selected=effort
    warnings=["Experimental: this coding-tool, model and engine combination needs live validation."]
    if not plan.get("tool"):
        warnings.append("The model's coding-tool calls are unverified; it may only answer with text.")
    if tool=="opencode":
        result=copy.deepcopy(original)
        model={"name":"Engine Room ("+plan["id"]+")","limit":{"context":plan["context"],"output":plan["context"]}}
        if plan.get("tool"): model["tool_call"]=True
        if plan.get("reasoning"): model["reasoning"]=True
        if plan.get("vision"):
            model["attachment"]=True; model["modalities"]={"input":["text","image"],"output":["text"]}
        if choices:
            if selected is not None: model["options"]={"reasoningEffort":selected}
            model["variants"]={name:{"disabled":True} for name in ("minimal","low","medium","high","xhigh","max") if name not in choices}
            model["variants"].update({name:{"reasoningEffort":name} for name in choices})
            model["variants"]["off"]={"reasoningEffort":"none"}
        result.setdefault("provider",{})[provider]={"npm":"@ai-sdk/openai-compatible","name":"Engine Room",
            "whitelist":[plan["id"]],"options":{"baseURL":url,"apiKey":"{env:"+variable+"}"},"models":{plan["id"]:model}}
        result["model"]=provider+"/"+plan["id"]
        content=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(",",":"))
        if len(content.encode("utf-16-le"))>48000:
            raise ValueError("The merged inline tool settings are too large for a dependable Windows launch. Existing settings were kept.")
        child["OPENCODE_CONFIG_CONTENT"]=content
        args=("--model",result["model"])
    else:
        # Override only the selected model/provider for this invocation. Do not move
        # CODEX_HOME, copy auth, weaken approvals or disable the user's integrations.
        settings={"model_provider":_string(provider),"model_context_window":str(plan["context"]),
            "model_providers."+provider:'{name="Engine Room",base_url='+_string(url)+',wire_api="responses",env_key='+_string(variable)+',requires_openai_auth=false}'}
        if selected is not None: settings["model_reasoning_effort"]=_string(selected)
        args=["--model",plan["id"]]
        for key,value in settings.items(): args.extend(("--config",key+"="+value))
        args=tuple(args)
        warnings.append("Codex requires a compatible Responses API; model listing alone does not verify it.")
    return LaunchPlan(tool,tuple(args),child,tuple(warnings))


def launch(executable,plan,working_directory,*,console=True,desktop_idle=False,runner=subprocess.Popen):
    """Launch a user-selected native executable with an isolated environment copy.

    The UI must check that a single-instance desktop application is closed first;
    it must never terminate an existing application to refresh its environment.
    """
    target=Path(executable)
    directory=Path(working_directory)
    if (not target.is_absolute() or not target.is_file() or not directory.is_dir()
            or (os.name=="nt" and target.suffix.lower()!=".exe")):
        raise ValueError("Choose an installed native tool executable and an existing project folder.")
    if plan.tool=="opencode" and target.name.lower()=="opencode.exe" and not desktop_idle:
        raise ValueError("Check that OpenCode is closed before opening this session. Existing windows were not changed.")
    flags=(subprocess.CREATE_NEW_CONSOLE if console else subprocess.CREATE_NO_WINDOW) if os.name=="nt" else 0
    try:
        return runner([str(target),*plan.args],cwd=str(directory),env=dict(plan.environment),creationflags=flags)
    except Exception:
        raise RuntimeError("The selected coding tool could not open. Its existing settings were not changed.") from None
