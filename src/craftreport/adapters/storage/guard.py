"""Single-process resource leases; transactions never span asynchronous waits."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.engine import Connection

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.application import ports
from craftreport.contracts import ExpectedVersion, ResourceRef
from craftreport.contracts.identity import check_preconditions

type ResourceRead = Callable[[Connection, ResourceRef], ports.ResourceSnapshot | ports.Missing]


@dataclass
class _Lock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


@dataclass(frozen=True, eq=False, slots=True)
class DurableLease:
    owner: DurableGuard
    authoritative_versions: ports.Preconditions
    task: asyncio.Task[object] | None = field(default_factory=asyncio.current_task)

    def valid(self) -> bool:
        return self.owner.is_active(self)

    def check(self, connection: Connection) -> ports.GuardCheck:
        if not self.valid():
            return ports.GuardLost()
        expected = self.owner.preconditions(self)
        actual = self.owner.versions(connection, expected)
        if actual != expected:
            return ports.VersionConflict(expected, actual)
        return ports.GuardCurrent()

    async def assert_current(self) -> ports.GuardCheck:
        if not self.owner.is_current(self):
            return ports.GuardLost()
        try:
            return await self.owner.database.transaction(self.check)
        except (StorageUnavailable, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return ports.ServiceUnavailable("guard")


@dataclass(frozen=True, slots=True)
class _Issued:
    versions: ports.Preconditions
    task: asyncio.Task[object] | None


class DurableGuard:
    def __init__(self, database: Database, read: ResourceRead, timeout: float = 2.0) -> None:
        if timeout <= 0:
            raise ValueError("Positive guard timeout required")
        self.database, self.read, self.timeout = database, read, timeout
        self._locks: dict[ResourceRef, _Lock] = {}
        self._leases: dict[DurableLease, _Issued] = {}
        self._claims: dict[DurableLease, str] = {}

    def capture(self, operation_id: str, versions: ports.Preconditions) -> DurableLease:
        leases = [
            lease
            for lease in self._leases
            if self.is_current(lease) and self.preconditions(lease) == versions
        ]
        if len(leases) != 1 or self._claims.setdefault(leases[0], operation_id) != operation_id:
            raise StorageUnavailable("No unique original operation lease")
        return leases[0]

    def is_active(self, lease: DurableLease) -> bool:
        issued = self._leases.get(lease)
        return (
            issued is not None
            and lease.owner is self
            and lease.authoritative_versions == issued.versions
            and lease.task is issued.task
            and issued.task is not None
            and not issued.task.done()
            and not issued.task.cancelling()
        )

    def is_current(self, lease: DurableLease) -> bool:
        issued = self._leases.get(lease)
        return (
            self.is_active(lease) and issued is not None and issued.task is asyncio.current_task()
        )

    def preconditions(self, lease: DurableLease) -> ports.Preconditions:
        if not self.is_active(lease):
            raise StorageUnavailable("Lease authority is no longer current")
        return self._leases[lease].versions

    def versions(
        self, connection: Connection, requested: ports.Preconditions
    ) -> ports.Preconditions:
        versions: list[ExpectedVersion] = []
        for pin in requested:
            value = self.read(connection, pin.resource)
            versions.append(
                ExpectedVersion(pin.resource, "absent")
                if isinstance(value, ports.Missing)
                else value.version
            )
        return tuple(versions)

    @asynccontextmanager
    async def acquire(self, preconditions: ports.Preconditions) -> AsyncGenerator[ports.GuardLease]:
        check_preconditions(preconditions)
        held: list[tuple[ResourceRef, _Lock]] = []
        requested: list[tuple[ResourceRef, _Lock]] = []
        lease = DurableLease(self, preconditions)
        try:
            try:
                async with asyncio.timeout(self.timeout):
                    for pin in sorted(
                        preconditions, key=lambda item: (item.resource.kind, item.resource.identity)
                    ):
                        slot = self._locks.setdefault(pin.resource, _Lock())
                        slot.users += 1
                        requested.append((pin.resource, slot))
                        await slot.lock.acquire()
                        held.append((pin.resource, slot))
            except TimeoutError as error:
                raise ports.GuardAcquisitionError(ports.ServiceUnavailable("guard")) from error
            self._leases[lease] = _Issued(tuple(preconditions), asyncio.current_task())
            result = await lease.assert_current()
            if not isinstance(result, ports.GuardCurrent):
                reason = (
                    result
                    if isinstance(result, ports.VersionConflict)
                    else ports.ServiceUnavailable("guard")
                )
                raise ports.GuardAcquisitionError(reason)
            yield lease
        finally:
            self._claims.pop(lease, None)
            self._leases.pop(lease, None)
            for _, slot in reversed(held):
                slot.lock.release()
            for resource, slot in requested:
                slot.users -= 1
                if slot.users == 0:
                    del self._locks[resource]
