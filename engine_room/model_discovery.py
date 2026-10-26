"""Read-only, pinned metadata for the existing desktop planner; never execute model code."""
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin,urlsplit

from .model_metadata import StopRedirect

MODEL=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
SHA=re.compile(r"[a-f0-9]{40}\Z")
CONFIG=("model_type","max_position_embeddings","num_hidden_layers","num_key_value_heads","head_dim",
        "num_attention_heads","hidden_size","kv_lora_rank","layer_types","dtype","torch_dtype")


def identifier(value):
    if not isinstance(value,str) or len(value)>200 or not MODEL.fullmatch(value) or ".." in value:
        raise ValueError("Choose an owner/model identifier.")
    return value


def config_view(value,*,nested=True):
    if not isinstance(value,dict): raise ValueError("Invalid model configuration.")
    result={key:value[key] for key in CONFIG if key in value}
    quant=value.get("quantization_config")
    if isinstance(quant,dict): result["quantization_config"]={"quant_method":quant.get("quant_method")}
    if value.get("vision_config"): result["vision_config"]={"present":True}
    if nested and "text_config" in value: result["text_config"]=config_view(value["text_config"],nested=False)
    return result


class Discovery:
    def __init__(self,credentials,opener=None):
        self.credentials=credentials
        self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),StopRedirect())
    def read(self,url,headers,*,optional=False,pinned_revision=None):
        for attempt in range(4):
            try:
                with self.opener.open(urllib.request.Request(url,headers=headers),timeout=20) as response:
                    raw=response.read(2*1024*1024+1)
                if len(raw)>2*1024*1024: raise ValueError("Metadata is too large.")
                value=json.loads(raw)
                if not isinstance(value,dict): raise ValueError("Invalid metadata.")
                return value
            except urllib.error.HTTPError as error:
                if optional and error.code==404: return None
                if error.code not in {301,302,303,307,308} or attempt==3: raise ValueError("Metadata is unavailable.") from None
                target=urljoin(url,error.headers.get("Location","")); parts=urlsplit(target)
                if parts.scheme!="https" or parts.netloc!="huggingface.co" or parts.fragment or parts.username:
                    raise ValueError("Metadata redirect left the trusted origin.") from None
                if pinned_revision is not None and pinned_revision not in parts.path.split("/"):
                    raise ValueError("Metadata redirect changed the pinned revision.")
                url=target
        raise ValueError("Metadata redirects exceeded the limit.")
    def repository(self,model,headers):
        identifier(model)
        url="https://huggingface.co/api/models/"+model
        initial=self.read(url,headers)
        revision=initial.get("sha")
        if not isinstance(revision,str) or not SHA.fullmatch(revision): raise ValueError("Model revision is missing.")
        info=self.read(url+"/revision/"+revision+"?blobs=true",headers,pinned_revision=revision)
        if info.get("sha")!=revision: raise ValueError("Model revision changed.")
        config=self.read("https://huggingface.co/"+model+"/resolve/"+revision+"/config.json",headers,optional=True,pinned_revision=revision)
        return info,config_view(config) if config is not None else None
    def discover(self,model,credential_ref=None,base_model=None):
        identifier(model)
        explicit_base=base_model is not None
        if base_model is not None: identifier(base_model)
        headers={"User-Agent":"EngineRoom/0.1"}
        if credential_ref: headers["Authorization"]="Bearer "+self.credentials.read(credential_ref)
        info,config=self.repository(model,headers)
        if (info.get("gated") or info.get("private")) and not credential_ref:
            raise ValueError("Choose an explicit model access credential on the named connection.")
        siblings=info.get("siblings")
        if not isinstance(siblings,list) or len(siblings)>2048: raise ValueError("The model file index exceeds the supported bound.")
        files=[]
        for item in siblings:
            if not isinstance(item,dict) or not isinstance(item.get("rfilename"),str) or len(item["rfilename"])>200:
                raise ValueError("Invalid model file index.")
            row={"rfilename":item["rfilename"],"size":item.get("size")}
            lfs=item.get("lfs")
            if isinstance(lfs,dict) and isinstance(lfs.get("sha256"),str) and re.fullmatch(r"[a-f0-9]{64}",lfs["sha256"]): row["lfs"]={"sha256":lfs["sha256"]}
            files.append(row)
        card=info.get("cardData") or {}
        suggested=card.get("base_model") if isinstance(card,dict) else None
        if isinstance(suggested,list): suggested=suggested[0] if suggested else None
        if base_model is None and isinstance(suggested,str):
            try: base_model=identifier(suggested)
            except ValueError: pass
        base_config=config; base_revision=info["sha"] if config is not None else None
        needs_base=any(row["rfilename"].endswith(".gguf") for row in files) and config is None
        if base_model and (needs_base or explicit_base):
            base_info,base_config=self.repository(base_model,headers); base_revision=base_info["sha"]
        gguf=info.get("gguf")
        projected={key:info.get(key) for key in ("sha","pipeline_tag","library_name")}
        projected.update(siblings=files,cardData={"base_model":base_model},gguf={"context_length":gguf.get("context_length")} if isinstance(gguf,dict) else {})
        return dict(model_id=model,info=projected,config=config,base_model=base_model,base_revision=base_revision,base_config=base_config,
            warning="Experimental: metadata checked; this model and tool combination has not passed release validation.")
