# Proposed task 3.4 services and schema v5

Status: proposal only, awaiting independent review and root GO. Requirements
5.1, 5.5, 5.7, 6.1 and 6.2; Design DurableSchema and concrete provider contract.
Task 3.2 is accepted at `0cdc70a`, task 3.3 at `3fce4bb`. This proposal changes
no source, task state, approval metadata or engineering limit.

## Exact v4 to v5 transition

Keep all seven v4 tables and their DDL unchanged. Add only `handoffs`:

| Column | SQLAlchemy declaration |
| --- | --- |
| operation_id | String, primary key, nonnull, non-cascading ForeignKey to commands.operation_id |
| reference | String, primary key, nonnull |
| handoff_bytes | LargeBinary, nonnull |
| handoff_digest | String, nonnull |

The composite primary key is `(operation_id, reference)`. No separate owner,
principal, version or capability table duplicates the canonical record.
`TypeAdapter(RecordedHandoff)` in existing `storage/serialization.py` derives
the representation from the existing immutable application dataclass. Reuse
canonical JSON, SHA-256, strict extra-forbid decoding and exact re-encoding.
Retain the complete Principal, operation ID, reference, owner and ordered pins;
retained permitted scopes are historical identity, never future authorization.

New databases create exactly v5. Existing exact v4 is validated before writes;
in the existing initialization transaction create only handoffs, validate exact
v5 and update only deployment.schema_version to 5. Preserve identity, epoch,
retention profile, settings bytes and all prior rows. Earlier recognized v1-v3
continue through the existing explicit transitions, then this one transition.
Partial/unknown schemas, extra objects, altered constraints and claimed v5 with
missing handoffs fail untouched. No unrestricted create_all over retained state,
replacement database, schema parser or generic migration registry is introduced.
Fault injection after table creation and after version update must roll back
both DDL and version; actual file reopen must establish original v4 rows/schema.

## Exact handoff and current fencing

`DurableHandoffs` belongs in existing `storage/providers.py`. Record only an
already admitted command, validating its current canonical journal/header/history
through `DurableJournal.retained`. Require matching deployment and subject,
exact operation ID, and handoff versions equal, in order, to both the original
intent.expected_versions and the captured issued lease tuple. Each listed pin
must belong to intent.resources; membership cannot substitute for exact tuple
equality. Queries cannot acquire an execution owner. Duplicate identical writes
are idempotent only against the original captured authority; they never bind
existing bytes to a later lease. Changed owner/principal/pins fail without writes.
Readback verifies bytes/digest, row key and original retained command ownership.
Cross-owner inspection fails closed without returning another caller's content.

The kernel's local Execution owner is a private per-instance UUID, not an
installed-owner identity. Its `_pending` calls record and inspect in the same
original task while holding the issued DurableGuard lease. Extend the existing
guard with a narrow method that captures the exact issued lease for the current
task and exact ordered pins at record time. Bind that lease, original task and
operation/reference together in this provider lifetime. Inspect must validate
that original captured authority, never search for a later lease with equal
pins. A later operation, reused owner string or new same-pin lease cannot revive
the old record. No mutation of lease fields can grant authority. Invalidation,
task cancellation/completion, provider close and process restart invalidate the
live acceptance while preserving its canonical historical bytes. Stored content
without current authority returns ServiceUnavailable, never live RecordedHandoff.
Known absent row remains Missing. Lost write acknowledgement uses exact readback;
it never creates a second reference or starts another effect.

Admission acquires exactly intent.expected_versions; `_pending` copies precisely
that tuple. Retain it even when empty or partial, without inventing pins or
changing application admission. Empty resources and pins establish local
admission/task ownership only. Declared resources with omitted pins likewise
establish no business-resource fencing. A partial tuple fences only its listed
resources. For example, resources `(feed:A, feed:B)` with pins `(feed:A=1,)`
does not fence feed:B. Full fencing is claimed only for resources actually
covered by the issued tuple; existing changes_business_state validation remains
the owner of commands that require complete preconditions.

External transfer owners need their own trusted *current* acceptance and resource
fence evidence. The present HandoffStore signature supplies no external owner
port, and `HostSettings.installed_owners` is only a string allowlist. This task
does not turn that allowlist into liveness. External transfer is unavailable
until an explicitly injected exact-record acceptance/fence collaborator exists;
no external transfer implementation or generic owner registry is proposed here.

## Capability decision clarification

Use the already activated installed manifests, existing immutable registry and
`packaging.version.Version` / `packaging.specifiers.SpecifierSet`. Preserve exact
manifest.provided version strings in decisions, distinct from package versions;
reject duplicate identities, invalid
versions/ranges and unsupported requirements. A provider failure is unavailable.
Do not infer app support from a package merely being installed. Empty requirements
can succeed only after actual configured capability health is established.

