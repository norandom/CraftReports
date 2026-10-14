"""Isolated installed-wheel host; stdout is a private typed control pipe."""

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import threading
import traceback
from contextlib import redirect_stdout
from pathlib import Path

# -I deliberately excludes the script directory. Add helpers, never package sources.
HELPERS = Path(__file__).resolve().parent
sys.path.extend((str(HELPERS), str(HELPERS.parent / "kernel")))

from typing import Literal  # noqa: E402

import craftreport_kernel_fixture  # noqa: E402
import kernel_services  # noqa: E402
from kernel_services import Providers  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field, ValidationError  # noqa: E402

import craftreport  # noqa: E402
from craftreport.composition.app import BoundServer, open_application  # noqa: E402


def installed_origins() -> dict[str, str]:
    origins: dict[str, str] = {}
    for module in (craftreport, craftreport_kernel_fixture):
        if module.__file__ is None:
            raise RuntimeError("Installed package has no origin")
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(Path(sys.prefix).resolve()):
            raise RuntimeError("Package imported outside installed environment")
        origins[module.__name__] = str(path)
    if "pytest" in sys.modules:
        raise RuntimeError("Child imported pytest")
    origins["kernel_services"] = str(Path(kernel_services.__file__).resolve())
    return origins


class ObserveCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command: Literal["observe"]
    request_id: str = Field(min_length=1, max_length=64)
    result_ref: str | None = Field(default=None, max_length=128)


def shutdown_reader(
    loop: asyncio.AbstractEventLoop, server: BoundServer, providers: Providers
) -> None:
    # A daemon thread also works with Windows anonymous pipes; EOF closes the host.
    while True:
        command = sys.stdin.readline()
        if command == "" or command.rstrip("\r\n") == "shutdown":
            break
        try:
            request = ObserveCommand.model_validate_json(command)
        except ValidationError:
            print("kernel_server rejected unknown control command", file=sys.stderr, flush=True)
            continue
        future = asyncio.run_coroutine_threadsafe(providers.observe(request.result_ref), loop)
        print(
            json.dumps({"request_id": request.request_id, **future.result(timeout=5)}), flush=True
        )
    try:
        loop.call_soon_threadsafe(server.request_shutdown)
    except RuntimeError:
        pass


async def serve(providers: Providers, imports: dict[str, str]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        settings, credentials = providers.settings(port)
        async with open_application(settings, providers.open()) as application:
            # Uvicorn configures access output on stdout by default. Keep the control
            # pipe for startup and observation records, retaining all logs on stderr.
            with redirect_stdout(sys.stderr):
                server = application.server(listener)
            thread = threading.Thread(
                target=shutdown_reader,
                args=(asyncio.get_running_loop(), server, providers),
                daemon=True,
            )
            thread.start()
            print(
                json.dumps(
                    {
                        "port": port,
                        "credentials": credentials,
                        "imports": imports,
                        "pid": os.getpid(),
                        "parent_pid": os.getppid(),
                        "epoch": settings.deployment_epoch,
                        "fixture": {
                            "resource_kind": "synthetic",
                            "resource": "target-1",
                            "initial_value": "before",
                        },
                    }
                ),
                flush=True,
            )
            await server.serve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--failure", choices=("startup", "cleanup"))
    parser.add_argument("--boundary-probe", action="store_true")
    args = parser.parse_args()
    run_dir = Path(str(args.run_dir)).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    failure = str(args.failure) if args.failure is not None else None
    providers = Providers(run_dir, failure, boundary_probe=bool(args.boundary_probe))
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    code = 0
    try:
        asyncio.run(serve(providers, installed_origins()))
    except Exception:
        code = 1
        print("kernel_server lifecycle failed", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
    finally:
        providers.write_cleanup(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
