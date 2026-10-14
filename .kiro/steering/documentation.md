# Feature quickstarts and executable examples

Updated: 2026-10-14. Owner-requested Kiro workflow extension: delivered
user-facing features include a practical how-to guide and runnable adopter code
that also demonstrates the feature. This is project memory
and a review requirement, not a newly implemented automated documentation gate.

## Purpose and audience

A report owner or integrator should be able to perform a supported task without
reconstructing it from architecture notes or an agent conversation. Documentation
is part of feature delivery. A guide must explain what the reader can do today
and how to recognize the result.

Apply this rule to UI features and public integration features, including REST
and MCP operations used by ordinary software. Internal refactoring does not
require a new user guide unless it changes a supported workflow.

Use COBESY to structure the reader's task: name the audience, lead with the
observable result, reduce setup barriers and provide a small, reproducible
example. Keep the guide useful at the point of action. Readers should be able
to report a failed step without guessing whether they misunderstood the product.

## Location and naming

Write guides under `docs/quickstarts/` with the pattern
`Quickstart_How_to_<task>.md`. Use a stable task name with underscores. Preserve
the `Quickstart_How_to_` prefix requested by the owner.

Example: `Quickstart_How_to_retrieve_an_operation_result.md` documents a caller's
complete result-retrieval task. A future live-dashboard feature will get its own
guide when the visible workflow has been implemented and verified.

Use one guide per coherent user-facing feature. Closely related options can
share that guide; low-level engine commands do not each need a separate file.
Start from `docs/quickstarts/_template.md`. Link each guide from the quickstart
index and the relevant product or technical entry point.

## Carry the guide through Kiro

| Phase | Required documentation decision |
| --- | --- |
| Discovery / requirements | Identify the reader, supported task, observable outcome and reason to choose this workflow; name the planned guide/example paths and acceptance alongside the feature |
| Design | Define the actual UI/API path, environment and small executable example; identify approved code ownership/budgets and the evidence needed to verify guide and demo |
| Tasks | Include mandatory guide/example creation or update with file owners, prerequisite implementation and actual execution validation; both are part of feature acceptance |
| Implementation | Write the guide and runnable example against the working feature; record the environment, commands and effects actually exercised |
| Review / final validation | Follow the guide and run the example; check contracts, links, readiness claims, actual effects and owned cleanup before accepting delivery |

Reuse the specification's existing numeric requirement identifiers where they
apply. Do not invent a second requirements numbering system. A guide does not
approve a feature, activate parked scope or replace phase review.

When a feature changes, update its guide in the same delivery task. During an
upgrade, verify changed commands, inputs, outputs and supported application
versions rather than copying the old readiness claim.

## Guide contract

Every guide must contain:

1. The reader's task and the observable result.
2. Current availability and scope: supported product behavior, app preview or
   synthetic verification as applicable. State missing prerequisites clearly.
3. Required environment, permissions, data and services. Distinguish Windows,
   WSL/Linux and a remote host where their commands or addresses differ.
4. Exact steps and a small public or synthetic example. Clearly identify values
   the reader supplies; never imply a placeholder is a runnable default.
5. Expected output and independent verification appropriate to the promise.
6. Troubleshooting for likely failures, with concrete diagnostics and recovery.
7. Cleanup for owned resources and a useful next step or reference.

Keep one task in focus. Link stable setup and protocol references instead of
duplicating their complete procedures. A guide may require an assembled host,
but must identify its provider, authentication and capability prerequisites;
there is no implied default production server.

## Adopter code and feature demos

Examples serve two purposes: show a useful outcome and provide code an integrator
can adapt. Lead with the reader's task and the reason to use the workflow.
Explain when direct app MCP is sufficient and which reusable reporting behavior
the facade adds. Distinguish current behavior from the reporting roadmap; do not
claim that the protocol alone makes a report accurate or complete.

Use the public interface with ordinary Python/REST/MCP callers. Do not require an
AI service, private pack or notebook. Keep reusable caller code separate from
demo fixture/bootstrap code; the demo runs that same caller path against a
small public or synthetic fixture. Examples are recipes, not a new client SDK.

Every example documents its input, invocation, expected output, independent
verification and cleanup. A self-contained demo owns its deployment/processes
and bounded run duration. A caller against an operator's host must not stop that
host. Credentials are supplied explicitly and excluded from saved transcripts.
Polling inspects the accepted operation; it must not replay business commands.

Executable Python belongs to a declared owner and the canonical typed/linted
scope. Current kernel recipes use `scripts/examples/`; their synthetic launcher
uses the existing verification harness. Do not place executable files under
content-only ownership to evade code checks or approved budgets. Public data and
pack examples receive their own approved ownership when that scope is activated.

For each future report feature, deliver a runnable example with its quickstart.
A live-report demo must publish identified synthetic snapshots, visibly update
the intended workbook, exercise the promised start/stop or pause/resume behavior
and stop cleanly. When XLSX export is demonstrated, inspect the actual file and
reopen/read back its contents against the same snapshot. These are delivery
requirements for implemented features, not claims that they are available now.

Use actual execution and one meaningful failure/recovery case where the feature
requires it. Reuse existing independent oracles and fixtures; do not mock away
the promised application, effect or artifact. Record limitations beside the
example, and keep the guide and executable synchronized when contracts change.

## Verification and evidence

Use the same acceptance rules as the feature. Browser guides identify the actual
page and workbook; live-report guides check visible refresh and controls.
Export guides inspect actual saved bytes and reopen the artifact. API guides
check the typed outcome and declared target effect or retained result. An HTTP
200, MCP success or screenshot alone cannot prove a broader workflow.

Record the relevant tested environment, result and evidence location in the
feature's validation record. Local screenshots, videos, credentials and private
data stay outside public documentation. Link tracked source/reference files so
the guide works from a clean checkout.

For documentation-only edits, verify links, anchors, commands against their
source contracts and factual readiness. Use existing executable examples and
feature evidence where applicable. Do not add tests that merely duplicate prose
or claim an unperformed deployment. Required repository hooks still apply.

If a documented acceptance-critical step fails, fix the owning feature or state
the limitation and keep the corresponding acceptance open. A polished guide
cannot turn a partial implementation into a completed feature.

## Readiness and privacy

Write current guides for available capabilities. Plan future guide paths in
specs/tasks; do not publish placeholder how-to files for unimplemented live
dashboards, XLSX workflows or future Craft apps.

Public examples use synthetic or redistributable data. Private templates,
credentials, endpoints and portfolio data remain deployment-local. The first
complete example must work without a private pack or an AI service when the
feature contract requires ordinary software access.

The quickstart index states what can be evaluated now. Kiro metadata and the
breadth ledger remain authoritative for approvals and lifecycle; guide prose
does not create a second status ledger.
