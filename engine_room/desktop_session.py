"""Session-owned loopback model access and desktop-driven access pulses."""
from dataclasses import replace
import http.client
import http.server
import os
import secrets
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit
import uuid

from .controller_protocol import MAX_FRAME,PROTOCOL,decode,encode
from .records import Receipt,Store
from .model_request import validate_body


def pending(receipt):
    return receipt.unresolved if receipt.mode=="rental" else receipt.state!="detached"


class ModelStream:
    def __init__(self,client,operation_id,operation_key,*,popen=subprocess.Popen):
        self.client=client; self.operation_id=operation_id; self.operation_key=operation_key
        self.process=popen(client.args(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        self._lock=threading.Lock()

    def connect(self):
        request_id=uuid.uuid4().hex; e=self.client.endpoint
        message=dict(schema=PROTOCOL,request_id=request_id,controller_id=e.controller_id,
            client_host_id=e.client_host_id,method="model_stream",params=dict(operation_id=self.operation_id,operation_key=self.operation_key))
        timer=threading.Timer(30,self.close); timer.daemon=True; timer.start()
        try:
            self.process.stdin.write(encode(message)); self.process.stdin.flush()
            response=decode(self.process.stdout.readline(MAX_FRAME+1))
            if (type(response.get("schema")) is not int or response["schema"]!=PROTOCOL
                    or response.get("request_id")!=request_id or response.get("controller_id")!=e.controller_id
                    or response.get("ok") is not True or response.get("result")!={"stream":True}):
                raise ValueError("Model connection refused")
            return self
        except Exception:
            self.close()
            raise RuntimeError("This session's verified private model connection is unavailable.") from None
        finally: timer.cancel()

    def close(self):
        with self._lock:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=2)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=2)
            for pipe in (self.process.stdin,self.process.stdout):
                try: pipe.close()
                except (OSError,ValueError): pass


class PipeSocket:
    def __init__(self,stream): self.stream=stream
    def makefile(self,*args,**kwargs): return self.stream


class RelayServer(http.server.ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False
    def __init__(self,relay):
        self.relay=relay; self.slots=threading.BoundedSemaphore(8)
        super().__init__(("127.0.0.1",0),RelayHandler)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False): self.shutdown_request(request); return
        try: super().process_request(request,address)
        except Exception: self.slots.release(); raise
    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()
    def handle_error(self,request,address): pass


class RelayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    server_version="EngineRoom"
    sys_version=""
    routes={"GET":{"/v1/models","/health"},"POST":{"/v1/chat/completions","/v1/completions","/v1/embeddings","/v1/responses"}}
    def log_message(self,*args): pass
    def setup(self):
        super().setup(); self.connection.settimeout(15)
        with self.server.relay.lock: self.server.relay.sockets.add(self.connection)
    def finish(self):
        try: super().finish()
        except (OSError,ValueError): pass
        finally:
            with self.server.relay.lock: self.server.relay.sockets.discard(self.connection)
    def error(self,status,message):
        data=(message+"\n").encode()
        self.send_response(status); self.send_header("Content-Type","text/plain; charset=utf-8")
        self.send_header("Content-Length",str(len(data))); self.send_header("Connection","close")
        self.end_headers(); self.wfile.write(data); self.wfile.flush()
        # Half-close before bounded discard: closing with unread request bytes can
        # reset TCP on Windows and erase the useful rejection response.
        try:
            self.connection.shutdown(socket.SHUT_WR)
            deadline=time.monotonic()+0.1; remaining=65536
            while remaining and time.monotonic()<deadline:
                self.connection.settimeout(max(0.001,deadline-time.monotonic()))
                chunk=self.rfile.read1(min(remaining,8192))
                if not chunk: break
                remaining-=len(chunk)
        except (OSError,ValueError): pass
    def do_GET(self): self.proxy()
    def do_POST(self): self.proxy()
    def proxy(self):
        self.close_connection=True; relay=self.server.relay
        host=self.headers.get("Host","")
        if self.headers.get("Origin") is not None or host not in {"127.0.0.1:"+str(relay.port),"localhost:"+str(relay.port)}:
            self.error(403,"Use this session's local coding-tool connection."); return
        auth=self.headers.get_all("Authorization",[])
        if len(auth)!=1 or not secrets.compare_digest(auth[0].encode("utf-8"),("Bearer "+relay.token).encode()):
            self.error(401,"This session's API key is required."); return
        target=urlsplit(self.path)
        if target.scheme or target.netloc or target.query or target.fragment or target.path not in self.routes[self.command]:
            self.error(404,"This model API route is not available through Engine Room."); return
        lengths=self.headers.get_all("Content-Length",[])
        try:
            if self.headers.get("Transfer-Encoding") is not None or len(lengths)>1: raise ValueError()
            length=int(lengths[0]) if lengths and lengths[0].isascii() and lengths[0].isdigit() else (0 if not lengths else -1)
            if length<0 or (self.command=="POST" and not lengths) or (self.command=="GET" and length): raise ValueError()
            if self.command=="POST" and self.headers.get("Content-Type","").partition(";")[0].strip().lower()!="application/json": raise ValueError()
        except ValueError:
            self.error(400,"Send one JSON request with an explicit content length."); return
        if length>64*1024*1024:
            self.error(413,"This request exceeds the local 64 MiB transfer limit."); return
        body=None
        if self.command=="POST" and relay.selected_model is not None:
            try:
                body=self.rfile.read(length)
                if len(body)!=length: raise ValueError()
                validate_body(body,relay.selected_model)
            except (ValueError,UnicodeError,RecursionError):
                self.error(400,"Choose the exact model selected for this connection in a valid JSON request."); return
        stream=None; started=False
        try:
            stream=relay.new_stream(); stream.connect()
            request=(self.command+" "+target.path+" HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nAccept: application/json, text/event-stream\r\nContent-Length: "+str(length)+"\r\n\r\n").encode()
            stream.process.stdin.write(request); stream.process.stdin.flush()
            if body is not None:
                stream.process.stdin.write(body); stream.process.stdin.flush()
            left=length if body is None else 0
            while left:
                chunk=self.rfile.read(min(left,65536))
                if not chunk: raise OSError("Client body ended early")
                stream.process.stdin.write(chunk); stream.process.stdin.flush(); left-=len(chunk)
            response=http.client.HTTPResponse(PipeSocket(stream.process.stdout)); response.begin()
            if not 100<=response.status<=599: raise ValueError("Invalid upstream status")
            self.send_response(response.status)
            for name in ("Content-Type","Content-Length","Cache-Control","Content-Encoding"):
                value=response.getheader(name)
                if value is not None and "\n" not in value and "\r" not in value and not (name=="Content-Length" and response.chunked): self.send_header(name,value)
            self.send_header("Connection","close"); self.end_headers(); started=True
            while True:
                chunk=response.read1(65536)
                if not chunk: break
                self.wfile.write(chunk); self.wfile.flush()
        except Exception:
            if not started:
                try: self.error(503,"This session's private model connection is unavailable. Check Engine Room status.")
                except (OSError,ValueError): pass
        finally:
            if stream is not None: relay.release(stream)


class ModelRelay:
    def __init__(self,client,receipt,*,stream_factory=ModelStream,selected_model=None):
        if selected_model is not None and (not isinstance(selected_model,str) or not selected_model or len(selected_model)>500 or any(ord(c)<32 for c in selected_model)):
            raise ValueError("Choose an explicit served model ID.")
        if receipt.mode=="attachment" and selected_model is None:
            raise ValueError("Existing-machine access requires the explicitly selected model.")
        self.selected_model=selected_model
        self.client=client; self.operation_id=receipt.operation_id; self.operation_key=receipt.operation_key(); self.stream_factory=stream_factory
        self.token=secrets.token_urlsafe(32); self.lock=threading.Lock()
        self.streams=set(); self.sockets=set(); self.closed=False
        self.server=RelayServer(self); self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs=dict(poll_interval=0.1),name="engine-room-model-relay",daemon=True)
        self.thread.start()
    @property
    def url(self): return "http://127.0.0.1:"+str(self.port)+"/v1"
    def new_stream(self):
        with self.lock:
            if self.closed: raise RuntimeError("Model relay is closed")
            stream=self.stream_factory(self.client,self.operation_id,self.operation_key); self.streams.add(stream)
            return stream
    def release(self,stream):
        stream.close()
        with self.lock: self.streams.discard(stream)
    def close(self):
        with self.lock:
            if self.closed: return
            self.closed=True; streams=list(self.streams); sockets=list(self.sockets)
        for connection in sockets:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        failed=False
        for stream in streams:
            try: stream.close()
            except Exception: failed=True
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        if failed: raise RuntimeError("A local model stream did not close cleanly. Rental shutdown still needs controller confirmation.")


