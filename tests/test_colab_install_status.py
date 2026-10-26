from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock,patch

from engine_room.payload import ROOT,source_payload
from engine_room_connectors._colab.bootstrap import status_code,install_status,wait_installed
import test_colab_bootstrap as staging_fixture
from test_colab_probe import plan
from test_records import rental


class InstallerObservationTests(unittest.TestCase):
    stage=staging_fixture.StagingTests.stage
    def setUp(self):
        staging_fixture.StagingTests.setUp(self); self.stage()
        spec=importlib.util.spec_from_file_location("owned_install_status",ROOT/"remote/install_status.py")
        self.observer=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.observer)
        (self.root/'install-start.json').write_text(json.dumps(dict(source_sha256=self.payload['sha256'],state='submitted')))
        self.process=Mock(); self.process.poll.return_value=None
        self.handle=dict(operation_key=self.key,root=str(self.root),source_sha256=self.payload['sha256'],process=self.process)
    def status(self,handle=None): return self.observer.collect(str(self.root),self.key,self.payload['sha256'],self.handle if handle is None else handle)
    def installed_files(self):
        (self.root/'runtime-ready').write_text('installed\n')
        python=self.root/'venv/bin/python'; python.parent.mkdir(parents=True); python.write_text('synthetic interpreter')
        (self.root/'python-path').write_text(str(python))
        llama=self.root/'llama/llama-server'; llama.parent.mkdir(); llama.write_text('synthetic binary'); llama.chmod(0o700)
        (self.root/'llama-path').write_text(str(llama))
    def test_marker_cannot_override_live_or_failed_owned_process(self):
        self.installed_files()
        self.assertEqual('installing',self.status()['state'])
        self.process.poll.return_value=1
        self.assertEqual(dict(state='failed',progress='installer-exited'),self.status())
        self.process.poll.return_value=0
        self.assertEqual(dict(state='installed',progress='dependencies-installed'),self.status())
    def test_actual_owned_child_exit_overrides_markers_without_pid_lookup(self):
        self.installed_files()
        for code,state in (("pass","installed"),("raise SystemExit(7)","failed")):
            process=subprocess.Popen([sys.executable,"-I","-c",code],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                process.wait(timeout=10)
                self.assertEqual(state,self.status({**self.handle,"process":process})["state"])
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)

    def test_missing_or_mismatched_process_authority_remains_unknown(self):
        self.installed_files(); self.process.poll.return_value=0
        for changed in ({},{**self.handle,'operation_key':'b'*64},{**self.handle,'process':None}):
            self.assertEqual('unknown',self.status(changed)['state'])
        self.assertEqual('unknown',self.observer.collect(str(self.root),'b'*64,self.payload['sha256'],self.handle)['state'])
    def test_phase_failure_is_prompt_and_raw_logs_never_leave_probe(self):
        (self.root/'phase').write_text('Installing hash-verified GGUF runtime')
        (self.root/'install.log').write_text('synthetic private exception')
        self.assertEqual('native-gguf-artifacts:27',self.status()['progress'])
        self.assertNotIn('private',json.dumps(self.status()))
        (self.root/'phase').write_text('Setup failed')
        self.assertEqual('failed',self.status()['state'])
        (self.root/'phase').write_text('synthetic private arbitrary phase')
        self.assertNotIn('private',json.dumps(self.status()))
    def test_zero_exit_with_external_or_missing_runtime_paths_is_not_installed(self):
        self.installed_files(); self.process.poll.return_value=0
        (self.root/'llama-path').write_text(str(self.base/'unrelated'))
        self.assertEqual('failed',self.status()['state'])
        (self.root/'runtime-ready').write_text('not installed')
        self.assertEqual('failed',self.status()['state'])
    def test_generated_owned_kernel_status_uses_process_object_without_pid_search(self):
        receipt=replace(rental(),connector_id='colab',resource_id='owned',state='active',protection_id='proof')
        self.key=receipt.operation_key()
        # Generate a second exact owned stage for this scope.
        self.root=self.base/('engine-room-'+self.key[:32]); self.stage(); self.installed_files()
        (self.root/'install-start.json').write_text(json.dumps(dict(source_sha256=self.payload['sha256'],state='submitted')))
        production='/content/engine-room-'+self.key[:32]
        launched=dict(root=production,source_sha256=self.payload['sha256'],state='installing')
        code=status_code(receipt,plan(),launched).replace(repr(production),repr(str(self.root)))
        prefix=f"import types; _engine_room_installer={{'operation_key':{self.key!r},'root':{str(self.root)!r},'source_sha256':{self.payload['sha256']!r},'process':types.SimpleNamespace(poll=lambda:0)}}; "
        result=subprocess.run([sys.executable,'-I','-'],input=prefix+code,capture_output=True,text=True,timeout=20)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual('installed',json.loads(result.stdout)['state'])


class InstallerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.receipt=replace(rental(),connector_id='colab',resource_id='owned',state='active',protection_id='proof',created_at=999,deadline=2000)
        self.installing=dict(root='/content/engine-room-'+self.receipt.operation_key()[:32],source_sha256=source_payload(plan())['sha256'],state='installing')
        self.session=Mock(); self.cancel=threading.Event(); self.authorize=Mock()
    def status(self):
        return install_status(self.session,'connection',self.receipt,plan(),self.installing,authorize=self.authorize,cancel=self.cancel)
    def wait(self):
        return wait_installed(self.session,'connection',self.receipt,plan(),self.installing,authorize=self.authorize,cancel=self.cancel,now=lambda:1000)
    def test_unknown_or_arbitrary_status_is_never_ready(self):
        for value in (dict(state='ready',progress='model-ready'),dict(state='installed',progress='synthetic private log'),
                dict(state='installing',progress='private\nexception')):
            self.session.execute.return_value=json.dumps(value)
            with self.assertRaises(ValueError): self.status()
    def test_wait_accepts_only_confirmed_installed_and_refuses_known_failure(self):
        self.session.execute.return_value=json.dumps(dict(state='installed',progress='dependencies-installed'))
        self.assertEqual('installed',self.wait()['state'])
        for state,progress in (('failed','installer-exited'),('unknown','installer-proof-unavailable')):
            self.session.execute.return_value=json.dumps(dict(state=state,progress=progress))
            with self.assertRaises(RuntimeError): self.wait()
    def test_cancellation_during_status_cannot_advance_to_installed(self):
        def stopped(*args,**kwargs):
            self.cancel.set()
            return json.dumps(dict(state="installed",progress="dependencies-installed"))
        self.session.execute.side_effect=stopped
        with self.assertRaisesRegex(RuntimeError,"cancelled or expired"): self.wait()

    def test_cancelled_or_expired_wait_starts_no_kernel_request(self):
        self.cancel.set()
        with self.assertRaises(RuntimeError): self.wait()
        self.session.execute.assert_not_called(); self.cancel.clear()
        self.receipt=replace(self.receipt,deadline=1000)
        with self.assertRaises(RuntimeError): self.wait()
        self.session.execute.assert_not_called()
