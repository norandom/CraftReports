"""Installed durable host: private startup pipe and observed graceful shutdown."""

import asyncio
import json
import os
import socket
import sys
import threading
from contextlib import redirect_stdout
from pathlib import Path

import craftreport
from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.snapshot_wire import snapshot_codec
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.providers import DurableResources
from craftreport.application import ports
from craftreport.composition.app import BoundServer
from craftreport.composition.settings import HostSettings
from craftreport.composition.snapshot_host import configure_snapshot, open_snapshot_application
from craftreport.contracts import Principal
from craftreport.interfaces.principal import AuthenticatedIdentity, PrincipalBoundary


class OwnerPolicy:
    def owns(self, principal: Principal) -> bool:
        return principal.deployment_scope == "installed-snapshot" and principal.subject == "alice"

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        return ports.AccessAllowed() if self.owns(principal) else ports.AccessDenied()

    async def probe(self) -> None:
        assert self.owns(Principal("installed-snapshot", "alice", frozenset()))


def shutdown(loop: asyncio.AbstractEventLoop, server: BoundServer) -> None:
    sys.stdin.readline()
    loop.call_soon_threadsafe(server.request_shutdown)


async def serve(path: Path) -> None:
    origin = Path(str(craftreport.__file__)).resolve()
    assert origin.is_relative_to(Path(sys.prefix).resolve())
    assert "pytest" not in sys.modules
    policy = OwnerPolicy()
    boundary, credentials = PrincipalBoundary.conformance(
        "127.0.0.1",
        "installed-snapshot",
        (AuthenticatedIdentity("alice", frozenset()), AuthenticatedIdentity("bob", frozenset())),
        policy,
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]

        def settings(database: Database, resources: DurableResources) -> HostSettings:
            return HostSettings(
                "127.0.0.1",
                (f"127.0.0.1:{port}",),
                (),
                database.deployment.epoch,
                database.deployment.retention_profile,
                boundary,
                (configure_snapshot(resources, owner_policy=policy.owns),),
            )

        finger = CanonicalFingerprint()
        async with open_snapshot_application(
            path,
            "installed-snapshot",
            settings,
            codec=snapshot_codec(),
            fingerprint=finger,
            normalization_policy=finger.policy,
            owner_probes={"access": policy.probe, "capabilities": policy.probe},
        ) as application:
            with redirect_stdout(sys.stderr):
                server = application.server(listener)
            threading.Thread(
                target=shutdown, args=(asyncio.get_running_loop(), server), daemon=True
            ).start()
            print(
                json.dumps(
                    {
                        "port": port,
                        "pid": os.getpid(),
                        "parent_pid": os.getppid(),
                        "origin": str(origin),
                        "credentials": {c.identity.subject: c.token for c in credentials},
                    }
                ),
                flush=True,
            )
            await server.serve()
    print(json.dumps({"closed": True, "pid": os.getpid()}), flush=True)


if __name__ == "__main__":
    asyncio.run(serve(Path(sys.argv[1]).resolve()))
