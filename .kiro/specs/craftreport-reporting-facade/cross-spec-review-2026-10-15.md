# Foundation cross-spec review

## Scope and provenance

Independent reviewer: `/root/review_foundation_cross_spec_fallback`, fresh context.
The configured `spec-reviewer` launch failed because its model was unavailable
on this account; that launch performed no review. A supported-model reviewer
examined the same contracts instead. No runtime acceptance is implied.

The review compared the kernel, browser verification, snapshot runtime,
report-model/packs and GridCraft app plans against the umbrella baseline.
Reviewed new Design hashes: snapshot `C29B0E3B15E40FF1AB7E70E0EF130FB28A07E59C4D69F67E101A343409427B73`,
model `FB76B8461D3E35A3E840A62435A8EE54614387BCAAC32B5F61A5A89F481C935A`,
app `3107C097155F8449BE586ACB59501E091CD7BEE084B2111A9B2E6645A3D291BE`.

## Initial verdict: NEEDS_FIXES

Report preparation declares pack-source/artifact-visibility resources and retained
preparation evidence, but the specified providers do not assign their authoritative
readback and trusted fact retention. The kernel requires every declared resource
and the complete evidence pin set. The repair belongs to report-model operation
composition, with only a narrow existing-storage integration where necessary.
It must preserve the sole kernel journal/result store and existing limits.

Clarify the runtime lifecycle start fence versus storage/kernel leases, including
pause ordering, bounded facade response behavior and nested-call lock ordering.
Also make the report-model implementation dependency on snapshot contracts and
the distinction between operation names, contract versions and MCP tool names
explicit. These clarifications do not change snapshot task 2.1's value contract.

## Final verdict: PASS

The bounded repair by `/root/repair_cross_spec_providers` passed the same
independent review on 2026-10-15. Report-model owns immutable pack-resource
observations, composed guards/readers and typed preparation facts. Snapshot task
3.3 owns restricted retention/readback in the existing evidence table, with no
reporting dependency or second journal. Installed negative cases cover altered
or missing pins and unavailable evidence.

The lifecycle fence now uses the actual bounded facade response contract and
releases before inspection. No storage/kernel lease spans a nested app call;
app start excludes the mutable binding lease. Pause ordering and pending/failure
semantics have explicit tests. Operation naming and dependencies are aligned.
No remaining important inconsistency was found in the reviewed repair.

Reviewed repaired Design hashes:

- Snapshot: `BE9038811456AAE3892B7989AC5E425EBD3BDC37750CB8EF287839DC41F2C317`
- Model: `AC197E331C9D46B43E866F3B3B4ADFE595E6A8EA527D98A824111B3874E1BF5E`
- App: `AFAC1315DBAE049EB825FFCD3A1EA30C392DA04444B0AE8C29199538E3C6E9FB`

Reviewed task hashes before subsequent task-completion bookkeeping:
snapshot `C0F3AC210227982422976D1091B11C845133480B3605666EDBAE7A22DCD66AD5`,
model `EECF21C0BB211D7BB16F4AAA7C101039DE6F2AA5A8BCA0DF9A3BDE09AA7CAB56`.
The repair changes future provider/lifecycle bullets; snapshot task 2.1's value
contract is unchanged. Acceptance follows the recorded bounded overnight authority.
This is specification consistency approval, not runtime or feature acceptance.
