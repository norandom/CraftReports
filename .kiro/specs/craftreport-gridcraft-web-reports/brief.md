# Brief: craftreport-gridcraft-web-reports

Date: 2026-10-15. Discovery re-entry for the approved reporting foundation.
Language: English, matching the umbrella. This brief does not establish browser
feasibility, approved app contracts or a working reporting journey.

## Problem

Report users need an ordinary external producer to drive a reusable, live
GridCraft report and obtain an XLSX representing one complete snapshot. Today,
synthetic kernel success and browser feasibility work do not connect those
parts into a product workflow.

## Current State

The kernel has accepted synthetic-scope implementation. Browser verification
has approved phase plans and partial implementation; full browser/profile
acceptance remains open, including separate headed evidence. Snapshot/runtime
and report-model/packs are new discovery scopes. Historical native GridCraft
scripts are prototypes and cannot prove a released browser workflow.

The umbrella's
[requirements 6, 7, 8, 10 and 12](../craftreport-reporting-facade/requirements.md)
define the principal app journey, with snapshot/run, presentation, quality and
recovery obligations in 3, 4, 9 and 11 supplied by the appropriate child owners.

## Desired Outcome

With AI disabled, an ordinary client publishes supplied synthetic data, prepares
a reusable report, updates the identified released GridCraft page/document,
controls its refresh through the shared lifecycle operations, and exports one
pinned snapshot. Actual saved bytes and a fresh reopened workbook agree with
the displayed table, line chart, declared supported styles and run identity.
Partial, stale, disconnected or unverified effects remain explicit.

## Approach

Implement one thin GridCraft browser capability package consuming reviewed
snapshot-runtime and report-model contracts. Reuse the released app's verified
interaction/file route and existing Playwright evidence harness; retain
app-specific semantic rendering in the package. Ordinary REST/MCP/UI callers
invoke the same kernel operations and runtime lifecycle.

Direct GridCraft MCP is sufficient for individual supported app edits. The
facade adds reusable definitions, producer ordering, retained pins, lifecycle
control and report/artifact evidence. A new browser automation framework or
generic cross-app renderer would add machinery before this workflow works.
Implement the smallest supported end-to-end table/chart report first.

## Scope

- **In:** exact app/build/mode/page/document discovery; report-owned regions;
  table and line-chart rendering from prepared content; supported semantic-style
  mappings; unchanged external sentinel content; shared live lifecycle controls
  and freshness display; target read-back/conflict detection; snapshot-pinned
  actual XLSX save/download, byte inspection and fresh reopen; ordinary MCP
  integrated journey, public demo and truthful failure/recovery evidence.
- **Out:** native/headless engine substitution for browser effects, local
  GridCraft builds, source-only bridges, other Craft apps, a designer, financial
  calculations, alternate runtime scheduler, private-template distribution,
  SDK/notebook development and unverified target features.

## Boundary Candidates

- `packages/craftreport-gridcraft/`: installed capability descriptor/operations,
  browser-mode driver, owned-region renderer, target/artifact verification,
  package tests and app-specific support documentation. No generic transport
  extraction unless real reuse justifies it.
- Existing composition/interfaces wire one capability through the kernel;
  runtime retains binding/pinned-run lifecycle and reports app observations.
- Existing browser-verification owner supplies deployment/profile identity,
  acquisition and reusable evidence plumbing; app acceptance tests exercise the
  complete facade path rather than copy the fixture harness into production.
- Generic deployment configuration under `deploy/` only as needed, with
  explicit ownership and reuse of current documented GridCraft hosting.

## Out of Boundary

This package does not own publication ordering, storage journals, reusable model
compilation or quality-release policy. It supplies real effects and evidence to
those owners and never repairs missing contracts with a second local state
machine. Worksheet/browser controls request facade operations; they do not
create another refresh loop. Save and reopen are distinct evidence stages.

## Upstream / Downstream

- **Upstream:** accepted operation kernel; reviewed snapshot/runtime and
  report-model/packs interfaces; browser-verification's actual released-browser
  interaction/file capabilities. Model/runtime specs can be generated and
  independently accepted before browser feasibility closes.
- **Planning dependency:** consume both reviewed upstream designs before freezing
  this Design/tasks. Parallel app discovery or bounded feasibility work is
  permissible; implementation cannot assume unresolved contract names or routes.
