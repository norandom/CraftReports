"""Versioned publication registrations with injected codecs and real handlers."""

from dataclasses import dataclass, replace
from typing import cast

from craftreport.application.ports import Missing, ReadContext, ServiceUnavailable, VersionConflict
from craftreport.application.registry import (
    BoundOperation,
    Codec,
    CommandBehavior,
    OperationBinding,
    QueryBehavior,
)
from craftreport.contracts import (
    EvidencePolicy,
    JsonObject,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    OperationLimits,
    ResourceRef,
)
from craftreport.data.values import Snapshot, SnapshotRef
from craftreport.runtime.bindings import BindingOperations
from craftreport.runtime.publication import (
    LatestRequest,
    LatestSelection,
    PublicationOperations,
    PublicationResult,
)
from craftreport.runtime.values import BindingState, BindRequest, InspectRequest, RunPins


@dataclass(frozen=True, slots=True)
class BindingCodecs:
    request: Codec[BindRequest]
    inspect: Codec[InspectRequest]
    result: Codec[BindingState | RunPins | Missing | VersionConflict | ServiceUnavailable]


def binding_descriptors(codecs: BindingCodecs) -> tuple[OperationDescriptor, ...]:
    return (
        OperationDescriptor(
            OperationKey("runtime.bind", "1"),
            OperationKind.COMMAND,
            codecs.request.schema(),
            codecs.result.schema(),
            True,
            True,
            ("binding", "feed"),
            (),
            ("journal", "guard", "resources", "effects", "evidence", "results"),
            OperationLimits(),
            EvidencePolicy(("binding_persisted",)),
        ),
        replace(
            _descriptor(
                "runtime.inspect",
                codecs.inspect,
                codecs.result,
                False,
                "binding",
                OperationLimits(),
            ),
            resources=("binding", "run"),
        ),
    )


def binding_operations(
    handlers: BindingOperations, codecs: BindingCodecs
) -> tuple[BoundOperation, ...]:
    descriptors = binding_descriptors(codecs)
    return (
        OperationBinding(
            descriptors[0],
            codecs.request,
            codecs.result,
            CommandBehavior(handlers.bind),
            lambda v: (
                ResourceRef("binding", v.spec.binding_id),
                ResourceRef("feed", v.spec.feed_id),
            ),
        ).bind(),
        OperationBinding(
            descriptors[1],
            codecs.inspect,
            codecs.result,
            QueryBehavior(handlers.inspect),
            lambda v: (ResourceRef(v.kind, v.identity),),
        ).bind(),
    )


@dataclass(frozen=True, slots=True)
class PublicationCodecs:
    publication: Codec[JsonObject]
    publication_result: Codec[PublicationResult]
    reference: Codec[SnapshotRef]
    read_result: Codec[Snapshot | Missing | VersionConflict | ServiceUnavailable]
    latest_request: Codec[LatestRequest]
    latest_result: Codec[LatestSelection | Missing | ServiceUnavailable]


def _descriptor[Q, R](
    name: str,
    request: Codec[Q],
    result: Codec[R],
    command: bool,
    resource: str,
    limits: OperationLimits,
) -> OperationDescriptor:
    return OperationDescriptor(
        OperationKey(name, "1"),
        OperationKind.COMMAND if command else OperationKind.QUERY,
        request.schema(),
        result.schema(),
        command,
        command,
        (resource,),
        (),
        ("journal", "guard", "resources", "effects", "evidence", "results")
        if command
        else ("resources",),
        limits,
        EvidencePolicy(("publication_decided",) if command else ()),
    )


def publication_descriptors(
    codecs: PublicationCodecs, limits: OperationLimits = OperationLimits()
) -> tuple[OperationDescriptor, ...]:
    return (
        _descriptor(
            "snapshot.publish", codecs.publication, codecs.publication_result, True, "feed", limits
        ),
        _descriptor(
            "snapshot.read", codecs.reference, codecs.read_result, False, "snapshot", limits
        ),
        _descriptor(
            "snapshot.latest", codecs.latest_request, codecs.latest_result, False, "feed", limits
        ),
    )


def publication_operations(
    handlers: PublicationOperations,
    codecs: PublicationCodecs,
    limits: OperationLimits = OperationLimits(),
) -> tuple[BoundOperation, ...]:
    if (
        limits.max_input_bytes > 1_048_576
        or limits.max_output_bytes > 1_048_576
        or limits.max_nesting_depth > 32
    ):
        raise ValueError("Publication limits may only lower the advertised profile")

    async def latest(
        request: LatestRequest, context: ReadContext
    ) -> LatestSelection | Missing | ServiceUnavailable:
        result = await handlers.latest(request, context)
        try:
            codecs.latest_result.encode(result)
        except ValueError:
            return ServiceUnavailable("snapshot_selection_content")
        return result

    descriptors = publication_descriptors(codecs, limits)
    return (
        OperationBinding(
            descriptors[0],
            codecs.publication,
            codecs.publication_result,
            CommandBehavior(handlers.publish),
            lambda value: (ResourceRef("feed", cast(str, value["feed_id"])),),
        ).bind(),
        OperationBinding(
            descriptors[1],
            codecs.reference,
            codecs.read_result,
            QueryBehavior(handlers.read),
            lambda value: (ResourceRef("snapshot", f"{value.feed_id}:{value.producer_version}"),),
        ).bind(),
        OperationBinding(
            descriptors[2],
            codecs.latest_request,
            codecs.latest_result,
            QueryBehavior(latest),
            lambda value: (ResourceRef("feed", value.feed_id),),
        ).bind(),
    )
