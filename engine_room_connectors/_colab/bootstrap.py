"""Owned Colab source staging after actual capacity checks; no engine starts here."""
import json
import base64
import hashlib
import io
import tarfile
import re
from pathlib import Path

from engine_room.payload import FILES,payload_files,source_payload
from .probe import code as probe_code,inspect_runtime

ROOT=Path(__file__).resolve().parents[2]


def staging_code(receipt,plan,base="/content"):
    receipt.validate()
    if receipt.mode!="rental" or receipt.connector_id!="colab" or not receipt.resource_id:
        raise ValueError("An owned Colab rental is required for staging.")
    probe_code(base)  # Apply the same explicit-root grammar as the inventory step.
    payload=source_payload(plan,native=True)
    source=(ROOT/"remote/stage.py").read_text(encoding="utf-8")
    key=receipt.operation_key()
    snippet=f"_er_stage={{'__name__':'engine_room_stage'}}; exec({source!r},_er_stage); print(_er_stage['json'].dumps(_er_stage['stage']({base!r},{key!r},{payload['base64']!r},{payload['sha256']!r},{payload_files(plan,native=True)!r}),sort_keys=True)); del _er_stage"
    if len(snippet.encode())>262144: raise ValueError("The inspected runtime source exceeds the kernel transfer limit.")
    return snippet,payload


def staging_steps(receipt,plan,base="/content"):
    receipt.validate(); probe_code(base)
    if receipt.mode!="rental" or receipt.connector_id!="colab" or not receipt.resource_id:
        raise ValueError("An owned Colab rental is required for staging.")
    payload=source_payload(plan,native=True)
    expected=dict(root=base.rstrip("/")+"/engine-room-"+receipt.operation_key()[:32],source_sha256=payload["sha256"],state="staged")
    if len(payload["base64"])<180000:
        snippet,_=staging_code(receipt,plan,base)
        return [(snippet,expected)],payload
    encoded=payload["base64"]; key=receipt.operation_key(); digest=payload["sha256"]; total=len(encoded)
    if total>1024*1024: raise ValueError("The native runtime archive exceeds its transfer cap.")
    scope=dict(operation_key=key,source_sha256=digest,total=total)
    def ack(offset): return dict(state="receiving",operation_key=key,source_sha256=digest,offset=offset)
    steps=[(f"import json\nif '_engine_room_upload' in globals(): raise ValueError('An upload already exists; recover without replay')\n_engine_room_upload={scope!r} | {{'data':''}}\nprint(json.dumps({ack(0)!r}))",ack(0))]
    guard=f"if not isinstance(globals().get('_engine_room_upload'),dict) or set(_engine_room_upload)!={{'operation_key','source_sha256','total','data'}} or any(_engine_room_upload.get(k)!=v for k,v in {scope!r}.items()) or not isinstance(_engine_room_upload['data'],str): raise ValueError('Upload scope changed')\n"
    for offset in range(0,total,65536):
        chunk=encoded[offset:offset+65536]; end=offset+len(chunk)
        snippet="import hashlib,json\n"+guard+f"if len(_engine_room_upload['data'])!={offset} or {end}>{total}: raise ValueError('Upload offset changed')\n_er_chunk={chunk!r}\nif len(_er_chunk)>65536 or hashlib.sha256(_er_chunk.encode('ascii')).hexdigest()!={hashlib.sha256(chunk.encode()).hexdigest()!r}: raise ValueError('Upload chunk changed')\n_engine_room_upload['data']+=_er_chunk\ndel _er_chunk\nprint(json.dumps({ack(end)!r}))"
        steps.append((snippet,ack(end)))
    source=(ROOT/"remote/stage.py").read_text(encoding="utf-8")
    finish="import json\n"+guard+f"if len(_engine_room_upload['data'])!={total}: raise ValueError('Upload is incomplete')\n_er_stage={{'__name__':'engine_room_stage'}}; exec({source!r},_er_stage)\nprint(json.dumps(_er_stage['stage']({base!r},{key!r},_engine_room_upload['data'],{digest!r},{payload_files(plan,native=True)!r}),sort_keys=True))\ndel _engine_room_upload,_er_stage"
    steps.append((finish,expected))
    if any(len(code.encode())>262144 for code,_ in steps): raise ValueError("The runtime transfer code exceeds its cap.")
    return steps,payload


