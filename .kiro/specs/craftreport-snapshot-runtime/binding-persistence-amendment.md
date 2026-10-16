# Binding persistence and runtime contract amendment

Status: proposed; pending independent review and owner approval. Task 5.1 remains open. No production changes or limit increases are authorized by this document alone.

This completes the concrete design for existing snapshot-runtime task 5.1, required by the XLSX-first adopter journey recorded in ../craftreport-reporting-facade/first-release-continuation.md. Scope is existing requirements 3.1, 3.2, 3.5, 5.1 and 6.2. Existing public snapshot/report contracts and exact RunPins remain unchanged.

Ownership correction: add adapters/binding_codecs.py to the existing adapters owner's explicit file plan and typed/import checks. No new capability or ownership transfer. Keep task IDs/dependencies unchanged; implementation and acceptance remain task 5.1. All stated estimates are planning figures, not approvals to exceed enforced caps.

# Task 5.1 minimum implementation proposal

Scope: requirements 3.1, 3.2, 3.5, 5.1 and 6.2. This is a proposal for the reviewed transition required by design.md, not implementation authorization or behavioral evidence.

## Exact values and wire policy

Preserve the approved RunPins field names/order exactly: run_id, binding_id, binding_generation, snapshot, definition, template, theme, pack, resolved_parameters, parameter_digest, validation_scope, prepared_operation_id, prepared_result_ref, prepared_digest, target. All are frozen dataclass values; four version pins use contracts.pins.VersionPin; snapshot uses SnapshotRef; resolved_parameters is declaration-ordered tuple[tuple[str, Scalar], ...]. TargetIdentity has adapter_id, closed mode native/browser/headless, mandatory session_id/document_id.

BindingSpec holds binding_id, feed_id, requirements:InputRequirements, requirements_digest, the same four VersionPins, resolved_parameters, parameter_digest, validation_scope and target. BindingState holds spec, generation, revision, intent (initial stopped), selected_run_id; no applied claim is fabricated. BindRequest holds spec and expected_generation (0 for creation). InspectRequest is a closed binding/run discriminator plus identity. PreparedRunInputs has all immutable RunPins content fields except run/binding/generation/target, which runtime derives from the selected binding. PreparationIssue carries a closed failure code and safe locations, without private source values.

Resolve the currently unspecified validation_scope representation as a lowercase SHA-256 string matching reporting validation_scope_identifier(ReleasePolicy). Runtime imports no report/policy types. Requirements digest and parameter digest are SHA-256 over existing canonical JSON encoding of InputRequirements and declaration-ordered named tagged parameters respectively. Exact recomputation is required at ingress and retained decode; no caller-supplied digest is trusted. Use existing encode_parameter/decode_parameter for scalar kind/value envelopes, preserving int/decimal/date/time/text distinctions. No raw JSON numeric transport for int64, producer versions, generation/revision or expected_generation; bounded decimal strings with 0 permitted only for absent expected generation.

Reuse model_shape/StrictWireModel/PydanticCodec and TypeAdapter for concrete unions. Current snapshot_wire.py is 281/300 LLOC; snapshot_models.py is160/300. Add explicitly owned adapters/binding_codecs.py for binding wire conversion, importing the existing scalar/requirements/reference helpers. This is a concrete new operation codec, not a framework. Do not put ORM or report compiler types into values/runtime. Public results distinguish conflict/missing/unavailable and retain exact run values.

## Guard, resource and owner policy

Persist binding subjects from DurableJournal.retained(original operation), never from wire. Existing configured trusted owner policy must explicitly authorize binding creation/update/inspect, bound feed and target; the selected deployment/subject is fixed by host principal configuration. Reject a different subject before returning existence, pins or provenance. Binding inspect declares binding resource; run inspect declares run resource and resolves retained owning subject before content read. Bind declares only storage-owned binding and bound feed resources. A configured trusted principal-and-target allowlist predicate separately authorizes the exact TargetIdentity at ingress; no app resource/version or authoritative app-state observation is invented. Target authorization means the principal may name that configured target, not that its session/document exists, is live, or has been verified. Later app integration owns actual target verification before any effect.

