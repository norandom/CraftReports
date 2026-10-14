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
`fail_open` and `fail_close` are synthetic failure controls for later activation
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
rewritten. These are inputs for activation tests, not additional production
plugins or a claim that task 4.2 activation validation already exists.

Installation is distinct from selection, initialization, and verified support.
The future activator selects exact distribution/entry-point pairs before loading,
requires explicitly enabled dependencies, and publishes only a fully validated
registry. Capability code is trusted deployment code; typed contexts and import
boundaries do not sandbox malicious Python.

This example supports requirements 1.1, 1.2, 1.4, 2.5, 7.1 and 7.4 within
synthetic packaging and author-contract scope. It does not establish production
durability, browser/native behavior, financial accuracy, or reporting-artifact
fidelity. Full activation, transport and conformance acceptance remain later
kernel tasks.
