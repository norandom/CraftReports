# Independent design review

- Mode: independent; reviewer `/root/review_upstream_designs`, fresh read-only context.
- Reviewed source: final `design.md`, SHA256 `C29B0E3B15E40FF1AB7E70E0EF130FB28A07E59C4D69F67E101A343409427B73` (identical bytes to the reviewed draft).
- Requirements source: SHA256 `5C01A102B1BE62603D1A43DF42F38FC3DD4D53D872683588848B3A56124557EE`.
- Verdict: PASS on 2026-10-15 after bounded NEEDS_FIXES remediation and pass-two clarification. All 36 acceptance criteria mapped; no unresolved design blockers.

The independent reviewer verified exact schema/precision/canonicalization, all nine provider obligations, conservative preadmission readback-size limits, truthful recovery, fresh preparation for each selected snapshot, pause fencing and absence of a model/runtime dependency cycle.

Repairs: metric kind/shape/nullability completeness and declared dataset field requirements; dataset label/source provenance; generic app-owned RunPreparer returning exact newly prepared pins before generation/lifecycle recheck and target start; SnapshotReader moved to data.ports and recovery to runtime, keeping the application kernel unchanged at its measured 1,449/1,500 LLOC; generic VersionPin in contracts.pins; exact conflict union; microsecond lexical checks; correct quickstart index. Standalone runtime proof uses clearly synthetic fixture preparation/effects over real durable providers, with independently observed local effects and explicit scope.

Root must still activate exact import/owner/default budget scopes before source. SQLAlchemy resolution, database durability, actual scheduler and public-client behavior remain implementation tasks. This review ran no production code, tests, browser or database.

Approval provenance: owner-directed bounded overnight fast-track in `../craftreport-reporting-facade/overnight-run-2026-10-15.md`; tasks invoked with `-y` only after independent design PASS. Task generation and approval remain pending their separate gates.
