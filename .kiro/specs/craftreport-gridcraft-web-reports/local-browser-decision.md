# First-release browser ownership

On 2026-10-16 the owner selected **Local Windows browser launched by
CraftReport** for viewing the first live workbook. This resolves the deployment
choice for the existing adopter launcher and same-session report design.

The user runs the Windows launcher. It opens an isolated visible browser
context containing the companion controls and the GridCraft workbook that
CraftReport actually controls. Publication, refresh, controls and export refer
to that identified page, document and engine. Opening the static hosting URL in
another tab creates another engine; it is not a view of the controlled workbook.
The guide must make this distinction explicit and direct the user to the
launcher-owned window.

Debian WSL Docker, or a configured Linux server later, serves the downloaded
GridCraft web bundle. Its Rust/WASM engine runs in the Windows browser. The
Windows launcher owns browser interaction; a container does not need an X
server. This decision adds no shared remote session, browser streaming service,
multi-user synchronization or new app protocol.

The launcher uses the reviewed facade and app adapter, not another lifecycle
loop. Its shutdown closes only resources it owns. A closed or disconnected
controlled page must produce the existing unavailable/conflict/recovery outcome;
the launcher cannot silently substitute a new engine as the old document.

## Implementation and verification

Carry this choice into existing GridCraft integration and adopter tasks, including
`scripts/examples/gridcraft_report_host.py`,
`scripts/examples/run_live_gridcraft_report.py` and the planned
`docs/quickstarts/Quickstart_How_to_run_a_live_GridCraft_report.md`.
These are planned deliverables, not runnable instructions today. Existing
ownership, source budgets and task dependencies remain unchanged.

Automated development and acceptance runs remain headless Windows runs. The
owner's choice authorizes a user-launched visible product experience; it does
not authorize unattended foreground tests. A headless profile's rendering and
interaction proof does not establish headed profile support. Record the actual
headed browser/profile and verify visible table/chart updates, controls,
identity, export and cleanup before accepting that experience. Until an
explicitly requested visible review supplies that evidence, its acceptance
remains `MANUAL_VERIFY_REQUIRED`.

This decision records the owner's selection. The corresponding design/task
integration still requires independent consistency review before acceptance;
it does not close any implementation task or waive a verification gate.
