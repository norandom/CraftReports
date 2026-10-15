"""Concrete snapshot resource reader and guarded durable effect provider."""

from sqlalchemy.engine import Connection

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.guard import DurableGuard, DurableLease
from craftreport.adapters.storage.snapshots import Fingerprint, Publication, SnapshotStore
from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import JsonObject, ResourceRef
from craftreport.data.values import Snapshot


class DurableResources:
    def __init__(
        self,
        database: Database,
        codec: Codec[Snapshot],
        fingerprint: Fingerprint,
        policy: str,
    ) -> None:
        self.database = database
        self.store = SnapshotStore(database, codec, fingerprint, policy)
        self.guard = DurableGuard(database, self.store.read)

    async def read(
        self, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing | ports.ServiceUnavailable:
        try:
            return await self.database.transaction(
                lambda connection: self.store.read(connection, resource)
            )
        except (StorageUnavailable, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return ports.ServiceUnavailable("resources")

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
    ) -> ports.ResourceEffectResult:
        if (
            not isinstance(guard, DurableLease)
            or guard.owner is not self.guard
            or not self.guard.is_current(guard)
            or resource not in tuple(pin.resource for pin in self.guard.preconditions(guard))
        ):
            return ports.GuardLost()
        try:
            publication = self.store.prepare(change)
            if resource != ResourceRef("feed", publication.snapshot.feed_id):
                raise ValueError("Publication resource mismatch")
            current = await guard.assert_current()
            if not isinstance(current, ports.GuardCurrent):
                return current
            return await self.database.transaction(
                lambda connection: self._commit(connection, publication, guard)
            )
        except (StorageUnavailable, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return ports.ServiceUnavailable("effects")

    def _commit(
        self, connection: Connection, publication: Publication, guard: DurableLease
    ) -> ports.ResourceEffectResult:
        current = guard.check(connection)
        if not isinstance(current, ports.GuardCurrent):
            return current
        return self.store.commit(connection, publication, self.guard.preconditions(guard))
