# Roadmap: earn trust in one complete report

The first product milestone is a report built from externally supplied portfolio
data and metrics, updated visibly in GridCraft and exported as an XLSX file from
one identified snapshot. Ordinary MCP clients must be able to drive the workflow
with AI disabled.

The [current readiness summary](index.md#current-readiness) describes what can be
evaluated today. The sequence below reflects the owner's
[approved five-part decomposition](../.kiro/steering/roadmap.md).
It is a dependency plan, not a release calendar. Actual phase approval comes from
each specification's metadata; older status prose in planning documents is not
the approval authority.

## Delivery sequence and gates

| Order | Bounded scope | Evidence needed before relying on it |
| --- | --- | --- |
| 1 | [Operation kernel](../.kiro/specs/craftreport-operation-kernel/requirements.md) | Typed contracts, shared guards and installed REST/MCP behavior with independently observed effects, result readback, cleanup and current conformance evidence |
| 2 | Browser verification | An owned browser running the downloaded official release, retained screenshots/video/diagnostics, and real save/reopen feasibility with app, document and artifact identities matched |
| 3 | Snapshot runtime | Validated producer publication, ordered immutable snapshots, retained operation/binding state, scheduling and truthful restart reconciliation |
| 4 | Report model and packs | Declarative report compilation, compatible versioned templates/themes, public/private pack separation and scoped draft/release findings |
| 5 | GridCraft web reports | Owned report regions, controls, visible live refresh and actual XLSX export through the composed system, including reopen and content comparison |

Only the operation kernel has an initialized bounded specification. The other
four entries require their own Requirements, Design and Tasks reviews before
implementation. Browser feasibility can be researched early; integrated app
reports depend on the browser proof, snapshot runtime and report/packs contracts.
The umbrella [foundation requirements](../.kiro/specs/craftreport-reporting-facade/requirements.md)
remain the acceptance baseline.

## The first reporting acceptance gate

A synthetic external producer must drive one identified report through the
public facade. Verify that displayed cells/charts, exported bytes and receipts
refer to the same snapshot. Exercise a real control and inspect the reopened
file. Include pause/resume, export during refresh, duplicate retries and
late/out-of-order/rejected updates under the approved contracts.

Keep evidence of input acceptance, target mutation, saved bytes, reopen checks
and numerical validation distinct. An imported metric's provenance is not an
independent check of its calculation. Failed or unevaluated required quality
checks allow clearly marked drafts and block release as validated output.

The [testing policy](../.kiro/steering/testing.md) defines these evidence rules.
A second small feature should reuse the demonstrated ownership and verification
pattern before the project generalizes across more apps.

## Scope boundaries

The foundation includes external data and metric ingestion, reporting contracts,
templates, visible GridCraft reports, snapshot-consistent XLSX and app-to-app MCP.
Python/Polars is the processing direction; database/ORM selection remains a
downstream design decision. DuckDB is excluded.

External Python and Jupyter producers retain their calculations. A client SDK,
notebook service, local portfolio-method engine, built-in GIPS pack, designer
clone and enterprise distribution are outside this foundation.

Accounting, forensic accounting, invoices, tax/books, WordCraft letters and
assessments, and other Craft apps remain parked. Each needs a bounded use case,
methodology or standards scope, capability owner and acceptance evidence before
activation. Private packs remain external to the public project.

Consult [breadth.toml](../breadth.toml) for lifecycle/ownership and
[quality.toml](../quality.toml) for engineering requirements. The
[product strategy](product-strategy.md) proposes how to evaluate adoption as these
gates are met; it adds no approved implementation scope or delivery dates.
