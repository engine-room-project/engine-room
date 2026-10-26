import json
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine_room.records import DamagedRecord, Receipt, Store


def rental(operation="op1", **kwargs):
    defaults = dict(operation_id=operation, connection_id="connection1", connector_id="test",
                    account_id="synthetic-account", mode="rental", state="intent", created_at=100,
                    deadline=200)
    defaults.update(kwargs)
    return Receipt(**defaults)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state")

    @unittest.skipUnless(os.name=="nt","Windows delete-sharing semantics")
    def test_transient_windows_reader_conflict_retries_without_deleting_receipt(self):
        from engine_room.records import atomic_json
        target=Path(self.temp.name)/"conflict.json"
        atomic_json(target,{"old":True})
        original=os.replace; calls=[]
        error=PermissionError("synthetic sharing conflict"); error.winerror=32
        def replace_once(source,destination):
            calls.append(destination)
            if len(calls)<3:
                self.assertEqual({"old":True},json.loads(target.read_text()))
                raise error
            return original(source,destination)
        with patch("engine_room.records.os.replace",side_effect=replace_once): atomic_json(target,{"new":True})
        self.assertEqual(3,len(calls)); self.assertEqual({"new":True},json.loads(target.read_text()))

    def test_operation_scope_stays_stable_when_allocation_identity_arrives(self):
        intent=replace(rental(),protection_id="controller")
        active=replace(intent,state="active",allocation_submitted=True,resource_id="synthetic-pod")
        self.assertEqual(intent.operation_key(),active.operation_key())
        for change in (dict(connection_id="another"),dict(account_id="another-account"),dict(deadline=300)):
            self.assertNotEqual(intent.operation_key(),replace(intent,**change).operation_key())

    def test_round_trip_and_account_binding(self):
        record = rental()
        self.store.save(record)
        self.assertEqual([record], self.store.scan())
        self.assertEqual("synthetic-account", self.store.scan()[0].account_id)

    def test_corrupt_record_does_not_hide_later_receipt(self):
        self.store.path("aaa").write_text('{"token":"synthetic-sensitive-value",', encoding="utf-8")
        healthy = rental("zzz", state="active", resource_id="owned-pod", protection_id="proof1")
        self.store.save(healthy)
        records = self.store.scan()
        self.assertIsInstance(records[0], DamagedRecord)
        self.assertEqual(healthy, records[1])
        self.assertNotIn("sensitive", repr(records[0]))
        self.assertEqual(2, len(self.store.blockers()))

    def test_interrupted_replace_preserves_old_receipt(self):
        old = rental()
        self.store.save(old)
        with patch("engine_room.records.os.replace", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                self.store.save(replace(old, state="unresolved"))
        self.assertEqual([old], self.store.scan())
        self.assertEqual([], list(self.store.root.glob("*.tmp")))

    def test_fsync_happens_before_replacement(self):
        events = []
        import os
        real_replace = os.replace
        def move(src, dst):
            events.append("replace")
            real_replace(src, dst)
        with patch("engine_room.records.os.fsync", side_effect=lambda fd: events.append("sync")), patch("engine_room.records.os.replace", side_effect=move):
            self.store.save(rental())
        self.assertEqual(["sync", "replace"], events[:2])

    def test_mismatch_unknown_fields_and_invalid_json_are_isolated(self):
        data = rental().__dict__.copy()
        data["account_key"] = "synthetic-only"
        self.store.path("extra").write_text(json.dumps(data),encoding="utf-8")
        self.store.path("wrong-name").write_text(json.dumps(rental().__dict__),encoding="utf-8")
        self.assertTrue(all(isinstance(r, DamagedRecord) for r in self.store.scan()))
        self.assertEqual(2, len(self.store.scan()))

    def test_state_invariants(self):
        for record in [rental(deadline=None), rental(deadline=float("nan")), rental(deadline=99),
                       rental(state="off", resource_id="pod"), rental(state="active"),
                       rental(operation_id="../escape"), rental(account_id=""),
                       rental(mode="attachment", deadline=None, state="off", resource_id="vm")]:
            with self.subTest(record=record), self.assertRaises(ValueError):
                self.store.save(record)

    def test_attachments_do_not_block_rentals_or_assert_machine_off(self):
        attachment = rental(mode="attachment", deadline=None, state="detached", resource_id="existing-vm")
        self.store.save(attachment)
        self.assertEqual([], self.store.blockers())
        self.assertEqual("detached", self.store.scan()[0].state)

    def test_only_off_state_releases_blocker(self):
        active = rental(state="unresolved", resource_id="pod", protection_id="proof")
        self.store.save(active)
        self.assertEqual([active], self.store.blockers())
        self.store.save(replace(active,state="off"))
        self.assertEqual([], self.store.blockers())

    def test_lock_excludes_another_writer_and_releases_after_failure(self):
        with self.store.allocation_lock():
            with self.assertRaises(TimeoutError):
                with Store(self.store.root).allocation_lock(timeout=0):
                    self.fail("Second writer entered")
        with self.assertRaises(RuntimeError):
            with self.store.allocation_lock():
                raise RuntimeError("simulated operation failure")
        with self.store.allocation_lock(timeout=0):
            pass

    def test_oversized_record_is_preserved_for_recovery(self):
        path=self.store.path("large")
        path.write_bytes(b" "*16385)
        self.assertIsInstance(self.store.scan()[0],DamagedRecord)
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
