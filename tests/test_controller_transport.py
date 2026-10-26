from dataclasses import asdict,replace
import base64
import json
from pathlib import Path
import socket
import shutil
import stat
import subprocess
import os
import time
import sys
import tempfile
import threading
import warnings
import getpass
import unittest
from unittest.mock import Mock,patch

from engine_room.controller_client import Client,Endpoint
from engine_room.controller_protocol import Dispatcher,MAX_FRAME,decode,encode
from engine_room.controller_service import LocalServer,local_call,private_root
from engine_room.connectors import Registry
from engine_room.lifecycle import Controller
from engine_room.protection import Enrollment
from test_lifecycle import Clock,Provider


def envelope(method,params=None):
    return dict(schema=1,request_id="c"*32,controller_id="independent-controller",client_host_id="b"*64,method=method,params=params or {})


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.clock=Clock(); self.provider=Provider(self.clock)
        self.registry=Registry(); self.registry.register(self.provider)
        self.enrollment=Enrollment("independent-controller","a"*64,"b"*64,True)
        self.controller=Controller(self.temp.name,self.registry,self.enrollment,actual_host_id="a"*64,now=self.clock,monotonic=self.clock,interval=60)
        self.provider.store=self.controller.store
        self.controller.start(); self.dispatcher=Dispatcher(self.controller)
        self.connection=self.controller.connections.add("Synthetic connection","test","explicit-credential")
        self.selection={"gpu":"synthetic","disk_gb":1000}
        self.plan=dict(id="example/model",revision="a"*40,context=8192,engine="vLLM",dtype="float16",fileSizes={"model.safetensors":10**9},weightBytes=10**9,overheadBytes=10**9,kvBytesPerToken=1024)
    def tearDown(self):
        self.provider.allocation_release.set(); self.provider.setup_release.set()
        for worker in self.controller._workers.values(): worker.join(timeout=2)
        self.controller.close(); self.temp.cleanup()
    def call(self,method,params=None):
        if method in {"heartbeat","cancel","model_stream"} and isinstance(params,dict):
            params={**params,"operation_key":self.controller.store.load(params["operation_id"]).operation_key()}
        return self.dispatcher.dispatch(envelope(method,params))
    def request_params(self):
        quote=self.call("quote",dict(connection_id=self.connection.id,selection=self.selection))["result"]
        return dict(operation_id="operation1",connection_id=self.connection.id,selection=self.selection,
            plan=self.plan,approved_quote=quote,rate_ceiling=2,duration_seconds=600)
    def test_round_trip_request_retry_and_cancel_keep_provider_confirmation(self):
        params=self.request_params()
        self.assertTrue(self.call("request",params)["ok"])
        self.controller._workers["operation1"].join(timeout=2)
        self.assertTrue(self.call("request",params)["ok"]); self.assertEqual(1,self.provider.allocations)
        self.assertEqual("active",self.call("status",dict(operation_id="operation1"))["result"]["records"][0]["state"])
        self.provider.keep_after_delete=True
        response=self.call("cancel",dict(operation_id="operation1"))
        self.assertTrue(response["ok"]); self.assertEqual("unresolved",response["result"][0]["state"])
        self.assertNotEqual("off",self.controller.store.load("operation1").state)
    def test_wrong_host_or_controller_refused_before_provider_calls(self):
        for change in (dict(controller_id="other"),dict(client_host_id="a"*64)):
            message={**envelope("request",self.request_params()),**change}
            self.assertFalse(self.dispatcher.dispatch(message)["ok"])
        self.assertEqual(0,self.provider.allocations)
    def test_arbitrary_commands_and_credential_fields_are_not_rpc_operations(self):
        for method,params in (("credential",dict(value="synthetic-token")),("exec",dict(command="synthetic")),("info",dict(credential="synthetic-token"))):
            response=self.call(method,params)
            self.assertFalse(response["ok"]); self.assertNotIn("synthetic-token",str(response))
    def test_wrong_receipt_scope_cannot_renew_cancel_or_open_an_operation(self):
        self.call("request",self.request_params()); self.controller._workers["operation1"].join(timeout=2)
        before=self.controller.store.load("operation1")
        for method in ("heartbeat","cancel","model_stream"):
            response=self.dispatcher.dispatch(envelope(method,dict(operation_id="operation1",operation_key="0"*64)))
            self.assertFalse(response["ok"])
        self.assertEqual(before,self.controller.store.load("operation1")); self.assertEqual([],self.provider.deletions)

    def test_scoped_session_readiness_is_fresh_and_does_not_renew_lease(self):
        self.assertTrue(self.call("request",self.request_params())["ok"])
        self.controller._workers["operation1"].join(timeout=2)
        before=self.controller.store.load("operation1")
        scope=dict(operation_id=before.operation_id,operation_key=before.operation_key())
        self.controller.tick()
        result=self.call("session_status",scope)
        self.assertTrue(result["ok"]); self.assertTrue(result["result"]["ready"])
        self.assertEqual("ready",result["result"]["phase"])
        self.clock.advance(31)
        stale=self.call("session_status",scope)["result"]
        self.assertFalse(stale["ready"]); self.assertEqual("unresolved",stale["phase"])
        self.assertEqual(before.lease_expires_at,self.controller.store.load("operation1").lease_expires_at)
        self.assertFalse(self.call("session_status",scope|dict(operation_key="0"*64))["ok"])
        self.clock.advance(90); self.controller.tick()
        self.assertEqual("off",self.call("session_status",scope)["result"]["phase"])
    def test_provider_error_is_not_returned_to_client(self):
        self.provider.quote=Mock(side_effect=ValueError("synthetic-private-token"))
        response=self.call("quote",dict(connection_id=self.connection.id,selection=self.selection))
        self.assertFalse(response["ok"]); self.assertNotIn("synthetic-private-token",str(response))
    def test_status_does_not_renew_lease_and_expiry_still_stops(self):
        self.call("request",self.request_params()); self.controller._workers["operation1"].join(timeout=2)
        self.clock.advance(121)
        self.call("status")
        self.controller.tick()
        self.assertEqual("off",self.controller.store.load("operation1").state)
    def test_history_is_bounded_and_all_receipts_remain_accessible(self):
        from test_records import rental
        for index in range(23): self.controller.store.save(replace(rental(),operation_id="synthetic"+str(index),state="cancelled"))
        seen=set(); cursor=""
        for _ in range(3):
            response=self.call("status",dict(after=cursor,limit=10))["result"]
            self.assertLessEqual(len(response["records"]),10)
            for record in response["records"]:
                self.assertNotIn(record["operation_id"],seen); seen.add(record["operation_id"])
            cursor=response["next_cursor"]
        self.assertEqual(23,len(seen)); self.assertIsNone(cursor)
    def test_wire_limits_duplicates_and_nonfinite_numbers_are_refused(self):
        for raw in (b'{"x":1,"x":2}\n',b'{"x":NaN}\n',b'{}',b'{}\n{}\n',b'x'*(MAX_FRAME+1)):
            with self.assertRaises(ValueError): decode(raw)
        with self.assertRaises(ValueError): encode(dict(large="x"*MAX_FRAME))
        self.assertEqual(envelope("info"),decode(encode(envelope("info"))))


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.key=Path(self.temp.name)/"synthetic-identity"; self.key.write_text("synthetic fixture, not a key")
        public=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"+bytes(32)
        self.endpoint=Endpoint("100.64.0.10",22,"engine_room","ssh-ed25519 "+base64.b64encode(public).decode(),str(self.key),"independent-controller","a"*64,"b"*64,True)
    def test_pinned_isolated_command_uses_only_explicit_identity(self):
        runner=Mock()
        def respond(args,**kwargs):
            message=decode(kwargs["input"])
            return subprocess.CompletedProcess(args,0,encode(dict(schema=1,request_id=message["request_id"],controller_id="independent-controller",ok=True,result=dict(controller_host_id="a"*64,client_host_id="b"*64))))
        runner.side_effect=respond
        client=Client(Path(self.temp.name)/"client",self.endpoint,runner=runner,actual_host_id="b"*64)
        client.call("info")
        args=runner.call_args.args[0]
        self.assertEqual("none",args[args.index("-F")+1]); self.assertIn("StrictHostKeyChecking=yes",args)
        self.assertIn("IdentityAgent=none",args); self.assertIn("ClearAllForwardings=yes",args)
        self.assertEqual("engine-room-controller-rpc",args[-1])
        self.assertIn(str(self.key),args); self.assertNotIn("accept-new",str(args))
    @unittest.skipUnless(shutil.which("ssh"),"OpenSSH offline parser")
    def test_real_openssh_parser_accepts_pinned_config_with_spaces(self):
        client=Client(Path(self.temp.name)/"state with spaces",self.endpoint,actual_host_id="b"*64)
        args=client.args(); args.insert(1,"-G")
        parsed=subprocess.run(args,capture_output=True,timeout=10)
        self.assertEqual(0,parsed.returncode)
        output=parsed.stdout.decode()
        self.assertIn("identityagent none",output)
        self.assertIn("clearallforwardings yes",output)
        self.assertIn(client.known.resolve().as_posix(),output.replace("\\","/"))
    def test_public_loopback_and_invalid_ssh_targets_are_refused(self):
        for change in (dict(address="8.8.8.8"),dict(address="127.0.0.1"),dict(address="example.invalid"),dict(username="root; command"),dict(host_key="ssh-ed25519 invalid")):
            with self.assertRaises(ValueError): replace(self.endpoint,**change).validate()
    def test_other_desktop_or_response_enrollment_is_refused(self):
        with self.assertRaises(ValueError): Client(self.temp.name,self.endpoint,actual_host_id="c"*64)
        def respond(args,**kwargs):
            request=decode(kwargs["input"])
            return subprocess.CompletedProcess(args,0,encode(dict(schema=1,request_id=request["request_id"],controller_id="independent-controller",ok=True,result=dict(controller_host_id="c"*64,client_host_id="b"*64))))
        client=Client(self.temp.name,self.endpoint,runner=respond,actual_host_id="b"*64)
        with self.assertRaises(RuntimeError): client.call("info")
    def test_ambiguous_ssh_failure_is_not_automatically_retried_or_reported_off(self):
        runner=Mock(side_effect=subprocess.TimeoutExpired("ssh",180))
        client=Client(self.temp.name,self.endpoint,runner=runner,actual_host_id="b"*64)
        with self.assertRaisesRegex(RuntimeError,"shutdown is not confirmed"): client.call("request",dict(operation_id="operation1"))
        self.assertEqual(1,runner.call_count)
    def test_credential_prompt_refuses_noninteractive_or_echo_fallback(self):
        from engine_room.controller_service import prompt_credential
        with patch("engine_room.controller_service.sys.stdin.isatty",return_value=False):
            with self.assertRaises(ValueError): prompt_credential()
        def insecure(*args):
            warnings.warn("Synthetic echo fallback",getpass.GetPassWarning)
            return "synthetic-token"
        with patch("engine_room.controller_service.sys.stdin.isatty",return_value=True),patch("engine_room.controller_service.getpass.getpass",side_effect=insecure):
            with self.assertRaises(getpass.GetPassWarning): prompt_credential()

    def test_configuration_round_trip_does_not_store_private_key_contents(self):
        client=Client(Path(self.temp.name)/"state",self.endpoint,actual_host_id="b"*64); client.save()
        saved=(client.directory/"controller.json").read_text()
        self.assertNotIn("synthetic fixture",saved)
        restored=Client.read(client.directory,actual_host_id="b"*64)
        self.assertEqual(self.endpoint,restored.endpoint)