Extend existing DurableResources with concrete binding read/effect routing. Use one combined_read(connection, resource) for guard and read; ReportResources.combined_read delegates to it rather than directly to snapshot store. Absent binding has authoritative token absent; retained resource token is decimal revision. Bind handler uses existing context effects; BindingStore checks current DurableLease and expected generation inside the same short transaction, retains spec/generation/revision and original command ownership, inserts binding_persisted evidence, and independently rereads exact bytes. Evidence inspection validates the closed binding fact, original command and exact historical committed spec/pins (not just current mutable binding). Reuse existing evidence/result tables and serialization. No direct handler database write or alternate journal.

Every semantic spec change increments generation and revision; identical spec may return unchanged state after checking expected_generation. Prior runs/evidence remain immutable. Selection reads actual retained snapshot, checks completeness and exact feed/ref; injected RunPreparer runs outside SQL transaction. Before commit, recheck generation/revision and compare all newly prepared snapshot/pins/parameter/scope fields. Retain exact prepared operation/result identity and digest. Task5.1 internal select_run is pin selection and retention only; it grants no running permission and starts no app effect. Initial stopped intent remains stopped after selection. Task5.3 must independently require running intent and recheck generation/lifecycle revision under its approved start fence before effect admission; retained pins alone never authorize start. Historical run readback survives binding replacement and restart.

## Schema and task boundary

Storage audit supplies exact v5-to-v6 bindings/runs columns, constraints and transactional upgrade. Existing migration validates recognized old schema before creating only new tables; preserve deployment identity/epoch/profile/settings and historical bytes; unknown/partial schemas fail untouched. Foreign keys connect runs to bindings and snapshots. Keep immutable historical binding evidence bytes in existing evidence table, avoiding a third table.

Task5.1 includes bind/inspect registrations, host injection, durable run selection and synthetic retained preparation collaborator tests. Task5.2 owns effect observations/applied advancement; task5.3 owns scheduling, lifecycle controls, start fence, cancellation and actual AppOperationCaller start; task5.4 owns restart reconciliation. Initial stopped intent permits task5.1 without implementing those operations. Documentation/example feature delivery remains task6.3, with this task recording narrow API evidence only.

## Budget and verification

Measured current storage1615/2000, runtime210/1500; audit reports adapters1567/1800. Planning additions: storage220-300 including v6/evidence/read routing; runtime250-400; adapters160-220; composition40-70. These are estimates, not guaranteed fits or permission to exceed caps. Preserve local50/300/10. No numeric cap changes. Closed schema/wire duplication is the main adapter risk; derive models from dataclasses and existing helpers.

Verify feature flag OFF failing tests, ON passing, removed passing; exact value mutation rejection and malformed scalar/digest rejection; generation/revision CAS; complete/incomplete selection; stale preparation rejection; principal denial; actual SQLite close/reopen preserving all pins and historical evidence; recognized v5 upgrade and unknown/partial v6 fail-untouched; ordinary REST/MCP catalog+bind+inspect using the installed harness. Run focused pytest, Ruff and strict Pyright; parent owns final frozen canonical gate.

## Exact acceptance clarifications

The numeric transport rule applies only to snapshot producer versions and numeric
counters (generation, revision and expected_generation). Generic
VersionPin.version remains the existing nonempty string label, including values
such as `1.0.0` and `house-blue`. Preserve existing scalar encodings. Verify a
nonnumeric version-label roundtrip.

The `binding_persisted` fact has exactly three keys: `schema_version` (the string
`1`), `before` (null on creation, otherwise canonical BindingState), and `after`
(canonical BindingState). Its canonical bytes are bounded to 2,097,152 bytes;
each encoded state is independently bounded to 1,048,576 bytes, and the total
fact bound is checked before any effect. The existing evidence row/reference
supplies operation identity, canonical fact digest and full completion pins.
Reject extra fields, invalid state/digest values and inconsistent identities.

