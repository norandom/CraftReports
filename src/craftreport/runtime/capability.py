"""Versioned publication registrations with injected codecs and real handlers."""

from dataclasses import dataclass
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
from craftreport.runtime.publication import (
    LatestRequest,
    LatestSelection,
    PublicationOperations,
    PublicationResult,
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

    return (
        OperationBinding(
            _descriptor(
                "snapshot.publish",
                codecs.publication,
                codecs.publication_result,
                True,
                "feed",
                limits,
            ),
            codecs.publication,
            codecs.publication_result,
            CommandBehavior(handlers.publish),
            lambda value: (ResourceRef("feed", cast(str, value["feed_id"])),),
        ).bind(),
        OperationBinding(
            _descriptor(
                "snapshot.read", codecs.reference, codecs.read_result, False, "snapshot", limits
            ),
            codecs.reference,
            codecs.read_result,
            QueryBehavior(handlers.read),
            lambda value: (ResourceRef("snapshot", f"{value.feed_id}:{value.producer_version}"),),
        ).bind(),
        OperationBinding(
            _descriptor(
                "snapshot.latest",
                codecs.latest_request,
                codecs.latest_result,
                False,
                "feed",
                limits,
            ),
            codecs.latest_request,
            codecs.latest_result,
            QueryBehavior(latest),
            lambda value: (ResourceRef("feed", value.feed_id),),
        ).bind(),
    )
