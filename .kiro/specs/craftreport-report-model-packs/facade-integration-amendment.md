# Facade integration contract amendment

Status: proposed for independent design/task review and explicit scope approval.
Prepared 2026-10-16. No source implementation, test execution, phase approval or
completion is claimed. This document is the only change made by its author.
The owner authorized completing the first visible workflow; that direction is
not approval of the upstream contract changes proposed below.

## Boundary and source findings

This amendment resolves report task 8 integration defects without a new guard,
journal, middleware system, dependency or budget. It reopens only task 7's result
alternatives and task 8's shared integration scope. Requirements 1.1–1.4,
3.2, 3.5, 4.3–4.7, 5.3–5.4 and 6.1–6.4 remain unchanged. Downstream visible
GridCraft, controls, XLSX byte/reopen and adopter acceptance remain mandatory.

Source inspection, rather than the earlier planning estimates, establishes:

- `application/execution.py` records a handoff using the original lease's full
  authoritative tuple. `storage/providers.py` captures that tuple through
  `DurableGuard.capture`, which requires the original active concrete lease.
  A wrapper delegating only snapshot pins cannot meet that identity contract.
- `application/dispatch.py` converts query handler exceptions into missing
  results. `reporting/ports.py:ValidationResult` has only a success shape.
- `application/outcomes.py` already implements an operator-owned
  `DiagnosticPolicy`; `Execution._effect` supplies its empty default.
  `_completion_failures` currently checks missing evidence before failed state.
- `themes/resolve.py` checks fixed capability ranges and mandatory properties,
  but the requested decimal/date properties depend on the selected theme.
  Rejecting every unsupported optional property in an input codec would reject
  supported requests that do not use that property.
- `ConfiguredPackReader` loads immutable packs at activation and filters reads
  by source scope. Missing and inaccessible reads deliberately share
  `PackFailure(not_found)`. Invalid/conflicting configured packs prevent
  activation; they are not per-request detailed source disclosures.

Discovery used the local kiro-spec-design guidance for light extension analysis,
boundaries and simplification. This is a draft amendment, not replacement of the
approved Design or its independent review record. No new technology is selected.

## One existing durable guard

Replace the Design's non-report-subset guard delegation paragraph with ordinary
assembly of one `DurableGuard(database, combined_read)` before activation.
`combined_read(connection, resource)` serves the two immutable report resource
observations and otherwise calls the existing `SnapshotStore.read` with that
connection. Report tokens and metadata use the existing canonical encoding and
unchanged exact pin definition. Missing pack observations remain missing.

Use that very guard instance for `DurableResources.guard`, the guarantee provider
and `DurableHandoffs`. The report resource reader serves the same observation
values and delegates other resources to the original durable reader. Snapshot
effects retain their concrete lease ownership checks and reject report-resource
mutations. Do not wrap leases or change `capture`, evidence pin equality, locks,
timeouts or handoff authority. Construct the assembly once; no replacement after
host activation or alongside active operations is permitted.

With full caller preconditions, the original lease contains all three pins.
With omitted preconditions, current admission issues an empty precondition
lease: do not describe it as a full pinned lease. Immutable snapshots and pack
activation observations supply the execution readback, and every successful
fact still carries the independently observed full three-resource tuple.
Partial caller preconditions remain kernel-supported where the descriptor allows
them; supplied changed pins must reject, and no caller subset replaces full
completion evidence. Record this distinction in tests and consumer documentation.

## Exact public result alternatives

Keep the existing success objects byte-for-byte in shape. Extend only the two
report result codecs to a closed disjoint alternative with a sole `failure` key:

```text
validate result = existing ValidationResult | {failure: ReportFailure}
prepare result  = existing PreparationResult | {failure: ReportFailure}
ReportFailure = {stage, code, recovery, issues, total_issue_count, omitted_issue_count}
```

