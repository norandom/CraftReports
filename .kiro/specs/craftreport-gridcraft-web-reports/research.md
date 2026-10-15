# GridCraft web-report integration research

## Summary

Research only, 2026-10-15. App Design/tasks remain pending both upstream reviewed
contracts. This record preserves an independent library/release assessment by
`/root/downstream_library_architecture`; it establishes no new runtime acceptance.

## Released browser boundary

The selected official v0.7.0 downloaded web archive has SHA256
`ad10af2baf9c7ed4ccbd81e32b37698f5075cdf4f26b726fee7fc7938a3a8d27`.
The reviewer checked distributed JS/WASM hashes against the cached bundle record.
The JS imports parent/origin/postMessage facilities; the compiled WASM contains
the bridge event names. This corroborates compiled capability presence, not
successful end-to-end behavior.

The opt-in `?host=parent` bridge accepts `gridcraft:open` and emits `ready`, `save`,
`dirty` and startup `failed`. It checks same origin and parent-window identity.
It provides no general cell-command/query interface, save trigger, request ID,
document identity or open-applied acknowledgment. The host must independently
bind page/session/run identity and persist/verify saved bytes. GridCraft's saved
flag follows posting bytes and cannot establish successful host persistence.

Sources: [released host bridge](https://github.com/storytold/gridcraft/blob/v0.7.0/apps/gridcraft-web/src/host.rs),
[official releases](https://github.com/storytold/gridcraft/releases).

Repeated file open adds a document except when replacing an untouched initial
blank. It is not a supported same-document refresh mechanism. A live report must
retain the intended document and preserve unrelated content.
[Released file commands](https://github.com/storytold/gridcraft/blob/v0.7.0/crates/engine/src/cmd/file.rs).

## Smallest useful integration candidate

Use a verified bridge or actual picker to load an initial workbook. Bind the
table and line chart to an owned region, then perform narrow real UI updates in
that same document. Serialize app actions, verify document/run markers and reject
conflicting external edits. Host controls may call the shared facade lifecycle;
they must not create another scheduler. Actual Save bytes need inspection and a
fresh-context reopen against the pinned run. These are candidates for Design
and feasibility proof, not current capability claims.

The existing browser harness is a verification owner, not production reporting
logic to copy wholesale. Reuse supported library facilities and semantic checks;
keep the release-specific driver in the GridCraft package.

## Workbook libraries and precision

XlsxWriter is a candidate for initial workbook construction. Explicitly write
text and disable formula/URL conversion; its default formula conversion is unsafe
for supplied text semantics. Numeric cells use floating-point representation,
normally limited to 15 significant digits: reject unsupported numeric precision
or require an explicit text representation. Check write return values for failed
or truncated writes.
[Workbook options](https://xlsxwriter.readthedocs.io/workbook.html),
[worksheet writing](https://xlsxwriter.readthedocs.io/worksheet.html).

openpyxl is a candidate independent inspector, but load/save is not a transparent
arbitrary-workbook editing path: unsupported shapes can be lost. Do not use it
to silently normalize the artifact being verified.
[openpyxl tutorial](https://openpyxl.readthedocs.io/en/stable/tutorial.html).

Library-generated XLSX can bootstrap a report; it cannot substitute for promised
GridCraft export/save and reopen evidence. Pin any adopted dependency only after
reviewed Design selection and actual compatibility checks.

## Current runtime caution

On 2026-10-15 a Windows headless fixture-refactor review failed at `chart-before`
before Save, while the no-file scenario passed. The refactor was withdrawn.
The healthy failure is retained at
`artifacts/browser-verification/task-3.3/acceptance/a70eaed1-332f-4fd2-9835-ac3d7c400386`.
The category-copy screenshot exists and visibly shows the selected reference;
the receipt remained unresolved. Root cause is not established, and neither
the screenshot nor source equivalence proves a successful chart observation.
Both owned deployments cleaned up gracefully. App acceptance must resolve
relevant timing/readback failures against its actual final driver and workload.

## Design discovery and synthesis, 2026-10-15

Consulted `kiro-spec-requirements`, `kiro-spec-design` full-discovery, synthesis
and review rules, `kiro-spec-tasks` ordering/review rules, all required steering,
the breadth/quality ledgers, umbrella requirements and both independently
accepted upstream designs/tasks. Documentation steering's COBESY guidance is
applied narrowly to the adopter task/result/verification sequence; it does not
create a rollout program or a substitute acceptance gate.

The installed kernel already offers capability factories, explicit service
bundles and composable `GuaranteeProviders`, but no general evidence writer in
ordinary command contexts. Snapshot storage owns only its documented retained
resources/effects. The app therefore owns bounded immutable external-effect
facts and exact app resource/evidence/guard wrappers, delegates kernel
journal/results/handoffs unchanged and adds no upstream table. Root confirmed
this as a Design proposal requiring independent review, not an approved
implementation shortcut. Actual UI rechecks remain necessary: a stored local
document revision does not fence external user edits.

The existing `scripts/browser_verification/interactions.py` has one B3 edit,
fixed canvas selection geometry and fixture-bound checks. Its chart observer
also uses calibrated controls/crops. Reusing acquisition/evidence utilities in
acceptance tooling is reasonable; copying that fixture driver into production
would not yield a generic or proved reporting capability. No `packages/`
directory existed at discovery.

### Selected composition and simplifications

- Keep one fixed shape per binding (bounded table/chart dimensions and types),
  construct the bootstrap once and use real UI value edits in that document.
  Reject structural/shape changes before mutation; no repeated open or padding.
- Use a small same-origin companion panel with native controls calling the
  existing facade. Its polling reads shared runtime state; it owns no schedule.
- Prefer the official same-origin parent bridge for one bootstrap and actual
  Save byte capture, with real keyboard/menu Save. Its missing request/document
  identifiers require an exclusive lane plus independently checked workbook
  markers and exact bytes. This is a proposed real feasibility route, not proof.
- Actual app inspection saves supplement UI clipboard/chart observations for
  types/styles and conflict checks. They have native saved/dirty side effects
  and are explicit scratch evidence, never user exports. After-dispatch failures
  remain partial/unknown. One lane covers inspection/update/export; independent
  reopen consumes immutable captured bytes in a separate context.
- App facts retain external effects only. The sole operation retry/history and
  retained result authority stays in the durable kernel providers. No generic
  transport, browser framework, alternative compiler or storage engine is added.

### Dependency verification

Official package metadata checked on 2026-10-15 selects XlsxWriter 3.2.9 and
openpyxl 3.1.5, both declaring Python >=3.8; openpyxl declares et-xmlfile.
These are Design dependency selections and still require lock/install/compatibility
verification. Existing Playwright is pinned 1.64.0. Sources:
[XlsxWriter metadata](https://pypi.org/pypi/XlsxWriter/json),
[openpyxl metadata](https://pypi.org/pypi/openpyxl/json),
[Playwright download API](https://playwright.dev/python/docs/api/class-page#page-expect-download).

XlsxWriter's explicit write APIs/options avoid accidental formula/URL conversion;
normal numeric cells do not support arbitrary Decimal38 precision. The app
profile must reject unsupported precision before mutation and still compare
actual saved values; the preparation layer's broad scalar support does not grant
browser fidelity. openpyxl is used only to inspect, never resave/repair the
artifact under verification. Bounded ZIP/XML checks precede workbook parsing.

### Rejected routes and open gate

Repeated open creates a different document and is rejected as live refresh.
Independent headless engines or direct library XLSX generation cannot establish
browser mutation/app save/reopen. A custom general cell bridge or app source
patch would violate the released-boundary scope. Native prototype behavior and
the failed chart fixture are not promoted into support claims.

The first real feasibility task must establish same-document input/readback,
chart/style effects, unchanged outside content, official Save correlation,
actual persisted bytes and fresh GridCraft reopen. It must also reject a
deliberate owned-cell conflict. If this does not work, production expansion stops
and the route returns to independent Design review. No new runtime acceptance
was performed while writing this Design. Headed acceptance remains
`MANUAL_VERIFY_REQUIRED`.
