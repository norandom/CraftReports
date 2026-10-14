"""Typed deployment selections close over their own services and settings codec."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from craftreport.application.capabilities import CapabilityFactory, CapabilityInstance
from craftreport.application.registry import Codec
from craftreport.contracts import CapabilityManifest, JsonObject
from craftreport.contracts.values import freeze_object


@dataclass(frozen=True, slots=True)
class PreparedCapability:
    manifest: CapabilityManifest
    open: Callable[[], AbstractAsyncContextManager[CapabilityInstance]]


@dataclass(frozen=True, slots=True)
class ConfiguredCapability:
    distribution: str
    entry_point: str
    prepare: Callable[[object], PreparedCapability]


def configure[Services, Settings](
    distribution: str,
    entry_point: str,
    adapt: Callable[[object], CapabilityFactory[Services, Settings]],
    services: Services,
    codec: Codec[Settings],
    settings: JsonObject,
) -> ConfiguredCapability:
    """Adapt trusted entry-point code explicitly; retain all generic types locally.

    The adapter receives the loaded callable and checks its author contract. The
    codec must strictly validate input, as PydanticCodec.for_input does. No service
    lookup or untyped global container is passed to the capability.
    """
    values = freeze_object(settings)

    def prepare(loaded: object) -> PreparedCapability:
        factory = adapt(loaded)
        manifest = factory.describe()
        if manifest.settings_schema != freeze_object(codec.schema()):
            raise ValueError("Settings codec does not match manifest schema")
        validated = codec.decode(values)
        return PreparedCapability(manifest, lambda: factory.open(services, validated))

    return ConfiguredCapability(distribution, entry_point, prepare)
