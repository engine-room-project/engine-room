from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.connections import Connection
from engine_room.connectors import Registry
from engine_room.private_endpoint import ModelEndpoint
from engine_room.records import Receipt,atomic_json
from engine_room_connectors._ssh_attachment import SSHAttachment


class AttachmentConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.credentials=Mock(); self.loader=Mock(return_value=Mock(account_id="ssh-account",resource_id="existing-model"))
        self.factory=Mock(); self.http=Mock()
        self.connector=SSHAttachment(self.root,credentials=self.credentials,identity_loader=self.loader,forward_factory=self.factory,http_factory=self.http,now=lambda:1000)
        self.connection=Connection("connection","ssh","ssh-account","Existing model","explicit-path",dict(model_id="served-model"))
        self.receipt=Receipt("attached","connection","ssh","ssh-account","attachment","active",1000,resource_id="existing-model")
        self.forward=Mock(); self.forward.receipt=self.receipt; self.forward.closed=False; self.forward.process.poll.return_value=None
        self.endpoint=ModelEndpoint(str(self.root/"s"/self.receipt.operation_key()[:16]/"m.sock"),self.receipt.operation_key(),"existing-model",1,2,3)
        self.forward.endpoint=self.endpoint; self.forward.close.return_value=True; self.factory.return_value=self.forward
        self.http.return_value.json.return_value=dict(data=[dict(id="served-model")])
    def test_attachment_capability_and_explicit_form_have_no_rental_actions(self):
        registry=Registry(); registry.register(self.connector)
        self.assertEqual(("attachment",),registry.descriptors()[0].modes)
        form=self.connector.form("connection")
        self.assertEqual({"host","port","username","host_key","model_port","model_id"},{row["name"] for row in form["fields"]})
        self.assertIn("billing continues",form["help"])
        for method in ("terminate","allocate","prepare","setup","quote"):
            with self.assertRaises(ValueError): getattr(self.connector,method)(self.connection,self.receipt)
        self.factory.assert_not_called(); self.loader.assert_not_called()
    def test_attach_checks_only_selected_read_only_model_list_and_is_not_replayed(self):
        self.assertEqual(self.endpoint,self.connector.attach(self.connection,self.receipt))
        self.http.return_value.json.assert_called_once_with("/v1/models",limit=32768)
        self.forward.start.assert_called_once(); self.assertEqual("ready",self.connector.health(self.connection,self.receipt).status)
        self.assertIsNone(self.connector.health(self.connection,self.receipt).rate)
        self.connector.pulse(self.connection,self.receipt); self.forward.pulse.assert_called_once()
        with self.assertRaises(ValueError): self.connector.attach(self.connection,self.receipt)
        self.assertEqual(1,self.factory.call_count)
        self.connector.disconnect(self.connection,self.receipt); self.forward.close.assert_called_once()
    def test_model_mismatch_closes_only_retained_forward(self):
        self.http.return_value.json.return_value=dict(data=[dict(id="different-model")])
        with self.assertRaises(ValueError): self.connector.attach(self.connection,self.receipt)
        self.forward.close.assert_called_once()
        self.assertEqual("unknown",self.connector.health(self.connection,self.receipt).status)
    def test_changed_principal_refuses_start_and_revokes_pulse_but_local_close_does_not_read_key(self):
        self.loader.return_value.account_id="different"
        with self.assertRaises(ValueError): self.connector.attach(self.connection,self.receipt)
        self.factory.assert_not_called()
        self.connector.forwards[self.receipt.operation_id]=self.forward
        with self.assertRaises(ValueError): self.connector.pulse(self.connection,self.receipt)
        self.forward.close.assert_called_once(); self.loader.reset_mock()
        self.connector.disconnect(self.connection,self.receipt); self.loader.assert_not_called()
    def test_other_receipt_or_rental_cannot_use_local_disconnect(self):
        for receipt in (replace(self.receipt,account_id="other"),replace(self.receipt,mode="rental",deadline=1600,protection_id="controller")):
            with self.assertRaises(ValueError): self.connector.disconnect(self.connection,receipt)
        self.forward.close.assert_not_called()
    def test_detached_receipt_refuses_before_identity_access(self):
        with self.assertRaises(ValueError): self.connector.attach(self.connection,replace(self.receipt,state="detached"))
        self.loader.assert_not_called(); self.factory.assert_not_called()
    @unittest.skipUnless(sys.platform.startswith("linux"),"Linux-only key preflight/owner-private recovery")
    def test_preflight_and_saved_closed_proof_preserve_machine_shutdown_boundary(self):
        result=self.connector.preflight("explicit-path",self.connection.settings)
        self.assertEqual("ssh-account",result["account_id"])
        self.loader.assert_called_once_with(self.connection.settings,"explicit-path",self.credentials)
        root=self.root/"s"/self.receipt.operation_key()[:16]; root.mkdir(mode=0o700,parents=True)
        proof=dict(schema=1,state="closed",disconnected=True,operation_key=self.receipt.operation_key(),resource_id=self.receipt.resource_id)
        atomic_json(root/"forward.json",proof)
        self.connector.disconnect(self.connection,self.receipt)
        atomic_json(root/"forward.json",proof|dict(state="ready"))
        with self.assertRaises(ValueError): self.connector.disconnect(self.connection,self.receipt)
        self.assertTrue((root/"forward.json").exists()); self.factory.assert_not_called()

    def test_failed_preflight_can_disconnect_without_credentials_and_cannot_replay(self):
        self.loader.side_effect=ValueError("synthetic rotated key")
        with self.assertRaises(ValueError): self.connector.attach(self.connection,self.receipt)
        self.factory.assert_not_called(); self.loader.reset_mock()
        self.connector.disconnect(self.connection,self.receipt)
        self.loader.assert_not_called()
        with self.assertRaises(ValueError): self.connector.attach(self.connection,self.receipt)
        self.factory.assert_not_called()
        with self.assertRaises(ValueError):
            self.connector.disconnect(self.connection,replace(self.receipt,resource_id="another-model"))
