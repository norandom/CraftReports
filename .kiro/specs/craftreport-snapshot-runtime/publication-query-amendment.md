# Proposed publication decisions and bounded snapshot queries

Proposal only for task4.1 under the bounded overnight authority; no source,
existing spec/task metadata, ownership or numeric limit changes are implied.
Requirements1.1-1.6,2.1-2.6,3.1,6.1 and6.3; Design PublicationOperations,
SnapshotCodecs and DurableSchema. Root owns integration and approval. Task3.5's
accepted tombstone contract is a prerequisite, not an alternate implementation.

## Existing completion constraint and the narrow proposed change

SnapshotStore.commit returns EffectDisposition.NONE for an identical retained
version/digest and preserves its original operation_id. EvidenceReader's
snapshot_persisted verification selects the snapshot by reference.operation_id.
The kernel requires every required-stage EvidenceRef to match the *current*
operation and complete declared-resource version set. EvidencePolicy is
unconditional; optional stages are removed by the existing default stage policy.
Therefore a new retry key cannot borrow an earlier publication's persistence
proof, claim another write, or complete under an unconditional snapshot_persisted
requirement. The original retry key still returns its original retained receipt
without invoking the handler; this amendment does not change that path.

Propose a single required stage `publication_decided`, backed by a small real
current-operation decision fact. It records the outcome of the actual guarded
storage decision, including a nonmutating business refusal. This explicitly
replaces the publication descriptor's unconditional snapshot_persisted stage;
it does not alter EvidencePolicy, outcome_update, dispatch or other operations.
For accepted input, that stage carries **both** the current operation's actual
snapshot_persisted EvidenceRef and its decision EvidenceRef. No-op outcomes carry
only their fresh decision reference. The original snapshot's operation/evidence
remain historical and are never relabelled as this operation's write.

| Outcome | Feed/snapshot effect | Required-stage evidence | Final receipt when all retention/readback checks pass |
| --- | --- | --- | --- |
| accepted | APPLIED; new snapshot/high-water/revision committed | Actual current-op persistence fact + current-op decision fact | COMPLETE; result says accepted |
| existing | NONE; original snapshot identity and bytes/tombstone unchanged | Current-op existing decision only | COMPLETE; result says existing and current content availability |
| stale_version | NONE; unseen lower version refused | Current-op stale decision only | COMPLETE; result says stale_version |
| version_conflict | NONE; retained same-version digest differs | Current-op conflict decision only | COMPLETE; result says version_conflict |

COMPLETE here means the declared publication decision and result are retained;
only accepted means a new snapshot was committed. Known business refusal is not
an unknown target effect. Missing/unavailable decision or result retention cannot
complete. Uncertain snapshot/decision commit acknowledgement is UNKNOWN and
AMBIGUOUS until exact local readback/reconciliation establishes the outcome;
never resubmit an effect with a replacement identity. A known pre-effect failure
has NONE and no successful required stage. No wire request supplies passed facts.

## Existing-table decision evidence, not a second state authority

Reuse the evidence table and exact canonical helpers. A closed fact contains
exactly schema_version="1", operation_id, feed_id, requested_version,
requested_digest, status, nullable retained_version/retained_digest, high_water,
high_water_digest and feed_revision. Versions/revisions use canonical positive
decimal strings; digests use lowercase SHA256. Scope is publication_decided.
Ownership comes from the retained command and feed, not new request fields.
The fact has an explicit64KiB ceiling and repeats feed_id only once. Preflight
its actual bounded metadata before business writes; no committed acceptance may
discover afterwards that its mandatory evidence frame cannot fit.

Under the existing guard and one short Database transaction, verify exact admitted
producer fingerprint/expected pins through the existing SnapshotStore command
check, make the existing-version/high-water decision and persist that fresh fact.
Accepted snapshot/high-water, existing real persistence fact and decision fact
commit atomically. No-op paths write only their truthful operation audit fact:
no feed revision increment, snapshot rewrite, fabricated persisted content or
new version is permitted. Scope remains feed-only for kernel completion pins.
Re-read exact canonical decision bytes/ref/digest and its original journal link.
The reader verifies the closed status predicates and original declared feed pin,
not merely an unrelated journal sample. The fact is observed historical evidence,
never the canonical current feed state or an alternative retry journal.

Historical verification uses retained identity/operation/fact relationships rather
than demanding that a later feed still has the same current revision. A checked
tombstone can support an existing/conflict **identity decision**, while current
content remains Missing. It cannot newly verify snapshot_persisted content.
Accepted receipts retain their real persistence reference, so the existing
current-supporting-content checks still withhold reproducibility after purge.
No separate decision table, mutation framework or completion-rule engine is added.

