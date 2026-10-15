# Proposed preparation-scope reuse and retained fact envelope

Status: NEEDS_CONTEXT; proposal for independent review only. No implementation,
phase approval, task acceptance, budget increase or downstream effect is implied.
This repairs the producer seam identified in
`artifacts/report-model-packs/task-5/independent-review.md`. Root owns integration
under the existing bounded overnight authorization. This author's only changed
file is this proposal. The Kiro design skill's integration/boundary guidance was
consulted; this is an amendment, not regeneration of the approved Design.

## Problem and bounded decision

The approved `reports.prepare` operation observes exactly three resources and no
target: snapshot, report pack source and report pack artifact scope. The app adds
document, and where declared run/artifact, resources. Whole CheckScope equality
therefore invalidates genuine retained preparation checks when the app supplies
its own observations. The current evaluator also replaces a finding's original
scope with the current scope, obscuring the dependency actually observed.

Permit dependency-aware reuse only for `definition`, `bindings` and
`semantic_resolution`. Preserve the original observation scope and original
EvidenceRefs. App-owned checks remain exact-current-scope checks. Neither policy
reuse nor retained old facts constitute completion evidence for a new operation.
No actual trusted producer currently revalidates preparation under app pins;
adding a reattestation procedure would require more ownership and code than this
bounded dependency rule and is not proposed.

## Required trusted scope input and its sole authority

Amend the pure function signature to:

```python
evaluate(scope: CheckScope, policy: ReleasePolicy,
         checks: tuple[CheckObservation, ...], *,
         preparation_scope: CheckScope) -> QualityEvaluation
```

`preparation_scope` is required and keyword-only. Existing task-5 fixtures must
be updated; report task 8 and the app producers are not implemented yet, so there
is no accepted runtime caller needing a compatibility fallback. An optional
argument would either retain the unsafe inference or silently withhold draft
eligibility when provenance was omitted. No public operation accepts this input,
and no new scope registry, contract class, receipt field or stored authority is
introduced. Policy stays pure and imports only the existing kernel values.

The input is a derived view of the original trusted prepare command's receipt,
not a caller assertion or a source set inferred from the observations being
checked. Its integrity is established by the producer before calling evaluate:

1. Report task 8 uses its existing exact resource extractor to derive identities
   from the successfully read SnapshotRef and qualified exact pack selection P:
   `ResourceRef('snapshot', feed_id + ':' + str(producer_version))`,
   `ResourceRef('report_pack_source', P)` and
   `ResourceRef('report_pack_artifact_scope', P)`. These are the resource kinds
   already named in the approved Design. Obtain all three authoritative versions
   from the composed reader/guard. The snapshot version equals the retained
   snapshot content digest. Pack versions come from the immutable activation
   observations. Do not derive versions from caller preconditions.
2. Before fact creation, task 8 requires its command's entire declared resource
   set to equal those three resources, and uses their complete observed version
   tuple for preparation scope, facts and OutcomeProposal evidence. This must
   work when a permitted caller omits preconditions. Original command identity,
   key and versions remain owned by the existing journal and kernel checks.
3. The app retrieves the authorized original complete `reports.prepare` version
   1 receipt and independently reads/decodes its retained PreparationResult using
   the existing facade result path. Recompute/verify the prepared content digest
   through the existing prepared codec. Cross-check the result's SnapshotRef,
   qualified pack, definition/template/theme/parameters and policy against the
   requested run as already required by the app Design. Derive the three expected
   resource identities by the same existing extraction rule. Derive the original
   observed version tuple from the original COMPLETE receipt's prepared StageResult
   EvidenceRefs, requiring all refs to agree. Independently inspect those refs
   through the composed trusted EvidenceReader and require AVAILABLE/PASSED.
   Require the tuple's ResourceRefs to equal both the receipt's entire resources
   set and the three extracted input identities, and require compatibility with
   any declared expected_versions. Receipt has no separate observed_versions
   field: optional expected_versions and candidate result Finding.scope are not
   the authoritative complete observed tuple. Compare all retained preparation
   observation scopes and each prepared fact ref to that verified tuple; require
   original operation/key and `prepared` stage before constructing observations. A typed
   retained result alone, or an AVAILABLE result without verified original facts,
   is insufficient. The evidence reader returns verification status, not a
   public fact-body API; no new arbitrary fact reader is proposed.
4. Construct preparation_scope from that original tuple, verified prepared
   digest, original validation_scope_digest, target=None and artifact_digest=None.
   The original validation digest must equal the current selected validation
   scope. Never infer a missing digest, choose latest inputs or silently change
   the report's declared validation scope to make reuse succeed.

