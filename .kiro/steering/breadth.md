# Breadth and Lifecycle Control

Updated: 2026-10-13. The ledger has scoped kernel Design approval. Task 1.3 verified its standalone enforcing gate; task 1.4 verified local hook integration and configured CI, while hosted CI execution remains unverified and the complete future map remains unapproved.

## Sources of Truth

`breadth.toml` records every real spec and top-level capability, scope/line, actual/planned ownership, lifecycle and closure decision. The feature map explains user breadth; the core map explains structure. The ledger links them without replacing either.

Kiro phase/generated/approved state is read from each actual `spec.json`; do not duplicate it as a second mutable authority. A lifecycle state is not a Kiro phase approval. The four current work lines are defined in `overview.md`.

## Lifecycle States

| State | Meaning |
| --- | --- |
| `active` | In a declared work line; only phase-authorized work may land. Planned paths are not existing implementations. |
| `done` | Acceptance work is complete with evidence; retained code has a capability owner. |
| `parked` | No implementation work lands; remove unused scaffolding/registrations if present, while retaining spec history. |
| `retiring` | Exact deletion/exit surfaces and their execution/evidence are scheduled. |
| `review` | A disposition is needed; do not treat this as implemented or implicitly active scope. |
| `removed` | The declared closure executed and was verified; retain a tombstone for one release. |

Closure identifies code, registrations, imports, endpoints, flags, dependencies and documentation surfaces as applicable. A closed ticket or deletion promise is not execution evidence. No deletion is authorized merely by this draft.

Parked entries with no scaffolding have no deletion target; record that explicitly. If unused scaffolding exists later, record exact removal targets. Retiring entries need a start date, targets, accountable owner and closure evidence.

## Truthful Breadth Counts

Derive spec totals/phases from actual metadata. Derive actual Python modules from source, not the proposed code tree. Keep planned module counts and existing prototype files separately visible.

`open_fronts` equals active/review actual spec entries plus review/retiring capability entries whose required closure has not executed, counted once by ID. Publish the contributing IDs alongside the number.

The current baseline is two active specs: the umbrella with approved requirements and the operation kernel with approved requirements, Design and Tasks, with kernel implementation authorized. Task 1.1 created the minimal package initializer; the gate derives current source counts from the actual tree. The four later roadmap scopes are not initialized specs. Planned capabilities are not implemented modules or extra spec fronts under this metric; local method/domain implementation remains parked for the foundation. Subsequent kernel Design approval covers only its explicit owners and budgets. The full future map remains unapproved; approved_spec_scopes and approved_capability_owners identify the scoped approval.

## Gate Contract to Implement after Map Approval

1. A real spec reaching `tasks-generated`, or a later phase with generated tasks, needs a ledger entry.
2. New immediate modules/packages under `src/craftreport` need declared capability ownership. More-specific extension ownership/lifecycle overrides a broader parent scope.
   New self-contained capability packages under `packages/` also need declared owners; package tests and resources remain associated with that capability and are measured under the applicable source/test policy.
3. Parked feature scaffolding cannot be activated under a parent's general ownership entry; activate its own ledger entry through review first.
4. A retiring entry with required, unexecuted closure fails when UTC elapsed time exceeds 14 days. Scheduled CI must check aging even without a commit.
5. Fail stale/inconsistent counts, ambiguous ownership, unknown states/lines, and claims of closure without matching evidence.

Use this gate in pre-commit and CI once implemented. Keep strict typing/Ruff/LLOC decisions in `quality.toml`; lifecycle approval and engineering checks must remain separately inspectable.

When splitting a large spec, register the actual new spec before tasks generation, assign bounded ownership and revalidation dependencies, and avoid making one umbrella spec conceal unresolved work.
