# Browser verification brief

Date: 2026-10-14. The owner authorized initialization and requirements generation
for the next item in the approved five-part roadmap. Requirements, Design and
Tasks retain their separate human review gates.

## Problem and intended change

Report integrators and evaluators need to know that automation can change the
GridCraft workbook they can see and produce a file whose reopened content agrees.
Today, an nginx Compose probe serves the official browser bundle and a smoke
script has recorded rendering and input dispatch. The completed Python kernel
has synthetic REST/MCP evidence; neither proves browser workbook edits, file
persistence or a reporting connection.

This feature establishes a repeatable, isolated browser verification workflow:
acquire an official prebuilt release, identify the actual page/workbook, perform
a small known edit through supported browser interactions, save an XLSX, inspect
the saved bytes, reopen those bytes and compare the result. The evaluator can
watch the headed run; unattended execution retains screenshots, video and
diagnostics. A missing supported route remains a named feasibility finding.

## Boundary Candidates

- Released app acquisition and browser readiness, including the distinction
  between static assets and a server-side document engine.
- Project-owned or explicitly configured external deployments and isolated
  browser contexts, with exact app/document/artifact identities.
- Reference fixture interaction, actual file persistence and fresh-page reopen.
- Evidence, sensitivity/failure checks and truthful owned-resource cleanup.
- A task quickstart and executable Python adopter/demo entry point.

The reference fixture checks known cell values/types and unchanged sentinel
content. Its line-chart content is a feasibility check for the foundation's
required chart path, not declarative report compilation or a live dashboard.

## Included and excluded scope

Included: released-browser feasibility, an observable edit/save/reopen journey,
app/file capability findings, recorded safe diagnostics, repeatable verification
and a small executable demo without AI or private content.

Excluded: snapshot publication/scheduling, live start/stop or pause/resume,
template/theme compilation, production persistence, a general GridCraft adapter,
financial methods, GIPS evaluation, WOPI integration and other Craft apps. The
browser workflow does not inherit the kernel's passing status or close the
umbrella reporting acceptance criteria.

## Confirmed constraints

- Download the latest official GridCraft release, minimum 0.6.1, record its exact
  asset/checksum and do not compile GridCraft locally or substitute unreleased
  source features.
- Docker runs in Debian WSL here; Linux and explicitly provided remote instances
  are supported deployment orientations. `0.0.0.0` is a bind address, not a
  browser destination. The existing probe on port 8871 remains untouched.
- Playwright is the requested repeatable browser flow. Reference practices from
  `../because-security-quant-terminal` inform isolation, diagnostics, finalized
  recordings and cleanup; its application architecture is not part of this spec.
- Match the tested page, document, app build and saved artifact. A separate native
  or headless MCP workbook cannot substitute for the selected browser workbook.
- Retain screenshots and success/failure review videos using synthetic fixtures;
  saved bytes and reopened semantic content are separate evidence.
- Typed Python, Ruff, reviewed ownership/budgets and existing phase gates remain
  mandatory. Concrete modules, dependencies and numeric limits belong in Design.

## Known release facts and current evidence

Checked 2026-10-14: official latest release remains v0.6.1. The web archive's
published SHA-256 is
`86048ba175689ff852c141d6115e5491f0856f891300c3e1f91274b9c2709a42`.
The bundle contains HTML, JavaScript and compiled Rust/WASM, with no server-side
code. Tagged browser code uses file selection for Open and a native Save picker
when available, with a download fallback. A cancellation is not a saved artifact.
These source contracts are not runtime proof of every file route.

Primary references:

- [Official latest-release metadata](https://api.github.com/repos/storytold/gridcraft/releases/latest)
- [Release-tag hosting contract](https://github.com/storytold/gridcraft/blob/v0.6.1/packaging/web/README.md)
- [Release-tag browser file behavior](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/web.rs)
- [Browser mode contract](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/main.rs)
- [Current setup and probe scope](../../../docs/gridcraft-setup.md)
- [Session and protocol boundaries](../../../docs/craft-app-protocols.md)

## Planned user-facing artifacts

Quickstart: `docs/quickstarts/Quickstart_How_to_verify_GridCraft_in_a_browser.md`.
Proposed Python entry point: `scripts/examples/verify_gridcraft_browser.py`.
That example will run the same small browser journey used for verification and
demonstrate its visible and saved-file effects. The proposed path is a planning
reference; exact code ownership, supporting modules, fixture ownership and
dependencies are reviewed in Design. No future feature guide or executable
implementation is created during requirements work.
