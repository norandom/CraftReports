# Snapshot storage budget calibration proposal

Status: proposed for independent review and owner approval. No limit or task
approval changes take effect from this document.

## Decision requested

Raise only `snapshot-storage` aggregate production source from 1,500 to 2,000
logical lines for its already approved first-release responsibilities. Keep
function 50, module 300 and McCabe 10 limits, every other capability limit,
ownership, release scope and acceptance requirement unchanged. This is a bounded
numeric limit, not a waiver. No additional database backend or generic framework
is authorized.

## Evidence and remaining allocation

Accepted storage measures 1,393 LLOC. A concrete partial task 4.1 candidate adds
176 measured LLOC for authorized queries and decision verification. It excludes
atomic decision writing and final readback integration. Independent diagnosis
confirmed that moving selection orchestration to runtime saves only 32 storage
lines while adding 18 lines overall; it does not resolve the remaining work.
The candidate is unintegrated sizing code, not behavioral acceptance or proof
that every implementation must exceed the current limit.

The former 40-70-line task 4.1 forecast did not account adequately for the
reviewed decision/evidence contract. Repeated compression attempts would delay
the first usable producer workflow without demonstrating a complete fit.

| Storage responsibility | LLOC basis |
| --- | ---: |
| Accepted durable providers, journal, retention, schema and snapshots | 1,393 measured |
| Partial task 4.1 query/decision candidate | 176 measured, unintegrated |
| Remaining decision write/readback/evidence integration | 40-100 estimated |
| Binding/run persistence, existing task 5.1 | 170-220 estimated |
| Restricted recovery reads, existing task 5.4 | 15-30 estimated |
| Remaining imports and provider integration | 10-30 estimated |
| Total before any deletions | 1,804-1,949 planning range |

The proposed 2,000 cap leaves 51 lines above this upper planning estimate.
Estimates are not implemented source or a guarantee of final fit. Actual source
remains measured at each acceptance; exceeding 2,000 would still block the task
and require a new explicit decision. Shared adapter and runtime budgets are not
raised and remain independently enforced.

Three existing-code reuse candidates total 34 potential deletions: shared
concrete contract decoding (19), fixed ordered schema transitions (12), and a
redundant preliminary schema whitelist (3). None is credited in the allocation.
Apply only independently verified behavior-preserving reductions with exact
serialization, migration rollback and corrupt-schema regressions. Keep evidence,
authorization, retained identity, precision and recovery checks intact. Avoid
another immutable-fact insertion implementation when the existing concrete
storage helper can serve it without a general framework.

## Proposed task 4.0: enforce the approved storage calibration

After owner approval, insert executable task 4.0 before blocked task 4.1. It
depends on accepted 3.5 and this approval. Existing task IDs remain unchanged;
the spec has 20 executable tasks after insertion. Task 4.1 depends on 4.0 as
well as its current prerequisites.

Root-owned scope is `quality.toml`, the existing exact-limit policy loader and
quality gate, focused `tests/engineering` checks, and matching scope/approval
metadata. Reuse the installed capability-limit machinery; add no new gate system.
Prove snapshot-storage 2,000 passes and 2,001 fails, other unexcepted owners still
fail at 1,501, and the existing browser-only 3,400 exception stays unchanged.
Retain strict approved-capability/rule/value/metadata checks and local 50/300/10
enforcement. Use the existing RED/GREEN/removal protocol, independent review,
canonical installed hook, selective commit and push before resuming task 4.1.

Approval changes the numeric allocation only. It does not approve the optional
SnapshotCatalogue/LatestSelector design proposal, move storage semantics into
runtime, weaken acceptance, or mark task 4.1 complete. Continue with the existing
approved publication/query contract unless a separate architectural correction
is reviewed and approved. Latest-complete selection, pause/resume, durable retry,
actual saved XLSX and independent reopen remain required for the release.

## Evidence references

Local investigation: `artifacts/snapshot-runtime/task-4.1/storage-sizing.json`,
`budget-boundary-report.md`, `selection-seam-sizing.json` and
`fresh-debug-report.md`. The independent debug verdict is STOP_FOR_HUMAN because
the complete task fit was not established. These artifacts record measurements
and their exclusions; they do not substitute for future implementation tests.
