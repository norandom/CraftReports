"""Ordinary HTTP and official MCP clients over the owned listener, without AI."""

import asyncio
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

import httpx
import httpx2
from installed_process import InstalledProcess, write_json
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel


class OperationKey(BaseModel):
    name: str
    contract_version: str


class Operation(BaseModel):
    key: OperationKey


class Manifest(BaseModel):
    identity: str
    version: str


class Capability(BaseModel):
    manifest: Manifest
    verification: str


class Catalog(BaseModel):
    operations: list[Operation]
    capabilities: list[Capability]
    deployment_epoch: str


@dataclass(frozen=True)
class Discovery:
    protocol_version: str
    tools: tuple[str, ...]
    operations: tuple[str, ...]
    verification: str


@contextmanager
def rest_client(owner: InstalledProcess, principal: str = "alice") -> Generator[httpx.Client]:
    assert owner.control is not None
    with httpx.Client(
        base_url=owner.endpoint,
        headers={"Authorization": f"Bearer {owner.control.credentials[principal]}"},
        timeout=3,
        trust_env=False,
    ) as client:
        yield client


@asynccontextmanager
async def mcp_client(
    owner: InstalledProcess,
    principal: str = "alice",
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> AsyncGenerator[Client]:
    assert owner.control is not None
    credential = token if token is not None else owner.control.credentials[principal]
    async with (
        asyncio.timeout(owner.timeout),
        httpx2.AsyncClient(
            headers={
                **({"Authorization": f"Bearer {credential}"} if token != "" else {}),
                **(headers or {}),
            },
            timeout=5,
            trust_env=False,
        ) as http,
    ):
        async with Client(
            streamable_http_client(owner.endpoint + "/mcp", http_client=http)
        ) as client:
            yield client


def rest_catalog(owner: InstalledProcess) -> Catalog:
    assert owner.control is not None
    deadline = time.monotonic() + owner.timeout
    with rest_client(owner) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(owner.endpoint + "/v1/catalog")
            except httpx.ConnectError:
                assert owner.process is not None and owner.process.poll() is None
                time.sleep(0.05)
                continue
            write_json(
                owner.directory / "rest-transcript.json",
                {
                    "method": "GET",
                    "path": "/v1/catalog",
                    "principal": "alice",
                    "status": response.status_code,
                    "response": response.json(),
                },
                secrets=owner.secrets,
            )
            response.raise_for_status()
            catalog = Catalog.model_validate_json(response.content)
            assert catalog.deployment_epoch == owner.control.epoch
            return catalog
    raise TimeoutError("Authorized REST discovery did not become usable")


async def mcp_discovery(owner: InstalledProcess) -> tuple[str, tuple[str, ...]]:
    assert owner.control is not None
    async with mcp_client(owner) as client:
        tools = await client.list_tools()
        protocol = client.protocol_version
        assert protocol is not None
        write_json(
            owner.directory / "mcp-transcript.json",
            {
                "method": "tools/list",
                "principal": "alice",
                "protocol_version": protocol,
                "response": tools.model_dump(mode="json"),
            },
            secrets=owner.secrets,
        )
        return protocol, tuple(tool.name for tool in tools.tools)


def discover(owner: InstalledProcess) -> Discovery:
    catalog = rest_catalog(owner)
    protocol, tools = asyncio.run(mcp_discovery(owner))
    assert len(catalog.capabilities) == 1
    capability = catalog.capabilities[0]
    assert capability.manifest.identity == "synthetic"
    return Discovery(
        protocol,
        tools,
        tuple(sorted(op.key.name for op in catalog.operations)),
        capability.verification,
    )
