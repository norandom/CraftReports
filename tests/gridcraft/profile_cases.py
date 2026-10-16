"""Task4 synthetic boundary inputs, paired evaluator output and fixed geometry oracle."""

import io
import json
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256

from craftreport_gridcraft.values import MappingPlan
from craftreport_gridcraft.workbook import (
    _candidate_mapping,  # pyright: ignore[reportPrivateUsage] -- isolated profile test
)

from craftreport.adapters.binding_codecs import parameter_digest
from craftreport.adapters.report_codecs import prepared_identifier, validation_scope_identifier
from craftreport.data.values import SnapshotRef
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins, TargetIdentity


def candidate_run(prepared: PreparedReport, run_id: str = "run-1") -> RunPins:
    return RunPins(
        run_id,
        "binding-1",
        1,
        prepared.snapshot,
        prepared.definition,
        prepared.template,
        prepared.theme,
        prepared.pack.version_pin,
        prepared.resolved_parameters,
        parameter_digest(prepared.resolved_parameters),
        validation_scope_identifier(prepared.release_policy),
        "prepare-1",
        "result-1",
        prepared.content_digest,
        TargetIdentity("gridcraft", "browser", "session-1", "document-1"),
    )


def boundary_plans(
    initial: MappingPlan,
    quality: Callable[[PreparedReport], QualityEvaluation],
) -> tuple[MappingPlan, ...]:
    cases = (
        (
            ("W" * 14, "é" * 7, "Gamma", "Delta"),
            (0, 1, 9999, 5000),
            ('"\\quoted', "https://example.invalid/", "é" * 15, "W" * 30),
        ),
        (
            ('"\\' + "W" * 10, "Beta", "Gamma", "Delta"),
            (1, 9999, 0, 15),
            ("=1+1", "https://example.invalid/", "x" * 30, '"\\quoted'),
        ),
    )
    output: list[MappingPlan] = []
    for version, (categories, values, literals) in enumerate(cases, 2):
        source = initial.prepared
        rows = tuple(zip(categories, values, literals, strict=True))
        series = replace(source.charts[0].series[0], values=(values[0], None, values[2], values[3]))
        report = replace(
            source,
            tables=(replace(source.tables[0], rows=rows),),
            charts=(replace(source.charts[0], categories=categories, series=(series,)),),
            snapshot=SnapshotRef(
                "supplied", version, sha256(json.dumps(rows).encode()).hexdigest()
            ),
        )
        report = replace(report, content_digest=prepared_identifier(report))
        layout = replace(
            initial.layout,
            run=replace(candidate_run(report, f"run-{version}"), target=initial.layout.run.target),
        )
        mapped = _candidate_mapping(report, quality(report), layout)
        assert isinstance(mapped, MappingPlan)
        output.append(mapped)
    return tuple(output)


def drawing_signature(data: bytes) -> str:
    """Exact fixed chart anchor plus actual outside object preserved after initial import."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ET.fromstring(archive.read("xl/drawings/drawing1.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"}
    chart = list(root)[0]
    actual = tuple(
        int(chart.findtext(f"x:{side}/x:{field}", namespaces=ns) or "-1")
        for side in ("from", "to")
        for field in ("col", "colOff", "row", "rowOff")
    )
    assert actual == (0, 0, 17, 0, 5, 161925, 34, 57150), actual
    assert 0 <= actual[0] <= actual[4] < 8 and 17 <= actual[2] <= actual[6] < 38
    assert len(root) == 2
    outside = ET.tostring(list(root)[1]).decode()
    assert "SAFE" in outside
    return outside


def metadata_expected(plan: MappingPlan) -> dict[str, str]:
    """Independent metadata oracle derived from authoritative input pins, never mapped cells."""
    run, layout, quality = plan.layout.run, plan.layout, plan.quality
    entries = (
        ("document", layout.document_marker, None),
        ("run", run.run_id, None),
        (
            "snapshot",
            f"{run.snapshot.feed_id}@{run.snapshot.producer_version}",
            run.snapshot.content_digest,
        ),
        ("prepared", run.prepared_digest, None),
        *(
            (label, f"{pin.identity}@{pin.version}", pin.content_digest)
            for label, pin in zip(
                ("definition", "template", "theme", "pack", "profile"),
                (run.definition, run.template, run.theme, run.pack, layout.profile.pin),
                strict=True,
            )
        ),
        ("designation", quality.draft_designation, None),
        ("summary_sha256", sha256(quality.validation_summary.encode()).hexdigest(), None),
        ("quality_scope", quality.scope_label, None),
    )
    result: dict[str, str] = {}
    for row, (label, value, digest) in enumerate(entries, 1):
        result.update({f"J{row}": label, f"K{row}": value})
        if digest is not None:
            result[f"L{row}"] = digest
    return result
