# Browser verification research and decisions

## Summary

- **Feature:** craftreport-browser-verification.
- **Discovery scope:** complex integration; full discovery on 2026-10-14.
- The released app is an egui canvas. Name Box, formula bar, clipboard, chart
  selection and file controls are candidate real UI routes, not a DOM cell API.
- The native Save picker is not Playwright's upload chooser. An explicitly
  controlled Chromium profile can exercise the released download fallback;
  acceptance must not imply default-browser or native-picker support.
- A single-series fixture allows a narrow live source-binding oracle: category
  field plus the selected chart's source-range outline, independently checked
  against actual saved OOXML. Runtime feasibility remains to be demonstrated.

## Research Log

### Project and reference workflow

Read approved requirements, brief, core steering, overview/testing/engineering/
breadth/documentation, ledger/quality policy, the current gate entry points and
CI. Applied `kiro-spec-design` full discovery, synthesis and review-gate rules.
The documentation extension requires both an executable recipe and a quickstart.
The design defines their reader outcome and evidence; future guide writing uses
the project's COBESY workflow and cannot claim undelivered capabilities.

Read-only local discovery confirmed the existing Python wheel includes only
`src/craftreport`, and fast checks already lint/type scripts and tests. Import
checking currently omits tooling, requiring targeted rules. The broad
development-gates owner has a roughly 969-LLOC baseline; it cannot absorb a whole
browser harness without a separately reviewed boundary/budget.

The sibling `../because-security-quant-terminal/perspective/tests/` provides
`owned-process.mjs`, `owned-directory.mjs`, `app-fixtures.mjs` and lifecycle tests.
Useful contracts are immediate resource registration, isolated contexts,
diagnostics before navigation, explicit safe recordings, context close before
video finalization, and forced cleanup as failure. Its Angular/server state,
Node imports and application assertions are not adopted. The local
`tests/kernel/installed_process.py` is another lifecycle reference, not a new
dependency of the public example.

### Released browser interaction

Sources are the inspected v0.6.1 tagged implementation; the prior requirements
discovery identified this as latest and recorded its official archive checksum.
Implementation resolves latest afresh and freezes the actual selected build.

- [Browser file services](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/web.rs):
  Open selects bytes asynchronously; Save chooses a native picker when present
  and otherwise uses a browser download. Cancellation is not persistence.
