# Brief: craftreport-report-model-packs

Date: 2026-10-15. Discovery re-entry for the approved reporting foundation.
Language: English, matching the umbrella. This is a discovery brief, not a
finalized Design or an implemented report compiler.

## Problem

Report owners need to reuse a table/line-chart report with new supplied data and
consistent presentation without rewriting workbook commands. They also need
clear evidence of what was checked; professional formatting must not imply
financial-method validation or standards assurance.

## Current State

The accepted kernel supplies guarded operations and evidence values, but no
report-definition language, compiler, semantic theme resolver, pack loading or
quality policy evaluation. The umbrella's
[requirements 1, 4, 5 and 9](../craftreport-reporting-facade/requirements.md)
define this boundary; reproducibility/access criteria in 3, 10 and 11 apply at
its seams. Browser verification is in progress and does not compile reports.

## Desired Outcome

A report owner validates one declarative reusable definition and public pack,
binds explicitly supplied values, resolves a semantic theme and receives a
deterministic target-neutral prepared report with pinned identities and scoped
findings. An external private fixture pack follows the same validation path.
Required failed/unevaluated checks permit marked draft eligibility and block a
validated release label; actual export and final target consistency are app-owned.

## Approach

Use ordinary typed models, pure compilation functions and existing kernel
codecs/registrations. Start with the required table and line chart, typed
parameters and one semantic profile. Load declarative packs from explicitly
configured sources; use qualified identifiers and exact versions. The compiled
report is a plain value, not a generic command language or app-session handle.

Direct app scripts are appropriate for isolated edits but do not provide these
reusable definitions, snapshot pins or scoped findings. A universal report
designer/DSL is substantially larger than the foundation. The chosen small
compiler prepares the concrete first workflow and leaves unsupported constructs
explicit rather than adding generic plugin machinery.

## Scope

- **In:** versioned definitions and typed parameters; named dataset/metric
  bindings; one supplied-value table and line-chart model; deterministic content
  preparation; semantic themes and permitted overrides; public/configured private
  declarative pack compatibility and visibility; scoped findings, invalidation
  and draft/release eligibility; ordinary REST/MCP validation/preparation.
- **Out:** financial calculations/aggregation, portfolio/GIPS methods, arbitrary
  Python/formulas/SQL in definitions, visual designer, Crystal compatibility,
  subreports/cross-tabs, alternate Craft applications, generic policy language,
  private-repository synchronization and browser/export implementation.

## Boundary Candidates

- `src/craftreport/reporting`: definition/parameter contracts, binding validation
  and pure preparation into table/chart content and pinned presentation metadata.
- `src/craftreport/themes`: semantic-role resolution and compatible declarative
  pack/template selection, without numerical reinterpretation.
- `src/craftreport/policies`: separate layout, template, consistency, compliance
  and accuracy findings and explicit draft/release eligibility. A required check
  with missing evidence stays unevaluated; imported evidence stays external.
- Existing interfaces/composition use the kernel facade; public data-only packs
  live under `examples/`. Private packs remain outside checkout/build context.

## Out of Boundary

Runtime owns accepted input storage, run/binding retention and scheduling. This
capability receives immutable values and produces prepared content/findings; it
does not publish snapshots, move the latest pointer or maintain app state.
GridCraft owns style mapping support, actual mutation, export/reopen and resulting
consistency evidence. Compilation cannot call those stages passed in advance.
Pack source visibility and rendered-artifact distribution are distinct policies.

## Upstream / Downstream

- **Upstream:** accepted operation kernel and approved umbrella acceptance
  baseline. Snapshot-runtime planning is independent; compiler tests can consume
  plain snapshot fixtures through the agreed immutable value seam.
- **Downstream:** GridCraft web reports consumes the reviewed prepared-report
  contract and theme requirements; runtime consumes declared binding requirements
  to select complete input. Integration waits for both reviewed value contracts.
- **Shared seam to settle in Design:** schema/versioned snapshot view and input
  requirements; prepared table columns/typed cells and line-chart series/order;
  definition/parameter/pack/theme pins; target-required capabilities; scoped
  findings with evidence references; draft designation and release decision.
  Reuse kernel identities/outcomes instead of inventing a second receipt type.
- Keep snapshot values/storage independent of compiler imports. The app reports
  real target/output observations to the findings evaluator; it does not
  implement a second policy engine or weaken required checks.

## Existing Spec Touchpoints

- **Extends:** no existing executable scope; this bounded spec allocates the
  umbrella's reusable report/presentation and release-policy obligations.
- **Adjacent:** snapshot/runtime owns data and retained lifecycle; kernel owns
  access/dispatch/evidence mechanics; GridCraft owns target rendering/output;
  browser verification remains its distinct feasibility/evidence owner.

## Constraints and Design Decisions

Use typed Python and installed Pydantic/schema support. Prefer a small concrete
schema and ordinary functions to a custom extensible language. Definitions and
packs cannot contain executable code. Preserve imported values, precision,
labels, units and method metadata; presentation changes create new evidence.

Design must settle the minimum supported schema/types, one theme's semantic
roles, long-label/null/empty-data behavior, configured pack-root resolution,
asset/path boundaries, duplicate-version conflict handling, source/artifact
visibility and exact release-check scope. Do not imply supported output styles
until a target has verified their mapping. Existing 50/300/10 local limits apply;
review default 1,500 capability budgets for reporting/themes/policies before
implementation without increasing them or splitting merely to evade budgets.
Before source lands, tasks must activate the exact reviewed owners in
`quality.toml` and update `scripts/check_imports.py` and its tests for narrowly
declared reporting/themes/policies dependencies. Root coordinates shared gate
edits; do not bypass kernel-only import rules or disable the gate.

## Documentation, Example and Acceptance

Reader: a report owner/integrator. Planned guide:
`docs/quickstarts/Quickstart_How_to_prepare_a_reusable_report.md`.
Planned runnable ordinary-client recipe/demo:
`scripts/examples/prepare_reusable_report.py`, consuming synthetic definitions,
templates and themes under `examples/reports/`, `examples/templates/` and
`examples/themes/`. The feature owner owns guide content and execution evidence;
ledger ownership must include executable recipes separately from content packs.

Follow the guide to prepare one table/chart report against two different supplied
snapshots, preserving values and producing pinned content. Exercise missing
bindings, incompatible/private pack visibility, unsupported executable content
and a required unevaluated-check draft/release rejection. Inspect prepared values
and findings using an ordinary caller with AI disabled. Public checks must pass
without private packs. Check distribution contents and safe diagnostics for the
private synthetic fixture; do not publish private source bodies/assets. Record
actual commands/effects and clean up only owned resources. This demo proves
preparation, not live rendering or XLSX fidelity.

## Authorization and Next Gate

[Overnight authorization](../craftreport-reporting-facade/overnight-run-2026-10-15.md)
fast-tracks this scope within the recorded deadline while retaining independent
reviews and fresh acceptance evidence. Future phase metadata must record its
provenance. Next: initialize/register this spec and generate/review requirements
and Design in parallel with snapshot-runtime. App integration planning consumes
their reviewed contracts. This handoff generates no downstream phase files.