Derive the original bind request from after.spec and before.generation (zero
when absent), encode with the actual request codec, and verify its fingerprint
against the retained runtime.bind command using existing normalization. Check
trusted command subject/deployment, binding/feed resource identities and all
original expected pins. Before.revision must match the original binding token;
creation requires absent. Creation produces generation/revision 1 and stopped
intent with no selected run. A changed spec increments generation/revision once,
clears selection and preserves the task's stopped intent. An identical spec
preserves the entire before state, including selection and revision. Stale
generation/version conflicts emit no binding persistence fact and no write.

The fact's completion versions are exactly the unchanged guarded feed token and
the resulting binding revision. No-op binds under a new operation ID retain a
new fact with identical before/after and unchanged resource versions. Insert
the fact atomically with the binding decision and independently reread both.
Historical verification uses the immutable fact, original command and its
complete pins; it must not compare after against a later mutable binding row.
The write path captures before from the guarded database read, never the caller.
Test historical evidence after replacement and selection as well as new-command
no-op binds.

The trusted injected RunPreparer owns report-specific acceptance before returning
PreparedRunInputs. In the actual reporting composition it must read the original
reports.prepare receipt through authorized inspection, require that its retained
result reference equals the returned reference and is available, independently
verify its passed `prepared` stage evidence with the complete original source
pins, and decode the retained result. Compare the decoded prepared content,
snapshot, four version pins, parameters/digest and validation scope exactly.
The prepared-content digest is distinct from the checksum of the enclosing
PreparationResult bytes; never substitute one for the other. Pending, missing,
unlinked or unverifiable preparation cannot select a run. A terminal failed
receipt with passed preparation and retained content may still support a draft;
it never grants passed quality or validated release. Preserve those findings.

Binding persistence independently verifies common retained operation/result
ownership, exact receipt linkage and canonical result checksum and matches all
returned pins against the selected snapshot and binding. Report-specific parsing
stays in the injected reporting collaborator, with no reporting imports in
runtime/storage and no new general verifier framework. Protected run readback
rechecks retained linkage; missing or purged supporting content cannot become
fresh successful preparation evidence. The standalone fixture uses a clearly
test-only preparer with actual retained result, passed preparation observation
and independently known content; it is never registered as production
reports.prepare or accepted as proof of GridCraft/XLSX behavior. No public wire
field can supply trusted preparation status.


# Task 5.1 exact retained schema proposal

Draft for independent review; not an approval. Scope is binding specification and immutable run persistence only. The approved design and journal-reuse-amendment require this reviewed version transition before new tables land.

## Physical schema v6

Reuse schema.py metadata, SQLAlchemy String/Integer/LargeBinary, canonical JSON and SHA-256. Columns are NOT NULL unless explicitly nullable below. No named constraints, indexes, cascade deletion, defaults or triggers.

`bindings`:

| Column | SQLAlchemy type | Constraint |
| --- | --- | --- |
| binding_id | String | Primary key |
| subject | String | Trusted retained command subject |
| generation | Integer | CHECK generation > 0 |
| revision | Integer | CHECK revision > 0 |
| operation_id | String | ForeignKey commands.operation_id |
| binding_bytes | LargeBinary | Canonical encoded BindingState |
| binding_digest | String | SHA-256 binding_bytes |

`runs`:

| Column | SQLAlchemy type | Constraint |
| --- | --- | --- |
| run_id | String | Primary key |
| binding_id | String | ForeignKey bindings.binding_id |
| binding_generation | Integer | CHECK binding_generation > 0 |
| feed_id | String | Composite FK below |
| producer_version | Integer | CHECK producer_version > 0; composite FK below |
| run_bytes | LargeBinary | Canonical encoded exact RunPins |
| run_digest | String | SHA-256 run_bytes |

ForeignKeyConstraint([feed_id, producer_version], [snapshots.feed_id, snapshots.producer_version]). Do not add a composite FK to mutable current binding generation: historical runs must survive generation changes. RunPins retains prepared_operation_id/prepared_result_ref/prepared_digest; verify those trusted links before insertion and on protected content read, without adding speculative lifecycle columns or duplicating prepared content.

## Trust and mutation invariants

