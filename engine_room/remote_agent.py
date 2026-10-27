"""Loopback-only remote status and model supervisor. No account credentials or raw logs."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request



def model_identity(model_id,opener=None):
    opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/v1/models",timeout=3) as response:
        data=json.loads(response.read(1024*1024))
    ids={item.get("id") for item in data.get("data",[]) if isinstance(item,dict)}
    return {"engine-room",model_id}.issubset(ids)


def progress(root):
    # Only this runtime's dedicated storage. Do not expose model filenames or log lines.
    folder=Path(os.environ.get("ENGINE_ROOM_WEIGHTS",str(root/"weights")))
    try:
        active=json.loads((root/"model-storage.json").read_text(encoding="utf-8"))
        folder=Path(active["path"])
    except (OSError,ValueError,TypeError,KeyError): pass
    size=0; modified=0
    if folder.is_dir():
        for directory,dirs,files in os.walk(folder,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
            for name in files:
                path=Path(directory)/name
                try:
                    if path.is_symlink(): continue
                    item=path.stat(); size+=item.st_size; modified=max(modified,item.st_mtime_ns)
                except OSError: pass
    return str(size)+":"+str(modified)


def status(root,process,settings,identity=model_identity):
    if process.poll() is not None:
        return {"status":"failed","phase":"The model process stopped. Check model access, storage and GPU compatibility.","sampled_at":time.time(),"progress":"stopped"}
    try: ready=identity(settings["id"])
    except Exception: ready=False
    return {"status":"ready" if ready else "starting","phase":"Model ready" if ready else "Downloading or loading the model",
            "sampled_at":time.time(),"progress":progress(root)}


def child_environment(root):
    environment=os.environ.copy()
    # Hub auth can come from OIDC, legacy env, token files or Colab secrets. Never
    # let an image/account's ambient Hub settings select credentials for this child.
    for name in tuple(environment):
        if name.startswith(("HF_","HUGGING_FACE_","HUGGINGFACE_")):
            environment.pop(name)
    auth=Path(tempfile.mkdtemp(prefix=".hub-auth-",dir=root))
    environment["HF_HOME"]=str(auth)
    environment["HF_TOKEN_PATH"]=str(auth/"token")
    environment["HF_HUB_DISABLE_TELEMETRY"]="1"
    environment["HF_HUB_DISABLE_IMPLICIT_TOKEN"]="1"
    environment["HF_ENDPOINT"]="https://huggingface.co"
    if (root/"llama-path").is_file():
        environment["LLAMA_SERVER"]=(root/"llama-path").read_text().strip()
        environment["LD_LIBRARY_PATH"]=(root/"llama-libraries").read_text().strip()
    secret=root/".hfkey"
    if secret.exists():
        if secret.is_symlink() or secret.stat().st_mode&0o077 or secret.stat().st_size>16384:
            raise ValueError("The model credential file is not private.")
        token=secret.read_text().strip()
        if not token: raise ValueError("The selected model credential is empty.")
        environment["HF_TOKEN"]=token
        environment["HF_HUB_DISABLE_IMPLICIT_TOKEN"]="0"
        secret.unlink()
    return environment


def start_model(root):
    environment=child_environment(root)
    try:
        return subprocess.Popen([sys.executable,"-m","engine_room.model_server"],cwd=root,env=environment,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    finally:
        environment.pop("HF_TOKEN",None)


def main():
    if os.name!="posix":
        raise ValueError("The remote model supervisor requires Linux.")
    root=Path(os.environ["ENGINE_ROOM_ROOT"])
    if not root.is_absolute() or not (root/"runtime-ready").is_file():
        raise ValueError("The pinned runtime is not ready.")
    import fcntl
    with open(root/"agent.lock","a+b") as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 0
        settings=json.loads((root/"model.json").read_text(encoding="utf-8"))
        process=start_model(root)
        class Feed(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path!="/": self.send_error(404); return
                body=json.dumps(status(root,process,settings),allow_nan=False).encode()
                self.send_response(200); self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self,*args): pass
        try:
            http.server.ThreadingHTTPServer(("127.0.0.1",8001),Feed).serve_forever()
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    return 0


if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception: print("Model supervision failed. Check the runtime setup and credential file.",file=sys.stderr); raise SystemExit(1)
