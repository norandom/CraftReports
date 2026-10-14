# Why use CraftReport for a recurring report?

You have already calculated the numbers. You need to present them again when the
inputs change, keep the layout consistent, and explain which inputs went into the
file you sent. CraftReport's intended value is a reusable reporting workflow for
that job: one report definition connects a visible view, an exported workbook and
evidence of what was checked.

Today, the repository provides the operation kernel underneath that workflow.
It does not yet provide the complete reporting service. Evaluate the kernel for
integration behavior; use GridCraft directly if you need a chart or workbook edit
now.

## When direct GridCraft or app MCP is enough

For a one-off chart, a small workbook edit or an app-specific automation, direct
GridCraft use may be all you need. A compatible native or headless app MCP session
can expose relevant app operations. Check the selected mode's capabilities and
target identity. A headless MCP engine does not thereby control the workbook open
in your browser.

Direct MCP plus your own Python code could also implement the recurring workflow.
You would own the report definitions, input versions, templates, refresh state,
export checks and evidence. CraftReport's proposed advantage is to share those
responsibilities across reports and callers so each integration can reuse them.
It uses ordinary REST and MCP interfaces, and requires no AI service.

| Your need | Appropriate next action | CraftReport readiness |
| --- | --- | --- |
| Create one chart or edit a workbook | Use GridCraft directly, or its verified mode-specific MCP operations | No finished reporting workflow to substitute today |
| Evaluate typed operations, guarded retries and retained result retrieval through REST/MCP | Run the kernel evaluation and inspect synthetic effect evidence | Implemented and accepted within the synthetic kernel scope |
| Reuse a report definition and house style for successive input versions | Inspect the reporting scope and its next acceptance gate | Planned reporting capability |
| Keep a visible live report and reopened XLSX tied to the same snapshot | Wait for the identified browser and artifact path to pass reporting acceptance | Not delivered by the kernel or browser hosting probe |
| Review required checks before releasing a report | Agree the report's checks and inspect future run evidence | Draft/release reporting policy is required but not yet delivered |

The [protocol guide](craft-app-protocols.md) explains the session boundary. The
[GridCraft setup](gridcraft-setup.md) is a static nginx hosting recipe for an
externally downloaded official application archive. Its compiled Rust WASM engine
runs in the browser; that Compose recipe contains no Rust server or Python
reporting backend. Hosting the app is separate from connecting its visible
document to reporting operations.

The documented recipe requires downloading/extracting the archive and setting
`CRAFT_WEB_ROOT`; its default port is 8872. The separately exercised local probe
serves an already extracted GridCraft 0.6.1 archive on port 8871. Its Rust WASM
file is 18,461,052 bytes. Both deployments serve static files through nginx;
the recipe alone does not include or start the application archive.

## What the reusable reporting workflow is meant to add

The [reporting requirements](../.kiro/specs/craftreport-reporting-facade/requirements.md)
define intended behavior. These are requirements, not claims that the complete
workflow works in this checkout.

- Report owners define tables, charts, bindings and parameters once, then reuse
  that intent with compatible versioned templates and themes. They do not have
  to script individual app commands for every cycle (requirements 1, 4 and 5).
- Producers publish identified snapshots with supplied values and provenance.
  Each run pins its inputs, definition, parameters and presentation versions,
  so reviewers can identify what changed (requirements 2 and 3).
- A visible report and its exported XLSX use the same pinned snapshot. Completion
  needs evidence from the selected app document and actual saved bytes, including
  reopen/read-back (requirements 6 through 8).
- Reviewers inspect separate findings for layout, consistency, accuracy and
  applicable policy. Failed or unevaluated required checks permit marked drafts
  and block release as validated output (requirements 9 and 11).

External producers retain ownership of their calculations. Accepting a metric's
schema does not validate its financial method. A future validated-output label
must state its checked scope; it cannot imply firm-wide compliance or GIPS
certification.

## What you can evaluate now

The implemented typed, modular kernel gives capability authors and integrators
one operation contract with shared validation, authorization, version guards,
retry handling, outcome receipts and retained result retrieval through REST and
MCP. This is the current reusable foundation.

All 26 kernel tasks are accepted within their synthetic scope. The
[final validation assessment](../.kiro/specs/craftreport-operation-kernel/implementation-validation.md)
records 611 kernel tests and ten fresh installed catalog proofs. Installed
journeys compare public results with independently observed synthetic target
state, including value, version and effect count. Temporary providers establish
no production durability. Hosted CI execution remains unverified.

Start with [kernel verification](quickstarts/Quickstart_How_to_verify_the_kernel.md)
or the [task quickstart index](quickstarts/index.md). The separate browser preview
establishes GridCraft hosting and rendering only. Neither evaluation establishes
live reporting, XLSX fidelity or numerical-method assurance.

## Executable examples should teach a task and demonstrate its effect

A useful Python example has two readers. An integrator needs code they can run
and adapt using the public REST or ordinary MCP interfaces. A feature evaluator
needs a consequence they can check. The same example should serve both purposes:
a complete small task with prerequisites, inputs, commands, expected outputs and
failure guidance beside it.

For today's kernel, that task is synthetic: discover an enabled operation, change
an identified target under a version guard, inspect its receipt, retrieve retained
content, and compare it with observed target state. An equivalent retry must
retain the operation identity and produce no second effect. This demonstrates
the integration contract without presenting a synthetic target as a report.
The [REST](rest-client.md), [MCP](mcp-client.md) and
[result retrieval](result-readback.md) references explain the public interfaces;
the quickstarts provide evaluation paths. The [runnable examples](examples.md)
provide Python callers for REST, MCP and result retrieval, plus a synthetic demo
that exercises those callers against an isolated host. They use the same public
interfaces an integrator would use; their observed effect belongs to the
synthetic target, not to a browser workbook.

For the future reporting feature, the example must publish a small identified
dataset, select a reusable definition/template, update the selected visible
document, save an XLSX, reopen it and compare both outputs with that snapshot.
It must retain inspectable evidence and show a required-check failure as a draft.
That is the feature demonstration to build when the reporting capability ships.
A successful API response or screenshot alone cannot demonstrate this task.

## Test the value with the report you already produce

After reporting acceptance passes, choose one recurring report with its owner,
integrator and reviewer. Agree expected content and checks before the trial.
Produce the existing workflow's output and the CraftReport output from the same
identified inputs, then repeat for another input version. Compare the visible
report, reopened XLSX and evidence with the existing output. Record manual
corrections, unexplained differences and support needed to repeat the task.

Establish the baseline before proposing a time or cost target. This repository
has no observed savings or adoption results. The value hypothesis fails if the
owner still has to reconcile unexplained differences by hand, cannot identify
the source snapshot, or cannot independently repeat the workflow from its guide.
Keep the existing process available while testing.

The [product strategy](product-strategy.md) proposes how to run that trial.
Team culture, trust relationships and psychological safety are unknown; its
adoption assumptions need confirmation with the participating team. The
[roadmap](roadmap.md) identifies what must be delivered before this report trial
is available.
