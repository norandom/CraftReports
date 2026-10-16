"""Immutable operation registration and typed preparation boundary.

Preparation is internal to the fixed dispatcher pipeline, after coarse access
checks. It neither authorizes work nor grants a way to reorder shared guards.
Codecs and resource extractors are trusted capability code; extractors must be
pure. Wire limits/canonical fingerprints belong to the codec/dispatcher tasks.
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from typing import Protocol

from craftreport.application.ports import CommandContext, ReadContext
from craftreport.application.service_values import DiagnosticPolicy
from craftreport.contracts import (
    Diagnostic,
    EffectDisposition,
    EvidenceRef,
    JsonObject,
    OperationDescriptor,
    OperationKind,
    OutcomeProposal,
    Principal,
    ResourceRef,
    StageResult,
)
from craftreport.contracts.values import freeze_object, require_immutable, require_unique


class Codec[T](Protocol):
    def decode(self, value: JsonObject) -> T: ...
    def encode(self, value: T) -> JsonObject: ...
    def schema(self) -> JsonObject: ...


class QueryHandler[Q, R](Protocol):
    async def __call__(self, request: Q, context: ReadContext) -> R: ...


class CommandHandler[Q, R](Protocol):
    async def __call__(self, request: Q, context: CommandContext) -> OutcomeProposal[R]: ...


@dataclass(frozen=True, slots=True)
class QueryBehavior[Q, R]:
    handler: QueryHandler[Q, R]


@dataclass(frozen=True, slots=True)
class CommandBehavior[Q, R]:
    handler: CommandHandler[Q, R]
    eligibility: Callable[[Q, Principal], Awaitable[Diagnostic | None]] | None = None


@dataclass(frozen=True, slots=True)
class ObservedQuery:
    encode_result: Callable[[], JsonObject]


@dataclass(frozen=True, slots=True)
class ObservedCommand:
    """Keep observations available even if later result conversion raises.

    OutcomeRules owns failure classification and canonical completion; encoding
    is deliberately separate from observing behavior and never replays it.
    """

    effect: EffectDisposition
    stages: tuple[StageResult, ...]
    evidence: tuple[EvidenceRef, ...]
    diagnostics: tuple[Diagnostic, ...]
    handoff_ref: str | None
    encode_result: Callable[[], JsonObject | None]


@dataclass(frozen=True, slots=True)
class PreparedQuery:
    canonical_content: JsonObject
    resources: tuple[ResourceRef, ...]
    _invoke: Callable[[ReadContext], Awaitable[ObservedQuery]]

    async def invoke(self, context: ReadContext) -> ObservedQuery:
        if type(context) is not ReadContext:
            raise TypeError("Query invocation requires ReadContext")
        return await self._invoke(context)


@dataclass(frozen=True, slots=True)
class PreparedCommand:
    canonical_content: JsonObject
    resources: tuple[ResourceRef, ...]
    _invoke: Callable[[CommandContext], Awaitable[ObservedCommand]]
    eligibility: Callable[[Principal], Awaitable[Diagnostic | None]] | None = None

    async def invoke(self, context: CommandContext) -> ObservedCommand:
        if type(context) is not CommandContext:
            raise TypeError("Command invocation requires CommandContext")
        return await self._invoke(context)


type PreparedCall = PreparedQuery | PreparedCommand


@dataclass(frozen=True, slots=True)
class BoundOperation:
    descriptor: OperationDescriptor
    _prepare: Callable[[JsonObject], PreparedCall]
    diagnostic_policy: DiagnosticPolicy = DiagnosticPolicy()

    def prepare(self, payload: JsonObject) -> PreparedCall:
        return self._prepare(payload)


def _observed_command[R](proposal: OutcomeProposal[R], codec: Codec[R]) -> ObservedCommand:
    def encode() -> JsonObject | None:
        return None if proposal.result is None else freeze_object(codec.encode(proposal.result))

    return ObservedCommand(
        proposal.effect,
        proposal.stages,
        proposal.evidence,
        proposal.diagnostics,
        proposal.handoff_ref,
        encode,
    )


@dataclass(frozen=True, slots=True)
class OperationBinding[Q, R]:
    """Retains the request/result pair through conversion and typed invocation."""

    descriptor: OperationDescriptor
    input_codec: Codec[Q]
    result_codec: Codec[R]
    behavior: QueryBehavior[Q, R] | CommandBehavior[Q, R]
    resource_refs: Callable[[Q], tuple[ResourceRef, ...]]
    diagnostic_policy: DiagnosticPolicy = DiagnosticPolicy()

    def bind(self) -> BoundOperation:
        descriptor = replace(self.descriptor)
        expected = (
            OperationKind.QUERY
            if isinstance(self.behavior, QueryBehavior)
            else OperationKind.COMMAND
        )
        if descriptor.kind is not expected:
            raise ValueError("Handler classification does not match descriptor")
        if freeze_object(self.input_codec.schema()) != descriptor.input_schema:
            raise ValueError("Input codec schema does not match descriptor")
        if freeze_object(self.result_codec.schema()) != descriptor.result_schema:
            raise ValueError("Result codec schema does not match descriptor")
        return BoundOperation(descriptor, self._prepare, self.diagnostic_policy)

    def _prepare(self, payload: JsonObject) -> PreparedCall:
        request = self.input_codec.decode(freeze_object(payload))
        require_immutable(request)
        canonical = freeze_object(self.input_codec.encode(request))
        resources = tuple(self.resource_refs(request))
        require_unique(resources, "prepared resources")
        if any(resource.kind not in self.descriptor.resources for resource in resources):
            raise ValueError("Resource extractor returned an undeclared resource kind")
        behavior = self.behavior
        if isinstance(behavior, QueryBehavior):
            return self._query_call(request, canonical, resources, behavior)
        return self._command_call(request, canonical, resources, behavior)

    def _query_call(
        self,
        request: Q,
        canonical: JsonObject,
        resources: tuple[ResourceRef, ...],
        behavior: QueryBehavior[Q, R],
    ) -> PreparedQuery:
        async def invoke(context: ReadContext) -> ObservedQuery:
            result = await behavior.handler(request, context)
            return ObservedQuery(lambda: freeze_object(self.result_codec.encode(result)))

        return PreparedQuery(canonical, resources, invoke)

    def _command_call(
        self,
        request: Q,
        canonical: JsonObject,
        resources: tuple[ResourceRef, ...],
        behavior: CommandBehavior[Q, R],
    ) -> PreparedCommand:
        async def invoke(context: CommandContext) -> ObservedCommand:
            proposal = await behavior.handler(request, context)
            return _observed_command(proposal, self.result_codec)

        callback = behavior.eligibility
        return PreparedCommand(
            canonical,
            resources,
            invoke,
            (lambda principal: callback(request, principal)) if callback is not None else None,
        )


class OperationRegistry(Protocol):
    def resolve(self, name: str, version: str) -> BoundOperation | None: ...
    def describe(self) -> tuple[OperationDescriptor, ...]: ...


def _descriptor_key(descriptor: OperationDescriptor) -> tuple[str, str]:
    return descriptor.key.name, descriptor.key.contract_version


@dataclass(frozen=True, slots=True, init=False)
class ImmutableOperationRegistry:
    """Activation snapshot; authorized visibility is the facade's responsibility."""

    _operations: tuple[BoundOperation, ...]

    def __init__(
        self,
        operations: Iterable[BoundOperation],
        advertised: Iterable[OperationDescriptor] | None = None,
    ) -> None:
        ordered = tuple(sorted(operations, key=lambda item: _descriptor_key(item.descriptor)))
        keys = tuple(_descriptor_key(item.descriptor) for item in ordered)
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate operation/version key")
        if advertised is not None:
            descriptions = tuple(sorted(advertised, key=_descriptor_key))
            if descriptions != tuple(item.descriptor for item in ordered):
                raise ValueError("Bindings do not match advertised operation descriptors")
        object.__setattr__(self, "_operations", ordered)

    def resolve(self, name: str, version: str) -> BoundOperation | None:
        return next(
            (
                item
                for item in self._operations
                if _descriptor_key(item.descriptor) == (name, version)
            ),
            None,
        )

    def describe(self) -> tuple[OperationDescriptor, ...]:
        return tuple(item.descriptor for item in self._operations)