class DesktopSession:
    """The UI must pulse touch(); an orphaned helper cannot renew rentals forever."""
    def __init__(self,client,receipt,root,*,relay_factory=ModelRelay,interval=30,ui_timeout=60,clock=time.monotonic,initial_touch=None,record_lock=None,selected_model=None):
        receipt.validate()
        if not pending(receipt) or receipt.cancel_requested or (receipt.mode=="attachment" and receipt.state!="active"):
            raise ValueError("Only an ongoing authorized session can start desktop access.")
        if receipt.mode=="attachment" and (not isinstance(selected_model,str) or not selected_model or len(selected_model)>500 or any(ord(c)<32 for c in selected_model)):
            raise ValueError("Existing-machine access requires the explicitly selected model.")
        if type(interval) not in (int,float) or type(ui_timeout) not in (int,float) or not 0<interval<=30 or not interval<ui_timeout<=60:
            raise ValueError("Use bounded desktop heartbeat and UI-liveness intervals.")
        if client.endpoint.controller_id!=receipt.protection_id:
            raise ValueError("This receipt belongs to another independent controller.")
        touched=clock() if initial_touch is None else initial_touch
        if type(touched) not in (int,float) or not 0<=clock()-touched<ui_timeout:
            raise ValueError("The window is no longer actively confirming this session.")
        self.client=client; self.receipt=receipt; self.store=Store(root)
        if self.store.path(receipt.operation_id).exists():
            old=self.store.load(receipt.operation_id)
            if old.operation_key()!=receipt.operation_key() or old.cancel_requested or not pending(old):
                raise ValueError("Preserve and recover this desktop operation before starting another lease.")
        self.scope=dict(operation_id=receipt.operation_id,operation_key=receipt.operation_key())
        self.clock=clock; self.interval=interval; self.ui_timeout=ui_timeout
        self.lock=record_lock if record_lock is not None else threading.Lock(); self.last_touch=touched; self.stopped=threading.Event()
        self.store.save(receipt)
        self.relay=relay_factory(client,receipt,selected_model=selected_model) if receipt.mode=="attachment" else relay_factory(client,receipt)
        self.thread=threading.Thread(target=self._loop,name="engine-room-desktop-lease",daemon=True); self.thread.start()
    def touch(self):
        if self.stopped.is_set(): raise ValueError("This desktop session has stopped. Read recovery status first.")
        with self.lock: self.last_touch=self.clock()
    def _save(self,data):
        checked=Receipt(**data).validate(); original=self.receipt
        if original.resource_id is not None and checked.resource_id!=original.resource_id:
            raise ValueError("The provider resource changed during this session.")
        for name in ("operation_id","connection_id","connector_id","account_id","mode","created_at","deadline","protection_id","rate_ceiling","rate_unit","quote_key","rate_scope"):
            if getattr(checked,name)!=getattr(original,name): raise ValueError("Controller response differs from this session.")
        with self.lock:
            latest=self.store.load(checked.operation_id)
            if latest.operation_key()!=checked.operation_key() or (latest.resource_id is not None and latest.resource_id!=checked.resource_id):
                raise ValueError("The durable session scope changed.")
            if not pending(latest) and pending(checked):
                self.receipt=latest; return latest
            if self.stopped.is_set(): checked=replace(checked,cancel_requested=True)
            self.store.save(checked); self.receipt=checked
        return checked
    def _loop(self):
        try:
            while not self.stopped.is_set():
                with self.lock: fresh=0<=self.clock()-self.last_touch<self.ui_timeout
                if not fresh: break
                checked=self._save(self.client.call("heartbeat" if self.receipt.mode=="rental" else "attachment_pulse",dict(self.scope)))
                if not pending(checked) or checked.cancel_requested: break
                self.stopped.wait(self.interval)
        except Exception: pass
        finally:
            self.stopped.set()
            try: self.relay.close()
            except Exception: pass
            try:
                with self.lock:
                    self.receipt=replace(self.receipt,cancel_requested=True); self.store.save(self.receipt)
            except Exception: pass
            try:
                self.client.call("cancel" if self.receipt.mode=="rental" else "disconnect_attachment",dict(self.scope))
                status=self.client.call("status",dict(operation_id=self.receipt.operation_id))
                if len(status["records"])==1: self._save(status["records"][0])
            except Exception: pass  # Keep the pending local receipt. Never infer off.
    def close(self):
        self.stopped.set()
        try:
            with self.lock:
                self.receipt=replace(self.receipt,cancel_requested=True); self.store.save(self.receipt)
        finally:
            try: self.relay.close()
            finally: self.thread.join(timeout=2)
        return self.store.load(self.receipt.operation_id)
