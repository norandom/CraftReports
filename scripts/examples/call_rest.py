"""POST an explicitly supplied envelope, then inspect without replaying it."""

from urllib.parse import quote

import httpx

from scripts.examples.common import (
    ExampleFailure,
    JsonObject,
    cli,
    configuration,
    parse_object,
    require_operation,
    workflow,
)


async def run(request: JsonObject | None, identity: str | None) -> JsonObject:
    url, token = configuration()
    async with httpx.AsyncClient(
        base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=10, trust_env=False
    ) as client:

        async def execute(action: str, value: JsonObject) -> JsonObject:
            if action == "catalog":
                response = await client.get("/v1/catalog")
            elif action == "invoke":
                response = await client.post("/v1/invoke", json=value)
            else:
                operation_id = value["operation_id"]
                assert isinstance(operation_id, str)
                path = "/v1/operations/" + quote(operation_id, safe="")
                response = await client.get(path + ("/result" if action == "result" else ""))
            # Structured failures are useful even when HTTP returns an error status.
            result = parse_object(response.content)
            if response.is_error:
                raise ExampleFailure(
                    f"HTTP request failed with status {response.status_code}", result
                )
            return result

        if identity is None:
            catalog = await execute("catalog", {})
            if request is None:
                return catalog
            require_operation(catalog, request)
        return await workflow(execute, request, identity)


if __name__ == "__main__":
    raise SystemExit(cli("rest"))
