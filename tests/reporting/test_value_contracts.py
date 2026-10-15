"""Closed immutable presentation and scoped evidence contracts."""

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, replace
from typing import Literal, cast

import pytest

from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.policies import values as policies
from craftreport.themes import values as themes

DIGEST = "a" * 64


@pytest.fixture
def scope() -> policies.CheckScope:
    return policies.CheckScope(
        DIGEST,
        (ExpectedVersion(ResourceRef("snapshot", "feed:one"), "1"),),
        None,
        None,
        "b" * 64,
    )


@pytest.fixture
def evidence(scope: policies.CheckScope) -> EvidenceRef:
    return EvidenceRef(
        "producer-claim",
        "portfolio-q3",
        "operation-1",
        OperationKey("reports.prepare", "1"),
        scope.resource_versions,
        DIGEST,
    )


@pytest.fixture
def theme() -> themes.Theme:
    style = themes.TextStyle("Arial", 11, False, False, "#112233", None, "left", True)
    return themes.Theme(
        VersionPin("public/house", "1.0.0", DIGEST),
        tuple((role, style) for role in themes.SemanticRole),
        (themes.ValueFormat("decimal", 2),),
        themes.ChartStyle(("#112233", "#445566"), 2, True, True),
        themes.GridStyle(False, 24, 18),
        ((themes.SemanticRole.HEADER, "color"),),
    )


def test_closed_semantic_roles_and_independent_dimension_status() -> None:
    assert {role.value for role in themes.SemanticRole} == {
        "title",
        "header",
        "row_label",
        "source",
        "input",
        "constant",
        "external_result",
        "output",
        "key_result",
        "note",
        "check_pass",
        "check_warn",
        "check_fail",
        "draft",
    }
    assert {item.value for item in policies.QualityDimension} == {
        "layout",
        "template",
        "consistency",
        "compliance",
        "accuracy",
    }
    assert {item.value for item in policies.CheckStatus} == {
        "passed",
        "failed",
        "unevaluated",
        "not_applicable",
    }


def test_theme_preserves_presentation_and_is_recursively_frozen(theme: themes.Theme) -> None:
    require_immutable(theme)
    assert theme.formats[0].negative_style == "leading_minus"
    assert theme.null_marker == "—"
    with pytest.raises(FrozenInstanceError):
        setattr(theme.grid, "column_width", 20)
    resolved = themes.ResolvedTheme(
        theme.version_pin,
        theme.styles,
        theme.formats,
        theme.chart,
        theme.grid,
    )
    require_immutable(resolved)
    assert resolved.styles == theme.styles


def test_theme_requires_complete_unique_roles_and_closed_overrides(theme: themes.Theme) -> None:
    with pytest.raises(ValueError):
        replace(theme, styles=theme.styles[:-1])
    with pytest.raises(ValueError):
        replace(theme, styles=theme.styles + (theme.styles[0],))
    with pytest.raises(ValueError):
        replace(
            theme,
            permitted_overrides=((themes.SemanticRole.HEADER, cast(themes.StyleProperty, "css")),),
        )
    with pytest.raises(ValueError):
        replace(theme, permitted_overrides=theme.permitted_overrides * 2)
    with pytest.raises((TypeError, ValueError)):
        replace(
            theme,
            styles=cast(
                tuple[tuple[themes.SemanticRole, themes.TextStyle], ...], list(theme.styles)
            ),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"color": "url(remote)"},
        {"size_pt": True},
        {"size_pt": float("nan")},
        {"alignment": "arbitrary"},
        {"font_family": "x" * 1000},
        {"wrap": 1},
    ],
)
def test_style_rejects_unsupported_or_unbounded_values(changes: dict[str, object]) -> None:
    style = themes.TextStyle("Arial", 11, False, False, "#112233", None, "left", True)
    with pytest.raises((TypeError, ValueError)):
        replace(style, **changes)


@pytest.mark.parametrize(
    "format",
    [
        ("decimal", -1, None),
        ("text", 2, None),
        ("date", 2, "yyyy-mm-dd"),
        ("decimal", None, "yyyy-mm-dd"),
        ("date", None, "x" * 1000),
    ],
)
def test_formats_reject_incompatible_fields(format: tuple[str, int | None, str | None]) -> None:
    kind, places, pattern = format
    with pytest.raises(ValueError):
        themes.ValueFormat(cast(themes.FormatKind, kind), places, pattern)