This input buys an independent exact-set comparison: an observation that omits
one source pin cannot define its own smaller dependency set. It does not claim
that the pure evaluator can establish access, persisted-byte validity or correct
resource extraction. Those are explicit trusted producer obligations, tested at
their real seams. Copying preparation_scope from a candidate observation without
the original receipt/result/fact cross-check is prohibited.

For this first slice the evaluator additionally rejects a preparation_scope
without exactly one of each of the three named resource kinds, matching pack
identities for the two pack kinds, and no other resources; target/artifact must
be absent. Empty, partial, duplicate and extra source sets cannot pass through
either same-scope evaluation or dependency reuse. The existing tuple/value bounds
and unique-resource checks remain. Trusted producers establish the actual snapshot
and pack identities; a three-kind shape check alone cannot establish provenance.
Malformed required scope is an input-contract error, not a passing observation.

## Exact reuse and finding rules

For each of the three preparation checks, accept its status only when all these
conditions hold:

- The observation's whole CheckScope equals preparation_scope, including its
  complete original ordered resource_versions, content digest, validation digest,
  absent target and absent artifact.
- Current scope has the same content and validation digests. Every original
  source ResourceRef is present exactly once in current resource_versions with
  its original version. Changed versions, identity substitutions and removals
  invalidate reuse. Additional app/run/artifact resources are allowed only in
  the current scope; they do not change the observed preparation dependency.
- Origin is craftreport; each evidence ref has a nonempty actual fact-byte digest
  and exactly the WHOLE original observation resource_versions tuple. Evidence
  availability/ownership/readback has already been established by the trusted
  producer. Do not compare a fact-byte digest to the prepared-content digest.

Return the original observation's scope and evidence in each preparation Finding,
including when invalidated to unevaluated with a bounded reason. Never rewrite
old observations to current target/artifact provenance. Current evaluation
context is supplied to evaluate; finding.scope states what was actually observed.

For layout_fit, target_consistency, artifact_consistency and artifact_reopen,
keep whole observation.scope == current scope and whole evidence resource tuple
== current scope.resource_versions, plus the existing target/artifact presence
requirements. A changed target, document, run, artifact or additional current
resource invalidates an old app observation. No subset reuse applies to them.
Methodology/compliance remain external or unevaluated under the existing rules;
no new assurance evaluator exists. Contradictory duplicates still fail, and
identical duplicates remain bounded to one finding per check. Draft and validated
eligibility continue to be calculated only by the existing policy evaluator.

Set containment for current dependencies is by ResourceRef/version, independent
of current tuple ordering. Exact original scope/ref equality and exact operation
completion tuple rules retain their existing ordering/canonical behavior.

For the preparation call current scope == preparation_scope. For app evaluation
the current scope extends that source tuple with the app operation's declared
resources and current target/artifact identity. Reusing source checks across a
new target or final designation capture is allowed; each new app pass must produce
fresh exact-current app observations. A changed validation_scope_digest requires
new preparation. An app export policy may require artifact checks only when that
validation scope was already selected consistently for preparation; it cannot
silently substitute a different declared scope while retaining old checks.

## Exact validation scope identity

For schema version 1, validation_scope_digest is SHA-256 of the existing kernel
canonical JSON bytes for exactly this envelope:

```json
{"schema_version":"1","required_checks":["definition","bindings"],"scope_label":"selected scope"}
```

The shown check list and label are illustrative values: encode the exact retained
ReleasePolicy.required_checks in its retained order and its exact scope_label.
No other fields occur in this envelope. Reuse the existing canonical_bytes
implementation through the report adapter/composition; pure policies gain no
adapter import or independent hash implementation. Object key order follows the
existing canonical encoder. Changing a check, its order or scope_label changes
the digest. Requested draft/validated designation is excluded because it selects
an output decision from the same evaluated policy, rather than changing policy.

Select and retain one ReleasePolicy before preparation. App evaluation uses that
same retained policy and digest, including any artifact-required checks selected
at preparation time. It cannot add/remove required checks for a later export
while reusing old preparation evidence. A different policy requires preparation
again. The current closed policy contains only required_checks and scope_label;
any future validation input changing its meaning requires an explicit versioned
contract change and new preparation, not an untracked additional scope field.
Task 7 tests deterministic identity and change sensitivity; task 8 and app tests
prove the same selected policy is used across the actual producer transition.

## Original facts versus new operation completion

Every original prepare EvidenceRef and every original stage ref still binds the
original operation/key and exactly snapshot + both pack resources, without
omissions, additions or target pins. Storage retention and original kernel
completion must continue to reject any weakened full set.

