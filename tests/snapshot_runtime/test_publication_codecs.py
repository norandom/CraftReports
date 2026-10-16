"""Publication metadata codecs preserve exact identities and closed alternatives."""

from datetime import UTC, datetime

import pytest

from craftreport.adapters import snapshot_wire as wire
from craftreport.adapters.canonical import WireFailure
from craftreport.application.ports import Missing, ServiceUnavailable, VersionConflict
from craftreport.contracts import Availability, JsonObject
from craftreport.data.requirements import DatasetRequirement, FieldRequirement, InputRequirements
from craftreport.data.values import SnapshotRef
from craftreport.runtime.publication import (
    LatestRequest,
    LatestSelection,
    PublicationResult,
    SnapshotSummary,
)

REF = SnapshotRef("feed", 2**63 - 1, "a" * 64)
STAMP = datetime(2026, 1, 1, tzinfo=UTC)


def test_publication_summary_and_findings_roundtrip() -> None:
    summary = SnapshotSummary(REF, 1, 2, 3, 6, 0, 0, STAMP, STAMP)
    result = PublicationResult("accepted", REF, REF, REF, Availability.AVAILABLE, summary)
    codec = wire.publication_result_codec()
    raw = codec.encode(result)
    assert codec.decode(raw) == result
    assert str(2**63 - 1) in str(raw)
    assert "2026-01-01T00:00:00.000000Z" in str(raw)
    with pytest.raises(WireFailure):
        codec.decode({**raw, "unexpected": True})


def test_latest_requirements_and_selection_roundtrip() -> None:
    request = LatestRequest(
        "feed", InputRequirements((DatasetRequirement("d", (FieldRequirement("x", "int64"),)),), ())
    )
    codec = wire.latest_request_codec()
    assert codec.decode(codec.encode(request)) == request
    result = LatestSelection(REF, Availability.AVAILABLE, "selected", REF, ())
    output = wire.latest_result_codec()
    assert output.decode(output.encode(result)) == result
    for failure in (Missing(), ServiceUnavailable("snapshots")):
        assert output.decode(output.encode(failure)) == failure
    with pytest.raises(WireFailure):
        codec.decode(
            {"feed_id": "feed", "requirements": {"datasets": [], "metrics": [], "trusted": True}}
        )


def test_reference_rejects_noncanonical_and_out_of_range_versions() -> None:
    codec = wire.snapshot_reference_codec()
    assert codec.decode(codec.encode(REF)) == REF
    for version in (1, True, "01", "0", str(2**63)):
        with pytest.raises(WireFailure):
            codec.decode(
                {"feed_id": "feed", "producer_version": version, "content_digest": "a" * 64}
            )


def test_read_is_bare_snapshot_and_closed_failures() -> None:
    codec = wire.snapshot_read_codec()
    content = wire.publication_codec().decode(
        {
            "schema_version": "1",
            "feed_id": "feed",
            "producer_version": "1",
            "datasets": [],
            "metrics": [],
        }
    )
    snapshot, _ = wire.finalize_snapshot(content, STAMP, STAMP)
    assert codec.encode(snapshot) == wire.snapshot_codec().encode(snapshot)
    assert codec.decode(codec.encode(snapshot)) == snapshot
    for failure in (Missing(), VersionConflict((), ()), ServiceUnavailable("snapshots")):
        assert codec.decode(codec.encode(failure)) == failure
    for raw in (
        {"kind": "missing", "extra": 1},
        {"kind": "invented"},
        {"kind": "missing", "schema_version": "1"},
    ):
        with pytest.raises(WireFailure):
            codec.decode(raw)


def test_capability_declares_versions_resources_and_decision_evidence() -> None:
    from unittest.mock import Mock

    from craftreport.application.registry import PreparedCommand, PreparedQuery
    from craftreport.contracts import ResourceRef
    from craftreport.runtime.capability import PublicationCodecs, publication_operations
    from craftreport.runtime.publication import PublicationOperations

    codecs = PublicationCodecs(
        wire.publication_codec(),
        wire.publication_result_codec(),
        wire.snapshot_reference_codec(),
        wire.snapshot_read_codec(),
        wire.latest_request_codec(),
        wire.latest_result_codec(),
    )
    handlers = Mock(spec=PublicationOperations)
    operations = {op.descriptor.key.name: op for op in publication_operations(handlers, codecs)}
    assert set(operations) == {"snapshot.publish", "snapshot.read", "snapshot.latest"}
    assert all(op.descriptor.key.contract_version == "1" for op in operations.values())
    publication = operations["snapshot.publish"]
    assert publication.descriptor.completion_evidence.required_stages == ("publication_decided",)
    payload: JsonObject = {
        "schema_version": "1",
        "feed_id": "feed",
        "producer_version": "1",
        "datasets": [],
        "metrics": [],
    }
    prepared = publication.prepare(payload)
    assert isinstance(prepared, PreparedCommand)
    assert prepared.resources == (ResourceRef("feed", "feed"),)
    exact = operations["snapshot.read"].prepare(wire.snapshot_reference_codec().encode(REF))
    assert isinstance(exact, PreparedQuery)
    assert exact.resources == (ResourceRef("snapshot", f"feed:{REF.producer_version}"),)
    assert operations["snapshot.latest"].prepare({"feed_id": "feed"}).resources == (
        ResourceRef("feed", "feed"),
    )


def test_metadata_timestamps_and_nested_fields_are_strict() -> None:
    codec = wire.publication_result_codec()
    summary = SnapshotSummary(REF, 1, 2, 3, 6, 0, 0, STAMP, STAMP)
    raw = codec.encode(
        PublicationResult("accepted", REF, REF, REF, Availability.AVAILABLE, summary)
    )
    from typing import cast

    from craftreport.contracts import JsonObject

    original = dict(cast(JsonObject, raw["summary"]))
    for timestamp in ("2026-01-01T00:00:00.0000001Z", "2026-01-01T00:00:00", 123):
        with pytest.raises(WireFailure):
            codec.decode({**raw, "summary": {**original, "accepted_at": timestamp}})
    with pytest.raises(WireFailure):
        codec.decode({**raw, "summary": {**original, "rows": True}})
    for missing_tag in ({}, {"service": "snapshots"}):
        with pytest.raises(WireFailure):
            wire.snapshot_read_codec().decode(missing_tag)


def test_result_budgets_do_not_truncate_output() -> None:
    from craftreport.data.requirements import BindingIssue

    result = LatestSelection(
        REF,
        Availability.AVAILABLE,
        "none",
        None,
        (BindingIssue(("x" * 1_048_576,), "missing_dataset"),),
    )
    with pytest.raises(WireFailure):
        wire.latest_result_codec().encode(result)
    with pytest.raises(WireFailure):
        wire.snapshot_read_codec().encode(ServiceUnavailable("x" * 1_048_576))