The persisted decision pins already exist in CommandIntent, Receipt and journal
observations. They survive restart unchanged. Interpret task 3.4's "persist ...
installed capability/version/mode decisions" through those existing records;
there is no approved capability table and no second activation authority.
Current support after restart is independently checked against current activation,
never granted by an older receipt. CapabilityRequirement has target_mode, but
CapabilityManifest and ActivationSnapshot have no supported-mode or resource-mode
observation. The initial resolver rejects **all** mode-constrained requirements
as unsupported. No mode grants, typed mode configuration or synthetic defaults
are introduced. Actual mode verification belongs to the later app owner's spec;
task 3.4 claims no browser/native support. An unbound or closed resolver is
unavailable, including for empty requirements.

## Single activation and scoped composition binding

Extend existing `composition/app.py` `open_application` with the optional
keyword-only argument
`on_activation: Callable[[ActivationSnapshot], AbstractAsyncContextManager[None]] | None = None`.
After entering the existing single `activate_snapshot` context, and before
constructing `_execution`, enter `on_activation(snapshot)` on the same
AsyncExitStack when supplied. Existing callers retain the None default and their
current behavior. No application-kernel source changes, second entry-point load,
activation reordering, new provider registry or alternative dispatcher is needed.

The planned `composition/snapshot_host.py` owns the concrete capability resolver
and its mandatory scoped binder. The binder publishes precisely that already
activated immutable snapshot for its own lifetime. Its state is permanently
one-shot: never-attempted -> bound -> closed. The first entry attempt burns the
right to bind *before* validation or awaits; failed entry closes permanently and
clears the snapshot. Every later attempt, overlapping or sequential, is rejected.
Before binding and after close, checks are unavailable. After every awaited
owner-health probe, a check rechecks that the same original binding is still
open before returning any decision, including supported for empty requirements.
Closure during a probe cannot return supported. It does not copy manifests into
a second mutable authority. Check installed versions from the
actual activation manifests with existing packaging semantics, not fresh discovery.
The host's provider context remains open while activation and the binder are
open. The callback closes before capability contexts and providers, after the
existing execution shutdown path. A callback/activation failure must unwind every
successfully entered context; no readiness, usable resolver or lost cleanup may
survive failed assembly. Task 3.4 tests this seam; task 4.2 still owns installed
REST/MCP host behavior and restart acceptance.

The minimal concrete assembler in snapshot_host.py is an async context manager
with this signature (existing types; no service container or transport added):

```python
type HealthProbe = Callable[[], Awaitable[ServiceUnavailable | None]]

@asynccontextmanager
async def open_snapshot_application(
    path: Path,
    deployment_id: str,
    settings: Callable[[Database, DurableResources], HostSettings],
    *,
    codec: Codec[Snapshot],
    fingerprint: Fingerprint,
    normalization_policy: str,
    owner_probes: Mapping[str, HealthProbe],
) -> AsyncGenerator[HostedApplication]: ...
```

It opens/owns Database(path, deployment_id), then creates DurableResources with
the exact supplied codec/fingerprint/policy, DurableJournal, DurableEvidence,
DurableResults, DurableHandoffs, actual health and the initially unbound resolver.
GuaranteeProviders uses that resources instance for reader/effects, its existing
guard, and the other six concrete collaborators. Internal storage services exist
before activation so capability factories can use them. The settings callable
closes capability selections over those concrete services through existing
configure; it must return settings whose principal.deployment_scope, epoch and
retention profile equal the opened deployment. Mismatch fails before activation.

With a small provider context retaining these concrete objects, the assembler
unconditionally calls `open_application(host_settings, provider_context,
on_activation=resolver.bind)` and yields only its returned HostedApplication.
No caller-selectable callback can omit this binder on this production path.
Readiness remains owned by the existing server lifespan. Finally close the
handoff/health lifetime and await Database.close after execution, binding and
capability cleanup, including failed settings/activation/callback entry. This
outer context owns the database; capability factories and clients do not close it.

## Actual health and retention inspection

