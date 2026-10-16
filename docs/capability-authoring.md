# Capability author contract

The executable example is the separate synthetic distribution in
`tests/fixtures/kernel_plugin`. It depends only on the installed `craftreport`
package and its declared runtime dependencies. It does not bundle the test
providers, production plugins, an AI service, or a notebook runtime.

Its packaging contract is standard Python metadata:

```toml
[project.entry-points."craftreport.capabilities"]
synthetic = "craftreport_kernel_fixture:factory"
```

The entry-point callable returns a typed
`CapabilityFactory[FixtureServices, Settings]`. `describe()` returns an immutable
`CapabilityManifest` without acquiring resources or changing business state.
The manifest declares package/version, stable identity, core compatibility,
provided and required capability versions, settings schema, operation
descriptors, and the digest of actual installed implementation bytes. A digest
identifies this fixture build; it does not certify behavior or create a passing
verification record.

`open(services, settings)` is an async context manager yielding a
`CapabilityInstance`. Its `bindings` exactly match advertised descriptors.
`aclose` delegates to the same idempotent closer owned by context exit: explicit
close followed by exit releases once. Initialization failure after acquisition
still releases; cleanup failure propagates even after resources are released.
The fixture records acquisition/open/release/failure events through the single
declared `LifecycleObserver` port. These are temporary lifecycle observations,
not business completion evidence. Factories must not perform business work
during activation.

Validate raw settings with the declared schema and typed codec **before** calling
`open`. The fixture defensively repeats validation before acquiring resources.
Its required resource kind must match the advertised resource declaration.
`fail_open` and `fail_close` are synthetic failure controls for activation
tests. Never allow plugin settings to disable the kernel's shared guards.

The following example runs against the installed fixture wheel. The packaging
test executes this exact Python block as well as checking installed file origins.

```python
import asyncio

from craftreport.application.registry import ImmutableOperationRegistry
from craftreport_kernel_fixture import factory
from craftreport_kernel_fixture.lifecycle import FixtureServices
from craftreport_kernel_fixture.models import SETTINGS


class Observer:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def record(self, capability: str, event: str) -> None:
        self.events.append((capability, event))


async def example() -> None:
    capability = factory()
    manifest = capability.describe()
    settings = SETTINGS.decode({"resource_kind": "synthetic"})
    observer = Observer()
    async with capability.open(FixtureServices(observer), settings) as instance:
        registry = ImmutableOperationRegistry(instance.bindings, manifest.operations)
        assert {item.key.name for item in registry.describe()} == {
            "synthetic.write", "synthetic.read"
        }
        assert observer.events == [("synthetic", "acquired"), ("synthetic", "opened")]
    assert observer.events[-1] == ("synthetic", "released")


asyncio.run(example())
```

Each `OperationBinding[Request, Result]` pairs strict codecs with a typed
handler. Conversion creates immutable request/result values. Use
`PydanticCodec.for_input()` for input normalization and a separate result codec
with its output budget. `bind()` retains the pair in a callable closure without
an untyped handler dictionary or unchecked handler casts. The synthetic write
starts business work and changes state, so it is a command. Its read operation
is a query receiving only `ReadContext`; mutation ports exist only on
`CommandContext`. Resource extraction is pure and declares the same kinds as
the manifest. Factory services are purpose-specific, not a global container.

For a command that must check an authorized selection before acceptance, supply
`CommandBehavior.eligibility`. This optional async callback receives the decoded
request and authenticated principal. Return `None` to allow admission or a
`Diagnostic` to reject it. It runs after resource authorization, retained-retry
lookup and guard acquisition; the kernel rechecks the original lease before
creating an operation. Equivalent retained retries return their receipt without
rerunning this check. The callback must not mutate a target or create evidence.
Queries have no eligibility callback.

Supply an explicit `OperationBinding.diagnostic_policy` to expose approved
diagnostic codes, recovery dispositions and public locations. The default policy
is empty. Use fixed public field locations; keep private source names and values
out of receipt diagnostics. The same policy filters eligibility rejections and
command outcomes. A reported failed stage remains failed even when its evidence
is absent; this never makes an unverified stage successful. The regression cases
in `tests/kernel/test_admission.py`, `test_execution.py` and `test_outcomes.py`
exercise these contracts through the kernel.

The write operation calls the supplied runtime effect port with its guard and
returns the provider's effect observation, version, and evidence references.
Missing evidence keeps its required effect stage pending; an acknowledgement
alone does not establish completion. The probe supplies an independent target
reader and retains a pinned evidence reference only after checking actual
synthetic state. The kernel's later outcome/dispatcher integration owns canonical
completion and evidence validation. Neither handlers nor this example bypass
those guards to expose an application endpoint.

Run the repeatable installed-wheel author check from the repository:

```powershell
uv.exe run --frozen python -m pytest -q tests/kernel/test_fixture_packaging.py
```

The helper builds the kernel and four separate fixture distributions, installs
them into an owned temporary environment using offline dependencies constrained
by the frozen lock, and runs isolated Python probes. Variants are copied into
owned temporary build directories: `unselected` raises on import,
`incompatible` declares an unsupported core version, and `collision` duplicates
the base capability/operation identities. The canonical fixture is never
rewritten. Activation tests add installed variants for dependency graphs,
identity/version mismatches, binding mismatches and MCP name limits.

Installation is distinct from selection, initialization, and verified support.
The activator selects exact distribution/entry-point pairs before loading,
requires explicitly enabled dependencies, and publishes only a fully validated
registry. Capability code is trusted deployment code; typed contexts and import
boundaries do not sandbox malicious Python.

Deployment code uses `composition.settings.configure(distribution, entry_point,
adapt, services, codec, settings)` for each selected entry point. `adapt` accepts
the loaded callable as `object`, checks the author contract and returns the
specific `CapabilityFactory[Services, Settings]`. The selection closes over that
typed factory, its purpose-specific service bundle and strict settings codec;
use `PydanticCodec.for_input()` for settings. Its schema must match the manifest.
Python package spelling is canonicalized (case, hyphens, underscores and dots);
the entry-point name must match exactly.

Use `async with composition.plugins.activate(selections) as registry:` and keep
registry use inside that lifetime. All selected settings and compatibility are
checked before any factory opens. Required capabilities must be explicitly
selected; initialization follows dependency order. A complete immutable
registry is yielded only after every binding matches its advertised descriptor.
Context exit unwinds in reverse order, including after initialization failure,
cancellation or cleanup failure. Cleanup exceptions propagate with their original
exception context. Treat unsuccessful context exit as failed deployment cleanup.

The `craftreport` namespace is reserved for core identities and operations.
Generated names append `.v` and the positive integer contract version. The
installed MCP 2.3.0 SDK's `mcp.shared.tool_name_validation` limit is 128 characters;
activation rejects names above it. This validates naming, not transport behavior.

Run `uv.exe run --frozen python -m pytest -q tests/kernel/test_activation.py` for
the isolated installed activation matrix, including selected-only imports,
dependency order, strict settings and reverse release on failures.

This example supports requirements 1.1, 1.2, 1.4, 2.5, 7.1 and 7.4 within
synthetic packaging and author-contract scope. It does not establish production
durability, browser/native behavior, financial accuracy, or reporting-artifact
fidelity. Transport and conformance acceptance remain later kernel tasks.
