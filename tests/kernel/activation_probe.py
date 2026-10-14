"""Installed activation journeys with real distribution discovery and resource traces."""

import asyncio
import sys
from dataclasses import replace
from typing import Protocol, runtime_checkable

from craftreport_kernel_fixture.lifecycle import FixtureServices
from craftreport_kernel_fixture.models import SETTINGS, Settings
from fixture_package_probe import Events

from craftreport.application.capabilities import CapabilityFactory
from craftreport.composition.plugins import activate
from craftreport.composition.settings import ConfiguredCapability, configure
from craftreport.contracts import JsonObject


@runtime_checkable
class EntryFactory(Protocol):
    def __call__(self) -> CapabilityFactory[FixtureServices, Settings]: ...


def adapt(value: object) -> CapabilityFactory[FixtureServices, Settings]:
    if not isinstance(value, EntryFactory):
        raise TypeError("Entry point must be a factory callable")
    return value()


def selection(
    events: Events, name: str = "synthetic", settings: JsonObject | None = None
) -> ConfiguredCapability:
    package = "craftreport-kernel-fixture" + ("" if name == "synthetic" else f"-{name}")
    return configure(
        package,
        name,
        adapt,
        FixtureServices(events),
        SETTINGS,
        {"resource_kind": "synthetic"} if settings is None else settings,
    )


async def happy() -> None:
    events = Events()
    async with activate([selection(events)]) as registry:
        assert len(registry.describe()) == 2
        assert events.names() == ["acquired", "opened"]
    assert events.names() == ["acquired", "opened", "released"]
    assert "craftreport_kernel_fixture_unselected" not in sys.modules


async def failures() -> None:
    expected = {
        "collision": "capability identity",
        "incompatible": "Incompatible core contract",
        "wrongrange": "missing/incompatible synthetic",
        "provideddup": "provided identity",
        "tooldup": "MCP name",
        "reserved": "MCP name",
        "badversion": "version does not match",
        "badpackage": "package does not match",
        "tool129": "MCP name",
        "unselected": "Unselected fixture was imported",
    }
    for variant, reason in expected.items():
        events = Events()
        published = False
        try:
            async with activate([selection(events), selection(events, variant)]):
                published = True
        except ValueError as error:
            assert reason in str(error), str(error)
        else:
            raise AssertionError(f"Accepted {variant}")
        assert not published and not events.events
    for settings in (
        {},
        {"resource_kind": "synthetic", "fail_open": "true"},
        {"resource_kind": "synthetic", "secret": "ignored"},
    ):
        events = Events()
        try:
            async with activate([selection(events, settings=settings)]):
                raise AssertionError("Published invalid settings")
        except ValueError as error:
            assert "craftreport-kernel-fixture/synthetic" in str(error)
            assert "invalid_input" in str(error)
        assert not events.events


async def graph_and_selection() -> None:
    for names in (("dependent",), ("cyclea", "cycleb"), ("synthetic", "synthetic")):
        events = Events()
        try:
            async with activate([selection(events, name) for name in names]):
                raise AssertionError("Published invalid graph")
        except ValueError:
            pass
        assert not events.events
    events = Events()
    for selected in (
        replace(selection(events), distribution="absent-package"),
        replace(selection(events), entry_point="absent-point"),
    ):
        try:
            async with activate([selected]):
                raise AssertionError("Published missing selection")
        except ValueError:
            pass
    async with activate(
        [
            selection(events, "dependent"),
            replace(selection(events), distribution="CraftReport_Kernel.Fixture"),
        ]
    ):
        assert events.events == [
            ("synthetic", "acquired"),
            ("synthetic", "opened"),
            ("dependent", "acquired"),
            ("dependent", "opened"),
        ]
    assert events.events[-2:] == [("dependent", "released"), ("synthetic", "released")]
    async with activate([selection(Events(), "tool128")]) as registry:
        assert (
            max(len(op.key.name + ".v" + op.key.contract_version) for op in registry.describe())
            == 128
        )


async def lifecycle() -> None:
    for failure in ("fail_open", "fail_close", "mismatch"):
        events = Events()
        name = "mismatch" if failure == "mismatch" else "dependent"
        settings: JsonObject = {"resource_kind": "synthetic"}
        if failure != "mismatch":
            settings = {"resource_kind": "synthetic", failure: True}
        published = False
        try:
            async with activate([selection(events), selection(events, name, settings)]):
                published = True
        except (ValueError, RuntimeError) as error:
            reason = str(error)
            if failure == "fail_open":
                assert "dependent" in reason and "initialization failed" in reason
            elif failure == "fail_close":
                assert "Synthetic cleanup failure after release" in reason
            else:
                assert "mismatch" in reason and "operation descriptors" in reason.lower()
        else:
            raise AssertionError("Ignored lifecycle failure")
        assert published == (failure == "fail_close")
        assert [identity for identity, event in events.events if event == "released"] == [
            name,
            "synthetic",
        ]


async def preflight_all_settings() -> None:
    events = Events()
    try:
        async with activate([selection(events), selection(events, "dependent", {})]):
            raise AssertionError("Published invalid settings")
    except ValueError as error:
        assert "craftreport-kernel-fixture-dependent/dependent" in str(error)
        assert "invalid_input" in str(error)
    assert not events.events


async def cleanup_chain_and_cancellation() -> None:
    events = Events()
    try:
        async with activate(
            [
                selection(events, settings={"resource_kind": "synthetic", "fail_close": True}),
                selection(events, "dependent", {"resource_kind": "synthetic", "fail_open": True}),
            ]
        ):
            raise AssertionError("Published failed initialization")
    except RuntimeError as error:
        chain: list[str] = []
        current: BaseException | None = error
        while current is not None:
            chain.append(str(current))
            current = current.__context__
        assert any("initialization fail" in reason for reason in chain)
        assert any("cleanup failure" in reason for reason in chain)
    else:
        raise AssertionError("Swallowed cleanup failure")
    assert [identity for identity, event in events.events if event == "released"] == [
        "dependent",
        "synthetic",
    ]
    events = Events()
    try:
        async with activate([selection(events), selection(events, "dependent")]):
            raise asyncio.CancelledError
    except asyncio.CancelledError:
        pass
    assert [identity for identity, event in events.events if event == "released"] == [
        "dependent",
        "synthetic",
    ]


async def main() -> None:
    await happy()
    await failures()
    await graph_and_selection()
    await lifecycle()
    await preflight_all_settings()
    await cleanup_chain_and_cancellation()
    print("installed activation verified")


if __name__ == "__main__":
    asyncio.run(main())
