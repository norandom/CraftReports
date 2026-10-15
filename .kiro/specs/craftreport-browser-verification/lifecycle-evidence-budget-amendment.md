# Approved lifecycle evidence contract and browser budget calibration

Status: **owner-approved on 2026-10-15 for both changes; specification applied**
after task 4.1 acceptance at `0c4dd15` under its existing contract. Task 4.0
implemented and independently verified the exact 3,400 gate on 2026-10-15.
Amended task 4.2 remains open. The proposal text below is retained as the exact
approval record; no native lifecycle or full-feature acceptance follows.

## Two decisions requested

Approve both of the following bounded changes explicitly:

1. Amend lifecycle acceptance to distinguish directly owned subprocess exit from
   completed closure through Playwright's public SDK. Record the latter as
   `sdk-closed`, with its declared observation limit, never as graceful native
   process exit. Keep every observable cleanup failure acceptance-blocking.
2. Raise only the `browser-verification` aggregate source limit from **2,800 to
   3,400 LLOC**, through the new independently reviewed Development-gates task
   **4.0** below. Retain **50 function LLOC, 300 module LLOC, McCabe 10**, and the
   global **1,500 capability LLOC** limit for every other capability.

Approval of one does not imply approval of the other. Task 4.2 cannot proceed
under this proposed contract unless both are approved and task 4.0 is accepted.
The existing owner-approved headless continuation authorizes only tasks 4.1 and
4.2; this proposal additionally requests only the prerequisite gate task 4.0.
**Stop before task 5.1 remains mandatory.** No later task is activated here.

## Why the existing contract needs a decision

Requirement 7.1 currently treats contexts, connections and acquired processes
together. Requirement 7.3 rejects forced termination, while the Design's
`CleanupFinding` describes graceful/forced/unexecuted shutdown. Those terms do
not distinguish native exit observations from SDK resource disposal.