`ReportFailure` is a frozen report-owned value in `reporting/ports.py`. `stage` is
`prepared` or `quality_evaluated`; `recovery` uses the existing
`RecoveryDisposition`. `issues` is a tuple of existing `DefinitionIssue`,
`BindingIssue` or `ThemeFailure` values: each already has exactly `code` and
`location`. Reuse their closed vocabularies and existing Pydantic/canonical JSON
machinery; no generic exception serialization, free-text detail or private path.
The outer code vocabulary is `invalid_definition`, `invalid_parameter`,
`incomplete_binding`, `pack_missing`, `input_unavailable`, plus the existing
closed `ThemeCode` vocabulary. Only `input_unavailable` and
`compatibility_unavailable` use `retry`; all other evaluated failures use
`correct_request`. Unexpected exceptions remain kernel service/result failures,
not fabricated domain errors. No `release_blocked` failure object is used because
that outcome has a real prepared result and quality findings.

Included preparation issues retain their exact codes/locations. Pack absence
uses `pack_missing`, stage `prepared`, no issues; it does not distinguish private
existence. Snapshot authoritative absence/conflict uses `input_unavailable` with
`correct_request`; provider unavailability uses the same code with `retry`.
These two existing provider outcomes are distinct by recovery, and are never
converted to successful empty content. The preceding general code mapping has
this explicit snapshot exception.

A validation query that successfully evaluates and retains a failure object has
receipt `complete` and an available failure result: completion means evaluation
finished, not that the definition is valid. It has no prepared result, quality
result, target stage or synthetic evidence. Malformed wire input still rejects
before handler execution. Failed encoding/retention remains a failed query
receipt or existing journal rejection; it must not become a successful evaluated
failure. Discovery remains unchanged.

Retained detailed issue locations are available only after both source and
artifact-scope authorization and the scoped pack read. They contain field/name
identifiers already permitted to that principal, never values, source bodies,
credentials or deployment paths. Do not expose these names in broadly reusable
receipt diagnostics: those use fixed public locations as specified below.
Unauthorized requests cannot reach semantic evaluation or inspect its results.

The result union is a compatibility change for task-7 clients expecting only
success. Keep operation version `1` only while these operations remain
unpublished, update the advertised schema and all three ordinary caller paths
together, and require independent review of that assumption. Existing successful
result bytes remain valid; mixed success/failure fields and unknown fields fail.
Failure detail is explicitly bounded: evaluate the existing checker once and
include its first `min(total_issue_count, 64)` issues in existing deterministic
checker order. `total_issue_count` is the exact size of that finite result;
`omitted_issue_count = total_issue_count - len(issues)`. An omission is a declared
bounded detail sample, never an assertion that the included issues are exhaustive.
Do not sort, shorten identifiers, change included codes/locations, silently
truncate, or add pagination or a second unbounded issue accumulator. Failures
with no issues have both counts zero. Counts and location integers are in
`0..2147483647`; reject inconsistent counts, including an included length other
than `min(total_issue_count, 64)`.

Each whole canonical issue is at most 4096 bytes, with at most eight location
components and each string component at most 128 canonical serialized UTF-8
bytes. These are report-produced location constraints: existing declaration and
resolved-reference checks bound parameter/source/field names to 128 bytes;
theme failures use the existing bounded identity/property vocabulary. The
selected dataset/field/metric names match those report requirements, so arbitrary
unused upstream names are not copied into report issues. Report checkers emit
locations no longer than eight components; the retained snapshot size/cardinality
bounds keep row indices and total issue counts below the stated integer limit.
This amendment does not tighten accepted snapshot/pack/request input limits.
Unexpected producer-contract violations fail truthfully, without clipping names
or reporting a successful evaluated failure. Verify these invariants against all
actual report failure producers during implementation.

The complete `{failure: ReportFailure}` canonical envelope is at most
`64 * 4096 + 1024 = 263168` bytes, below the unchanged validation 1 MiB and
preparation 8 MiB result limits. The 1024-byte allowance includes the fixed outer
keys, closed stage/code/recovery tokens, counts, array separators and wrapper.
Enforce this bound in the report result codec and verify maximal admitted issue
locations/counts; defensive overflow rejection is not a supported-input escape.
The existing three issue Literal code vocabularies are disjoint: decode by those
codes into the existing issue types, with no extra tag; reject unknown codes and
unknown fields. The success-result bound and its independent tests are unchanged.

## Narrow eligibility check before command admission

Add one optional typed eligibility callback to the existing command binding:
`Callable[[Q, Principal], Awaitable[Diagnostic | None]]`. Binding closes over the
immutable decoded request; `PreparedCommand` exposes only the bound
`Callable[[Principal], Awaitable[Diagnostic | None]]`. Existing operations default
to no callback. Queries do not acquire this callback. There is no registration
of pipeline stages, service provider or configurable execution order.

