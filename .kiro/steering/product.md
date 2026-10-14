# Product Overview

Updated: 2026-10-14. Consolidated from confirmed project decisions and approved foundation requirements. Capabilities described here are intended product behavior. Kernel implementation is in progress; the repository does not yet provide a production reporting service.

CraftReport is a public reporting facade for external data producers and Craft applications. Report owners describe reusable reporting intent; software callers invoke the same validated operations. The product aims for professional layout, templates, consistency, compliance evidence and accuracy with separately scoped checks.

## Core Capabilities

- Declarative report definitions, typed data bindings, parameters and versioned templates/themes.
- Publication of external datasets and imported metrics into identified snapshots, preserving meaning and provenance.
- Visible live GridCraft reports with controls, freshness and truthful pending/partial/failure states.
- Snapshot-consistent XLSX artifacts with actual byte inspection and reopen verification.
- Deterministic app-to-app MCP and data-push operations, with shared validation and optional AI access.

## Target Use Cases

The first specification delivers the reporting foundation using supplied portfolio data and metrics. The allocation framework and Jupyter remain external producers. CraftReport does not implement their optimization, calculations, notebooks, kernels or client SDK.

Local financial-method calculations and built-in GIPS rule packs are deferred. Later accounting, forensic, invoice, tax, book, correspondence and assessment use cases reuse common report content, templates, evidence and app contracts after bounded scope activation. Generic documents do not require portfolio datasets or compliance checks unrelated to their domain.

## Value Proposition

One reporting contract connects live viewing, frozen artifacts and software automation. Shared semantic themes standardize presentation across supported targets; versioned inputs and scoped evidence make consistency reviewable. AI is an optional caller, not an execution prerequisite.

Professional appearance is distinct from independently checked numbers or standards conformance. Imported metrics retain producer/method identity and an explicit validation status. A validated-report label states its checked scope rather than implying firm-wide or domain-wide assurance.

## Publication and Release Boundaries

Public engine/examples operate without private packs. Private layouts, branding, policies, credentials, inputs and runtime outputs remain deployment-specific and are not automatically bundled into public builds/catalogs. Template-source visibility and artifact distribution permissions are separate.

Failed or unevaluated required quality checks permit clearly marked drafts and block release as validated output. Draft export still respects input, access and artifact verification rules.

The four work lines and current reality are in `overview.md`; scope/ownership lifecycle is in `breadth.md`. Generated requirements and designs remain subject to their separate human-review phases.