Old refs may appear in quality findings as historical dependencies; they must
not be inserted into a later app OutcomeProposal.evidence or app StageResult as
though they were emitted by that app operation. AppFactStore retains the app's
actual policy decision/check observations and links the original preparation
operation/digest/refs as dependencies. Every new app completion/stage ref is
independently written/read back with its own operation/key and the complete
CURRENT declared resource/version tuple, including all upstream pins. Missing
old dependencies withhold evaluation/completion; a new app fact never regenerates
or enlarges the provenance of an original prepare fact. The unchanged kernel's
exact-full-set completion rule remains authoritative.

## Closed preparation-fact wire envelope for storage task 3.3

This fills the deliberately pending schema in snapshot-runtime's
[results-retention proposal](../craftreport-snapshot-runtime/results-retention-amendment.md).
It does not approve its separate v4 schema/linkage proposal. The narrow existing
method remains `retain_preparation_fact(reference: EvidenceRef,
canonical_fact: JsonObject) -> EvidenceRef | ServiceUnavailable`. Reporting owns
the typed PreparationFact and adapter conversion. Storage validates this one
closed wire shape using existing canonical JSON/Pydantic support, with no imports
from reporting/themes/policies, custom schema registry or policy evaluator.

The whole canonical UTF-8 JSON fact is <=16,384 bytes, including all keys, arrays,
quotes, escaping and separators. Reject greater size before writing. Exactly six
root fields are allowed, all required:

| Field | Exact wire constraint |
| --- | --- |
| schema_version | Literal string `1` |
| stage | `prepared` or `quality_evaluated`; equals reference.scope |
| prepared_digest | lowercase SHA-256 hex, exactly 64 ASCII characters |
| validation_scope_digest | lowercase SHA-256 hex, exactly 64 ASCII characters |
| checks | stage-specific fixed ordered array described below |
| decision | null for prepared; exact decision object for quality_evaluated |

Each check has exactly `check_id`, `status`, `origin`, `reason_code`. Check IDs
use the existing nine closed identifiers, in existing CheckId declaration order:
definition, bindings, semantic_resolution, layout_fit, target_consistency,
artifact_consistency, artifact_reopen, metric_methodology, compliance_statement.
Statuses are passed/failed/unevaluated/not_applicable; origins are
craftreport/external. reason_code matches `[a-z][a-z0-9_]{0,63}`. No evidence refs,
scope objects, rows, arbitrary statements, file paths or source bodies occur
inside these check objects. Unknown/duplicate keys, unknown IDs/status/origin,
wrong ordering, wrong type and extra fields reject. Use strict bools and strings;
no coercion.

For `prepared`, checks has exactly the first three checks, all craftreport/passed,
and decision is null. This fact is created only after successful actual guarded
readback and preparation. Unsuccessful input validation does not mint a prepared
fact. For `quality_evaluated`, checks has exactly all nine checks with the actual
evaluator findings' statuses/origins/reasons, including failed/unevaluated checks.
Its decision has exactly:

| Field | Exact wire constraint |
| --- | --- |
| requested_designation | draft or validated |
| draft_eligible | strict JSON boolean copied from QualityEvaluation |
| validated_release_eligible | strict JSON boolean copied from QualityEvaluation |
| blocking_checks | unique array of the closed nine IDs, <=9, preserving the actual evaluator's required-policy order |

Storage checks only the closed schema, original retained reports.prepare/1 command,
deployment/subject binding, original identity/key, exact three-resource full set,
declared precondition compatibility, byte digest, immutability and independent
readback. It does not recompute policy membership, draft eligibility or blocking
checks from these fields. The trusted reporting adapter copies the actual evaluate
result; task-8 tests compare those fields to that result. This is a specific trusted
producer port, never a public generic JSON assertion writer.

Full original operation/key and source pins are retained in the exact EvidenceRef
and sole journal, not duplicated as a second mutable authority in the fact. The
prepared_digest is the report identity; reference.content_digest is SHA-256 of
the exact canonical fact bytes and generally differs. Reference identity is
opaque and generated by the trusted adapter, with existing reference bounds.
All refs/facts must fit both this bound and the existing per-reference bounds;
the fact-size ceiling does not grant longer reference identifiers.

A valid quality_evaluated fact proves the stage was observed even when release
was blocked. EvidenceStatus.verification=PASSED means the retained fact was
independently verified, not that its quality decision allowed release. Task 8
maps the actual decision/request to StageResult: an eligible requested draft has
quality_evaluated PASSED even with missing required target checks; requested
validated with blockers has quality_evaluated FAILED/release_blocked and prepared
PASSED. Result/findings and both refs remain retained. Storage cannot turn failed
decision fields into a release or discard a valid failed-decision fact. An
interrupted fact-only write remains no completed result/receipt.