In `CommandAdmission._prepare`, invoke it after coarse/resource authorization,
health/capability checks, retry-key lookup, guard acquisition and the second
retry lookup, immediately before `_admit`. Inspect the original lease again
before journal admission if the callback awaited. Lease loss/conflict follows
the existing guard rejection path. Capacity reservation and acquired locks are
released on rejection as for other pre-admission failures.

The report callback performs a scoped immutable pack read and calls the existing
`resolve_theme` with the real injected compatibility callable. Its only semantic
eligibility purpose is exact selected-theme/override/target-support validation.
Absent/inaccessible packs produce safe `pack_missing`; theme failures map to the
closed safe diagnostic table below. Provider/checker unavailability yields a
retryable `service_unavailable` rejection. Unexpected exceptions follow existing
admission unavailability. No result, fact, journal acceptance, target effect or
operation ID is created by rejection. The handler rechecks the same immutable
selection and theme before preparation; this is guard defense using one existing
resolver, not another semantic implementation or cached mutable authority.

Retry lookup precedes this callback: equivalent retries return their retained
receipt and do not rerun eligibility, preparation or fact writes. Changed content
with the same key conflicts before callback. Existing authorization/health
checks still run before lookup; this does not promise bypass of a revoked grant.

A payload-only codec can reject fixed top-level mapping/version errors but cannot
know whether the selected theme requests an optional decimal/date property.
Therefore that partial approach cannot replace this check without either
weakening admission acceptance or overrejecting valid requests. Keep codecs
structural and use the single resolver after authorization.

## Existing diagnostic policy and truthful failed stages

Move the existing `DiagnosticPolicy` value unchanged to
`application/service_values.py` (retain an import/re-export from outcomes for
compatibility) so registry can reference it without the current outcomes/registry
cycle. Add a default-empty policy to `OperationBinding` and `BoundOperation`.
Only trusted installed bindings supply it; it is absent from request fields.
Pass the bound policy to `outcome_update` in `Execution._effect` and to the
existing `reject_request` sanitizer for eligibility rejection. No kernel import
of reporting and no general exception-to-diagnostic machinery is introduced.

Report policies allow exactly the closed outer failure codes/recoveries above,
plus `(quality_evaluated, release_blocked, correct_request)` and
`(prepared, service_unavailable, retry)`. Public diagnostic locations are only
`()`, `('definition',)`, `('parameters',)`, `('snapshot',)`, `('selection',)`,
`('theme',)`, `('overrides',)`, `('target_support',)`. Map domain roots `support`
to `target_support`; map binding issues to `snapshot`. Preserve full authorized
issue locations in typed results, not in an allowlist populated from untrusted
strings. Other operations retain their empty default; wrong operation keys,
unknown tokens, recoveries and locations remain suppressed by existing policy.

In `_completion_failures`, record a required stage's non-passed state before
checking absent evidence. Continue reporting absent/invalid evidence and continue
checking every supplied reference. Thus an explicit known failed stage produces
`stage_failed` and state `failed` even with no evidence; it can never produce
`passed` or `complete`. A stage never evaluated remains pending. Required passed
stages still require the same exact verified evidence. Canonical stage reasons
remain kernel-owned (`stage_failed`, `evidence_missing`, `verified`); domain
reasons/recovery are in the separately sanitized diagnostics and typed result.

| Evaluated outcome | Result and facts | Proposal and final receipt |
| --- | --- | --- |
| Draft preparation succeeds | Existing PreparationResult; both real facts | effect none; both required stages passed; complete only after result/evidence readback |
| Validated request blocked by required checks | Existing PreparationResult preserving draft eligibility and blockers; both real facts | effect none; prepared passed, quality_evaluated failed; failed receipt and release_blocked diagnostic |
| Known parameter/binding/definition failure after admission | ReportFailure; no prepared/quality success facts | effect none; prepared failed, quality_evaluated pending; failed receipt with exact allowed diagnostic |
| Result or evidence cannot be verified | Only actually available result/facts | Existing kernel failure policy; no complete receipt; do not mint replacement evidence |
| Interrupted/uncertain handler | No assumed domain result or facts | Existing unknown-effect/ambiguous policy and reconciliation obligations |