def test_pack_pin_keeps_version_attribution_and_distribution_separate() -> None:
    pin = VersionPin("public/house", "1.0.0", DIGEST)
    pack = themes.PackPin(pin, "Example author", "artifact:public")
    assert pack.version_pin is pin
    assert pack.artifact_visibility_scope == "artifact:public"
    require_immutable(pack)
    with pytest.raises(ValueError):
        replace(pack, attribution="界" * 512)
    with pytest.raises(ValueError):
        replace(pack, artifact_visibility_scope="x" * 129)


def test_scope_pins_are_exact_immutable_and_changed_scope_differs(
    scope: policies.CheckScope,
) -> None:
    require_immutable(scope)
    assert replace(scope, content_digest="c" * 64) != scope
    assert replace(scope, target=ExpectedVersion(ResourceRef("document", "doc:1"), "2")) != scope
    with pytest.raises(ValueError):
        replace(scope, content_digest="not-a-digest")
    with pytest.raises(ValueError):
        replace(scope, resource_versions=scope.resource_versions * 2)
    with pytest.raises((TypeError, ValueError)):
        replace(scope, resource_versions=cast(tuple[ExpectedVersion, ...], []))
    with pytest.raises(ValueError):
        replace(
            scope, resource_versions=(ExpectedVersion(ResourceRef("snapshot", "x" * 4000), "1"),)
        )


def test_external_statement_preserves_supplied_scope_issuer_and_evidence(
    evidence: EvidenceRef,
) -> None:
    statement = policies.ExternalStatement(
        "Producer claim only", "Fund A Q3", "Producer", (evidence,)
    )
    require_immutable(statement)
    assert statement.scope == "Fund A Q3"
    assert statement.evidence == (evidence,)
    for changes in ({"scope": ""}, {"issuer": ""}, {"evidence": ()}, {"text": "界" * 32768}):
        with pytest.raises(ValueError):
            replace(statement, **changes)


def test_observation_and_finding_retain_external_origin_without_method_assurance(
    scope: policies.CheckScope,
    evidence: EvidenceRef,
) -> None:
    observation = policies.CheckObservation(
        policies.CheckId.COMPLIANCE_STATEMENT,
        scope,
        policies.CheckStatus.UNEVALUATED,
        (evidence,),
        policies.CheckOrigin.EXTERNAL,
        "supplied_statement",
    )
    finding = policies.Finding(
        observation.check_id,
        policies.QualityDimension.COMPLIANCE,
        observation.status,
        scope,
        observation.evidence,
        observation.origin,
        observation.reason_code,
    )
    require_immutable(finding)
    assert finding.origin is policies.CheckOrigin.EXTERNAL
    assert finding.status is policies.CheckStatus.UNEVALUATED
    with pytest.raises(ValueError):
        replace(finding, dimension=policies.QualityDimension.ACCURACY)
    with pytest.raises(ValueError):
        replace(finding, evidence=(evidence,) * 9)
    with pytest.raises(ValueError):
        replace(finding, reason_code="unbounded " * 1000)


def test_release_policy_is_closed_unique_membership() -> None:
    policy = policies.ReleasePolicy((policies.CheckId.DEFINITION,), "Report preparation")
    require_immutable(policy)
    with pytest.raises(ValueError):
        replace(policy, required_checks=policy.required_checks * 2)
    with pytest.raises(ValueError):
        replace(policy, required_checks=(cast(policies.CheckId, "arbitrary_plugin"),))


