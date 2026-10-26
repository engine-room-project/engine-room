from dataclasses import replace
from pathlib import Path
import importlib
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock

from engine_room.connections import Connections
from engine_room.connectors import Descriptor, Registry
from test_records import rental


def connector(name="test"):
    result=Mock()
    result.descriptor=Descriptor(name,"Synthetic connector","Explicit test credential")
    result.preflight.return_value={"account_id":"synthetic-account","settings":{"region":"test-region"}}
    return result


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry=Registry()
        self.connector=connector()
        self.registry.register(self.connector)
        self.connections=Connections(self.temp.name,self.registry)

    def add(self,name="My connection"):
        return self.connections.add(name,"test","explicit-credential")

    def test_first_install_has_no_connections_or_default_provider(self):
        self.assertEqual({},self.connections.read())
        self.connector.preflight.assert_not_called()
        self.assertFalse(self.connections.path.exists())

    def test_add_records_explicit_credential_and_verified_account(self):
        item=self.add()
        self.connector.preflight.assert_called_once_with("explicit-credential",{})
        self.assertEqual(item,self.connections.read()[item.id])
        self.assertEqual("synthetic-account",item.account_id)
        self.assertEqual("explicit-credential",item.credential_ref)
        self.assertEqual({"region":"test-region"},item.settings)

    def test_multiple_named_connections_do_not_change_existing_account(self):
        first=self.add("First")
        self.connector.preflight.return_value={"account_id":"another-account","settings":{}}
        second=self.add("Second")
        self.assertNotEqual(first.id,second.id)
        self.assertEqual("synthetic-account",self.connections.read()[first.id].account_id)

    def test_duplicate_name_and_absent_credential_are_rejected_before_preflight(self):
        self.add()
        self.connector.preflight.reset_mock()
        for name,ref in [("MY CONNECTION","explicit-credential"),("Another","")]:
            with self.assertRaises(ValueError): self.connections.add(name,"test",ref)
        self.connector.preflight.assert_not_called()

    def test_failed_preflight_saves_nothing_and_omits_provider_error_text(self):
        self.connector.preflight.side_effect=RuntimeError("synthetic-sensitive-message")
        with self.assertRaises(ValueError) as error: self.add()
        self.assertNotIn("sensitive",str(error.exception))
        self.assertEqual({},self.connections.read())

    def test_missing_connector_has_actionable_failure(self):
        with self.assertRaisesRegex(ValueError,"Install the connector"):
            self.connections.add("Missing","missing","explicit-credential")
        self.assertEqual({},self.connections.read())

    def test_damaged_configuration_does_not_reset_connections(self):
        self.add()
        self.connections.path.write_text("{",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"damaged"): self.connections.read()
        self.assertEqual("{",self.connections.path.read_text())

    def test_remove_blocked_for_unresolved_operation_or_corrupt_receipt(self):
        item=self.add()
        record=replace(rental(),connection_id=item.id)
        self.connections.receipts.save(record)
        with self.assertRaisesRegex(ValueError,"Recover"): self.connections.remove(item.id)
        self.assertIn(item.id,self.connections.read())
        self.connections.receipts.save(replace(record,state="off",resource_id="pod",protection_id="proof"))
        self.connections.receipts.path("corrupt").write_text("{",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"Recover"): self.connections.remove(item.id)

    def test_remove_is_config_only_and_preserves_other_connection(self):
        first=self.add("First")
        second=self.add("Second")
        self.connections.remove(first.id)
        self.assertEqual([second.id],list(self.connections.read()))
        self.connector.terminate.assert_not_called()
        self.connector.disconnect.assert_not_called()

    def test_registry_extension_needs_no_workflow_changes(self):
        # A trusted separately installed package is discovered without editing core.
        package=Path(self.temp.name)/"synthetic_connectors"
        package.mkdir()
        (package/"__init__.py").write_text("",encoding="utf-8")
        (package/"extra.py").write_text('from test_connections import connector\ndef create_connector(): return connector("extra")\n',encoding="utf-8")
        sys.path.insert(0,self.temp.name)
        try:
            importlib.invalidate_caches()
            registry=Registry().discover("synthetic_connectors")
            added=Connections(Path(self.temp.name)/"second",registry).add("New connector","extra","chosen-credential")
            self.assertEqual("extra",added.connector_id)
        finally:
            sys.path.remove(self.temp.name)
            for key in list(sys.modules):
                if key=="synthetic_connectors" or key.startswith("synthetic_connectors."): del sys.modules[key]

    def test_duplicate_connector_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"): self.registry.register(connector())


if __name__=="__main__": unittest.main()