Nine short fixed check objects plus the fixed decision are comfortably inside
16 KiB; enforce the whole canonical limit independently rather than relying on
an estimated string count. This narrow schema adds no app/artifact observation
support to storage and no table beyond the separately reviewed v4 proposal.

## Task amendments and verification obligations

| Owner/task | Necessary amendment and evidence |
| --- | --- |
| report-model task 5 | Implement required trusted preparation_scope input, structural completeness and only the three-check dependency reuse; preserve original preparation Finding.scope/refs. Focused policy tests below and fresh independent review. |
| report-model task 7 | Encode/decode mixed original/current finding scopes without rescoping; retain existing whole-finding bounds and 8 MiB proof. No public passed-observation input. |
| report-model task 8 | Build exact source scope from actual selected inputs and composed guarded observations; emit/read back this closed fact envelope; invoke evaluate with required input; wire real original receipt/result/fact verification before app reuse. Test no-precondition full pins and stage/decision distinction. |
| snapshot-runtime task 3.3 | Adopt exactly this wire shape at the restricted existing evidence retention/readback seam; use real file-backed reopen and original command checks. Resolve independent v4 proposal before implementation. |
| GridCraft app producer/quality tasks | Read/authorize original retained result+receipt; verify source identities/full pins and old evidence; derive preparation_scope, produce fresh exact-current app checks and current-operation completion refs; preserve original preparation refs only as linked dependencies. |
| report-model/app adopter and final gates | Carry this seam through the existing planned quickstarts/examples and real installed-client/app tests. No new guide for an unimplemented capability is published by this proposal. |

Policy regression cases must model the actual source set, not uniform invented
scope fixtures: three genuine preparation checks with no target; current scope
adds a document, then a run/artifact and artifact digest; fresh app checks permit
the expected draft/release decision while preparation Finding scopes/refs stay
unchanged. Reordering the current tuple does not invalidate source dependencies.
Individually remove/change/substitute each original pin, use empty/one/two-source
preparation scope, mismatch pack IDs, append an original extra pin, mutate content
or validation digest, omit/alter an original evidence pin, change origin, supply
an app check with only source pins, and replay provisional app evidence for final
bytes. These must fail contract validation or become unevaluated as specified.
Also retain contradiction, missing/evidence-unavailable and assurance tests.

Producer regressions must use real internal collaborators at their task gates:
prepare through the actual kernel and file-backed provider, reopen, retrieve the
authorized original result/receipt and inspect facts, then evaluate the actual
source-to-app transition. A focused pure fixture can prove the policy rule but
cannot claim that task-8 or browser producers implement it. Test a result with
apparently valid three-kind scopes but a mismatching original receipt, inaccessible
old operation, unavailable/corrupt facts, changed pack activation, and omitted
caller preconditions. No such path may mint trusted current observations.

Storage tests must include both valid stages, quality_evaluated with false release
eligibility and unevaluated/failed findings surviving exact restart readback,
unknown fields/stages/checks/statuses, duplicate/order/type errors, wrong command
version/kind, wrong identity/key/full source set and reference scope, different
owner, corrupt bytes and immutable identity collision. Independently count the
largest permitted closed fact and confirm it fits 16,384 bytes; also reject a
malformed canonical fact exceeding 16,384. The bounded fields need not permit a
valid fact of exactly that size. Keep stored-fact verification separate from decision eligibility.
Task-8 tests prove exact equality to real evaluator decisions and original pins;
new app completion tests reject historical prep refs used as current completion.

No source/test changes, runtime tests, browser runs or commits accompany this
proposal. All existing 50/300/1,500/10 limits and exact-full-set kernel checks stay
in force. Root must reconcile reviewed changes into the relevant Designs/tasks
before implementation and measure any code growth at the owning capability.

## Context still needed before GO

1. Independent review must accept the required keyword API and explicit trusted
   receipt-derived input as a smaller integrity seam than reattestation, including
   its three-kind first-slice coupling. This author cannot self-approve it.
2. Root must jointly resolve this exact envelope with the concurrent
   results-retention/v4 proposal and confirm its retained fact inspection reports
   verified-observed independently from decision eligibility. That proposal is
   currently pending; this document alone cannot approve storage task 3.3.
3. The task-8 and app producers do not exist yet. Their exact original receipt,
   result-codec and EvidenceReader integration must prove the stated trusted
   provenance checks; until then only a reviewed policy contract can proceed,
   not an assertion that the prepare-to-app workflow works.
4. The exact validation-scope identity and single preselected policy rule above
   resolve the prior digest input gap; independent review must confirm these
   exact bytes before source implementation.

Formal handoff: NEEDS_CONTEXT pending these reviews/alignment inputs. Source
implementation and task completion remain withheld; the proposal file hash is
reported separately so the exact reviewed bytes can be frozen.