@unittest.skipUnless(sys.platform.startswith("linux"),"Linux owner-only Unix socket boundary")
class SocketTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.clock=Clock(); self.provider=Provider(self.clock)
        registry=Registry(); registry.register(self.provider)
        self.controller=Controller(self.temp.name,registry,Enrollment("independent-controller","a"*64,"b"*64,True),actual_host_id="a"*64,now=self.clock,monotonic=self.clock,interval=60)
        self.provider.store=self.controller.store; self.controller.start()
        self.server=LocalServer(self.temp.name,Dispatcher(self.controller))
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs=dict(poll_interval=0.05)); self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.thread.join(timeout=2); self.server.server_close(); self.controller.close(); self.temp.cleanup()
    def test_real_local_socket_is_owner_only_and_serves_bounded_rpc(self):
        self.assertEqual(0o600,stat.S_IMODE(self.server.path.stat().st_mode))
        self.assertTrue(local_call(self.temp.name,envelope("info"))["result"]["protection_healthy"])
    def test_malformed_client_cannot_stop_daemon_or_monitor(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(2); client.connect(str(self.server.path)); client.sendall(b'{"bad":NaN}\n')
            self.assertEqual(b"",client.recv(1))
        self.assertTrue(local_call(self.temp.name,envelope("info"))["ok"])
        self.assertTrue(self.controller._monitor.is_alive())
    def test_shared_state_directory_is_refused(self):
        root=Path(self.temp.name)/"shared"; root.mkdir(); root.chmod(0o755)
        with self.assertRaisesRegex(ValueError,"owner-only"): private_root(root)


@unittest.skipUnless(sys.platform.startswith("linux"),"Linux daemon subprocess")
class DaemonTests(unittest.TestCase):
    def start(self,root):
        environment={**os.environ,"ENGINE_ROOM_DATA_DIR":root}
        child=subprocess.Popen([sys.executable,"-m","engine_room.controller_service","serve","--root",root],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        until=time.monotonic()+10
        while time.monotonic()<until:
            if child.poll() is not None: self.fail("Controller daemon exited during startup")
            try:
                response=local_call(root,envelope("info"),timeout=1)
                if response["ok"]: return child
            except (OSError,ValueError): pass
            time.sleep(0.02)
        child.terminate()
        try: child.wait(timeout=5)
        except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=3)
        self.fail("Controller socket did not become ready within ten seconds")
    def test_actual_daemon_cancels_unsubmitted_intent_and_restarts_after_crash(self):
        from engine_room.protection import host_identity
        from engine_room.records import Store,atomic_json
        from test_records import rental
        with tempfile.TemporaryDirectory() as root:
            actual=host_identity()
            enrollment=Enrollment("independent-controller",actual,"b"*64,True)
            atomic_json(Path(root)/"enrollment.json",asdict(enrollment))
            store=Store(Path(root)/"receipts")
            store.save(replace(rental(),created_at=time.time(),deadline=time.time()+600))
            process=None
            try:
                process=self.start(root)
                self.assertEqual("cancelled",store.load("op1").state)
                second=subprocess.run([sys.executable,"-m","engine_room.controller_service","serve","--root",root],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
                self.assertEqual(1,second.returncode)
                self.assertTrue(local_call(root,envelope("info"))["ok"])
                process.kill(); process.wait(timeout=5)
                self.assertTrue((Path(root)/"controller.sock").exists())
                process=self.start(root)
                self.assertTrue(local_call(root,envelope("info"))["result"]["protection_healthy"])
                process.terminate(); self.assertEqual(0,process.wait(timeout=5))
                self.assertFalse((Path(root)/"controller.sock").exists())
            finally:
                if process is not None and process.poll() is None:
                    process.kill(); process.wait(timeout=5)

    def test_stop_with_unresolved_allocation_fails_without_claiming_shutdown(self):
        from engine_room.protection import host_identity
        from engine_room.records import Store,atomic_json
        from test_records import rental
        with tempfile.TemporaryDirectory() as root:
            atomic_json(Path(root)/"enrollment.json",asdict(Enrollment("independent-controller",host_identity(),"b"*64,True)))
            store=Store(Path(root)/"receipts")
            store.save(replace(rental(),created_at=time.time(),deadline=time.time()+600,state="allocating",allocation_submitted=True,protection_id="controller"))
            process=self.start(root)
            try:
                self.assertEqual("unresolved",store.load("op1").state)
                process.terminate(); self.assertEqual(1,process.wait(timeout=5))
                self.assertEqual("unresolved",store.load("op1").state)
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)

    def test_deployment_wrapper_executes_with_lf_shebang_and_quoted_home(self):
        with tempfile.TemporaryDirectory(prefix="controller home ") as home:
            home=Path(home)
            package=home/"engine-room"/"engine_room"; package.mkdir(parents=True)
            (package/"__init__.py").write_text("")
            (package/"controller_service.py").write_text("import json,sys\nfrom pathlib import Path\nPath('wrapper-called.json').write_text(json.dumps(sys.argv[1:]))\n")
            wrapper=home/"engine-room-controller-rpc"
            wrapper.write_bytes(Path("controller/engine-room-controller-rpc.sh").read_bytes()); wrapper.chmod(0o700)
            result=subprocess.run([str(wrapper)],env={**os.environ,"HOME":str(home)},capture_output=True,timeout=5)
            self.assertEqual(0,result.returncode)
            self.assertEqual(["rpc","--root",str(home/".local/share/engine-room-controller")],json.loads((home/"engine-room/wrapper-called.json").read_text()))