The complete binding and run values use the reviewed runtime codecs, exact encode/decode roundtrip and encode_object/decode_object checksums. Binding ID, feed, generation and all run identity columns must match decoded values where represented; identities are nonempty, integer counters bounded to signed64. BindingState has exactly spec, generation, revision, intent and selected_run_id; intent is initially stopped, selected_run_id is nullable and refers to a retained run of this binding when present. BindingSpec is immutable per generation. Creation starts generation/revision at1. A changed spec increments both exactly once under expected resource revision and expected business generation; exact same spec does not invent a generation change. The original retained runtime.bind command establishes owner subject, operation linkage, declared resources, expected versions, normalized fingerprint and actual operation identity. Caller-supplied ownership is forbidden. Existing bindings cannot change subject.

Use Database.transaction and the already issued DurableLease, with guard.check inside the transaction immediately before mutation. Keep one explicit binding ResourceEffects branch; do not generalize the mutation API. Binding readback evidence reuses the existing evidence table with an explicitly reviewed closed fact and verifier. Historical evidence must verify its original immutable fact/command, not require the current mutable binding to equal an older generation. No generic evidence writer is authorized.

Selection uses the existing owner-scoped SnapshotQueryAdapter latest-complete selection. Preparation occurs outside SQL and kernel leases. Before run insert, recheck binding generation/revision and selected exact snapshot, then independently verify all returned RunPins against BindingSpec, snapshot content identity, original prepared operation/result/digest and trusted subject/deployment. Immutable run_id conflicts cannot overwrite an earlier run; exact repeated bytes may read back that run. Runs retain every original pin across binding updates. The selected_run_id in canonical BindingState is updated atomically with run insertion/readback and resource revision; selection alone does not change binding generation. Inspection joins runs to bindings.subject for trusted ownership, never to a request-supplied subject. Rebinding preserves old runs and clears the current selected_run_id. Task5.1 implements only the stopped initial intent, not start/pause/resume/stop transitions.

Resource read dispatch must compose binding/run resources alongside existing feed/snapshot resources. ReportResources.combined_read currently directly calls upstream.store.read; update the composed dispatch consistently so pack observations and binding guards work together. Current configured access policy remains authoritative; grant/ownership of target adapter/session/document must be explicit and checked before protected reads/effects. Persisted subject alone does not grant arbitrary target access.

## Exact migration

Validate all exact v5 tables/columns/constraints/DDL before writes. Preserve an explicit v5 table set; do not redefine v5 through newly expanded metadata. Add only bindings and runs, validate exact v6 object set and DDL, then update singleton schema_version to6 in the same existing transaction. Preserve deployment identity, epoch, retention profile/settings, existing rows and bytes. Fresh databases create exact v6. Supported older versions retain their reviewed sequential transitions through v5, then this exact v6 transition; unknown versions, extra/missing objects, changed constraints and partial v6 fail untouched. No migration framework.

Update Database maintenance and DurableHealth current-schema checks from5 to6 together. Maintenance still refuses any noncurrent schema without migrating it. Existing offline purge still affects only its approved snapshot/result content; do not add binding/run deletion. Schema migration failure rolls back new tables and deployment version together.

## Verification and footprint

Require populated v5 migration/reopen with byte-identical old records and deployment settings; fresh v6; supported old-version chain; current-v6 reopen; exact unknown/partial/extra-object rejection without writes; failure after first table creation and before version update rolls back both DDL/data; FK and positive-counter violations reject. Require real file reopening for binding and runs; owner denial; changed spec generation/CAS; stale selection prevention; incomplete snapshot refusal; exact prepared mismatch refusal; checksum/key corruption unavailable; immutable old runs after later binding changes. Existing installed-host REST/MCP acceptance remains task5.1's integration obligation, not established by schema tests.

Read-only Radon measurement of current source: storage1615/2000 (385 available), adapters1567/1800 (233 available). schema.py120, providers.py210, snapshots.py283. Forecast net storage: schema30–50, binding persistence170–220, resource/evidence/health integration50–90 =250–360. This is a fit estimate, not permission to exceed caps. Keep binding code out of snapshots.py (17 available); each module<=300, function<=50, McCabe<=10. Runtime and composition remain at their existing budgets. New strict codecs must fit the233 adapter reserve; do not relocate responsibilities merely to evade ownership.

