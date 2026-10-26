from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from engine_room.connections import Connection
from engine_room.records import Store
from engine_room_connectors._colab.runtime import Runtime
from test_colab_probe import plan
from test_colab_model_start import receipt


@unittest.skipUnless(sys.platform.startswith("linux"),"Native Colab orchestration requires the Linux controller")
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.r=replace(receipt(),lease_expires_at=190); self.receipts=Store(self.root/"receipts"); self.receipts.save(self.r)
        self.connection=Connection(self.r.connection_id,"colab",self.r.account_id,"Example","explicit-ref",{})
        self.credentials=Mock(); self.api=Mock(); self.kernel=Mock(); self.ssh=Mock(); self.ssh.receipt=self.r; self.ssh.tunnel=None
        self.factory=Mock(return_value=self.ssh); self.metadata=Mock(); self.cancel=threading.Event()
        self.runtime=Runtime(self.root/"runtime",self.credentials,self.api,self.receipts,forward_root=self.root/"s",
            metadata=self.metadata,kernel=self.kernel,ssh_factory=self.factory,now=lambda:100)
        self.selection={"accelerator":"A100","engine":"llama.cpp"}
        self.runtime.prepare(self.connection,self.r,self.selection,plan())
    def setup(self): return self.runtime.setup(self.connection,self.r,plan(),self.cancel)
    def mocks(self):
        return patch.multiple("engine_room_connectors._colab.runtime",stage_runtime=Mock(return_value={"stage":"owned"}),
            start_install=Mock(return_value={"install":"owned"}),install_status=Mock(return_value={"state":"installed","progress":"dependencies-installed"}),start_model=Mock())
    def test_ordered_setup_checks_original_authority_and_uses_fresh_lease(self):
        order=[]; self.kernel.start.side_effect=lambda *a,**k:order.append("kernel")
        self.ssh.enroll.side_effect=lambda **k:order.append("enroll")
        self.ssh.forward.side_effect=lambda *a:order.append("forward")
        with self.mocks():
            import engine_room_connectors._colab.runtime as module
            module.stage_runtime.side_effect=lambda *a,**k:order.append("stage") or {"stage":"owned"}
            module.start_install.side_effect=lambda *a,**k:order.append("install") or {"install":"owned"}
            module.start_model.side_effect=lambda *a,**k:order.append("model")
            self.setup()
        self.assertEqual(["kernel","stage","install","enroll","model","forward"],order)
        args=self.factory.call_args.args; args[2](); self.api.runtime_access.assert_called_once_with(self.connection,self.r)
        self.assertEqual("forwarding",self.runtime.read(self.r)["state"])
    def test_durable_setup_intent_refuses_replay_after_uncertain_kernel(self):
        self.kernel.start.side_effect=TimeoutError("synthetic uncertain response")
        with self.assertRaises(TimeoutError): self.setup()
        with self.assertRaises(ValueError): self.setup()
        self.assertEqual(1,self.kernel.start.call_count); self.factory.assert_not_called()
    def test_cancel_between_stage_and_install_never_installs(self):
        with self.mocks():
            import engine_room_connectors._colab.runtime as module
            module.stage_runtime.side_effect=lambda *a,**k:self.cancel.set() or {"stage":"owned"}
            with self.assertRaises(ValueError): self.setup()
            module.start_install.assert_not_called(); module.start_model.assert_not_called()
    def test_changed_resource_cancel_and_expired_lease_refuse(self):
        self.runtime.now=lambda:101
        for changes in ({"resource_id":"unrelated"},{"cancel_requested":True},{"lease_expires_at":101},{"state":"stopping"}):
            self.receipts.save(replace(self.r,**changes))
            with self.assertRaises(ValueError): self.runtime.authority(self.connection,self.r,self.cancel)
        self.kernel.start.assert_not_called()
    def test_failed_or_uncertain_installer_never_reads_credentials_or_enrolls(self):
        with self.mocks():
            import engine_room_connectors._colab.runtime as module
            module.install_status.return_value={"state":"unknown","progress":"installer-proof-unavailable"}
            with self.assertRaises(RuntimeError): self.setup()
            module.start_model.assert_not_called(); self.factory.assert_not_called(); self.credentials.read.assert_not_called()
    def test_cancel_after_model_submission_never_starts_forward(self):
        with self.mocks():
            import engine_room_connectors._colab.runtime as module
            module.start_model.side_effect=lambda *a,**k:self.cancel.set()
            with self.assertRaises(ValueError): self.setup()
        self.ssh.forward.assert_not_called(); self.runtime.close(self.r); self.ssh.close.assert_called_once_with(self.r)
    def test_preparation_rejects_unknown_engine_before_metadata_or_new_state(self):
        self.metadata.reset_mock()
        with self.assertRaises(ValueError): self.runtime.prepare(self.connection,replace(self.r,operation_id="other"),
            {"accelerator":"A100","engine":"unsupported"},plan()|{"engine":"unsupported"})
        self.metadata.verify.assert_not_called(); self.assertFalse((self.root/"runtime/other").exists())
    def test_preparation_accepts_pinned_native_vllm_without_allocating_or_installing(self):
        from test_colab_upload import native_plan
        other=replace(self.r,operation_id="native-other")
        self.runtime.prepare(self.connection,other,{"accelerator":"A100","engine":"vLLM"},native_plan())
        self.assertEqual("prepared",self.runtime.read(other)["state"])
        self.kernel.start.assert_not_called(); self.api.runtime_access.assert_not_called()

    def test_status_reads_cached_progress_without_using_busy_kernel_and_close_preserves_unknown_files(self):
        before=self.kernel.mock_calls[:]; state=self.runtime.status(self.r)
        self.assertEqual("prepared",state["progress"]); self.assertEqual(before,self.kernel.mock_calls)
        sentinel=self.runtime.directory(self.r)/"unrelated"; sentinel.write_text("keep")
        self.runtime.close(self.r,discard=True); self.assertEqual("keep",sentinel.read_text()); self.factory.assert_not_called()
