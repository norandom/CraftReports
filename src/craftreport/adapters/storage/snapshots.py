"""Exact immutable snapshot bytes, owned feeds and atomic publication facts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.evidence import (
    STORAGE_FAILURES,
    snapshot_evidence,
    snapshot_row,
    validate_decision,
)
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.schema import commands, evidence, feeds, snapshots
from craftreport.adapters.storage.serialization import (
    PURGED,
    decision_frame,
    decode_evidence,
    decode_object,
    encode_evidence,
    encode_object,
)
from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    Principal,
    ReceiptState,
    ResourceRef,
)
from craftreport.data.requirements import check_completeness
from craftreport.data.values import Snapshot, SnapshotRef
from craftreport.runtime.publication import (
    LatestRequest,
    LatestSelection,
    PublicationDecision,
    PublicationResult,
    summarize,
)

type Fingerprint = Callable[
    [OperationKey, JsonObject, tuple[ResourceRef, ...], tuple[ExpectedVersion, ...]], str
]


@dataclass(frozen=True)
class Publication:
    operation_id: str
    snapshot: Snapshot
    content: JsonObject
    producer: JsonObject
    producer_bytes: bytes
    snapshot_bytes: bytes
    snapshot_digest: str


def snapshot_resource(snapshot: Snapshot) -> ResourceRef:
    return ResourceRef("snapshot", snapshot.feed_id + ":" + str(snapshot.producer_version))


def prepare_publication(codec: Codec[Snapshot], change: JsonObject) -> Publication:
    if set(change) != {"operation_id", "snapshot"}:
        raise ValueError("Unknown publication change")
    operation_id, raw = change["operation_id"], change["snapshot"]
    if (
        not isinstance(operation_id, str)
        or not operation_id.strip()
        or not isinstance(raw, Mapping)
    ):
        raise ValueError("Invalid publication change")
    snapshot = codec.decode(raw)
    content = codec.encode(snapshot)
    producer = {
        key: value
        for key, value in content.items()
        if key not in ("content_digest", "received_at", "accepted_at")
    }
    producer_bytes, digest = encode_object(producer)
    if digest != snapshot.content_digest:
        raise ValueError("Producer identity mismatch")
    payload, payload_digest = encode_object(content)
    return Publication(
        operation_id, snapshot, content, producer, producer_bytes, payload, payload_digest
    )


def read_retained_snapshot(codec: Codec[Snapshot], row: RowMapping) -> ports.ResourceSnapshot:
    content = decode_object(row["snapshot_bytes"], row["snapshot_digest"])
    stored = prepare_publication(codec, {"operation_id": row["operation_id"], "snapshot": content})
    if (
        stored.snapshot.feed_id != row["feed_id"]
        or stored.snapshot.producer_version != row["producer_version"]
        or stored.snapshot.content_digest != row["content_digest"]
        or stored.producer_bytes != row["producer_bytes"]
        or stored.snapshot_bytes != row["snapshot_bytes"]
    ):
        raise ValueError("Retained snapshot mismatch")
    return ports.ResourceSnapshot(
        ExpectedVersion(snapshot_resource(stored.snapshot), stored.snapshot.content_digest),
        content,
    )


class SnapshotStore:
    def __init__(
        self, database: Database, codec: Codec[Snapshot], fingerprint: Fingerprint, policy: str
    ) -> None:
        self.database = database
        self.codec, self.fingerprint, self.policy = codec, fingerprint, policy
        self.journal = DurableJournal(database)

    def prepare(self, change: JsonObject) -> Publication:
        return prepare_publication(self.codec, change)

    def queries(self, principal: Principal) -> SnapshotQueryAdapter:
        return SnapshotQueryAdapter(self, principal)

    async def read_decision(
        self, operation_id: str
    ) -> PublicationDecision | ports.Missing | ports.ServiceUnavailable:
        try:
            return await self.database.transaction(lambda c: self._decision(c, operation_id))
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("publication_decision")

    def _decision(
        self, connection: Connection, operation_id: str
    ) -> PublicationDecision | ports.Missing:
        rows = (
            connection.execute(
                select(evidence).where(evidence.c.operation_id == operation_id).limit(3)
            )
            .mappings()
            .all()
        )
        refs = tuple(
            decode_evidence(row["reference_bytes"], row["reference_digest"]) for row in rows
        )
        pairs = [
            (row, ref)
            for row, ref in zip(rows, refs, strict=True)
            if ref.scope == "publication_decided"
        ]
        if not pairs:
            return ports.Missing()
        if len(pairs) != 1 or any(
            ref.identity != row["identity"] or ref.operation_id != operation_id
            for row, ref in zip(rows, refs, strict=True)
        ):
            raise ValueError("Decision evidence differs")
        row, reference = pairs[0]
        if reference.content_digest != row["fact_digest"]:
            raise ValueError("Decision checksum linkage differs")
        item = validate_decision(
            connection,
            self.database,
            reference,
            decode_object(row["fact_bytes"], row["fact_digest"], max_bytes=65_536),
        )
        requested = SnapshotRef(item.feed_id, int(item.requested_version), item.requested_digest)
        latest = SnapshotRef(item.feed_id, int(item.high_water), item.high_water_digest)
        retained = (
            None
            if item.retained_version is None or item.retained_digest is None
            else SnapshotRef(item.feed_id, int(item.retained_version), item.retained_digest)
        )
        content = (
            None
            if retained is None
            else self._snapshot(connection, retained.feed_id, retained.producer_version)
        )
        availability = None if content is None else Availability.MISSING
        summary = None
        if isinstance(content, ports.ResourceSnapshot):
            availability = Availability.AVAILABLE
            if item.status in ("accepted", "existing"):
                summary = summarize(self.codec.decode(content.content))
        ordered = tuple(sorted(refs, key=lambda ref: ref.scope == "publication_decided"))
        return PublicationDecision(
            PublicationResult(item.status, requested, retained, latest, availability, summary),
            EffectDisposition.APPLIED if item.status == "accepted" else EffectDisposition.NONE,
            reference.resource_versions,
            ordered,
        )

    def _content(
        self, connection: Connection, row: RowMapping
    ) -> ports.ResourceSnapshot | ports.Missing:
        support = snapshot_evidence(connection, self.database, row["operation_id"])
        if row["snapshot_bytes"].startswith(PURGED):
            if support.availability is not Availability.MISSING:
                raise ValueError("Invalid snapshot removal")
            return ports.Missing()
        return read_retained_snapshot(self.codec, row)

    def _snapshot(
        self, connection: Connection, feed: str, version: int
    ) -> ports.ResourceSnapshot | ports.Missing:
        row = snapshot_row(connection, feed, version)
        return ports.Missing() if row is None else self._content(connection, row)

    def identity(
        self, connection: Connection, feed: str, version: int
    ) -> ExpectedVersion | ports.Missing:
        row = snapshot_row(connection, feed, version)
        if row is None:
            return ports.Missing()
        self._content(connection, row)
        return ExpectedVersion(
            ResourceRef("snapshot", feed + ":" + str(version)), row["content_digest"]
        )

    def read(
        self, connection: Connection, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing:
        if resource.kind == "snapshot":
            feed, separator, version = resource.identity.rpartition(":")
            if (
                not separator
                or not version.isascii()
                or not version.isdecimal()
                or not 0 < int(version) < 2**63
                or str(int(version)) != version
                or not feed
            ):
                raise ValueError("Invalid snapshot identity")
            return self._snapshot(connection, feed, int(version))
        if resource.kind != "feed":
            raise ValueError("Unsupported resource kind")
        row = (
            connection.execute(select(feeds).where(feeds.c.feed_id == resource.identity))
            .mappings()
            .one_or_none()
        )
        if row is None:
            return ports.Missing()
        if any(type(row[name]) is not int or row[name] <= 0 for name in ("revision", "high_water")):
            raise ValueError("Invalid retained feed revision")
        latest = self.identity(connection, resource.identity, row["high_water"])
        if (
            isinstance(latest, ports.Missing)
            or not isinstance(row["subject"], str)
            or not row["subject"].strip()
        ):
            raise ValueError("Retained feed has no authoritative snapshot")
        return ports.ResourceSnapshot(
            ExpectedVersion(resource, str(row["revision"])),
            {
                "high_water": str(row["high_water"]),
                "subject": row["subject"],
                "snapshot": latest.resource.identity,
                "content_digest": latest.version,
            },
        )

    def _command(
        self, connection: Connection, publication: Publication, versions: ports.Preconditions
    ) -> ports.RetainedCommand:
        row = (
            connection.execute(
                select(commands).where(commands.c.operation_id == publication.operation_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError("Missing admitted operation")
        retained = self.journal.retained(connection, row)
        if not isinstance(retained, ports.RetainedCommand):
            raise ValueError("Publication requires command")
        intent, receipt = retained.intent, retained.receipt
        resource = ResourceRef("feed", publication.snapshot.feed_id)
        if (
            receipt.state not in (ReceiptState.ACCEPTED, ReceiptState.PENDING)
            or receipt.operation != OperationKey("snapshot.publish", "1")
            or intent.retry_key.operation != receipt.operation
            or intent.resources != (resource,)
            or receipt.resources != (resource,)
            or intent.expected_versions != versions
            or receipt.expected_versions != versions
            or intent.normalization_policy != self.policy
            or intent.fingerprint
            != self.fingerprint(
                receipt.operation, publication.producer, intent.resources, intent.expected_versions
            )
        ):
            raise ValueError("Publication does not match retained admission")
        return retained

    def commit(
        self, connection: Connection, publication: Publication, versions: ports.Preconditions
    ) -> ports.ResourceEffectResult:
        retained = self._command(connection, publication, versions)
        snapshot = publication.snapshot
        feed = (
            connection.execute(select(feeds).where(feeds.c.feed_id == snapshot.feed_id))
            .mappings()
            .one_or_none()
        )
        subject = retained.intent.retry_key.subject
        if feed is not None and feed["subject"] != subject:
            raise ValueError("Publication does not own feed")
        existing = self.identity(connection, snapshot.feed_id, snapshot.producer_version)
        expected = ExpectedVersion(snapshot_resource(snapshot), snapshot.content_digest)
        status = "accepted"
        if isinstance(existing, ExpectedVersion):
            status = "existing" if existing == expected else "version_conflict"
        elif feed is not None and snapshot.producer_version < feed["high_water"]:
            status = "stale_version"
        accepted = status == "accepted"
        revision = 1 if feed is None else feed["revision"] + accepted
        high = snapshot.producer_version if accepted or feed is None else int(feed["high_water"])
        latest = expected if accepted else self.identity(connection, snapshot.feed_id, high)
        if isinstance(latest, ports.Missing):
            raise ValueError("Missing feed high water")
        fact: JsonObject = {
            "schema_version": "1",
            "operation_id": publication.operation_id,
            "feed_id": snapshot.feed_id,
            "requested_version": str(snapshot.producer_version),
            "requested_digest": snapshot.content_digest,
            "status": status,
            "retained_version": None
            if status == "stale_version"
            else str(snapshot.producer_version),
            "retained_digest": existing.version
            if isinstance(existing, ExpectedVersion)
            else (snapshot.content_digest if accepted else None),
            "high_water": str(high),
            "high_water_digest": latest.version,
            "feed_revision": str(revision),
        }
        decision_frame(fact)
        pins = (ExpectedVersion(ResourceRef("feed", snapshot.feed_id), str(revision)),)
        references: tuple[EvidenceRef, ...] = ()
        if accepted:
            self._advance(connection, publication, feed, subject, revision)
            references = (self._fact(connection, publication, pins),)
            stored = self._snapshot(connection, snapshot.feed_id, snapshot.producer_version)
            if (
                not isinstance(stored, ports.ResourceSnapshot)
                or stored.content != publication.content
            ):
                raise ValueError("Snapshot readback failed")
        references += (self._fact(connection, publication, pins, fact),)
        return ports.ResourceEffect(
            EffectDisposition.APPLIED if accepted else EffectDisposition.NONE, pins, references
        )

    def _advance(
        self,
        connection: Connection,
        publication: Publication,
        feed: RowMapping | None,
        subject: str,
        revision: int,
    ) -> None:
        snapshot = publication.snapshot
        values = {"subject": subject, "high_water": snapshot.producer_version, "revision": revision}
        if feed is None:
            connection.execute(insert(feeds).values(feed_id=snapshot.feed_id, **values))
        else:
            changed = connection.execute(
                update(feeds)
                .where(feeds.c.feed_id == snapshot.feed_id, feeds.c.revision == feed["revision"])
                .values(**values)
            )
            if changed.rowcount != 1:
                raise StorageUnavailable("Feed revision changed")
        connection.execute(
            insert(snapshots).values(
                feed_id=snapshot.feed_id,
                producer_version=snapshot.producer_version,
                operation_id=publication.operation_id,
                content_digest=snapshot.content_digest,
                producer_bytes=publication.producer_bytes,
                snapshot_bytes=publication.snapshot_bytes,
                snapshot_digest=publication.snapshot_digest,
            )
        )

    def _fact(
        self,
        connection: Connection,
        publication: Publication,
        pins: ports.Preconditions,
        decision: JsonObject | None = None,
    ) -> EvidenceRef:
        snapshot = publication.snapshot
        fact: JsonObject = {
            "operation_id": publication.operation_id,
            "feed_id": snapshot.feed_id,
            "producer_version": str(snapshot.producer_version),
            "content_digest": snapshot.content_digest,
        }
        fact = fact if decision is None else decision
        payload, digest = encode_object(fact)
        reference = EvidenceRef(
            uuid4().hex,
            "snapshot_persisted" if decision is None else "publication_decided",
            publication.operation_id,
            OperationKey("snapshot.publish", "1"),
            pins,
            digest,
        )
        reference_bytes, reference_digest = encode_evidence(reference)
        connection.execute(
            insert(evidence).values(
                identity=reference.identity,
                operation_id=reference.operation_id,
                reference_bytes=reference_bytes,
                reference_digest=reference_digest,
                fact_bytes=payload,
                fact_digest=digest,
            )
        )
        row = (
            connection.execute(select(evidence).where(evidence.c.identity == reference.identity))
            .mappings()
            .one()
        )
        observed = decode_evidence(row["reference_bytes"], row["reference_digest"])
        if (
            observed != reference
            or decode_object(row["fact_bytes"], row["fact_digest"]) != fact
            or row["operation_id"] != reference.operation_id
        ):
            raise ValueError("Committed fact readback failed")
        return observed


@dataclass(frozen=True, slots=True)
class SnapshotQueryAdapter:
    store: SnapshotStore
    principal: Principal

    def _feed(self, connection: Connection, feed_id: str) -> ports.ResourceSnapshot | ports.Missing:
        if self.principal.deployment_scope != self.store.database.deployment.identity:
            raise ValueError("Deployment differs")
        row = (
            connection.execute(select(feeds).where(feeds.c.feed_id == feed_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            return ports.Missing()
        if row["subject"] != self.principal.subject:
            raise ValueError("Feed owner differs")
        if any(
            type(row[name]) is not int or not 0 < row[name] < 2**63
            for name in ("revision", "high_water")
        ):
            raise ValueError("Invalid feed metadata")
        digest = connection.execute(
            select(snapshots.c.content_digest).where(
                snapshots.c.feed_id == feed_id, snapshots.c.producer_version == row["high_water"]
            )
        ).scalar_one()
        return ports.ResourceSnapshot(
            ExpectedVersion(ResourceRef("feed", feed_id), str(row["revision"])),
            {"high_water": str(row["high_water"]), "content_digest": digest},
        )

    def _read(
        self, connection: Connection, ref: SnapshotRef
    ) -> Snapshot | ports.Missing | ports.VersionConflict:
        if isinstance(self._feed(connection, ref.feed_id), ports.Missing):
            return ports.Missing()
        identity = self.store.identity(connection, ref.feed_id, ref.producer_version)
        expected = ExpectedVersion(
            ResourceRef("snapshot", ref.feed_id + ":" + str(ref.producer_version)),
            ref.content_digest,
        )
        if isinstance(identity, ports.Missing):
            return identity
        if identity != expected:
            return ports.VersionConflict((expected,), (identity,))
        content = self.store.read(connection, expected.resource)
        return (
            content
            if isinstance(content, ports.Missing)
            else self.store.codec.decode(content.content)
        )

    async def read(
        self, ref: SnapshotRef
    ) -> Snapshot | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        try:
            return await self.store.database.transaction(lambda c: self._read(c, ref))
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("snapshot_content")

    async def _page(self, feed: str, before: int) -> tuple[SnapshotRef, ...]:
        def load(connection: Connection) -> tuple[SnapshotRef, ...]:
            self._feed(connection, feed)
            rows = connection.execute(
                select(snapshots.c.producer_version, snapshots.c.content_digest)
                .where(snapshots.c.feed_id == feed, snapshots.c.producer_version <= before)
                .order_by(snapshots.c.producer_version.desc())
                .limit(16)
            ).all()
            return tuple(SnapshotRef(feed, row[0], row[1]) for row in rows)

        return await self.store.database.transaction(load)

    async def latest(
        self, request: LatestRequest
    ) -> LatestSelection | ports.Missing | ports.ServiceUnavailable:
        try:
            feed = await self.store.database.transaction(lambda c: self._feed(c, request.feed_id))
            if isinstance(feed, ports.Missing):
                return feed
            latest = SnapshotRef(
                request.feed_id,
                int(str(feed.content["high_water"])),
                str(feed.content["content_digest"]),
            )
            if request.requirements is not None:
                return await self._select(request, latest, Availability.AVAILABLE)
            content = await self.read(latest)
            if isinstance(content, (ports.ServiceUnavailable, ports.VersionConflict)):
                return ports.ServiceUnavailable("snapshot_selection_content")
            availability = (
                Availability.MISSING
                if isinstance(content, ports.Missing)
                else Availability.AVAILABLE
            )
            return LatestSelection(latest, availability, "not_requested", None, ())
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("snapshot_selection_content")

    async def _select(
        self, request: LatestRequest, latest: SnapshotRef, availability: Availability
    ) -> LatestSelection | ports.ServiceUnavailable:
        assert request.requirements is not None
        before, checked, issues = latest.producer_version, 0, ()
        while True:
            page = await self._page(request.feed_id, before)
            if not page:
                return LatestSelection(latest, availability, "none", None, issues)
            for ref in page:
                if checked == 64:
                    return ports.ServiceUnavailable("snapshot_selection_limit")
                content = await self.read(ref)
                if not isinstance(content, Snapshot):
                    return ports.ServiceUnavailable("snapshot_selection_content")
                found = check_completeness(content, request.requirements)
                del content
                if ref == latest:
                    issues = found
                if not found:
                    return LatestSelection(latest, availability, "selected", ref, issues)
                checked += 1
            before = page[-1].producer_version - 1
