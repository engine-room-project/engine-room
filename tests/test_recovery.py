from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from engine_room.records import Store
from engine_room.recovery import Connection, Observation, Recovery
from test_records import rental


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/"state")
        self.connection = Connection("connection1", "test", "synthetic-account")
        self.connector = Mock()
        self.connector.account_identity.return_value = self.connection.account_id
        self.recovery = Recovery(self.store, {"connection1": self.connection}, {"test": self.connector})

    def observation(self, record, status="active", owned=True):
        return Observation(record.account_id, record.resource_id, record.operation_id, status, owned)

    def active(self, operation="known"):
        record=rental(operation,state="active",resource_id="owned-pod",protection_id="independent-proof")
        self.store.save(record)
        return record

    def test_pending_and_corrupt_records_do_not_prevent_known_cleanup(self):
        pending=rental("aaa",state="allocating",protection_id="proof")
        self.store.save(pending)
        self.store.path("bbb").write_text("{",encoding="utf-8")
        known=self.active("zzz")
        self.connector.reconcile.return_value=self.observation(pending,"unknown",False)
        self.connector.observe.side_effect=[self.observation(known),self.observation(known,"absent",False)]
        results=self.recovery.recover()
        self.assertEqual(["unresolved","unresolved","off"],[r.state for r in results])
        self.connector.terminate.assert_called_once_with(self.connection,known)
        self.assertEqual(2,len(self.store.blockers()))

    def test_uncertain_reconciliation_retains_candidate_without_authorizing_deletion(self):
        record=rental("pending",state="allocating",protection_id="proof",allocation_submitted=True)
        self.store.save(record)
        self.connector.reconcile.return_value=Observation(record.account_id,"candidate",record.operation_id,"unknown",False)
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.assertEqual("candidate",self.store.load("pending").resource_id)
        self.connector.terminate.assert_not_called()

    def test_wrong_account_cannot_treat_404_as_off_or_delete(self):
        self.active()
        self.connector.account_identity.return_value="different-account"
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.connector.observe.assert_not_called()
        self.connector.terminate.assert_not_called()
        self.assertEqual(1,len(self.store.blockers()))

    def test_reconfigured_connection_preserves_old_account_record(self):
        self.active()
        self.recovery.connections["connection1"]=replace(self.connection,account_id="other-account")
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.connector.account_identity.assert_not_called()

    def test_unrelated_resource_is_never_terminated(self):
        record=self.active()
        self.connector.observe.return_value=self.observation(record,owned=False)
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.connector.terminate.assert_not_called()

    def test_delete_acknowledgement_without_absence_does_not_mean_off(self):
        record=self.active()
        self.connector.observe.return_value=self.observation(record)
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.assertEqual(1,len(self.store.blockers()))

    def test_provider_confirmed_absence_closes_same_account_receipt(self):
        record=self.active()
        self.connector.observe.return_value=self.observation(record,"absent",False)
        self.assertEqual("off",self.recovery.recover()[0].state)
        self.connector.terminate.assert_not_called()
        self.assertEqual([],self.store.blockers())

    def test_pending_no_match_cannot_be_treated_as_confirmed_absence(self):
        record=rental("pending",state="allocating",protection_id="proof")
        self.store.save(record)
        self.connector.reconcile.return_value=self.observation(record,"absent",False)
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.connector.terminate.assert_not_called()

    def test_mismatched_operation_cannot_be_terminated(self):
        record=self.active()
        self.connector.observe.return_value=replace(self.observation(record),operation_id="unrelated")
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.connector.terminate.assert_not_called()

    def test_exception_details_are_not_exposed(self):
        self.active()
        self.connector.observe.side_effect=RuntimeError("synthetic-sensitive-provider-error")
        result=self.recovery.recover()[0]
        self.assertEqual("unresolved",result.state)
        self.assertNotIn("sensitive",repr(result))

    def test_attachment_disconnect_never_terminates_machine(self):
        record=rental("attached",mode="attachment",deadline=None,state="active",resource_id="existing-vm")
        self.store.save(record)
        self.assertEqual([],self.recovery.recover())
        result=self.recovery.disconnect_attachment(record)
        self.assertEqual("detached",result.state)
        self.connector.disconnect.assert_called_once_with(self.connection,record)
        self.connector.terminate.assert_not_called()
        self.connector.observe.assert_not_called()

    def test_reconciled_identity_survives_failed_termination(self):
        record=rental("pending",state="allocating",protection_id="proof")
        self.store.save(record)
        self.connector.reconcile.return_value=Observation(record.account_id,"newly-known-pod",record.operation_id,"active",True)
        self.connector.terminate.side_effect=RuntimeError("simulated deletion failure")
        self.assertEqual("unresolved",self.recovery.recover()[0].state)
        self.assertEqual("newly-known-pod",self.store.scan()[0].resource_id)

    def test_failed_receipt_write_does_not_prevent_later_cleanup(self):
        first=self.active("aaa")
        second=replace(self.active("zzz"),resource_id="second-pod")
        self.store.save(second)
        self.connector.observe.side_effect=[RuntimeError("simulated failure"),self.observation(second),self.observation(second,"absent",False)]
        original=self.store.save
        def save(record):
            if record.operation_id==first.operation_id:
                raise OSError("simulated unavailable record")
            original(record)
        with patch("engine_room.records.Store.save",side_effect=save):
            result=self.recovery.recover()
        self.assertEqual(["unresolved","off"],[r.state for r in result])
        self.connector.terminate.assert_called_once_with(self.connection,second)

    def test_connector_extension_uses_same_recovery_workflow(self):
        record=replace(self.active(),connector_id="additional")
        self.store.save(record)
        connection=replace(self.connection,connector_id="additional")
        recovery=Recovery(self.store,{"connection1":connection},{"additional":self.connector})
        self.connector.observe.return_value=self.observation(record,"absent",False)
        self.assertEqual("off",recovery.recover()[0].state)


if __name__=="__main__":
    unittest.main()