- [Formula bar](https://github.com/storytold/gridcraft/blob/v0.6.1/crates/ui-egui/src/formula_bar.rs):
  Name Box navigates references; formula bar displays/edits active cell content.
  egui IDs do not establish HTML selectors.
- [UI clipboard delivery](https://github.com/storytold/gridcraft/blob/v0.6.1/crates/ui-egui/src/lib.rs)
  and [grid copy handling](https://github.com/storytold/gridcraft/blob/v0.6.1/crates/ui-egui/src/grid.rs):
  real Copy can supply observed cell text, subject to browser focus/permissions.
  It does not establish stored numeric/string types. Freshness needs an independent
  nonce protocol so stale clipboard content cannot pass a disconnected action.
- [Chart rendering](https://github.com/storytold/gridcraft/blob/v0.6.1/crates/ui-egui/src/chartview.rs):
  selected chart values ranges are outlined when references are simple and on the
  current sheet. This supports a proposed single-series B2:B4 pixel/geometry check.
- [Chart dialogs](https://github.com/storytold/gridcraft/blob/v0.6.1/crates/ui-egui/src/dialogs.rs):
  Select Data displays an overall range, resolved series names and first category
  reference. There is no Edit Series values-reference field. Imported charts can
  have a blank overall source; requiring it populated would be a false oracle.

Implication: the first executable slice must prove these routes on real released
bytes. No source inspection, private engine call or headless receipt can close
the UI acceptance criteria. The design preserves blocked status if the chart
outline or fresh clipboard route cannot be observed reliably.

### Browser profile and artifacts

[Playwright downloads](https://playwright.dev/python/docs/downloads) provides an
event-bound download handle; copy its bytes before context closure.
[Playwright video lifecycle](https://playwright.dev/python/docs/videos) requires
awaiting context closure before treating video as finalized.
[File uploads](https://playwright.dev/python/docs/input#upload-files) supports
chooser-based import, not evidence of native Save-picker automation.
[Browser permissions](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-grant-permissions)
remain browser/profile-dependent; clipboard capability is checked rather than
assumed. [Browser installation](https://playwright.dev/python/docs/browsers)
ties the selected Playwright package to its browser binaries.

There is no verified browser flag in this research that guarantees picker absence.
Use a disclosed pre-navigation removal of that capability for the initial
Chromium download-fallback profile. The app/archive and its Save branch remain
unchanged. A replacement picker that returns synthetic bytes was rejected.
Firefox's natural fallback was considered, but adds an unproven clipboard path.
Native-picker behavior remains unverified and is not needed to claim this scoped
fallback journey. Any inability to remove the capability blocks the profile.

### Dependencies and fixture representation

Primary package metadata checked 2026-10-14:

| Dependency | Selected version | Declared Python compatibility |
| --- | --- | --- |
| [Playwright](https://pypi.org/pypi/playwright/json) | 1.64.0 | >=3.10 |
| [Pillow](https://pypi.org/pypi/Pillow/json) | 12.3.0 | >=3.10 |
| [XlsxWriter](https://pypi.org/pypi/XlsxWriter/json) | 3.2.9 | >=3.8 |

These metadata declarations support Python 3.12 selection, not a claim that the
new stack has been installed/tested here. Exact lock resolution and browser/system
dependency installation belong to implementation. Playwright and Pillow are
dev-only additions. XlsxWriter is a one-time fixture authoring tool; retain a
small static XLSX, its provenance and independent semantic expectations.
[Its chart API](https://xlsxwriter.readthedocs.io/chart.html) supports a line
chart with explicit category/value references. No runtime workbook writer or
financial computation is needed for this verification scope.

## Architecture Pattern Evaluation

| Option | Benefit | Cost / decision |
| --- | --- | --- |
| Development-only typed journey | Small ownership surface; ordinary Python demo and CI share actual path | Selected; must explicitly enforce tooling isolation |
| Production GridCraft plugin now | Could later serve report operations | Rejected here: introduces kernel integration and general adapter scope before feasibility |
| Native/headless MCP verification | Rich semantic commands | Rejected as browser evidence: different engine/document |
| General visual automation framework | Potential reuse across apps | Rejected: speculative breadth before one route works |
| Snapshot-only screenshot proof | Easy to record | Rejected: insufficient cell, file, source-binding and cleanup evidence |

## Design Decisions

### Generalization: one typed stage result

Readiness, edit observation, persistence, artifact inspection, reopen and cleanup
all need target identity, requirement references and independently inspectable
status. Use one local finding shape with distinct stages, without changing the
kernel's public receipts or introducing a generic workflow engine.

### Build versus adopt

Adopt Playwright, Chromium, existing Docker recipe, published app bundles and
XlsxWriter fixture authoring. Build only the small app-specific interaction map,
fixture expectation comparison and evidence reduction. Standard ZIP/XML parsing
is sufficient for the fixed fixture; do not build an XLSX renderer/recalculator.
Pillow supplies actual crop comparison rather than inventing image primitives.

### Simplification and ownership

Keep the recipe and helpers outside the production wheel. Use the existing
static-serving recipe with unique project/port/mount overrides instead of another
nearly identical Compose file. No database, service queue, public plugin or API
endpoint is introduced. A most-specific browser-verification tooling owner with
one 1,500-LLOC aggregate makes size accountable across its cohesive files.

### Independent oracles and bounded feasibility

The input fixture and expected before/after values exist before app execution.
Readback uses fresh real UI copy, chart binding uses observed range geometry and
category text, stored types/references use independently inspected bytes, and
reopen observes a fresh page. Reviewed visual baselines are profile-specific;
never derive them automatically from a candidate and call that candidate passed.
The disconnected-action challenge must fail before a restored separate run can
establish sensitivity and recovery. These are implementation acceptance gates,
not completed experiments in this design phase.

## Risks and Mitigations

- Canvas coordinates/accessibility vary: freeze measured profile geometry and
  require fresh runtime proof on change; no guessed selector counts as evidence.
- Chart-range highlight may be unstable or absent: retain 3.4 as blocked and
  return for a scoped decision; do not replace it with saved-file-only proof.
- Native picker cannot be driven by ordinary upload APIs: explicitly scope the
  controlled download-fallback profile, retain actual bytes, avoid native claims.
- Font/graphics changes affect crops: separate reviewed profile baselines and
  semantic checks; no broad tolerance adjustment merely to turn a run green.
- Partial startup can leak processes or video: register immediately and test
  failure/cancellation cleanup; forced termination remains acceptance failure.
- Latest release can change under a run: resolve once, pin all loaded assets,
  reject unknown profile geometry and revalidate before claiming compatibility.
- The 1,500-LLOC allocation is tight: validate the first slice against it; simplify
  or request an explicit amendment before additional scope, never hide helpers
  under test-only accounting.

## References

The primary sources above establish contracts and design constraints. Runtime
evidence remains the implementation deliverable. Local references:
[approved requirements](requirements.md), [brief](brief.md),
[testing steering](../../steering/testing.md),
[engineering steering](../../steering/engineering.md),
[documentation extension](../../steering/documentation.md),
[current setup](../../../docs/gridcraft-setup.md).
