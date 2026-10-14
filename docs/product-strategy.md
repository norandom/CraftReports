# Product strategy: make one recurring report worth adopting

Proposal for evaluation, not approved implementation scope or a launch commitment.

CraftReport should earn adoption by making one recurring report easier to
refresh, review and reproduce. External producers already own the data and
calculations; report owners still need a trustworthy way to present their results.
The proposed first value is a visible report and an exported file that agree on
their inputs, with evidence a reviewer can inspect.

[Why CraftReport](why-craftreport.md) compares that intended value with direct
GridCraft/app MCP and identifies what an integrator can evaluate today.

The [roadmap](roadmap.md) supplies the technical gates. The
[current readiness summary](index.md#current-readiness) prevents an early kernel
evaluation from being mistaken for a finished reporting product.

## Assumptions to test with the first team

This proposal applies COBESY: understand the adoption conditions, compress the
message around a reader's task, then expand through trusted working relationships.
Repository requirements supply the technical knowledge. Team culture and trust
relationships have not been observed; the following are hypotheses to confirm.

| Input | Working hypothesis |
| --- | --- |
| Target behavior | A report owner and integrator reproduce one recurring report, inspect its evidence and voluntarily choose it for another reporting cycle |
| Hidden assumption | The report owner remains accountable for errors, so familiarity and an inspectable spreadsheet matter more than a new tool's feature count |
| Trusted anchor | The person whose review already determines whether that team's report can be distributed |
| First cluster | That reviewer, the report owner and the integrator responsible for the existing producer |

Ask the team whose judgment they consult before changing its reporting process.
Use the answer to identify the anchor; job title alone does not establish trust.
Psychological safety is unknown. If reporting a defect threatens someone's
standing, establish a protected trial and explicit permission to stop before
asking them to evaluate the product.

Frame the trial as a test of the workflow and documentation. Keep the existing
report available for comparison. Invite disagreements about numbers, layout and
evidence; record them as findings, not reluctance to adopt.

We are wrong if the owner still has to reconcile unexplained differences by hand,
cannot identify the source snapshot, or cannot repeat the workflow from its
instructions. A failed trial should change the product or documentation before
the team is asked to expand usage.

## First value path

After the reporting acceptance gates pass, invite a small team to choose one
recurring report and agree what counts as correct before starting.

1. The integrator supplies an identified dataset and existing metrics, preserving
   their producer, method and validation status.
2. The report owner reviews one template, refreshes the visible report and checks
   the displayed version and any pending or failed state.
3. The reviewer compares the exported and reopened XLSX with that snapshot and
   inspects the scope of validation evidence.
4. The team repeats the workflow for another input version and decides whether
   the result is useful enough for another reporting cycle.

Today, prospective integrators can start with the [quickstart](quickstart.md).
A report owner's first complete reporting trial remains gated on the roadmap.
Synthetic examples should make evaluation possible without private inputs.
Private layouts and policies stay in the team's deployment.

## Expand through peers who share the work

Changing a reporting workflow carries accountability and switching costs.
A product announcement cannot resolve those concerns. The proposed adoption
sequence concentrates support in one working group, then transfers its evidence
and practical experience to an adjacent group.

| Stage | Participants and action | Reason to proceed |
| --- | --- | --- |
| Prepare | Report owner, integrator and trusted reviewer agree on the report and expected results | The trial has a useful problem and an independent comparison |
| Repeat | The same group runs another reporting cycle and records friction | Useful results survive more than a guided demonstration |
| Transfer | An adjacent report owner and integrator reproduce the workflow with the first group available | More than one peer can explain and corroborate the result |
| Reuse | A capability author extracts only the demonstrated shared need | Reuse follows actual demand and the scope approval process |

Let the team choose the report and whether to continue. Preserve its current
process during evaluation to reduce switching risk. Keep the first change small,
provide setup and failure instructions beside the commands, and let the reviewer
inspect evidence independently. These remove practical barriers without treating
skepticism as a training problem.

Record time to first independently reproduced result, manual corrections,
unexplained mismatches, support interventions and voluntary repeat use. Establish
a baseline with the team before setting targets. Downloads, screenshots and
successful health checks do not establish adoption.

## Documentation that supports the next action

The documentation structure follows this composition blueprint. Each page has
one governing question; technical detail stays in the job aid where it is used.

| Page | Reader question and action | Writing rule |
| --- | --- | --- |
| [Index](index.md) | What is this, and what can I rely on now? Choose a path. | Lead with purpose and readiness; route by task |
| [Quickstart](quickstart.md) | Can I reproduce the current evaluation? Run and inspect it. | Put prerequisites, commands, expected results and failure links together |
| [Roadmap](roadmap.md) | What must be proved before the full report is usable? Inspect the next gate. | Separate evidence, approved sequence and parked scope |
| This strategy | Why would a team choose to use it again? Test the adoption hypothesis. | Name assumptions, people, barriers and conditions that would disprove the proposal |

Prefer concrete terms such as report owner, snapshot, visible update, exported
file and inspected evidence. Describe a validated report by the checks actually
performed. Broader reporting-platform ambitions can be revisited after a team
can reproduce and reuse the first workflow.
