"""Persistent bounded UI pipe; actual pulses and EOF remain visible during RPC."""
from dataclasses import asdict
from pathlib import Path
import queue
import sys
import threading
import time

from .controller_client import Client
from .controller_protocol import MAX_FRAME,decode,encode,fields
from .desktop_rental import Rental
from .desktop_attachment import Attachment
from .desktop_session import pending
from .paths import state_root
from .session_tools import SessionTools,request as tool_request


class Input:
    def __init__(self,stream,*,clock=time.monotonic):
        self.stream=stream; self.clock=clock; self.touched=clock(); self.closed=threading.Event(); self.ready=threading.Event()
        self.first=None; self.on_pulse=lambda:None; self.on_close=lambda:None; self.on_command=lambda value:None
    def inactive(self): return self.closed.is_set() or not 0<=self.clock()-self.touched<60
    def read(self):
        try:
            while not self.closed.is_set():
                raw=self.stream.readline(MAX_FRAME+1)
                if not raw: break
                value=decode(raw)
                if self.first is None:
                    fields(value,("action","request","confirmed"),("mode",))
                    if value["action"]!="begin" or value["confirmed"] is not True or value.get("mode","rental") not in {"rental","attachment"}: raise ValueError("Unconfirmed session")
                    self.first=value; self.touched=self.clock(); self.ready.set()
                elif value=={"action":"pulse"}:
                    self.touched=self.clock(); self.on_pulse()
                elif value=={"action":"stop"}: break
                elif value.get("action")=="tool_launch": self.on_command(tool_request(value))
                else: raise ValueError("Unsupported session frame")
        except Exception: pass
        finally:
            self.closed.set(); self.ready.set(); self.on_close()


class Host:
    def __init__(self,rental,source,destination,*,clock=time.monotonic,attachment=None):
        self.rental=rental; self.attachment=attachment; self.input=Input(source,clock=clock); self.destination=destination; self.clock=clock
        self.stop_started=threading.Event(); self.stop_thread=None; self.stop_result=None; self.view=None; self.commands=queue.Queue(maxsize=4); self.stop_guard=threading.Lock()
        self.input.on_pulse=self.pulse; self.input.on_close=self.stop; self.input.on_command=self.commands.put_nowait
    def send(self,value):
        self.destination.write(encode(value)); self.destination.flush()
    def pulse(self):
        try:
            if self.rental.session is not None: self.rental.touch()
        except Exception: self.input.closed.set(); self.stop()
    def stop(self):
        with self.stop_guard:
            if self.stop_started.is_set(): return
            self.stop_started.set()
            session=self.rental.session
            if session is not None: session.stopped.set()  # Stop renewal before potentially slow recovery RPC.
            def cleanup():
                try: self.stop_result=self.rental.stop()
                except Exception: pass  # Durable intent/receipt remains; no off assertion.
            self.stop_thread=threading.Thread(target=cleanup,name="engine-room-pipe-stop",daemon=True); self.stop_thread.start()
    def snapshot(self):
        receipt=self.rental.receipt
        if receipt is None:
            if isinstance(self.stop_result,dict) and self.stop_result.get("state")=="cancelled-before-submission":
                return dict(event="cancelled",state="cancelled-before-submission",shutdown_confirmed=False)
            return dict(event="pending",shutdown_confirmed=False)
        current=self.rental.receipts.load(receipt.operation_id)
        return dict(event="snapshot",receipt=asdict(current),shutdown_confirmed=current.state=="off",view=self.view)
    def run(self):
        reader=threading.Thread(target=self.input.read,name="engine-room-ui-input",daemon=True); reader.start()
        try:
            if not self.input.ready.wait(60) or self.input.first is None or self.input.inactive(): raise ValueError("No live confirmed UI")
            first=self.input.first
            if first.get("mode","rental")=="attachment":
                if self.attachment is None: raise ValueError("Attachment access is unavailable.")
                self.rental=self.attachment
            receipt=self.rental.begin(first["request"],confirmed=first["confirmed"],ui_touch=lambda:self.input.touched,is_closed=self.input.inactive)
            tools=SessionTools(self.rental,self.rental.tool_plan if first.get("mode","rental")=="attachment" else first["request"].get("plan",{}),self.input.inactive)
            self.send(self.snapshot())
            while not self.input.inactive():
                session=self.rental.session
                if session is None or session.stopped.is_set(): break
                try:
                    self.view=None
                    self.rental.refresh(receipt.operation_id)
                    self.view=self.rental.view()
                    self.send(self.snapshot())
                except Exception: self.send(dict(event="uncertain",shutdown_confirmed=False))
                for _ in range(4):
                    try: command=self.commands.get_nowait()
                    except queue.Empty: break
                    try: self.send(tools.open(command))
                    except Exception:
                        self.send(dict(event="tool_result",request_id=command["request_id"],opened=False,
                            message="The tool could not be opened. Check readiness, executable and project folder; existing settings were preserved."))
                if self.rental.receipt is not None and not pending(self.rental.receipt): break
                self.input.closed.wait(3)
            return 0
        except Exception:
            try: self.send(dict(event="error",message="The session could not be confirmed. Preserve recovery records; shutdown is not confirmed.",shutdown_confirmed=False))
            except Exception: pass
            return 1
        finally:
            self.input.closed.set(); self.stop()
            if self.stop_thread is not None: self.stop_thread.join(timeout=2)
            try: self.send(self.snapshot())
            except Exception: pass


def main():
    try:
        root=state_root()/"desktop"
        client=Client.read(root)
        rental=Rental(client,root/"rentals"); attachment=Attachment(client,root/"attachments")
        return Host(rental,sys.stdin.buffer,sys.stdout.buffer,attachment=attachment).run()
    except Exception:
        sys.stdout.buffer.write(encode(dict(event="error",message="The saved controller is unavailable. Preserve recovery records; shutdown is not confirmed.",shutdown_confirmed=False)))
        sys.stdout.buffer.flush(); return 1


if __name__=="__main__": raise SystemExit(main())