Effect `none` describes absence of an external report target mutation. Retained
results/evidence are operation bookkeeping; they do not claim a target effect.
Failure retention does not bypass stage failure to get a complete command.

## Existing task and file ownership requiring review

- Task 7: reopen `reporting/ports.py`, `adapters/report_models.py` and
  `adapters/report_codecs.py` and existing reporting codec tests for closed
  failure alternatives and the public schema/output-bound checks.
- Task 8: retain `reporting/operations.py`, `adapters/report_resources.py`,
  `composition/reporting.py` ownership and trusted fact writer scope. Root owns
  shared `composition/snapshot_host.py` assembly, installed entry point and
  ledger updates. Install one concrete report activation and pack health probe;
  preserve the accepted concrete retained-snapshot size prerequisite.
- Upstream kernel correction required by task 8: existing
  `application/service_values.py`, `registry.py`, `admission.py`, `execution.py`,
  `outcomes.py` and their focused tests. This explicitly supersedes task 8's
  instruction to keep kernel files unchanged. No transport change is proposed.
- Tasks 9–12 and downstream app consumers must handle validation failure results
  and release-blocked failed receipts with available content. Keep the planned
  `docs/quickstarts/Quickstart_How_to_prepare_a_reusable_report.md` and runnable
  `scripts/examples/prepare_reusable_report.py` in delivery and execution scope.

No new source path, capability or larger limit is authorized by this document.
Current shared adapter capacity is a blocker until measured fit is established;
removing a proposed custom guard saves forecast work, not existing measured
lines. No speculative savings from future refactors are credited. Root must
measure the whole candidate and residual required runtime/app codecs under the
unchanged 50/300/1500/10 limits, review concrete reuse/deletions and register any
necessary responsibility split before expansion. Do not move adapter algorithms
into composition or tests to pass the gate. If it cannot fit, return an explicit
scope/design blocker; this amendment does not resolve capacity by assertion.

## Required verification and approval decisions

Independent design/task review must approve: original-guard combined-read
assembly; both result alternatives and version-1 compatibility decision; the
narrow command eligibility callback and its precise ordering; policy plumbing
and safe locations; failed-stage classification without invented evidence; and
the exact reopened upstream file scope. Update authoritative Design/Tasks and
review references only after that decision. Existing approvals do not silently
cover these changes. Production implementation remains unapproved by this draft.

Before accepting task 8, run real kernel/file-backed integration proving:

1. Omitted, partial and full preconditions; changed pins; original handoff
   capture; full three-resource evidence; cancellation/lease loss and restart.
   Verify snapshot publication still uses its original concrete guard checks.
2. Coarse denial, resource denial and scoped-reader denial prevent semantic
   disclosure. Artifact grants alone cannot expose sources. Probe callback and
   handler call counts, no journal admission on rejection and no private tokens.
3. Top-level and requested-property unsupported/untested mappings reject before
   admission, malformed versions reject through the actual callable, optional
   unused unsupported properties remain acceptable, missing checker fails closed.
4. Exact success/failure result roundtrips, private-name location handling,
   query complete-plus-invalid semantics, failed-command available failure result,
   and release-blocked prepared-pass/quality-fail with both actual retained facts.
5. Unverified/missing/forged evidence still prevents completion; explicit failed
   stages stay failed without references; never-run stages stay pending; default
   policy suppresses unknown/wrong-operation diagnostics. Existing kernel query,
   command, retry and reconciliation behavior remains unchanged outside this seam.
6. Equivalent and conflicting retries avoid callback/effect replay, result/fact
   restart readback retains exact pins, and retention failure cannot be relabeled
   as successful evaluation. Verify zero/64/65/many issues, exact total/omitted counts,
   deterministic first-64 order, unchanged included locations, maximal names and
   row indices, typed code-discriminated roundtrips, unknown fields/codes and
   inconsistent counts. Check canonical 263168-byte envelope/4096-byte issue
   bounds and truthful overflow rejection without tightening valid source inputs.

Run canonical fast and integration checks sequentially with upstream snapshot
work and retain commands/exit codes and owned evidence. Installed REST/MCP,
quickstart/example execution, visible report behavior, XLSX saved bytes/reopen
and final feature validation remain later mandatory gates. This proposal records
no execution evidence and closes none of those gates.

