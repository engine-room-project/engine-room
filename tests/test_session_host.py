from unittest.mock import patch,Mock
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest

from engine_room.records import Store
from engine_room.session_host import Host
from test_records import rental


class SyntheticRental:
    def __init__(self,root):
        self.receipts=Store(root); self.receipt=None; self.session=None; self.entered=threading.Event()
        self.release=threading.Event(); self.stopped=threading.Event(); self.refreshed=threading.Event(); self.touches=0; self.stops=0
    def begin(self,request,*,confirmed,ui_touch,is_closed):
        self.entered.set()
        if not self.release.wait(3): raise TimeoutError("Synthetic submission barrier")
        if is_closed(): raise ValueError("Synthetic UI closed")
        self.start_touch=ui_touch()
        self.receipt=replace(rental(),protection_id="controller")
        self.receipts.save(self.receipt); self.session=types.SimpleNamespace(stopped=threading.Event())
        return self.receipt
    def touch(self): self.touches+=1
    def view(self): return dict(phase="starting",ready=False)
    def refresh(self,operation): self.refreshed.set(); return self.receipt
    def stop(self):
        self.stops+=1; self.stopped.set()
        if self.session: self.session.stopped.set()
        return None


class PipeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        read_fd,write_fd=os.pipe(); self.source=os.fdopen(read_fd,"rb"); self.writer=os.fdopen(write_fd,"wb",buffering=0)
        self.addCleanup(self.source.close); self.addCleanup(self.writer.close)
        self.rental=SyntheticRental(self.temp.name); self.output=io.BytesIO(); self.clock=0
        self.host=Host(self.rental,self.source,self.output,clock=lambda:self.clock)
        self.failures=[]
        def run():
            try: self.host.run()
            except Exception as error: self.failures.append(error)
        self.thread=threading.Thread(target=run); self.thread.start()
        self.addCleanup(self.finish)
    def finish(self):
        self.rental.release.set(); self.writer.close(); self.thread.join(timeout=4)
        self.assertFalse(self.thread.is_alive()); self.assertEqual([],self.failures)
    def write(self,value): self.writer.write(json.dumps(value).encode()+b"\n")
    def begin(self):
        self.write(dict(action="begin",request={},confirmed=True)); self.assertTrue(self.rental.entered.wait(2))
    def events(self): return [json.loads(line) for line in self.output.getvalue().splitlines()]
    def test_eof_is_processed_while_submission_is_blocked(self):
        self.begin(); self.writer.close()
        self.assertTrue(self.rental.stopped.wait(2)); self.assertTrue(self.thread.is_alive())
        self.rental.release.set(); self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive()); self.assertEqual(1,self.rental.stops)
        self.assertTrue(all(not item.get("shutdown_confirmed") for item in self.events()))
    def test_pulses_continue_during_slow_submission_and_stop_is_scoped_once(self):
        self.begin(); self.clock=59; self.write(dict(action="pulse"))
        # A bounded event synchronizes receipt of the pulse, without treating a file as process state.
        until=threading.Event()
        original=self.host.input.on_pulse
        self.host.input.on_pulse=lambda:(original(),until.set())
        self.clock=61; self.write(dict(action="pulse")); self.assertTrue(until.wait(2))
        self.rental.release.set(); self.assertTrue(self.rental.refreshed.wait(2)); self.assertEqual(61,self.rental.start_touch)
        self.write(dict(action="pulse")); self.write(dict(action="stop")); self.thread.join(timeout=4)
        self.assertFalse(self.thread.is_alive()); self.assertEqual(1,self.rental.stops)
        self.assertTrue(any(item["event"]=="snapshot" for item in self.events()))
    def test_unconfirmed_or_malformed_frames_cannot_begin_and_never_echo_input(self):
        self.writer.write(b'{"action":"begin","confirmed":false,"request":{"secret":"synthetic-secret"}}\n')
        self.thread.join(timeout=3); self.assertFalse(self.thread.is_alive()); self.assertFalse(self.rental.entered.is_set())
        self.assertNotIn(b"synthetic-secret",self.output.getvalue()); self.assertFalse(self.events()[0]["shutdown_confirmed"])


    def test_slow_tool_handoff_does_not_block_pulses_or_stop_detection(self):
        entered=threading.Event(); released=threading.Event(); pulse=threading.Event()
        self.addCleanup(released.set)
        def opening(command):
            entered.set()
            if not released.wait(3): raise TimeoutError("Synthetic tool barrier")
            return dict(event="tool_result",request_id=command["request_id"],opened=True)
        tool=Mock(); tool.open.side_effect=opening
        command=dict(action="tool_launch",request_id="c"*32,tool="codex",executable="synthetic.exe",working_directory="synthetic-folder",desktop_idle=False,confirmed=True)
        with patch("engine_room.session_host.SessionTools",return_value=tool):
            self.begin(); self.write(command)
            self.rental.release.set(); self.assertTrue(entered.wait(2))
            original=self.host.input.on_pulse
            self.host.input.on_pulse=lambda:(original(),pulse.set())
            self.write(dict(action="pulse")); self.assertTrue(pulse.wait(2))
            self.write(dict(action="stop")); self.assertTrue(self.rental.stopped.wait(2))
            released.set(); self.thread.join(timeout=4)
        self.assertFalse(self.thread.is_alive()); self.assertEqual(1,tool.open.call_count)

    def test_explicit_attachment_mode_uses_only_attachment_lifecycle(self):
        attachment=SyntheticRental(Path(self.temp.name)/"attachment"); attachment.tool_plan=dict(id="chosen",context=8192)
        original=attachment.begin
        def begin(*args,**kwargs):
            receipt=original(*args,**kwargs)
            attachment.receipt=replace(receipt,mode="attachment",deadline=None,state="active",resource_id="existing")
            attachment.receipts.save(attachment.receipt)
            return attachment.receipt
        attachment.begin=begin; self.host.attachment=attachment
        self.write(dict(action="begin",mode="attachment",request={},confirmed=True))
        self.assertTrue(attachment.entered.wait(2)); attachment.release.set()
        self.assertTrue(attachment.refreshed.wait(2)); self.assertFalse(self.rental.entered.is_set())
        self.write(dict(action="stop")); self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive()); self.assertEqual(1,attachment.stops)
        self.assertTrue(all(not item.get("shutdown_confirmed") for item in self.events()))


class ActualHostTests(unittest.TestCase):
    def test_missing_controller_fails_closed_in_isolated_process(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            code="import sys; sys.path.insert(0,sys.argv[1]); from engine_room.session_host import main; raise SystemExit(main())"
            result=subprocess.run([sys.executable,"-I","-c",code,str(root)],input=b'{"action":"begin","request":{},"confirmed":true}\n',
                capture_output=True,timeout=15,env={**os.environ,"ENGINE_ROOM_DATA_DIR":folder})
        self.assertEqual(1,result.returncode); self.assertEqual(b"",result.stderr)
        self.assertFalse(json.loads(result.stdout)["shutdown_confirmed"])
        self.assertNotIn(b"Users",result.stdout)