## Concrete public values and codec reuse

Keep snapshot.publish input exactly publication_codec's normalized immutable
producer JsonObject. Define the authoritative result dataclasses in the planned
runtime/publication.py before deriving their transport views:

- SnapshotSummary(reference: SnapshotRef, datasets:int, fields:int, rows:int,
  cells:int, metrics:int, metric_points:int, received_at:datetime,
  accepted_at:datetime), calculated from the exact retained Snapshot.
- PublicationResult(status: accepted|existing|stale_version|version_conflict,
  requested:SnapshotRef, retained:SnapshotRef|None, latest_accepted:SnapshotRef,
  content_availability:Availability|None, summary:SnapshotSummary|None,
  validation_findings:tuple[PublicationFinding,...]).
  accepted/existing retain the requested identity; version_conflict retains the
  actual different digest at the requested version; stale_version has retained=None.
  accepted is AVAILABLE with summary; readable existing is AVAILABLE with its
  **original** summary/times; purged existing is MISSING with summary=None.
  Conflict availability describes the existing conflicting identity, with no
  acceptance summary; stale has availability=None. No per-binding completeness
  claim is made by publication, which carries no binding requirements.
- snapshot.read input is the existing exact SnapshotRef. Its successful result
  remains the existing **bare SnapshotWire object**, without an extra wrapper.
  Missing, VersionConflict and ServiceUnavailable are the existing closed failure
  alternatives. A thin operation-specific codec delegates Snapshot to the existing
  snapshot_codec and uses installed Pydantic TypeAdapter for the small existing
  failure union/schema; it introduces no general union/serializer framework.
- LatestRequest(feed_id:str, requirements:InputRequirements|None=None).
  LatestSelection(latest_accepted:SnapshotRef, content_availability:Availability,
  selection_status:not_requested|selected|none, highest_complete:SnapshotRef|None,
  latest_issues:tuple[BindingIssue,...]). No feed returns existing Missing;
  uncertain selection returns existing ServiceUnavailable. No caller supplies an
  anchor, trusted completeness flag or arbitrary executable predicate.

Derive compatible frozen metadata with the reviewed library-backed strict-JSON
codec seam when available; explicitly convert wide producer versions and service
timestamps, reuse tagged parameter/scalar helpers where needed, and use one
shared SnapshotRefWire in snapshot_models for report/runtime consumers. Keep
OperationBinding registrations/capability descriptors in planned runtime/capability.py
with explicit injected codecs/collaborators. Runtime imports no adapters. The
existing snapshot_host owns finalizer/codec/reader injection. No alternate routes.

## Bounded coherent latest selection and purged candidates

Capture the feed's authoritative high-water identity/digest once. New publications
only add higher versions; unseen lower versions are refused and retained versions
are immutable, while purge requires the host stopped. Descending search below that
anchor is therefore a coherent cut even if a higher version arrives later.
Use SQLAlchemy ordered identity pages of at most16 rows and decode at most one
<=1MiB snapshot at a time. Release each short transaction before the next await;
do not fetch all history or hold a SQL transaction across asynchronous work.

Propose a concrete bounded first profile of at most64 candidate snapshots checked
per latest call. A highest complete candidate found in descending order is proven
highest at the captured cut. `none` is legal only after actual history exhaustion
with every preceding candidate readable and incomplete. Hitting64 without proof
returns ServiceUnavailable("snapshot_selection_limit"), **not** none or a lower
guessed selection. This is an explicit availability limit, not a claim to finish
an unlimited-history search. Its value/profile requires this amendment's review;
it adds no cursor cache, persistent index or generic query engine. Later expansion
would need an independently reviewed strategy, not a silent increased scan.

With requirements=None, return latest identity/current content availability and
selection_status=not_requested without a historical search. With requirements
present, a purged/unavailable candidate encountered before a proven selection
returns ServiceUnavailable("snapshot_selection_content"); its completeness is
unknown and cannot be silently skipped. Exact snapshot.read still returns Missing
for a checked tombstone. A proven selected older readable snapshot may follow
newer readable-but-incomplete snapshots. latest_issues concerns only the identified
latest candidate, never every historical version. Exact canonical output limits
bound diagnostics; if that current diagnostic result cannot fit, return unavailable
instead of truncating evidence or falsely reporting completeness.

The64-candidate profile intentionally limits availability for deeper searches;
root/reviewer must accept that explicit bounded behavior before implementation.
It does not redefine incomplete input as invalid publication or discard history.

## Finalized 1MiB invariant and evidence plan

