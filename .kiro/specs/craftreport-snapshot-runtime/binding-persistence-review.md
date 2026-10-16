# Binding persistence amendment independent design review

Reviewer: `/root/review_binding_amendment` (read-only design/code inspection).
Reviewed document: `binding-persistence-amendment.md`.
SHA-256: `D8394A2E6E6FB95EFD133B3756A0C6255A28325952A8BECE3C70144800C01D2C`.
Repair passes: 1.

## Summary

The amended proposal provides an implementable, bounded task 5.1 contract and exact v5-to-v6 transition. The three issues from the initial review are resolved without expanding capability ownership, introducing a framework, or raising limits.

## Critical issues

None remaining for this design scope.

The initial NO-GO applied to SHA-256 `9BA48FD37A65B0024149C17DFEFCCD20923CC3428428F37EFEB33E6D1F9E15E5`. Its findings are resolved as follows:

- **Historical binding evidence:** the exact bounded before/after fact, normalized original request fingerprint, complete command/resource pins, unchanged-bind behavior and transaction/readback rules now preserve historical evidence independently of mutable current state. Conflicts emit no persistence fact. Requirements 3.5 and 5.1.
- **Prepared-result trust:** receipt-linked retained results, independently verified passed preparation evidence, exact content/pin comparison and separate result/content digests now define acceptance. A quality-blocked draft retains its truthful findings; synthetic fixtures remain test-only. Report-specific parsing stays in the injected collaborator while storage verifies common retained linkage and ownership. Requirements 3.1, 3.2 and 5.1.
- **Version compatibility:** generic VersionPin labels remain unchanged; numeric counter rules and scalar encodings are distinguished. A nonnumeric label roundtrip is explicitly required. Requirements 3.2 and 5.1.

## Design strengths

Target authorization explicitly grants permission to name a configured target without claiming liveness. Task 5.1 selects and retains pins while stopped; task 5.3 retains its independent running-intent/start-fence obligation.

Exact migration validation, preserved historical bytes, composed binding/feed/report resource dispatch, and unchanged ownership limits fit existing patterns. New code must still satisfy actual measured caps; estimates do not establish implementation fit.

## Final assessment

**GO for the reviewed design hash.** Existing task/phase authorization remains required; this review does not grant it. No scope expansion beyond approved task 5.1 was identified, so this review does not require a fresh owner approval for these implementation details. The task remains open; this review is not implementation acceptance. No source code changed and no implementation test suites ran. Implementation must provide the specified focused, installed-interface, migration, corruption and real reopen evidence before task acceptance.

