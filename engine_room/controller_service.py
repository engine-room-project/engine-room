"""Linux owner-only controller daemon and forced-command SSH stdio bridge."""
import argparse
from dataclasses import asdict
import getpass
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import stat
import struct
import sys
import threading
import warnings

from .controller_protocol import MAX_FRAME,Dispatcher,decode,encode
from .credentials import Credentials
from .protection import Enrollment,host_identity
from .records import atomic_json
from .private_endpoint import ModelEndpoint


def private_root(root):
    root=Path(root).absolute()
    if root.is_symlink(): raise ValueError("Controller state cannot be a directory link.")
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=root.stat()
    if not sys.platform.startswith("linux") or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ValueError("Use an owner-only controller state directory on Linux.")
    return root


def socket_path(root):
    path=private_root(root)/"controller.sock"
    if len(os.fsencode(path))>100: raise ValueError("Choose a shorter private controller state path.")
    return path


def local_call(root,message,timeout=180):
    path=socket_path(root)
    info=path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ValueError("Controller socket is not private to this account.")
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout); connection.connect(str(path)); connection.sendall(encode(message))
        with connection.makefile("rb") as reader: raw=reader.readline(MAX_FRAME+1)
    return decode(raw)


class LocalServer(getattr(socketserver,"ThreadingUnixStreamServer",object)):
    # The fallback permits imports on Windows; private_root rejects runtime use there.
    daemon_threads=True
    block_on_close=False
    request_queue_size=8
    def __init__(self,root,dispatcher):
        self.path=socket_path(root); self.dispatcher=dispatcher
        if (dispatcher.controller._ownership is None
                or Path(root).resolve()!=dispatcher.controller.connections.root.resolve()):
            raise ValueError("The running controller must own this state directory before binding its socket.")
        self.slots=threading.BoundedSemaphore(8)
        if self.path.exists():
            info=self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():
                raise ValueError("Refusing to replace unrelated controller socket state.")
            # Controller.start owns the process lock before this server is constructed.
            self.path.unlink()
        super().__init__(str(self.path),Handler)
        self.path.chmod(0o600)
    def verify_request(self,request,address):
        try:
            _,uid,_=struct.unpack("3i",request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            return uid==os.getuid()
        except OSError: return False
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request,address)
        except Exception:
            self.slots.release(); raise
    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()
    def handle_error(self,request,address):
        # Never log requests, provider exceptions or credential-bearing tracebacks.
        pass
    def server_close(self):
        super().server_close()
        self.path.unlink(missing_ok=True)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            message=decode(self.rfile.readline(MAX_FRAME+1))
            response=self.server.dispatcher.dispatch(message)
            self.wfile.write(encode(response)); self.wfile.flush()
        except Exception:
            # Broken input/clients cannot affect the independent monitor.
            return


def serve(root):
    from .connectors import Registry
    from .lifecycle import Controller
    root=private_root(root)
    os.environ["ENGINE_ROOM_DATA_DIR"]=str(root)
    enrollment=Enrollment.read(root/"enrollment.json")
    controller=Controller(root,Registry().discover(),enrollment)
    server=None
    stop=threading.Event()
    def requested(signum,frame): stop.set()
    signal.signal(signal.SIGTERM,requested); signal.signal(signal.SIGINT,requested)
    try:
        controller.start()
        server=LocalServer(root,Dispatcher(controller))
        server.timeout=0.5
        while not stop.is_set(): server.handle_request()
    finally:
        if server: server.server_close()
        controller.close()
        if controller.store.blockers() or controller.attachments.pending():
            raise RuntimeError("Controller stopped with unresolved recovery records; local disconnection or rental shutdown is not confirmed.")


def bridge(root):
    # A forced SSH key may invoke exactly this command; no shell, arbitrary paths,
    # credential writes or remote process execution is exposed by the protocol.
    if os.environ.get("SSH_ORIGINAL_COMMAND") not in (None,"engine-room-controller-rpc"):
        raise ValueError("This SSH key is restricted to Engine Room controller requests.")
    raw=sys.stdin.buffer.readline(MAX_FRAME+1)
    message=decode(raw)
    response=local_call(root,message)
    if message.get("method")!="model_stream" or not response.get("ok"):
        sys.stdout.buffer.write(encode(response)); sys.stdout.buffer.flush()
        return
    # The scoped descriptor comes only from the active, freshly healthy session.
    endpoint=ModelEndpoint.read(response["result"]["endpoint"],root,message["params"]["operation_key"])
    from .streaming import duplex
    scope=response["result"]
    def authorized():
        try:
            fresh=local_call(root,message,timeout=10)
            return fresh.get("ok") is True and fresh.get("result")==scope
        except Exception: return False
    response["result"]={"stream":True}
    sys.stdout.buffer.write(encode(response)); sys.stdout.buffer.flush()
    request=None
    if "selected_model" in scope:
        from .model_request import guarded_request
        request=guarded_request(sys.stdin.fileno(),scope["selected_model"],authorized)
    with endpoint.connect(root,message["params"]["operation_key"],timeout=8) as peer:
        duplex(peer,sys.stdin.fileno(),sys.stdout.fileno(),authorized,request=request)



def prompt_credential():
    if not sys.stdin.isatty():
        raise ValueError("Enter credentials directly in an interactive controller terminal.")
    with warnings.catch_warnings():
        warnings.simplefilter("error",getpass.GetPassWarning)
        return getpass.getpass("Credential (hidden): ")


def main():
    parser=argparse.ArgumentParser(description="Private Engine Room controller; deployment requires explicit owner approval.")
    parser.add_argument("command",choices=("serve","rpc","credential","enroll","identity"))
    parser.add_argument("--root",required=True)
    parser.add_argument("--reference"); parser.add_argument("--replace",action="store_true")
    parser.add_argument("--controller-id"); parser.add_argument("--client-host-id")
    parser.add_argument("--confirm-independent-host",action="store_true")
    args=parser.parse_args()
    try:
        root=private_root(args.root)
        if args.command=="identity": print(host_identity())
        elif args.command=="credential":
            if not args.reference: raise ValueError("Choose a credential reference.")
            Credentials(root/"credentials").save(args.reference,prompt_credential(),overwrite=args.replace)
            print("Saved on this host for the current account.")
        elif args.command=="enroll":
            enrollment=Enrollment(args.controller_id,host_identity(),args.client_host_id,args.confirm_independent_host)
            enrollment.verify(host_identity(),args.client_host_id)
            if (root/"enrollment.json").exists(): raise ValueError("Enrollment exists. Preserve recovery state and review a host change explicitly.")
            atomic_json(root/"enrollment.json",asdict(enrollment)); print("Enrollment saved. Live independent-host validation is still required.")
        elif args.command=="serve": serve(root)
        else: bridge(root)
    except Exception:
        print("Controller command failed. Check explicit enrollment, owner-only permissions, prerequisites and recovery records. No shutdown is confirmed by this error.",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__": sys.exit(main())
