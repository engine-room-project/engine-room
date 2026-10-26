"""Fixed SSH-only model start after verified native installation; secrets use stdin."""
import base64
import hashlib
import io
import json
import shlex
import tarfile
import time

from engine_room.payload import source_payload
from .bootstrap import ROOT


def start_code(receipt,plan):
    receipt.validate()
    if (receipt.mode!="rental" or receipt.connector_id!="colab" or not receipt.resource_id
            or not receipt.protection_id or receipt.state not in {"allocating","active"} or receipt.cancel_requested):
        raise ValueError("An ongoing protected owned Colab rental is required for model start.")
    payload=source_payload(plan,native=True)
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload["base64"])),mode="r:gz") as archive:
        hashes={member.name:hashlib.sha256(archive.extractfile(member).read()).hexdigest() for member in archive.getmembers()}
    root="/content/engine-room-"+receipt.operation_key()[:32]
    return f"""import hashlib,json,os,pathlib,subprocess,sys,time
r=pathlib.Path({root!r})
if not r.is_dir() or r.resolve()!=r.absolute() or r.stat().st_mode&0o077: raise ValueError('Invalid private runtime root')
owner=r/'.engine-room-owner.json'
if owner.is_symlink() or not owner.is_file() or owner.stat().st_size>8192: raise ValueError('Invalid runtime ownership proof')
p=json.loads(owner.read_text())
if any(p.get(k)!=v for k,v in {{'schema':1,'operation_key':{receipt.operation_key()!r},'source_sha256':{payload['sha256']!r},'state':'staged'}}.items()): raise ValueError('Owned runtime proof changed')
for name,digest in {hashes!r}.items():
    f=r/name
    if f.is_symlink() or f.resolve()!=f.absolute() or not f.is_file() or f.stat().st_size>4194304 or hashlib.sha256(f.read_bytes()).hexdigest()!=digest: raise ValueError('Owned runtime source changed')
if time.time()>={receipt.deadline!r}: raise ValueError('Protected rental deadline expired')
ready=r/'runtime-ready'
python=r/'venv/bin/python'
if ready.is_symlink() or not ready.is_file() or ready.stat().st_size>32 or ready.read_text().strip()!='installed' or not python.is_file(): raise ValueError('Native installation is not confirmed')
home=r/'home'
if home.is_symlink() or not home.is_dir() or home.stat().st_mode&0o077: raise ValueError('Invalid private runtime home')
if (r/'model-start.json').exists() or (r/'model-start.json').is_symlink(): raise ValueError('Model start was already attempted')
secret=sys.stdin.buffer.read(16385)
if len(secret)>16384 or any(c<33 or c>126 for c in secret): raise ValueError('Invalid explicit model credential')
if secret:
    fd=os.open(r/'.hfkey',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as out: out.write(secret); out.flush(); os.fsync(out.fileno())
elif (r/'.hfkey').exists() or (r/'.hfkey').is_symlink(): raise ValueError('Unexpected existing credential state')
secret=b''
with (r/'model-start.json').open('x') as out:
    out.write(json.dumps({{'operation_key':{receipt.operation_key()!r},'resource_id':{receipt.resource_id!r},'state':'submitted'}})); out.flush(); os.fsync(out.fileno())
os.chmod(r/'model-start.json',0o600)
d=os.open(r,os.O_RDONLY)
try: os.fsync(d)
finally: os.close(d)
if time.time()>={receipt.deadline!r}: raise ValueError('Protected rental deadline expired')
env={{'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HOME':str(r/'home'),'LC_ALL':'C','ENGINE_ROOM_ROOT':str(r),'PYTHONPATH':str(r),'HF_HUB_DISABLE_TELEMETRY':'1'}}
process=subprocess.Popen([str(python),'-m','engine_room.remote_agent'],cwd=r,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
print('MODEL_START_SUBMITTED')
"""


def start_model(ssh,connection,receipt,plan,credentials,*,authorize,cancel,now=time.time):
    code=start_code(receipt,plan)
    if ssh.receipt.operation_key()!=receipt.operation_key() or ssh.receipt.resource_id!=receipt.resource_id:
        raise ValueError("The SSH connection belongs to another rental.")
    if cancel.is_set() or now()>=receipt.deadline: raise ValueError("Model start was cancelled or expired.")
    authorize()
    reference=connection.settings.get("hf_credential_ref")
    secret=credentials.read(reference).encode() if reference else b""
    try:
        if len(secret)>16384 or any(c<33 or c>126 for c in secret): raise ValueError("The explicit model credential is invalid.")
        if cancel.is_set() or now()>=receipt.deadline: raise ValueError("Model start was cancelled or expired.")
        authorize()
        command=shlex.join(['/usr/bin/python3','-I','-c',code])
        if ssh.run(command,data=secret,timeout=30)!=b'MODEL_START_SUBMITTED\n':
            raise RuntimeError("Model start was not confirmed. Recover the rental without repeating setup.")
    finally: secret=b""
