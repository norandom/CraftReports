"""Registry fixtures exercise typed preparation without transport or dispatch."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from test_ports import EffectDouble, InspectionDouble, LeaseDouble, ports

from craftreport.application import registry
from craftreport.application.ports import (
    CommandContext,
    CommandServices,
    ReadContext,
    ReadServices,
)
from craftreport.contracts import (
    EffectDisposition,
    EvidencePolicy,
    EvidenceRef,
    JsonObject,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    OperationLimits,
    OutcomeProposal,
    Principal,
    ResourceRef,
    StageResult,
    StageState,
)


@dataclass(frozen=True)
class SetRequest:
    amount: Decimal


class AmountCodec:
    def __init__(self) -> None:
        self.description: JsonObject = {"type": "object", "title": "amount"}
        self.fail_encode = False

    def schema(self) -> JsonObject:
        return self.description

    def decode(self, value: JsonObject) -> SetRequest:
        amount = value.get("amount", "0")
        if not isinstance(amount, str):
            raise ValueError("amount must be a decimal string")
        return SetRequest(Decimal(amount))

    def encode(self, value: SetRequest) -> JsonObject:
        if self.fail_encode:
            raise ValueError("result contract failure")
        return {"amount": str(value.amount)}


class TextCodec:
    def schema(self) -> JsonObject:
        return {"type": "object", "title": "text"}

    def decode(self, value: JsonObject) -> str:
        text = value["text"]
        if not isinstance(text, str):
            raise ValueError("text required")
        return text

    def encode(self, value: str) -> JsonObject:
        return {"text": value}


RESOURCE = ResourceRef("fixture", "target")
KEY = OperationKey("fixture.set", "1")
EVIDENCE = EvidenceRef("proof", "synthetic", "operation", KEY)
STAGE = StageResult("apply", StageState.PASSED, "observed", (EVIDENCE,))


def descriptor(kind: OperationKind = OperationKind.COMMAND) -> OperationDescriptor:
    codec = AmountCodec() if kind is OperationKind.COMMAND else TextCodec()
    return OperationDescriptor(
        KEY if kind is OperationKind.COMMAND else OperationKey("fixture.read", "2"),
        kind,
        codec.schema(),
        codec.schema(),
        kind is OperationKind.COMMAND,
        kind is OperationKind.COMMAND,
        ("fixture",),
        (),
        (),
        OperationLimits(),
        EvidencePolicy(),
    )


def contexts() -> tuple[ReadContext, CommandContext]:
    services = InspectionDouble()
    reads = ReadServices(services, services, services)
    principal = Principal("deployment", "caller", frozenset())
    lease = LeaseDouble(ports.GuardCurrent())
    return (
        ReadContext("operation", principal, reads),
        CommandContext("operation", principal, lease, CommandServices(reads, EffectDouble())),
    )


def command_binding(
    effects: list[Decimal],
    result_codec: AmountCodec | None = None,
) -> registry.OperationBinding[SetRequest, SetRequest]:
    async def handler(request: SetRequest, context: CommandContext) -> OutcomeProposal[SetRequest]:
        effects.append(request.amount)
        return OutcomeProposal(request, EffectDisposition.APPLIED, (STAGE,), (EVIDENCE,))

    def resources(request: SetRequest) -> tuple[ResourceRef, ...]:
        assert not effects
        return (RESOURCE,)

    return registry.OperationBinding(
        descriptor(),
        AmountCodec(),
        result_codec or AmountCodec(),
        registry.CommandBehavior(handler),
        resources,
    )


def query_binding(observed: list[str]) -> registry.OperationBinding[str, str]:
    async def handler(request: str, context: ReadContext) -> str:
        assert isinstance(context, ReadContext)
        observed.append(request)
        return request.upper()

    return registry.OperationBinding(
        descriptor(OperationKind.QUERY),
        TextCodec(),
        TextCodec(),
        registry.QueryBehavior(handler),
        lambda request: (RESOURCE,),
    )


def test_feature_catalog_available() -> None:
    assert registry.ImmutableOperationRegistry(()).describe() == ()


def test_distinct_bindings_prepare_and_invoke_with_exact_lookup() -> None:
    effects: list[Decimal] = []
    observed: list[str] = []
    catalog = registry.ImmutableOperationRegistry(
        (command_binding(effects).bind(), query_binding(observed).bind())
    )
    assert tuple(item.key.name for item in catalog.describe()) == ("fixture.read", "fixture.set")
    assert catalog.resolve("fixture.set", "2") is None
    assert catalog.resolve("missing", "1") is None
    read, command = contexts()
    bound = catalog.resolve("fixture.set", "1")
    assert bound is not None
    prepared = bound.prepare({})
    assert isinstance(prepared, registry.PreparedCommand)
    assert prepared.canonical_content == {"amount": "0"}
    assert prepared.resources == (RESOURCE,)
    assert effects == []
    result = asyncio.run(prepared.invoke(command))
    assert effects == [Decimal(0)]
    assert result.encode_result() == {"amount": "0"}
    assert result.effect is EffectDisposition.APPLIED
    query = catalog.resolve("fixture.read", "2")
    assert query is not None
    query_call = query.prepare({"text": "hello"})
    assert isinstance(query_call, registry.PreparedQuery)
    assert observed == []
    query_result = asyncio.run(query_call.invoke(read))
    assert query_result.encode_result() == {"text": "HELLO"}
    assert observed == ["hello"]


def test_encoding_failure_preserves_command_observation() -> None:
    effects: list[Decimal] = []
    codec = AmountCodec()
    prepared = command_binding(effects, codec).bind().prepare({"amount": "1.25"})
    assert isinstance(prepared, registry.PreparedCommand)
    result = asyncio.run(prepared.invoke(contexts()[1]))
    codec.fail_encode = True
    with pytest.raises(ValueError, match="result contract"):
        result.encode_result()
    assert effects == [Decimal("1.25")]
    assert result.effect is EffectDisposition.APPLIED
    assert result.stages == (STAGE,)
    assert result.evidence == (EVIDENCE,)


def test_invalid_input_never_invokes_behavior() -> None:
    effects: list[Decimal] = []
    with pytest.raises(ValueError, match="decimal string"):
        command_binding(effects).bind().prepare({"amount": 12})
    assert effects == []


def test_catalog_rejects_duplicates_and_advertisement_mismatch() -> None:
    binding = command_binding([]).bind()
    with pytest.raises(ValueError, match="Duplicate"):
        registry.ImmutableOperationRegistry((binding, binding))
    incompatible = replace(descriptor(), limits=OperationLimits(max_output_bytes=100))
    with pytest.raises(ValueError, match="advertised"):
        registry.ImmutableOperationRegistry((binding,), (incompatible,))
    with pytest.raises(ValueError, match="advertised"):
        registry.ImmutableOperationRegistry((binding,), ())
    assert registry.ImmutableOperationRegistry((binding,), (descriptor(),)).describe() == (
        descriptor(),
    )


def test_classification_and_codec_schema_mismatch_rejected() -> None:
    binding = command_binding([])
    with pytest.raises(ValueError, match="classification"):
        replace(binding, descriptor=descriptor(OperationKind.QUERY)).bind()
    for field in ("input_schema", "result_schema"):
        with pytest.raises(ValueError, match="schema"):
            changed = replace(descriptor(), **{field: {"title": "wrong"}})
            replace(binding, descriptor=changed).bind()
    with pytest.raises(ValueError, match="command"):
        replace(descriptor(), kind=OperationKind.QUERY)


def test_catalog_owns_immutable_snapshot() -> None:
    codec = AmountCodec()
    binding = replace(command_binding([]), input_codec=codec)
    items = [binding.bind()]
    catalog = registry.ImmutableOperationRegistry(items)
    items.clear()
    codec.description = {"title": "changed"}
    assert catalog.describe() == (descriptor(),)
    with pytest.raises(FrozenInstanceError):
        setattr(catalog, "_operations", ())


@pytest.mark.parametrize("resources", [(RESOURCE, RESOURCE), (ResourceRef("other", "id"),)])
def test_invalid_resource_extraction_blocks_behavior(resources: tuple[ResourceRef, ...]) -> None:
    effects: list[Decimal] = []

    def extract(request: SetRequest) -> tuple[ResourceRef, ...]:
        return resources

    binding = replace(command_binding(effects), resource_refs=extract)
    with pytest.raises(ValueError):
        binding.bind().prepare({})
    assert effects == []


def test_wrong_context_never_reaches_behavior() -> None:
    observed: list[str] = []
    effects: list[Decimal] = []
    query = query_binding(observed).bind().prepare({"text": "value"})
    command = command_binding(effects).bind().prepare({})
    assert isinstance(query, registry.PreparedQuery)
    assert isinstance(command, registry.PreparedCommand)
    read_context, command_context = contexts()
    with pytest.raises(TypeError, match="ReadContext"):
        asyncio.run(query.invoke(cast(ReadContext, cast(object, command_context))))
    with pytest.raises(TypeError, match="CommandContext"):
        asyncio.run(command.invoke(cast(CommandContext, cast(object, read_context))))
    assert observed == effects == []


def test_pending_observation_retains_missing_result_and_handoff() -> None:
    async def handler(request: SetRequest, context: CommandContext) -> OutcomeProposal[SetRequest]:
        return OutcomeProposal(None, EffectDisposition.UNKNOWN, (), (), handoff_ref="job-1")

    binding = replace(command_binding([]), behavior=registry.CommandBehavior(handler))
    prepared = binding.bind().prepare({})
    assert isinstance(prepared, registry.PreparedCommand)
    observed = asyncio.run(prepared.invoke(contexts()[1]))
    assert observed.encode_result() is None
    assert observed.effect is EffectDisposition.UNKNOWN
    assert observed.handoff_ref == "job-1"


def test_strict_typing_rejects_mismatched_codec_handler_and_context(tmp_path: Path) -> None:
    fixture = tmp_path / "invalid_bindings.py"
    fixture.write_text(
        """from craftreport.application.registry import (
    Codec, CommandBehavior, OperationBinding, PreparedQuery, QueryBehavior,
)
from craftreport.application.ports import CommandContext, ReadContext
from craftreport.contracts import OperationDescriptor, OutcomeProposal
async def command(request: int, context: CommandContext) -> OutcomeProposal[str]:
    raise NotImplementedError
async def query(request: str, context: ReadContext) -> str:
    return request
def invalid(desc: OperationDescriptor, numbers: Codec[int], words: Codec[str]) -> None:
    a: OperationBinding[int, str] = OperationBinding(
        desc, words, words, CommandBehavior(command), lambda request: ())
    b: OperationBinding[int, str] = OperationBinding(
        desc, numbers, numbers, CommandBehavior(command), lambda request: ())
    c: OperationBinding[int, str] = OperationBinding(
        desc, numbers, words, QueryBehavior(query), lambda request: ())
    d: QueryBehavior[int, str] = QueryBehavior(command)
    print(a, b, c, d)
async def invalid_context(call: PreparedQuery, context: CommandContext) -> None:
    await call.invoke(context)
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "--project",
            "pyproject.toml",
            "--outputjson",
            str(fixture),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 1, completed.stdout + completed.stderr
    diagnostics = report["generalDiagnostics"]
    lines = {entry["range"]["start"]["line"] for entry in diagnostics}
    for invalid_lines in ({10, 11}, {12, 13}, {14, 15}, {16}, {19}):
        assert invalid_lines & lines, diagnostics
    assert all(entry["rule"] != "reportMissingImports" for entry in diagnostics), diagnostics
