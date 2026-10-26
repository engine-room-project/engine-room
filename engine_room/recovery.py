"""Connector-neutral, ownership-scoped recovery; provider confirmation is mandatory."""
from dataclasses import dataclass, replace

from .records import DamagedRecord
from .connections import Connection


@dataclass(frozen=True)
class Observation:
    account_id: str
    resource_id: str | None
    operation_id: str
    status: str
    owned: bool = False


@dataclass(frozen=True)
class Result:
    operation_id: str
    state: str
    message: str


class Recovery:
    """Connectors are trusted installed code, supplied by a registry, never name branches.

    account_identity must query the authenticated provider identity. observe/reconcile
    return provider observations; terminate may target only the passed owned resource.
    A pending operation with no match remains unresolved, since allocation may be delayed.
    """

    def __init__(self, store, connections, connectors):
        self.store = store
        self.connections = connections
        self.connectors = connectors

    def _connector(self, receipt):
        connection = self.connections.get(receipt.connection_id)
        if (connection is None or connection.id != receipt.connection_id
                or connection.connector_id != receipt.connector_id
                or connection.account_id != receipt.account_id):
            raise ValueError("The original named connection and account are required.")
        connector = self.connectors[receipt.connector_id]
        if connector.account_identity(connection) != receipt.account_id:
            raise ValueError("The authenticated provider account differs from this receipt.")
        return connection, connector

    @staticmethod
    def _validate_observation(receipt, observation):
        if (not isinstance(observation, Observation)
                or observation.account_id != receipt.account_id
                or observation.operation_id != receipt.operation_id
                or observation.status not in {"active", "absent", "unknown"}
                or (receipt.resource_id and observation.resource_id != receipt.resource_id)):
            raise ValueError("Provider observation does not match this operation.")
        return observation

    def _rental(self, receipt):
        connection, connector = self._connector(receipt)
        observation = (connector.observe(connection, receipt) if receipt.resource_id
                       else connector.reconcile(connection, receipt))
        self._validate_observation(receipt, observation)
        if not receipt.resource_id:
            if observation.resource_id:
                receipt = replace(receipt, resource_id=observation.resource_id, state="unresolved")
                self.store.save(receipt)  # Retain a candidate even if ownership needs another read.
            if observation.status != "active" or not observation.owned or not observation.resource_id:
                raise ValueError("Allocation remains uncertain; keep this operation for reconciliation.")
        if observation.status == "absent":
            self.store.save(replace(receipt, state="off"))
            return Result(receipt.operation_id, "off", "Provider confirmed this rental is absent.")
        if observation.status != "active" or not observation.owned:
            raise ValueError("Resource ownership or provider state is uncertain.")
        self.store.save(replace(receipt, state="stopping"))
        connector.terminate(connection, receipt)
        confirmation = self._validate_observation(receipt, connector.observe(connection, receipt))
        if confirmation.status != "absent":
            raise ValueError("Termination requested; provider has not confirmed absence.")
        self.store.save(replace(receipt, state="off"))
        return Result(receipt.operation_id, "off", "Provider confirmed this rental is absent.")

    def recover(self, operation_ids=None):
        results = []
        with self.store.allocation_lock():
            for receipt in self.store.scan():
                if isinstance(receipt, DamagedRecord):
                    results.append(Result(receipt.filename, "unresolved", receipt.message))
                    continue
                if not receipt.unresolved or (operation_ids is not None and receipt.operation_id not in operation_ids):
                    continue
                try:
                    if not receipt.allocation_submitted and not receipt.resource_id and receipt.state == "intent":
                        self.store.save(replace(receipt,state="cancelled",cancel_requested=True))
                        results.append(Result(receipt.operation_id,"cancelled","Cancelled before any allocation request was submitted."))
                        continue
                    results.append(self._rental(receipt))
                except Exception:
                    # One failure must not strand later known rentals. Provider exceptions
                    # may contain credentials, so do not expose their text in this result.
                    # Reconciliation may already have saved a newly identified resource.
                    # Preserve that newer identity, even when subsequent deletion fails.
                    try:
                        latest = next(r for r in self.store.scan()
                                      if not isinstance(r, DamagedRecord)
                                      and r.operation_id == receipt.operation_id)
                        self.store.save(replace(latest, state="unresolved"))
                    except Exception:
                        # Storage failure must not prevent cleanup of other known rentals.
                        pass
                    results.append(Result(receipt.operation_id, "unresolved",
                        "Recovery is incomplete. Keep the record and check the original provider account."))
        return results

    def disconnect_attachment(self, receipt):
        if receipt.mode != "attachment":
            raise ValueError("A managed rental must use verified termination.")
        with self.store.allocation_lock():
            connection, connector = self._connector(receipt)
            connector.disconnect(connection, receipt)
            self.store.save(replace(receipt, state="detached"))
        return Result(receipt.operation_id, "detached", "Disconnected. The existing machine was not shut down.")
