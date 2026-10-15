# Brief: craftreport-snapshot-runtime

Date: 2026-10-15. Discovery re-entry for the approved reporting foundation.
Language: English, matching the umbrella. No phase files or implementation are
approved by this brief alone.

## Problem

External Python producers need to publish reusable data without coupling their
allocation framework or notebook to one workbook. Report users need a reliable
answer to which input was accepted, which version is displayed and what survives
a restart. The synthetic kernel providers establish none of that durability.

## Current State

The operation kernel is accepted within its synthetic scope. It already owns
dispatch, retry admission, resource/version guards, receipts, result read-back
and access checks. Production publication, storage, retained bindings and live
scheduling are absent. The umbrella's acceptance baseline is
[requirements 2, 3, 7 and 11](../craftreport-reporting-facade/requirements.md),
with shared operation/access and limit criteria in 10 and 12.

## Desired Outcome

An ordinary REST or MCP producer publishes a complete, explicitly typed,
producer-ordered snapshot and retrieves the same immutable content after a
service restart. A runtime binding can pin one snapshot, distinguish accepted
from applied state, pause/resume to the latest complete version and expose
unresolved effects truthfully. Actual GridCraft mutation remains app-owned.

## Approach

Build a thin publication and runtime capability on the installed kernel. Use
existing Pydantic codecs and operation registration; choose one mature durable
storage implementation during Design. Keep complete replacement snapshots as
the first useful input path. Do not create a generic persistence framework,
query compiler, event bus or second operation journal.

The alternatives are one expanding umbrella implementation (hides ownership)
and a generalized multi-backend runtime (adds machinery before a second useful
workflow). The chosen bounded capability lets report preparation proceed
independently and supplies the state needed for the first real live report.

## Scope

- **In:** named typed datasets and imported metrics; feed identity and ordered
  producer versions; immutable accepted snapshots; duplicate/stale/conflicting
  publication outcomes; retained kernel-provider guarantees; run pins and binding
  generations; one-process refresh coordination, 10-second reference cadence,
  pause/resume/stop and restart reconciliation; retention/missing-state reporting.
- **Out:** financial calculations, GIPS evaluation, append/merge/patch ingestion,
  notebook or client SDK, multi-worker orchestration, alternate databases,
  report layout/theme semantics, concrete browser mutation and XLSX export.

## Boundary Candidates

- `src/craftreport/data`: publication contracts and validation preserving declared
  types, labels/order, precision, units, timings and producer/method provenance.
- `src/craftreport/runtime`: retained run/binding state, selected complete version,
  scheduler lifecycle and recovery. It owns scheduling; app controls call it.
- `src/craftreport/adapters/storage`: the selected concrete durable providers,
  including the existing kernel's `OperationJournal`, `ExecutionGuard`,
  `ResultStore` and resource/evidence contracts where required by assembly.
- Existing interfaces/composition register and wire the capability through the
  shared facade. They do not acquire alternate validation or completion state.

## Out of Boundary

The runtime records an app-reported effect; it cannot manufacture successful
visible mutation. Report completeness is evaluated against declared binding
requirements supplied by the report model. Pure snapshot publication must not
import a report compiler or app driver. A published snapshot may be valid input
while incomplete for one report; that distinction must survive read-back.

## Upstream / Downstream

- **Upstream:** accepted operation kernel, approved umbrella requirements and
  [overnight authority](../craftreport-reporting-facade/overnight-run-2026-10-15.md).
- **Downstream:** report-model preparation consumes immutable snapshot values;
  GridCraft web reports consumes retained pins, bindings and lifecycle services.
  Browser feasibility is not a prerequisite for publication/restart acceptance.
- **Shared seam to settle in Design:** one plain immutable snapshot value with
  feed/version, datasets/schema, supplied metrics/provenance, content identity
  and distinct timestamps; binding requirements; run pins; conditional applied
  version advancement and partial/ambiguous effect observations. Use kernel
  `ResourceRef`, `ExpectedVersion`, `OutcomeProposal`, `StageResult` and evidence
  identities rather than parallel versions of those contracts.
- Report-model planning can proceed independently against that reviewed value
  seam. Integration waits for both reviewed contracts; no dependency cycle is
  created by putting compilation inside publication.

## Existing Spec Touchpoints

- **Extends:** no existing executable scope. This is a new bounded owner of the
  existing umbrella's publication/runtime obligations.
- **Adjacent:** kernel owns guard/admission semantics; report-model owns
  definitions/completeness and findings; GridCraft owns external target effects;
  browser verification owns released-browser feasibility and evidence harness.

## Constraints and Design Decisions

Use typed Python 3.12, locked kernel tools and the existing 50 function / 300
module LLOC / complexity 10 limits. New owner application of the default 1,500
capability LLOC budget needs review; this brief authorizes no increase.
Before source lands, tasks must apply the reviewed default to the exact owners
in `quality.toml` and extend `scripts/check_imports.py` plus its tests for the
reviewed data/runtime/storage dependencies. Root coordinates shared gate edits;
blanket import-rule relaxation is outside this scope.

Design must choose persistence from the existing reviewed candidates, justify
the bounded writer/concurrency workload, define atomic snapshot acceptance and
retry-journal recovery, and demonstrate restart read-back. No database/ORM is
selected here; DuckDB remains excluded. Prefer library transactions/query
expressions to handwritten SQL or a custom file-database engine. Polars is the
requested processing direction when needed; a small typed publication does not
need a dataframe-to-SQL round trip or a new supported ingestion format.

Define supported wire types/precision, integer producer ordering, canonical
content identity, retention, scheduler ownership, cancellation and restart
reconciliation before tasks. An interrupted external effect stays ambiguous
until inspected; restart must not blindly replay it or auto-claim a live target.

## Documentation, Example and Acceptance

Reader: an external Python producer/integrator. Planned guide:
`docs/quickstarts/Quickstart_How_to_publish_and_recover_a_snapshot.md`.
Planned runnable ordinary-client recipe/demo:
`scripts/examples/publish_and_recover_snapshot.py`, with public synthetic data
under `examples/data/`. The runtime feature owner owns its content and actual
execution validation; documentation and executable-code ledger owners must
explicitly cover those paths before tasks/code expand.

Follow the guide to publish, inspect, restart the owned service and retrieve
identical accepted values/identities. Exercise duplicate and stale/conflicting
publication, a rejected incomplete report binding, paused publication/resume
selection and one interrupted-effect recovery path. Verify retained bytes/state,
not just HTTP/MCP success. Record exact source/environment, commands, receipts,
evidence and owned cleanup. Do not claim visible-report acceptance from this demo.

## Authorization and Next Gate

The owner's eight-hour unattended instruction intentionally fast-tracks the
three foundation scopes through phase generation and implementation inside the
recorded deadline. Record that provenance in future `spec.json`; independent
requirements/design/task/implementation reviews and fresh evidence remain.
Next: initialize this bounded spec, register ownership, then generate/review
requirements and Design alongside the independent report-model spec. This
discovery handoff does not itself execute those phases.
