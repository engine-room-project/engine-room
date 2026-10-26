"""Bounded Jupyter WebSocket channel using the pinned optional transport package."""
import json
import socket
import ssl
import time
import threading
import re
import math
import base64
from urllib.parse import urlsplit
import uuid

from .kernel import kernel_id
from .proxy import access

MAX_MESSAGE=2*1024*1024


def bounded_websocket(deadline,cancel,clock=time.monotonic):
    # This narrow frame-buffer extension is covered against the exact hash-locked version.
    from importlib.metadata import version
    if version("websocket-client")!="1.9.2":
        raise RuntimeError("Install the pinned optional Colab controller dependencies.")
    import websocket
    from websocket._abnf import frame_buffer
    if websocket.isEnabledForTrace():
        raise RuntimeError("Disable WebSocket tracing before using private runtime access.")
    ws=websocket.WebSocket(enable_multithread=True)
    def receive(size):
        while True:
            if cancel.is_set() or clock()>=deadline or websocket.isEnabledForTrace():
                raise RuntimeError("The runtime channel stopped or expired.")
            ws.settimeout(min(1,max(0.001,deadline-clock())))
            try: return ws._recv(size)
            except websocket.WebSocketTimeoutException: continue
    class BoundedFrames(frame_buffer):
        def recv_length(self):
            super().recv_length()
            if self.length>MAX_MESSAGE:
                raise RuntimeError("The runtime frame exceeds the transfer limit.")
    ws.frame_buffer=BoundedFrames(receive,False)
    return ws


class Channel:
    def __init__(self,ws,deadline,cancel,clock=time.monotonic):
        self.ws=ws; self.deadline=deadline; self.cancel=cancel; self.clock=clock; self._close_lock=threading.Lock()
    def check(self):
        if self.cancel.is_set() or self.clock()>=self.deadline:
            raise RuntimeError("The runtime channel stopped or expired.")
        import websocket
        if websocket.isEnabledForTrace(): raise RuntimeError("Private runtime tracing is not allowed.")
    def send(self,message):
        self.check()
        raw=json.dumps(message,allow_nan=False,separators=(",",":")).encode()
        if len(raw)>MAX_MESSAGE: raise ValueError("The runtime request exceeds the transfer limit.")
        self.ws.send(raw,opcode=1)
    def _message(self,allowed):
        data=bytearray(); started=False
        for _ in range(256):
            self.check(); frame=self.ws.recv_frame(); self.check()
            if frame.mask_value or frame.rsv1 or frame.rsv2 or frame.rsv3:
                raise RuntimeError("The runtime frame is invalid.")
            if frame.opcode==8: raise RuntimeError("The runtime channel closed.")
            if frame.opcode==9:
                self.ws.pong(frame.data); continue
            if frame.opcode==10: continue
            if (frame.opcode not in allowed|{0} or (not started and frame.opcode not in allowed)
                    or (started and frame.opcode!=0)):
                raise RuntimeError("The runtime message framing is invalid.")
            started=True
            if len(data)+len(frame.data)>MAX_MESSAGE:
                raise RuntimeError("The runtime message exceeds the transfer limit.")
            data.extend(frame.data)
            if frame.fin:
                return bytes(data)
        raise RuntimeError("The runtime sent too many incomplete frames.")
    def receive(self):
        result=json.loads(self._message({1}))
        if not isinstance(result,dict): raise ValueError("Invalid runtime message.")
        return result
    def receive_bytes(self): return self._message({1,2})
    def send_bytes(self,data):
        self.check()
        if not isinstance(data,bytes) or len(data)>65536: raise ValueError("Invalid SSH transport chunk.")
        self.ws.send(data,opcode=2)
    def close(self):
        # Only our socket; shutdown also releases a concurrent blocked reader/writer.
        with self._close_lock:
            raw=self.ws.sock; self.ws.sock=None; self.ws.connected=False
            if raw is not None:
                try: raw.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                raw.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def connect(lease,identity,session_id,*,cancel,timeout=60,now=time.time,clock=time.monotonic):
    lease.require_current(now()); kernel_id(identity)
    if not isinstance(session_id,str) or uuid.UUID(session_id).hex!=session_id.replace("-",""):
        raise ValueError("Invalid runtime session identity.")
    if type(timeout) not in (int,float) or not 0<timeout<=300:
        raise ValueError("Use a bounded kernel execution timeout.")
    duration=min(timeout,lease.expires_at-now())
    return _open(lease,"/api/kernels/"+identity+"/channels?session_id="+session_id,
        cancel=cancel,duration=duration,now=now,clock=clock)


def public_key(value):
    if not isinstance(value,str) or not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]+={0,2}",value):
        raise ValueError("Use this operation's Ed25519 SSH public key.")
    raw=base64.b64decode(value.split()[1],validate=True)
    if len(raw)!=51 or raw[:19]!=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
        raise ValueError("The operation's SSH public key is invalid.")
    return value


def connect_ssh(lease,key,deadline,*,cancel,now=time.time,clock=time.monotonic):
    key=public_key(key)
    if type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline-now()<=86400:
        raise ValueError("An ongoing bounded rental is required for SSH transport.")
    # Token must be current at enrollment; an established SSH stream lives until the
    # rental deadline or local closure. No artificial model-generation timeout.
    return _open(lease,"/colab/ssh",cancel=cancel,duration=deadline-now(),now=now,clock=clock,
        headers={"X-Colab-Ssh-Pubkey":key})


def _open(lease,path,*,cancel,duration,now,clock,headers=None):
    lease.require_current(now())
    access(lease.resource_id,dict(url=lease.url,token=lease.token,tokenExpiresInSeconds=1),now())
    deadline=clock()+duration
    ws=bounded_websocket(deadline,cancel,clock)
    channel=Channel(ws,deadline,cancel,clock)
    raw=None
    try:
        channel.check(); host=urlsplit(lease.url).hostname
        raw=socket.create_connection((host,443),timeout=min(15,duration))
        # Explicit connected TLS prevents environment proxy discovery.
        tls=ssl.create_default_context().wrap_socket(raw,server_hostname=host); raw=None
        ws.sock=tls; channel.check(); lease.require_current(now())
        upgrade_deadline=clock()+min(15,duration)
        watchdog=threading.Timer(min(15,duration),channel.close); watchdog.daemon=True; watchdog.start()
        try:
            ws.connect("wss://"+host+path,socket=tls,timeout=min(15,duration),redirect_limit=0,suppress_origin=True,
                header={"X-Colab-Runtime-Proxy-Token":lease.token,"X-Colab-Client-Agent":"colab-cli",**(headers or {})})
        finally: watchdog.cancel()
        if clock()>=upgrade_deadline or ws.sock is None or not ws.connected:
            raise RuntimeError("Runtime upgrade did not finish within its deadline.")
        channel.check(); lease.require_current(now())
        return channel
    except Exception:
        if raw is not None: raw.close()
        channel.close()
        raise RuntimeError("The verified Colab runtime channel is unavailable. Check rental recovery before retrying setup.") from None
