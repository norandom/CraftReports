"""Real immutable upstream values for the fixed app-profile candidate."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from craftreport.adapters.report_codecs import (
    prepared_identifier,
    theme_identifier,
    validation_scope_identifier,
)
from craftreport.contracts.identity import (
    CapabilityRequirement,
    ExpectedVersion,
    OperationKey,
    ResourceRef,
)
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.pins import VersionPin
from craftreport.data.values import Field, SnapshotRef
from craftreport.policies.evaluate import evaluate
from craftreport.policies.values import (
    CheckId,
    CheckObservation,
    CheckOrigin,
    CheckScope,
    CheckStatus,
    QualityEvaluation,
    ReleasePolicy,
)
from craftreport.reporting.prepared import (
    PreparedColumn,
    PreparedLineChart,
    PreparedReport,
    PreparedSeries,
    PreparedTable,
)
from craftreport.runtime.values import RunPins
from craftreport.themes.values import (
    ChartStyle,
    GridStyle,
    PackPin,
    ResolvedTheme,
    TextStyle,
    Theme,
    ValueFormat,
)
from craftreport.themes.values import (
    SemanticRole as R,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/craftreport-gridcraft/src"))

if TYPE_CHECKING:
    from craftreport_gridcraft.app_values import BrowserTarget


@pytest.fixture
def prepared() -> PreparedReport:
    theme = Theme(
        VersionPin("public/gridcraft-fixed-theme", "1.0.0", "a" * 64),
        tuple(
            (
                r,
                TextStyle(
                    "Arial",
                    11,
                    r in (R.TITLE, R.HEADER, R.DRAFT),
                    False,
                    "#000000",
                    "#DCE6F1" if r in (R.HEADER, R.DRAFT) else None,
                    "left",
                    True,
                ),
            )
            for r in R
        ),
        (ValueFormat("text"), ValueFormat("int64", 2)),
        ChartStyle(("#4472C4",), 2.25, False, False),
        GridStyle(False, 24, 18),
    )
    theme = replace(
        theme, version_pin=replace(theme.version_pin, content_digest=theme_identifier(theme))
    )
    presentation = ResolvedTheme(
        theme.version_pin, theme.styles, theme.formats, theme.chart, theme.grid
    )
    fields = (
        Field("category", "Category", "text", False),
        Field("value", "Value", "int64", False),
        Field("literal", "Literal", "text", False),
    )
    columns = tuple(
        PreparedColumn(f, f.label, role, fmt)
        for f, role, fmt in zip(
            fields,
            (R.ROW_LABEL, R.OUTPUT, R.NOTE),
            (ValueFormat("text"), ValueFormat("int64", 2), ValueFormat("text")),
            strict=True,
        )
    )
    table = PreparedTable(
        "report_table",
        columns,
        (
            ("Alpha", 10, "=1+1"),
            ("Beta", 15, "https://example.invalid/"),
            ("Gamma", 30, "plain"),
            ("Delta", 20, "check"),
        ),
        None,
    )
    chart = PreparedLineChart(
        "report_line",
        fields[0],
        ("Alpha", "Beta", "Gamma", "Delta"),
        (
            PreparedSeries(
                "series",
                "Series",
                Field("series_value", "Series", "int64", True),
                (10, None, 30, 20),
                R.OUTPUT,
                ValueFormat("int64", 2),
            ),
        ),
        "gap",
    )
    pin = VersionPin("public/gridcraft-fixed", "1.0.0", "b" * 64)
    report = PreparedReport(
        "1",
        pin.identity,
        "Supplied series",
        pin,
        pin,
        theme.version_pin,
        PackPin(
            VersionPin("public/gridcraft-fixed-pack", "1.0.0", "c" * 64), "Synthetic", "public"
        ),
        SnapshotRef("supplied", 1, "d" * 64),
        (),
        (table,),
        (chart,),
        presentation,
        tuple(
            CapabilityRequirement(c, ">=1,<2")
            for c in ("report.table", "report.line_chart", "report.semantic_style")
        ),
        (),
        None,
        ReleasePolicy(tuple(CheckId), "Preparation only; no methodology assurance"),
        "e" * 64,
    )
    return replace(report, content_digest=prepared_identifier(report))


@pytest.fixture
def quality(prepared: PreparedReport) -> QualityEvaluation:
    return candidate_quality(prepared)


@pytest.fixture
def quality_factory() -> Callable[[PreparedReport], QualityEvaluation]:
    return lambda prepared: candidate_quality(prepared, "verified_" + "x" * 55)


def candidate_quality(prepared: PreparedReport, reason: str = "observed") -> QualityEvaluation:
    scope = CheckScope(
        prepared.content_digest,
        (
            ExpectedVersion(
                ResourceRef(
                    "snapshot", f"{prepared.snapshot.feed_id}:{prepared.snapshot.producer_version}"
                ),
                prepared.snapshot.content_digest,
            ),
            ExpectedVersion(
                ResourceRef("report_pack_source", "public/gridcraft-fixed-pack@1.0.0"), "source-1"
            ),
            ExpectedVersion(
                ResourceRef("report_pack_artifact_scope", "public/gridcraft-fixed-pack@1.0.0"),
                "scope-1",
            ),
        ),
        None,
        None,
        validation_scope_identifier(prepared.release_policy),
    )
    evidence = EvidenceRef(
        "candidate-preparation",
        "report-check",
        "candidate-operation",
        OperationKey("reports.prepare", "1"),
        scope.resource_versions,
        "a" * 64,
    )
    observations = tuple(
        CheckObservation(c, scope, CheckStatus.PASSED, (evidence,), CheckOrigin.CRAFTREPORT, reason)
        for c in tuple(CheckId)[:3]
    )
    return evaluate(scope, prepared.release_policy, observations, preparation_scope=scope)


@pytest.fixture
def run(prepared: PreparedReport) -> RunPins:
    from profile_cases import candidate_run

    return candidate_run(prepared)


@pytest.fixture
def browser_target(run: RunPins) -> BrowserTarget:
    from craftreport_gridcraft.app_values import BrowserTarget
    from craftreport_gridcraft.values import PROFILE

    return BrowserTarget(
        run.target,
        "deployment",
        "context",
        "page",
        1,
        "http://localhost:8871",
        "ad10af2baf9c7ed4ccbd81e32b37698f5075cdf4f26b726fee7fc7938a3a8d27",
        "cd4d0aa76dfb703870a6b5dbf63c88217221ebb7aac5c491f51c0e1b2d8fcbd9",
        "d1f2cfa583aea14443f0f68ee55403c18296cae237d1cfa7a2fdc3d886d4eb74",
        PROFILE.pin,
        "document-marker",
    )
