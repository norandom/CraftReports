# Kernel facade correction acceptance

Task 10.1 accepted on 2026-10-16 after independent review and matching-source
canonical verification. This supplements the original synthetic-kernel acceptance
in implementation-validation.md; that historical record and its evidence remain
unchanged. The approved callback/policy/stage correction is implemented. This
is not acceptance of report preparation, visible GridCraft, XLSX or the release.

## Verification

- Independent review: [facade-integration-implementation-review.md](facade-integration-implementation-review.md).
- Frozen ten-file source/test manifest: artifacts/kernel-task-10.1/source-manifest.json.
- Requirement-derived RED: 13 failed / 74 passed; disabled-callback sensitivity:
  3 failures. Final focused checks: 130 passed; Ruff/format and strict typing pass.
- Canonical integration: 648 kernel tests passed in 147.99 seconds; passed packet
  artifacts/kernel-20261016T084700-996f5d6a/kernel-manifest.json.
- Fresh installed REST/MCP catalog proofs passed. Durable installed snapshot
  REST publication and MCP readback after restart: 1 passed / 4 deselected.
- Independent audit verified 660 artifact hashes, ten frozen source/test hashes,
  36 criteria and ten catalog proofs. Owned cleanup passed except deliberate
  failure fixtures; no forced cleanup was treated as a success.
- Whole-scope staged fast hook passed. Logs:
  artifacts/kernel-10-1-review/integration.txt and hook.txt.
- Final task commit retains mandatory hooks; push is recorded by Git, not inferred
  from this assessment.

Application source is 1476/1500 LLOC, net +27; all local limits remain unchanged.
No dependency, framework, transport, reporting handler or budget increase was
introduced. Existing defaults and retry semantics remain; opted-in commands can
reject authorized ineligible selections before acceptance and expose only trusted
allowlisted diagnostics. Failed stages cannot become successful without evidence.

## Completion scope

The original accepted kernel plus this independently verified amendment closes
the reopened kernel implementation. Report task 7.1 and task 8 remain open,
including their own budget fit and real three-resource integration evidence.
Canonical installed snapshot testing is regression evidence for the previously
accepted publication slice; it does not close the remaining live runtime tasks.
