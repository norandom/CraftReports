"""Exact immutable snapshot bytes, owned feeds and atomic publication facts."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.schema import commands, evidence, feeds, snapshots
from craftreport.adapters.storage.serialization import (
    decode_evidence,
    decode_object,
    encode_evidence,
    encode_object,
)
from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import (
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    ReceiptState,
    ResourceRef,
)
from craftreport.data.values import Snapshot

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


class SnapshotStore:
    def __init__(
        self, database: Database, codec: Codec[Snapshot], fingerprint: Fingerprint, policy: str
    ) -> None:
        self.codec, self.fingerprint, self.policy = codec, fingerprint, policy
        self.journal = DurableJournal(database)

    def prepare(self, change: JsonObject) -> Publication:
        if set(change) != {"operation_id", "snapshot"}:
            raise ValueError("Unknown publication change")
        operation_id, raw = change["operation_id"], change["snapshot"]
        if (
            not isinstance(operation_id, str)
            or not operation_id.strip()
            or not isinstance(raw, Mapping)
        ):
            raise ValueError("Invalid publication change")
        snapshot = self.codec.decode(raw)
        content = self.codec.encode(snapshot)
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

    def _content(self, row: RowMapping) -> ports.ResourceSnapshot:
        content = decode_object(row["snapshot_bytes"], row["snapshot_digest"])
        stored = self.prepare({"operation_id": row["operation_id"], "snapshot": content})
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

    def _snapshot(
        self, connection: Connection, feed: str, version: int
    ) -> ports.ResourceSnapshot | ports.Missing:
        row = (
            connection.execute(
                select(snapshots).where(
                    snapshots.c.feed_id == feed,
                    snapshots.c.producer_version == version,
                )
            )
            .mappings()
            .one_or_none()
        )
        return ports.Missing() if row is None else self._content(row)

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
        latest = self._snapshot(connection, resource.identity, row["high_water"])
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
                "snapshot": latest.version.resource.identity,
                "content_digest": latest.version.version,
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
        existing = self._snapshot(connection, snapshot.feed_id, snapshot.producer_version)
        expected = ExpectedVersion(snapshot_resource(snapshot), snapshot.content_digest)
        if isinstance(existing, ports.ResourceSnapshot):
            if existing.version != expected:
                return ports.VersionConflict((expected,), (existing.version,))
            return ports.ResourceEffect(EffectDisposition.NONE, versions, ())
        if feed is not None and snapshot.producer_version < feed["high_water"]:
            latest = self._snapshot(connection, snapshot.feed_id, feed["high_water"])
            if isinstance(latest, ports.Missing):
                raise ValueError("Missing feed high water")
            return ports.VersionConflict((expected,), (latest.version,))
        revision = 1 if feed is None else feed["revision"] + 1
        self._advance(connection, publication, feed, subject, revision)
        pins = (ExpectedVersion(ResourceRef("feed", snapshot.feed_id), str(revision)),)
        reference = self._fact(connection, publication, pins)
        stored = self._snapshot(connection, snapshot.feed_id, snapshot.producer_version)
        if not isinstance(stored, ports.ResourceSnapshot) or stored.content != publication.content:
            raise ValueError("Snapshot readback failed")
        return ports.ResourceEffect(EffectDisposition.APPLIED, pins, (reference,))

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
        self, connection: Connection, publication: Publication, pins: ports.Preconditions
    ) -> EvidenceRef:
        snapshot = publication.snapshot
        fact: JsonObject = {
            "operation_id": publication.operation_id,
            "feed_id": snapshot.feed_id,
            "producer_version": str(snapshot.producer_version),
            "content_digest": snapshot.content_digest,
        }
        payload, digest = encode_object(fact)
        reference = EvidenceRef(
            uuid4().hex,
            "snapshot_persisted",
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