Playwright's public browser close operation disposes the browser; its documented
semantics allow force-like browser shutdown and recommend closing explicit
contexts first so their artifacts flush. Therefore a successful public close
call cannot prove graceful native-process exit or absence of SDK-internal force.
This is the reason for the proposed acceptance change, rather than evidence that
the present requirement has already been met. See the primary
[Playwright Python browser.close documentation](https://playwright.dev/python/docs/api/class-browser#browser-close),
checked on 2026-10-15. Implementation must retain its pinned SDK/browser identity.

The proposed observable contract uses public handles and exact ownership. It
adds no OS prerequisite or dependency, PID enumeration, process-image killing or
private Playwright implementation access. Windows Job Objects/Linux cgroups are
not proposed: additional containment would not establish whether the SDK used
internal force, and its implementation is outside this bounded change.

## Exact proposed requirements changes

Replace only criteria **7.1, 7.3, 7.4 and 7.5** with the following text upon
approval. Retain **7.2 verbatim** and every other requirement and acceptance
criterion, including the mandatory profiles and artifact/reopen checks.

**7.1:** When a run succeeds, fails or receives a supported cancellation request,
the Browser Verification workflow shall retain and settle its resource
acquisitions and perform bounded cleanup using exact owned handles and container
identities. It shall record directly launched deployment subprocess shutdown and
observed exit separately from completed public Playwright context, browser and
driver closure. Public SDK closure shall be classified `sdk-closed` only for an
identified Playwright SDK resource and shall not establish graceful native-process
exit. Cleanup findings shall remain separate from the primary journey result.

**7.3:** If cleanup explicitly requests force or observes force at any boundary,
fails or times out, leaves acquisition or closure unsettled, observes
an unexpected disconnection or surviving owned resource, or fails to finalize
required evidence, the Browser Verification workflow shall retain that failure
and withhold verified acceptance even if content assertions passed. Calling an
approved public SDK close/stop operation alone is not an observation or assertion
of native force. The declared
inability to observe Playwright-internal force shall be recorded as an immutable
capability limitation; it shall not excuse a per-run failed, timed-out or
unresolved public close operation, missing resource identity or unfinished video.

**7.4:** When a run is finalized, the Browser Verification workflow shall declare
a verified browser path only when all mandatory journey, saved-file, reopen,
evidence and cleanup checks for its declared scope passed under the approved
resource-specific closure contract. An `sdk-closed` finding may satisfy only the
matching identified Playwright SDK resource's public closure check; it shall not
satisfy a subprocess exit check or override any failed, blocked, unresolved or
unexecuted mandatory check.

**7.5:** When scoped browser evidence passes, the Browser Verification workflow
shall identify that scope and the declared SDK observation limitation without
claiming graceful native browser/driver process exit, absence of SDK-internal
force, live reporting, kernel-to-browser integration, production durability or
financial-method assurance that the run did not establish.

## Exact proposed Design changes

### Evidence and Journey lifecycle contract

Replace the lifecycle acceptance descriptions in **Evidence and Journey** and
the lifecycle-testing bullet with the resource-specific contract below; retain
the other stage, video, hash, diagnostic and finalization requirements.

- Register the acquisition task before awaiting it. Retain the exact public
  Playwright driver, browser and every context object returned, including main,
  reopen and video-decoding contexts. Retain partial-start ownership even when
  an operation fails or is cancelled. Never reconstruct ownership by discovery.
- A bounded, cancellation-protected cleanup owner settles acquisition tasks and
  accepts their late successful results into the same registry. A timeout or
  cancellation must not discard an acquisition task that can still return a
  resource. Unsettled acquisitions block acceptance; record their identities and
  state even when the cleanup deadline expires.
- Close owned main/reopen contexts first, then owned decoding contexts, then the
  browser, then the public Playwright driver. Attempt remaining independent
  cleanup after a failure within the recorded finite cleanup deadline. Retain
  close task identity/state so repeated cancellation cannot silently abandon an
  operation or convert it into success. Finalize the evidence packet only after
  cleanup outcomes and required video checks have been collected.
- Record `sdk-closed` only after the matching retained public close/stop operation
  completes successfully. A context closed incidentally by browser shutdown does
  not substitute for its own required context close and finalized recording.
  Explicitly distinguish expected disconnect caused by owned browser close from
  unexpected earlier disconnect; disconnection alone proves neither closure nor
  native process exit.
- Replace production Deployment's unretained `subprocess.run` boundary with
  retained `Popen` handles, using a Windows process group and Linux session for
  directly launched subprocesses. Record exact ownership, platform, shutdown
  requests, bounded waits, exit observation and any escalation. A request alone
  is not observed exit. Any requested or observed force blocks acceptance even
  if later exit is observed. Verify the real platform behavior; command-shape
  unit tests alone cannot establish it.
- Retain exact owned container IDs and both existing project/run label checks
  before mutation. Preserve externally owned deployments, unrelated resources,
  the shared archive cache and retained evidence. Keep startup uncertainty and
  late-acquisition failure visible; a stopped local Docker/WSL command does not
  prove remote container quiescence.
- The immutable declared capability limitation is
  `playwright_internal_force_unobservable`. Attach it to the matching SDK
  boundary and schema/SDK identity before execution; do not infer or toggle it
  from a failed run. No SDK outcome is mapped back to `graceful` by compatibility
  code, summaries or verdict reduction. Native browser PID/descendant-tree
  termination guarantees are outside the amended claim.

### Data Models

Replace the existing `ResourceRegistry` and `CleanupFinding` descriptions and
extend the `RunResult` description as follows. Use typed records/enums validated
at ingress; serialize identities and observations rather than live handles.

| Record | Proposed lifecycle fields and invariant |
| --- | --- |
| ResourceRegistry | Ordered acquisition token, owner run, exact resource kind, public handle or direct subprocess/container identity, acquisition task and pending/succeeded/failed/unsettled state, close task and state, dependency order. Retain late/partial acquisitions. Live handles remain internal. |
| Resource kind | Exact discriminants for Playwright driver, Playwright browser, Playwright context (including declared main/reopen/decode role), direct deployment subprocess and owned container. Unknown/unowned kinds cannot acquire an accepted closure result. |
| CleanupFinding | Owner/resource/acquisition identity, close mechanism, requested/observed force, bounded timestamps/deadline, acquisition settlement, public-close outcome or observed native exit status, unexpected disconnect, observed survivors, final video state, sanitized failure references and declared SDK limitation where applicable. |
| Closure result | `sdk-closed` only for a matching retained Playwright SDK kind and successful public operation; `graceful` only for a directly observed non-forced shutdown at the native subprocess/container boundary; `forced`, `failed`, `timed-out`, `unresolved` and `unexecuted` remain rejecting when mandatory. No absent observation becomes success. |
| RunResult | Existing source/build/profile/artifact and stage findings plus resource-specific cleanup, immutable declared capability limitations and an explicit lifecycle contract/schema version. Existing packets retain their historical semantics; versioned readers must not silently reinterpret old `graceful` records as new evidence. |

The reducer validates the resource kind and evidence before accepting closure.
Any primary failure remains failed regardless of cleanup success. Any mandatory
cleanup/video failure defeats otherwise passing content checks. A declared SDK
limitation provides no fallback for an unknown resource, unresolved acquisition,
close exception, close timeout, unexpected disconnect or observed survivor.

## Proposed browser-only source allocation

The parent-recorded measured baseline during task 4.1 finalization is
**2,744/2,800 LLOC**, leaving **56 LLOC**. This snapshot is a planning input,
not a claim of task 4.1 acceptance; remeasure the accepted source before gate
application. The task 4.2 increment is estimated at **180–280 LLOC**, not measured.
No hypothetical refactor savings are deducted.

| Planning component | Source LLOC |
| --- | ---: |
| Parent-measured baseline including current task 4.1 work | 2,744 |
| Task 4.2 upper planning estimate | 280 |
| Remaining ordinary CLI | 75 |
| Remaining profile/integration fault repairs | 100 |
| Uncertainty reserve | 150 |
| **Planning total** | **3,349** |
| **Proposed browser aggregate cap** | **3,400** |
| **Headroom above planning total** | **51** |

**Updated accepted-source measurement (2026-10-15):** task 4.1 was accepted and
committed at `0c4dd15` with **2,798/2,800 LLOC**, leaving **2** under the then-enforced
cap. This is **54 above** the 2,744 proposal snapshot. The table above
remains approval history. Keeping the same planning allocations, the updated
forecast is **2,798 + 280 + 75 + 100 + 150 = 3,403**, **3 above** the unchanged
approved **3,400** cap. These allocations remain estimates, not separate caps or
proof the work cannot fit. No hypothetical refactor savings or cap raise is
assumed. Task 4.0 is now accepted; 3,400 is enforced, leaving 602 LLOC.

The CLI/profile allocations describe future demand only; they authorize no
execution beyond 4.2. These are aggregate planning estimates, not separate caps.
Every browser-owned source/helper/example counts once; tests remain separately
measured. Preserve ownership seams and the same Journey; do not move code into
tests/artifacts/another capability to satisfy the cap. Reassess if measured work
cannot fit. No other capability or local/branching limit changes.

## Exact proposed task-plan changes

Add the following executable task **4.0** at the beginning of group 4. Retain
every existing task number, including the current task 4.1; the task count would
become **20**. This task is an ordered prerequisite, not parallel browser work.

**4.0 Implement the approved browser-only 3,400-LLOC calibration gate**

- Own only the Development-gates budget integration in
  `scripts/quality_policy.py`, `scripts/check_quality.py`, `quality.toml` and
  focused `tests/engineering` regressions. Amend the existing exact 2,800 browser
  override to exact 3,400 with explicit owner decision/rationale/reference;
  retain the parser's approval and narrow-scope validation.
- Reject unapproved, unknown, duplicate, wildcard or malformed overrides,
  unsupported rules and missing approval metadata. Do not accept limits from
  environment, command-line or browser run configuration. Preserve whole-scope
  ownership accounting and separate test reporting.
- Prove browser 3,399 and 3,400 pass and 3,401 fails; another capability passes
  1,500 and fails 1,501. Retain 50/300/10 boundary enforcement and existing
  malformed/approval checks. Use the required bounded RED/GREEN/removal
  sensitivity procedure for the changed gate behavior.
- Run focused engineering tests and canonical fast checks, obtain independent
  task review, then use the parent-run installed hook and selective task commit
  workflow. Remain within the Development-gates capability's unchanged 1,500 cap.
- Done only when the approved exact browser override is implemented and
  independently verified. Until then the existing implemented **2,800** limit
  governs browser source; approval text alone does not change enforcement.
- Boundary: Development-gates budget enforcement integration.
- Depends: 3.4 and explicit owner approval of both decisions in this amendment.
- Requirements: 2.6, 6.6, 8.1; Design references: Proposed Ownership and Budgets,
  File Structure Plan, Allowed Dependencies.

Replace task **4.2** with the following wording after approval:

**4.2 Complete bounded ownership cleanup and cancellation behavior**

- Register and retain exact public SDK objects/acquisition tasks, direct
  deployment subprocess handles and exact container identities through partial
  acquisition, late completion, success, failure and supported cancellation.
- Settle late acquisitions and use cancellation-protected bounded cleanup in
  context → decode-context → browser → driver order. Preserve primary and
  cleanup failures separately; close remaining owned resources after a failure
  where the deadline permits. Never classify unresolved tasks as closed.
- Implement and prove the amended resource-specific closure records/reducer:
  public SDK completion is `sdk-closed` only for exact Playwright SDK kinds;
  native directly owned shutdown needs observed exit. Retain the immutable
  SDK-internal-force limitation without weakening per-run failure checks.
- Replace Deployment's production subprocess boundary with retained `Popen`
  ownership, Windows process groups/Linux sessions and bounded shutdown/exit
  observations. Preserve exact container ID/dual-label checks, externally owned
  targets, unrelated files/services, shared cache and retained failed evidence.
- Done when real success/failure/cancellation and partial/late acquisition
  evidence establishes the declared boundary; requested/observed force, failed
  or timed-out cleanup, unsettled acquisitions, unexpected disconnect, observed
  survivors and unfinished video all prevent acceptance despite passing content.
- Validation: contract tests for wrong-kind `sdk-closed`, unknown/unowned
  resources, missing/duplicate identities, failure precedence, forced outcomes,
  close failure/timeout, repeated cancellation and late acquisition; real
  headless Playwright closure/finalized-video checks; real Windows process-group
  and Linux-session lifecycle faults and unrelated-resource preservation;
  relevant canonical fast checks and independent task review. Missing actual
  platform evidence stays open and cannot be replaced by mocked command tests.
- Boundary: Journey and Deployment cleanup integration, with public SDK closure
  at BrowserDriver/Evidence and typed records/reduction at their existing owners.
- Depends: 3.4, accepted 4.0, and accepted 4.1 evidence/reducer integration.
- Requirements: 7.1, 7.2, 7.3, 7.4, 7.5.

Task 4.1 retains its number and existing authorization within the current cap.
Any changed finalization/decoder behavior introduced by 4.2 must revalidate its
affected 4.1 contracts and real video evidence against final matching source.
Task 5.1 retains dependencies on 4.1/4.2 and the explicit stop for a separate
profile/verification decision. All other task criteria and boundaries remain.

## Application sequence and unchanged delivery obligations

1. Obtain independent proposal review and explicit owner decisions on both
   requested changes. Neither review nor this draft supplies owner approval.
2. Upon approval, apply the exact requirements/Design/task changes; record the
   owner decision and amended review/hash/count references in spec metadata and
   implementation notes. Reconcile the older continuation's unchanged-contract/
   2,800 statements only to the extent superseded by this explicit decision.
   Update engineering/quality scope references truthfully: approved 3,400 is
   pending enforcement until 4.0 acceptance. Do not predeclare that gate working.
   Reconcile Design's Proposed Ownership and Budgets section, its old forecast
   and obsolete concluding 1,500 statement; retain prior decisions as history.
3. Implement and independently accept 4.0 before further browser source expansion
   under the new cap, then perform only authorized 4.2 work after its prerequisites.
   Record real source totals, source-bound evidence and task-local review.
4. Stop before 5.1. Missing headed/Linux workbook profiles, future recipe/browser
   CI and complete-feature validation remain open. Run automated checks
   headlessly, without activating native windows. Historical headed evidence
   retains only its original scope.

The planned guide remains
`docs/quickstarts/Quickstart_How_to_verify_GridCraft_in_a_browser.md` under
Documentation ownership. The adopter example remains
`scripts/examples/verify_gridcraft_browser.py` under Browser-verification
ownership and its aggregate budget. Their actual reproduction/link/command
validation stays in 6.1; documentation of the amended lifecycle claim must agree
with delivered evidence when that task is separately authorized. No completed
guide/example or full-feature acceptance is claimed here.

## Review and owner decision record

- Independent proposal review: PASS on 2026-10-15 by
  `/root/review_lifecycle_amendment` after correcting criterion 7.3. Positive
  observations of force always reject; SDK opacity excuses no observed failure.
  Application guidance explicitly reconciles superseded Design budget text.
  This is approval for owner review, not owner approval or implementation acceptance.
- Owner decision on resource-specific lifecycle contract: approved explicitly
  on 2026-10-15.
- Owner decision on browser-only 3,400 cap and prerequisite task 4.0: approved
  explicitly on 2026-10-15.
- Gate implementation/acceptance: task 4.0 independently accepted on 2026-10-15;
  exact browser 3,400 and unchanged other/local limits verified.
- Task 4.2 acceptance and any later profile/feature decision: open.

## Specification application record

Applied on 2026-10-15 after task 4.1 independent acceptance and commit `0c4dd15`:
requirements 7.1/7.3/7.4/7.5, Design lifecycle/data/testing/budget references and
executable tasks 4.0/4.2 now carry the approved contract. Requirement 7.2 and all
other acceptance criteria remain unchanged. After 4.0 acceptance there are 20 executable tasks, 14
accepted and 6 pending. Current normalized-LF document hashes are recorded in
`spec.json` under `lifecycle_evidence_budget_amendment`; original review hashes
and historical budget decisions remain intact. Engineering steering records
implemented and independently verified 3,400 enforcement after task 4.0.
Specification application itself supplies no runtime evidence; task 4.2 remains open.
