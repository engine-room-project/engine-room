"""Parent-owned attachment helper control; only explicit UI pulses keep access alive."""
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time

from .controller_protocol import decode,encode
from .private_endpoint import ModelEndpoint


class ForwardClient:
    def __init__(self,root,receipt,*,popen=subprocess.Popen):
        receipt.validate()
        if receipt.mode!="attachment" or receipt.state!="active" or receipt.cancel_requested:
            raise ValueError("An active existing-machine attachment is required.")
        if not sys.platform.startswith("linux"): raise ValueError("Attachment control requires Linux.")
        self.root=Path(root).absolute(); self.receipt=receipt; self.popen=popen
        self.process=None; self.endpoint=None; self.pending=b""; self.lock=threading.RLock(); self.closed=False; self.disconnect_confirmed=False
    def read(self,seconds):
        until=time.monotonic()+seconds
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout,selectors.EVENT_READ)
            while b"\n" not in self.pending:
                remaining=until-time.monotonic()
                if remaining<=0 or not selector.select(max(0,remaining)): raise TimeoutError("Attachment response expired.")
                chunk=os.read(self.process.stdout.fileno(),4097)
                if not chunk: raise ValueError("Attachment helper ended without confirmation.")
                self.pending+=chunk
                if len(self.pending)>8192: raise ValueError("Oversized attachment response.")
        frame,self.pending=self.pending.split(b"\n",1)
        if len(frame)>4095: raise ValueError("Oversized attachment frame.")
        return decode(frame+b"\n")
    def start(self):
        with self.lock:
            if self.process is not None or self.closed: raise ValueError("This attachment helper cannot be replayed.")
            code="import sys;sys.path.insert(0,sys.argv[1]);from engine_room.attachment_forward import main;raise SystemExit(main(sys.argv[2]))"
            command=[sys.executable,"-I","-c",code,str(Path(__file__).resolve().parents[1]),str(self.root)]
            self.process=self.popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0,close_fds=True)
            try:
                self.process.stdin.write(encode(dict(operation_id=self.receipt.operation_id,operation_key=self.receipt.operation_key())))
                ready=self.read(30)
                if ready.get("event")=="closed" and ready.get("disconnected") is True and ready.get("shutdown_confirmed") is False:
                    self.disconnect_confirmed=True
                if set(ready)!={"event","endpoint","shutdown_confirmed"} or ready["event"]!="ready" or ready["shutdown_confirmed"] is not False:
                    raise ValueError("Attachment readiness was not confirmed.")
                forward_root=self.root/"s"/self.receipt.operation_key()[:16]
                endpoint=ModelEndpoint.read(ready["endpoint"],forward_root,self.receipt.operation_key())
                if endpoint.resource_id!=self.receipt.resource_id: raise ValueError("Attachment resource changed.")
                with endpoint.connect(forward_root,self.receipt.operation_key(),timeout=1): pass
                os.set_blocking(self.process.stdin.fileno(),False)
                self.endpoint=endpoint; return endpoint
            except Exception:
                self.close(); raise ValueError("The original private attachment could not be confirmed.") from None
    def pulse(self):
        with self.lock:
            if self.closed or self.process is None or self.process.poll() is not None: raise ValueError("The attachment is no longer connected.")
            try:
                if os.write(self.process.stdin.fileno(),b"pulse\n")!=6: raise OSError("Incomplete pulse")
            except OSError:
                self.close(); raise ValueError("Attachment renewal failed; reconnect explicitly.") from None
    def close(self):
        with self.lock:
            if self.closed: return self.disconnect_confirmed
            self.closed=True; process=self.process; self.endpoint=None; confirmed=self.disconnect_confirmed
            if process is None: return False
            try:
                if process.poll() is None:
                    try: os.write(process.stdin.fileno(),b"stop\n")
                    except OSError: pass
                process.stdin.close()
                response=self.read(5)
                confirmed=(response.get("event")=="closed" and response.get("disconnected") is True and response.get("shutdown_confirmed") is False)
            except Exception: pass
            finally:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3); confirmed=False
                for stream in (process.stdin,process.stdout):
                    try: stream.close()
                    except (OSError,ValueError): pass
            self.disconnect_confirmed=confirmed
            return confirmed