Use a closed explicit map of configured service names to small current probes,
not imports, discovery, container lookups, bool flags or object-presence tests.
Unknown names fail closed. Access/capability/app probes are supplied by their
actual trusted owners; no default successful access or app probe is installed.
The assembler copies owner_probes into an immutable closed map. It requires
explicit access and capabilities HealthProbe entries; additional external names
are only those explicitly supplied. Storage names are implemented internally and
cannot be overridden by owner entries. Resolver health awaits the actual
capabilities probe and checks its one-shot binding again afterwards. Probe None
means the owner made a current successful observation; ServiceUnavailable or any
probe exception fails closed. The map is explicit composition, not discovery.
Storage-backed services probe the opened lifetime and a real transactional read
of the retained deployment identity/epoch/profile/settings plus appropriate
canonical journal/content readback. Provider exceptions, malformed retained bytes,
identity mismatch and close invalidate health. Probe work is bounded; it does
not scan every historical row or claim every artifact has been audited.

This is bounded structural/canonical-read integrity, not a physical audit of the
entire SQLite database. Do not add quick_check, integrity_check, arbitrary SQL or
another PRAGMA exception: limiting returned errors does not bound scan work.

In existing storage/providers.py define the frozen value
`RetentionReport(deployment: Deployment, retained_kinds: tuple[str, ...],
removal: Literal["explicit-offline-only"])`, reusing schema.Deployment's exact
identity/epoch/profile/configured_limits bytes. `DurableHealth.retention() ->
RetentionReport | ServiceUnavailable` performs a fresh bounded retained deployment
read and validates it against the opened deployment before returning. Failures
return ServiceUnavailable("retention"); no cached-success inspection is allowed.
retained_kinds is exactly snapshots, retry_identities, receipts, results, bindings,
runs and evidence; the report's profile is retain-all. It states that committed
content is retained until explicit stopped-host maintenance and that future
purged content is Missing while I/O/integrity failure is Unavailable. No TTL or
purge implementation belongs to task 3.4; task 3.5 owns removal/tombstones.

## Files, proportionality and verification

Reuse existing schema.py, serialization.py, guard.py, database.py and providers.py;
results.py and evidence.py retain their existing responsibilities. A proposed
new `src/craftreport/composition/snapshot_host.py` is the Design's already planned
DurableHost boundary: only a small typed assembly of the nine concrete providers
from explicit database, codecs, active capability and owner-health inputs at this
stage. It adds no host transport or loader. Existing `composition/app.py` owns
only the optional callback/lifetime seam described above, with tests at the
existing composition-host seam. This root-directed boundary expansion requires
independent review before source expansion. Capability resolution remains at its
actual activation/composition boundary, so packaging needs no storage-wide import
exception; no unrelated provider moves evade storage limits.

Measured storage is 949/1500 LLOC, leaving 551 for *all* remaining storage work.
Planning allocation: task 3.4 storage 170-230, task 3.5 purge/tombstones 90-130,
task 5.1 binding/run persistence 170-220, total 430-580 against that 551 reserve.
The upper forecast exceeds reserve by 29 and is a risk, not an approved increase;
prefer small composition and existing library codecs, measure actuals, and return
to root if simplification cannot meet the unchanged cap. Proposed composition
assembly/resolver is 60-100 LLOC under composition's existing cap. Existing local
50 function / 300 module / McCabe 10 and aggregate limits remain unchanged.
No source file may be split merely to distribute budget pressure.

Behavioral TDD covers real file/reopen exact handoffs; missing, ownership denial,
digest/noncanonical/header/history/pin corruption; changed immutable writes;
same-pin second-operation non-revival; expired/original-task-transfer authority;
empty-resource, omitted-pin and partial-pin handoffs with exact limited claims;
unknown/unavailable services; installed version/range decisions and absent mode
observations; actual closure/corruption health; exact retain-all scope; populated
v4 migration, rollback at both cutpoints and unknown-schema rejection. Compose
all nine providers with real Database/journal/guard/resources/effects/evidence/
results, actual installed activation and explicit owner probes. Adapt focused
existing provider conformance without importing synthetic providers as defaults.
At the existing composition-host test seam, verify one activation/callback call,
unavailable before bind and after close, callback failure, activation failure,
overlapping and sequential second-bind rejection, failed-entry permanent closure,
closure during an awaited health probe, mismatched settings and cleanup order:
execution shutdown, binder,
capability lifetimes, then providers. A failure cannot leak a usable binding or
skip an execution shutdown after construction; failure before construction
unwinds entered contexts without inventing an execution shutdown. Existing callers
without a callback still pass. Assembler tests prove its mandatory binder and
database close after partial setup failure, plus typed retention readback/failure.

Validation: focused Windows pytest, scoped Ruff/format/Pyright, actual import,
breadth and quality gates; canonical hook/fast checks remain root-owned after
independent review. Retain source hashes, commands, exit codes and actual row/
reopen evidence under `artifacts/snapshot-runtime/task-3.4/`. No heavy commands
run during the root-owned browser check. No source or task completion is implied
by this proposal; independent review and root GO are required before source work.