- **Acceptance dependency:** each claimed app path needs matching current browser
  evidence. Headless unattended evidence remains scoped; missing headed evidence
  remains `MANUAL_VERIFY_REQUIRED`, and full browser-spec closure stays open.
- **Shared seam to settle in Design:** app session/document/build identity,
  declared owned region and generation; prepared content/theme mapping; pinned
  snapshot/run; apply/inspect observations; conflict/partial/ambiguous results;
  authorized destination and overwrite policy; immutable artifact identity and
  reopened table/chart/style comparison findings. Reuse kernel resource/version,
  outcome/stage and evidence values.
- **Downstream:** the integrated umbrella reference journey and future separately
  activated app packages. This feature does not activate them.

## Existing Spec Touchpoints

- **Extends:** no existing app implementation spec. Browser verification remains
  a separate prerequisite/verification owner, not the reporting package.
- **Adjacent:** snapshot-runtime owns scheduling/storage/recovery; report-model
  owns prepared semantics and policy; kernel owns dispatch/guards/receipts.
  Resolve any shared contract defect upstream and revalidate consumers.

## Constraints and Design Decisions

Use the latest official downloadable GridCraft release, minimum 0.6.1, with
recorded checksum/build, served from project-isolated Debian WSL Docker or an
explicit remote host. Never compile GridCraft. All unattended browser work is
headless; no foreground windows, X server or WSLg. Keep development tests on
Windows except affected Linux behavior/explicit platform acceptance.

Design must check the selected release's actual control/embedding/file
capabilities before choosing a route. Prefer a supported released bridge or SDK
when it establishes the required same-page effects; use browser interaction
where necessary. The earlier UI-only feasibility assumptions are historical,
not a restriction on newer official releases. Record unsupported bridge commands
explicitly rather than creating an unrestricted custom bridge.
An import/open bridge may create a new document; prove same-document identity
for live refresh rather than treating repeated workbook opens as owned-region
updates. Bootstrap/import and saved-byte capture can be separate supported uses
without claiming that the bridge also provides cell mutation, reads or save
acknowledgement identities.

Design must choose the actual verified browser control/file route, table/chart
and supported-style mappings, conflict oracle, live-control UI path and export
serialization/fencing. An independent headless MCP engine cannot establish
same-page browser mutation. A direct library-generated XLSX, if offered as a
separately named capability, cannot stand in for promised GridCraft export and
reopen. No unverified file-picker replacement or mocked save proves artifact
acceptance. Existing local 50/300/10 limits apply; review application of the
default 1,500 app capability LLOC budget, with no new numeric increase.
Before source lands, tasks must activate the exact reviewed owner in
`quality.toml` and extend `scripts/check_imports.py` plus its tests for the app
package and any narrowly justified Playwright import. Root coordinates shared
gate edits; do not broadly allow app SDK imports throughout the core.

## Documentation, Example and Acceptance

Reader: a report integrator or evaluator. Planned guide:
`docs/quickstarts/Quickstart_How_to_run_a_live_GridCraft_report.md`.
Planned ordinary-client recipe/demo:
`scripts/examples/run_live_gridcraft_report.py`, reusing the upstream synthetic
data/report pack. Package guidance belongs under
`packages/craftreport-gridcraft/docs/`. The app feature owner owns guide/demo
content and execution validation; ledger owners must cover app source, tests,
executable recipe, content, deployment and docs before task/code expansion.

Follow the guide against one identified page/workbook: publish versions, render
table/chart, exercise real controls, pause while publications continue, resume
to the highest complete version, and export while a newer publication arrives.
Inspect actual saved XLSX bytes and reopen in a separate verifier context;
compare the pinned values/types, chart series, supported styles and run identity.
Check unchanged sentinel content, one target disconnect/partial recovery case,
ordinary MCP evidence inspection and owned cleanup. Retain screenshots, flushed
review video and diagnostics with exact page/build/snapshot/artifact identities.
Unsupported or unavailable routes stay open; no polished guide creates a pass.

## Authorization and Next Gate

The [owner's overnight authority](../craftreport-reporting-facade/overnight-run-2026-10-15.md)
intentionally fast-tracks only the three foundation scopes within the recorded
deadline. Record it in future phase metadata; independent reviews and fresh
external-effect evidence remain mandatory. Next: initialize/register this spec,
generate bounded requirements, then settle app Design against both reviewed
upstream contracts and current browser findings. This discovery handoff does
not generate other phase files or close the browser acceptance gap.