Preserve task2.3's preadmission canonical candidate bound including maximum-length
service timestamps and64-character digest. Before acceptance commits, encode the
exact finalized bare snapshot.read object with its actual timestamps/digest and
enforce the same1,048,576-byte cap. Failure leaves prior snapshot/high-water/facts
unchanged. Existing snapshot_codec/encode_object provide this final check inside
the storage callback; the injected SnapshotReader also verifies retained exact
bytes/digest/identity and the bound on every read/reopen. Summary/decision bodies
never get embedded into snapshot.read. This preserves report preparation's6S
bound; use the actual stored S, not producer-framing length or a regenerated body.

Tests cover new-key duplicate completion without a new snapshot or borrowed
operation evidence; original retry identity; stale/conflict effect NONE with
fresh decision facts; dropped/wrong-op/current-pin decision/persistence evidence;
purged duplicate identity with Missing summary; final-byte overflow rollback;
exact read Missing/conflict/unavailable after reopen; descending anchored selection
during publication; >one page of incomplete candidates; actual exhaustion versus
64-limit; unknown purged candidate; bounded diagnostics and cancelled scan cleanup.
Use actual Database/provider/facade wiring and independent row/byte/readback
assertions. Installed REST/MCP host/restart journeys remain task4.2. No task is
accepted by producing this proposal.

## Whole remaining budgets and scope

Frozen task3.4 storage is1152/1500, leaving348. Keep the full residual estimate:
3.5 purge90-130,4.1 reader/latest/decision persistence40-70,5.1 binding/run
persistence170-220,5.4 restricted recovery reader15-30 =315-450 net, final1467-1602.
The new decision fact must be accounted within4.1's actual growth;40-70 is an
unimplemented estimate and may prove low. The upper forecast is a risk, not a
proof of impossibility or authority to raise limits. Measure bounded work at each
accepted task; simplify at real responsibility seams and report concrete overruns.

Shared adapters remain1200 before report task7 implementation. Its independently
reviewed forecast is155-185 for task7 plus70 for task8, less62 conservative net
same-owner schema reuse, plus92-155 for all remaining snapshot/runtime codecs:
combined1455-1548. Actual production measurement is still pending.
These forecasts include later bind/inspect/control/reconcile codec needs; no fit
claim or speculative future API expansion is needed to start approved bounded
work. Existing caps50/function,300/module,1500/owner and McCabe10 remain mandatory.
No new source file beyond the approved runtime/codec/storage/composition plan,
ownership move, broader kernel change or numeric exception is authorized here.

## Review repair: exact internal readback and completion contract

Keep the existing guarded ResourceEffects.apply route. Its concrete SnapshotStore
commit returns ResourceEffect with the decision reference for every known business
outcome, plus the persistence reference for accepted. Known stale/content conflict
therefore produce NONE with fresh audit evidence, not the precondition-conflict
alternative. Generic ResourceEffect/dispatch/kernel APIs remain unchanged.

Add one feature-owned PublicationDecisionReader Protocol in planned runtime/ports.py:
`async read_decision(operation_id: str) -> PublicationDecision | Missing | ServiceUnavailable`.
PublicationDecision is a frozen/slotted value defined with the other publication
values in runtime/publication.py: result: PublicationResult,
effect: EffectDisposition, completion_pins: tuple[ExpectedVersion,...],
evidence: tuple[EvidenceRef,...]. Runtime/ports uses a TYPE_CHECKING import to
avoid runtime cycles; publication handlers receive this protocol by injection.
The concrete restricted reader is in existing storage/snapshots.py, uses the
same database/journal and bounded canonical fact validators as the writer, and
is injected by snapshot_host. It is not a public read endpoint or a second writer.

The reader loads that exact operation's decision fact, validates its retained
command/owner/request identity, and derives the result from that recorded decision,
never a new current-feed decision. Current readable content supplies the original
accepted/existing snapshot's summary/times; a valid tombstone supplies only checked
identity and MISSING availability. The historical latest_accepted identity always
comes from the decision's recorded high-water, even after later publications.
No result is synthesized from a generic VersionConflict or unavailable return.

The trusted value constructor and handler require exactly one feed completion pin,
matching every evidence ref and the requested feed. Accepted requires APPLIED and
exactly two unique current-operation scopes, snapshot_persisted and
publication_decided. Other statuses require NONE and exactly publication_decided.
The handler checks the readback against the observed ResourceEffect's effect,
pins and references before emitting its required stage/result. A dropped, added,
wrong-operation or mismatching returned reference prevents successful completion.
All guard/current-authority checks remain in force through these observations.

