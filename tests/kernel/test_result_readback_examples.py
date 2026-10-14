"""Run the published result-retrieval examples with real adapters and execution."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

import httpx
import pytest
from fixture_dispatch import RESOURCE
from fixture_execution import executor
from mcp import Client
from test_mcp import connection
from test_result_readback import query_fixture
from test_transport_parity import client


@pytest.mark.anyio
async def test_documented_readback_examples() -> None:
    source = Path("docs/result-readback.md").read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    for block in source.split("```python\n")[1:]:
        exec(compile(block.split("```", 1)[0], "docs/result-readback.md", "exec"), namespace)
    rest_example = cast(
        Callable[[httpx.AsyncClient], Awaitable[dict[str, object]]],
        namespace["query_and_read_rest"],
    )
    mcp_example = cast(
        Callable[[Client], Awaitable[dict[str, object]]], namespace["query_and_read_mcp"]
    )
    fixture = query_fixture()
    owner = executor(fixture)
    before = await fixture.target.read(RESOURCE)
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        for result in (await rest_example(rest), await mcp_example(mcp)):
            assert result["value"] == {"value": "retained"}
        assert await fixture.target.read(RESOURCE) == before
        assert fixture.target.effect_count == 0
        assert fixture.calls == 2