def test_quality_result_is_bounded_and_cannot_claim_release_with_blockers(
    scope: policies.CheckScope,
) -> None:
    dimensions = {
        "definition": "template",
        "bindings": "template",
        "semantic_resolution": "template",
        "layout_fit": "layout",
        "target_consistency": "consistency",
        "artifact_consistency": "consistency",
        "artifact_reopen": "consistency",
        "metric_methodology": "accuracy",
        "compliance_statement": "compliance",
    }
    findings = tuple(
        policies.Finding(
            check,
            policies.QualityDimension(dimensions[check.value]),
            policies.CheckStatus.UNEVALUATED,
            scope,
            (),
            policies.CheckOrigin.CRAFTREPORT,
            "not_executed",
        )
        for check in policies.CheckId
    )
    quality = policies.QualityEvaluation(
        findings,
        True,
        False,
        (policies.CheckId.LAYOUT_FIT,),
        "Report only",
        "DRAFT",
        "layout_fit: unevaluated",
    )
    require_immutable(quality)
    assert len(quality.findings) == 9
    with pytest.raises(ValueError):
        replace(quality, validated_release_eligible=True)
    with pytest.raises(ValueError):
        replace(quality, findings=findings + (findings[0],))
    with pytest.raises(ValueError):
        replace(quality, draft_designation="")


def test_values_import_without_reporting_runtime_framework_or_adapters() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import craftreport.themes.values; "
            "import craftreport.policies.values; "
            "assert not any(name.startswith(('craftreport.reporting', 'craftreport.runtime', "
            "'craftreport.adapters', 'pydantic', 'fastapi')) for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_serialized_limits_account_for_unicode_and_escaping(
    theme: themes.Theme,
    scope: policies.CheckScope,
    evidence: EvidenceRef,
) -> None:
    assert len(json.dumps(asdict(theme), ensure_ascii=False).encode()) < 32768
    with pytest.raises(ValueError):
        replace(theme, version_pin=VersionPin('"' * 20000, "1", DIGEST))
    with pytest.raises(ValueError):
        replace(
            scope,
            resource_versions=tuple(
                ExpectedVersion(ResourceRef("snapshot", str(index) + "x" * 700), "1")
                for index in range(5)
            ),
        )
    with pytest.raises(ValueError):
        policies.ExternalStatement(
            "claim", "scope", "issuer", (replace(evidence, scope="界" * 1100),)
        )


def test_closed_override_and_format_values(theme: themes.Theme) -> None:
    override = themes.StyleOverride(themes.SemanticRole.INPUT, "color", "#445566")
    require_immutable(override)
    with pytest.raises(ValueError):
        replace(override, value="execute()")
    with pytest.raises(ValueError):
        replace(override, property_name=cast(themes.StyleProperty, "css"))
    assert themes.ValueFormat("date", date_pattern="yyyy-mm-dd").kind == "date"
    with pytest.raises(ValueError):
        replace(theme.chart, line_width=float("inf"))


def test_direct_style_values_reject_mutable_string_subclasses() -> None:
    class MutableText(str):
        pass

    alignment = MutableText("left")
    setattr(alignment, "caller_owned", [])
    with pytest.raises(TypeError):
        themes.TextStyle(
            "Arial",
            11,
            False,
            False,
            "#112233",
            None,
            cast(Literal["left", "center", "right"], alignment),
            True,
        )
    with pytest.raises(TypeError):
        themes.ValueFormat(cast(themes.FormatKind, MutableText("decimal")), 2)


@pytest.mark.parametrize("value", ["x" * 126, "界" * 42, '"' * 63])
@pytest.mark.parametrize("field", ["identity", "version"])
@pytest.mark.parametrize("wrapper", ["theme", "resolved", "pack"])
def test_theme_pack_version_identifiers_have_exact_serialized_bounds(
    theme: themes.Theme,
    value: str,
    field: str,
    wrapper: str,
) -> None:
    original: themes.Theme | themes.ResolvedTheme | themes.PackPin = theme
    if wrapper == "resolved":
        original = themes.ResolvedTheme(
            theme.version_pin,
            theme.styles,
            theme.formats,
            theme.chart,
            theme.grid,
        )
    elif wrapper == "pack":
        original = themes.PackPin(theme.version_pin, "Public example", "artifact:public")
    assert len(json.dumps(value, ensure_ascii=False).encode("utf-8")) == 128
    accepted_pin = replace(theme.version_pin, **{field: value})
    assert replace(original, version_pin=accepted_pin).version_pin is accepted_pin
    # Generic upstream pins remain valid; the reporting wrapper owns its bound.
    rejected_pin = replace(theme.version_pin, **{field: value + "x"})
    with pytest.raises(ValueError):
        replace(original, version_pin=rejected_pin)
    with pytest.raises(ValueError):
        replace(original, version_pin=replace(theme.version_pin, **{field: "x" * 100000}))