A known failure before calling apply has NONE and no passed stage. Once apply was
called, ServiceUnavailable does not prove no effect: perform at most an exact
local read_decision of the same operation, never resubmit with a new identity.
A fully validated retained decision may establish the original result/effect; an accepted decision whose persistence support was
purged is unavailable, never an accepted+MISSING result shape.
Missing/unavailable readback after possible commit remains UNKNOWN/AMBIGUOUS.
GuardLost/VersionConflict that explicitly precedes the business transaction is a
known no-effect failure. No cancellation or lost acknowledgment becomes an
assumed rollback. The implementation must test both committed-lost-ack and
precommit failure, and preserve uncertainty when readback cannot decide.

## Review repair: historical status and evidence predicates

At guarded write time, verify the original admitted normalized producer
fingerprint against the actual normalized input before making any decision.
Historical read_decision validates the retained fact/command/requested-digest
linkage; it does not claim to reconstruct absent rejected producer bytes or
recompute their fingerprint. Do not retain rejected bodies merely for this check.
Both paths verify operation key snapshot.publish v1, command/feed subject and deployment ownership,
exact requested identity, and declared feed resource. The mandatory authoritative
feed precondition is absent or its canonical positive revision. The decision's
feed_revision is the completion pin used by its own references. Accepted advances
absent to1 or numeric revision r to r+1. All other statuses require original
numeric r unchanged; no-op with an absent feed is invalid.

| Status | Required historical predicate |
| --- | --- |
| accepted | requested=retained=high-water including digest; original snapshot row belongs to this operation; feed completion revision advances exactly once |
| existing | requested=retained including digest; retained version <= recorded high-water; original numeric feed revision unchanged |
| version_conflict | requested and retained versions equal but digests differ; retained version <= recorded high-water; original numeric feed revision unchanged |
| stale_version | retained_version and retained_digest both null; requested version < recorded high-water; no identity exists for requested version at this decision; original numeric feed revision unchanged |

Validate the recorded high-water identity/digest through the retained snapshot row
or a fully validated identity tombstone. Stored versions are immutable and unseen
lower versions cannot subsequently be inserted, so these predicates remain
historically checkable without requiring today's feed revision/high-water to be
the old value. All nonnull retained fields must match that exact original row.
Checks do not adopt another feed's or principal's row merely because numbers match.

When inspecting an accepted decision reference, DurableEvidence must independently
locate and validate the same operation's exact snapshot_persisted reference/fact,
matching completion pins and actual original supporting content. Missing, corrupt,
wrong-owner or purged persistence support prevents PASSED for the decision itself.
This applies even if a caller supplies only the decision ref to generic inspection;
it does not require a conditional kernel rule. Separately test the typed handler's
exact emitted pair and missing/malformed retained support. No-op decisions verify
identity relationships only and never claim persisted content; valid tombstones
may support those identity decisions. Historical receipts remain unchanged.

## Review repair: authorization and publication findings

The registered resource extractors declare exactly feed:<feed_id> for publish and
latest, and snapshot:<feed_id>:<producer_version> for exact read. Existing operation
and resource authorization runs before handlers; catalog discovery grants no data
read access. The configured trusted owner policy must explicitly authorize a feed
read as inspection of that same owner's retained feed candidates for completeness.
A policy that grants only discovery or publication does not automatically grant
latest/history reading. No permissive default is introduced.

Concrete query providers validate deployment identity, retained feed ownership
against the admitted principal/owner context, and every candidate's membership
and owner before decoding. Define SnapshotQueries in runtime/ports.py extending
the existing SnapshotReader with async latest(request: LatestRequest) returning
LatestSelection | Missing | ServiceUnavailable. The handler receives an injected
Callable[[Principal], SnapshotQueries] factory; each call creates a lightweight
immutable principal-bound query adapter sharing the existing database. There is
no global/current-principal mutable state, request cache or new authorization
engine. The handler supplies the actual admitted principal, never a wire field.
Exact SnapshotReader.read keeps its existing signature on this scoped adapter.
The factory and concrete query adapter belong in the existing planned storage
and composition boundary; no new source module is needed. The assembler must
refuse ambiguous/missing owner policy. Actual facade tests
include denied feed, denied snapshot, catalog-only grants and cross-owner candidate
injection. Read/latest do not change ownership or accept caller-supplied principals.

PublicationFinding is a closed frozen value with check_id literal
schema_and_values or provenance_shape, status literal passed, and scope literal
supplied_publication. Every successful business decision returns these two ordered
findings only after the original input constructors/codec have completed their
actual structural/type/value/provenance-shape validation. They do not validate
external provenance claims, financial methodology or report completeness. For an
existing identity the summary/times remain the original retained snapshot's;
findings describe this valid submitted publication. Invalid input uses existing
preadmission WireFailure locations/rules and never receives these passed findings.
Tests distinguish valid-but-incomplete input from invalid input and verify returned
summary, original acceptance time and findings through the real facade.