def stage_runtime(session,connection,receipt,plan,accelerator,*,authorize,cancel,base="/content"):
    inventory=inspect_runtime(session,connection,receipt,plan,accelerator,authorize=authorize,cancel=cancel,root=base)
    steps,payload=staging_steps(receipt,plan,base)
    for snippet,expected in steps:
        if cancel.is_set(): raise ValueError("Runtime source upload was stopped.")
        result=session.execute(connection,receipt,snippet,authorize=authorize,cancel=cancel,timeout=60)
        try:
            if json.loads(result)!=expected: raise ValueError()
        except (ValueError,TypeError):
            raise ValueError("Owned source staging was not confirmed. Recover the rental before retrying setup.") from None
    return {**expected,"capacity":inventory["capacity"]}


def install_code(receipt,plan,staged):
    receipt.validate()
    if receipt.mode!="rental" or receipt.connector_id!="colab" or not receipt.resource_id:
        raise ValueError("An owned Colab rental is required for installation.")
    payload=source_payload(plan,native=True)
    root="/content/engine-room-"+receipt.operation_key()[:32]
    if not isinstance(staged,dict) or any(staged.get(k)!=v for k,v in dict(root=root,source_sha256=payload["sha256"],state="staged").items()):
        raise ValueError("The original owned source staging confirmation is required.")
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload["base64"])),mode="r:gz") as archive:
        hashes={member.name:hashlib.sha256(archive.extractfile(member).read()).hexdigest() for member in archive.getmembers()}
    # Source, digest and scope are non-secret. Never embed model/account credentials here.
    return f"""import hashlib,json,os,pathlib,subprocess,time
_er_root=pathlib.Path({root!r})
if not _er_root.is_dir() or _er_root.resolve()!=_er_root.absolute(): raise ValueError('Invalid owned source directory')
_er_proof=json.loads((_er_root/'.engine-room-owner.json').read_text())
if any(_er_proof.get(k)!=v for k,v in {{'schema':1,'operation_key':{receipt.operation_key()!r},'source_sha256':{payload['sha256']!r},'state':'staged'}}.items()): raise ValueError('Owned source proof changed')
for _er_name,_er_hash in {hashes!r}.items():
    _er_file=_er_root/_er_name
    if _er_file.is_symlink() or not _er_file.is_file() or _er_file.stat().st_size>4194304 or hashlib.sha256(_er_file.read_bytes()).hexdigest()!=_er_hash: raise ValueError('Owned source changed before installation')
_er_limit=min(2700,int({receipt.deadline!r}-time.time()))
if _er_limit<=0: raise ValueError('The protected rental setup deadline expired')
_er_marker=_er_root/'install-start.json'
with _er_marker.open('x',encoding='utf-8') as _er_out:
    _er_out.write(json.dumps({{'source_sha256':{payload['sha256']!r},'state':'submitted','deadline':{receipt.deadline!r}}})); _er_out.flush(); os.fsync(_er_out.fileno())
if os.name!='nt':
    _er_dir=os.open(_er_root,os.O_RDONLY)
    try: os.fsync(_er_dir)
    finally: os.close(_er_dir)
_er_home=_er_root/'home'; _er_home.mkdir(mode=0o700)
_er_env={{'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HOME':str(_er_home),'LC_ALL':'C','ENGINE_ROOM_ROOT':str(_er_root)}}
with (_er_root/'install.log').open('xb') as _er_log:
    os.chmod(_er_root/'install.log',0o600)
    _er_process=subprocess.Popen(['/usr/bin/timeout','--signal=TERM','--kill-after=10s',str(_er_limit),'/bin/bash',str(_er_root/'remote/install-colab.sh'),str(_er_root)],cwd=_er_root,env=_er_env,stdin=subprocess.DEVNULL,stdout=_er_log,stderr=subprocess.STDOUT,start_new_session=True)
_engine_room_installer={{'operation_key':{receipt.operation_key()!r},'root':str(_er_root),'source_sha256':{payload['sha256']!r},'process':_er_process}}
print(json.dumps({{'root':str(_er_root),'source_sha256':{payload['sha256']!r},'state':'installing'}}))
"""


def start_install(session,connection,receipt,plan,staged,*,authorize,cancel):
    snippet=install_code(receipt,plan,staged)
    raw=session.execute(connection,receipt,snippet,authorize=authorize,cancel=cancel,timeout=60)
    expected=dict(root=staged["root"],source_sha256=staged["source_sha256"],state="installing")
    try:
        if json.loads(raw)!=expected: raise ValueError()
    except (ValueError,TypeError):
        raise ValueError("Installer launch was not confirmed. Recover the rental without repeating setup.") from None
    return expected


def status_code(receipt,plan,installing):
    receipt.validate()
    if receipt.mode!="rental" or receipt.connector_id!="colab" or not receipt.resource_id:
        raise ValueError("An owned Colab rental is required for installer status.")
    payload=source_payload(plan,native=True)
    root="/content/engine-room-"+receipt.operation_key()[:32]
    expected=dict(root=root,source_sha256=payload["sha256"],state="installing")
    if not isinstance(installing,dict) or any(installing.get(k)!=v for k,v in expected.items()):
        raise ValueError("The original installer launch confirmation is required.")
    source=(ROOT/"remote/install_status.py").read_text(encoding="utf-8")
    return f"_er_status={{'__name__':'engine_room_install_status'}}; exec({source!r},_er_status); print(_er_status['json'].dumps(_er_status['collect']({root!r},{receipt.operation_key()!r},{payload['sha256']!r},globals().get('_engine_room_installer')),sort_keys=True)); del _er_status"


def install_status(session,connection,receipt,plan,installing,*,authorize,cancel):
    raw=session.execute(connection,receipt,status_code(receipt,plan,installing),authorize=authorize,cancel=cancel,timeout=30)
    try:
        data=json.loads(raw)
        if (not isinstance(data,dict) or set(data)!={"state","progress"}
                or data["state"] not in {"installing","installed","failed","unknown"}
                or not isinstance(data["progress"],str) or len(data["progress"])>100): raise ValueError()
        fixed={"installed":{"dependencies-installed"},"unknown":{"installer-proof-unavailable"},
            "failed":{"installer-exited","installer-failed","installer-incomplete","installer-python-missing","installer-runtime-missing"}}
        if data["state"]=="installing":
            if not re.fullmatch(r"native-(?:system-packages|model-python|gguf-artifacts|vllm-packages|vllm-verification|dependencies-installed|unrecognized|starting):[0-9]{1,20}",data["progress"]): raise ValueError()
        elif data["progress"] not in fixed[data["state"]]: raise ValueError()
    except (ValueError,TypeError):
        raise ValueError("The owned installer status could not be verified.") from None
    return data


def wait_installed(session,connection,receipt,plan,installing,*,authorize,cancel,now):
    while now()<receipt.deadline and not cancel.is_set():
        status=install_status(session,connection,receipt,plan,installing,authorize=authorize,cancel=cancel)
        if cancel.is_set() or now()>=receipt.deadline: break
        if status["state"]=="installed": return status
        if status["state"] in {"failed","unknown"}:
            raise RuntimeError("The owned native installer failed or lost its process proof. Recover the rental.")
        cancel.wait(2)
    raise RuntimeError("Native setup was cancelled or expired. Provider shutdown still needs confirmation.")
