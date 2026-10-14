# Requirements Document

## Introduction

CraftReport's operation kernel gives software integrators and capability authors one discoverable, versioned way to invoke reporting capabilities. It establishes consistent validation, access, retry and outcome semantics as self-contained capabilities are added. Required operations remain usable without AI.

The owner approved the five-part split and starting this bounded specification on 2026-10-13, then explicitly approved these 36 kernel criteria. The approved umbrella requirements remain the reporting acceptance baseline. Design has its own review phase.

## Boundary Context

- **In scope:** capability activation/discovery; declared operation contracts; shared invocation checks; command/query behavior; retry/version guard behavior; operation receipts and evidence references; ordinary software and MCP access; synthetic capability conformance verification.
- **Out of scope:** actual data publication and snapshot storage, live scheduling/restart recovery, report compilation/themes/policy evaluation, GridCraft control/deployment, XLSX generation/reopen and future finance/document domains. Plugin hot installation, a marketplace and an untrusted-code sandbox are excluded.
- **Adjacent expectations:** activated capabilities supply behavior and declare their required guarantees; configured services provide access decisions, retry records, version decisions and operation evidence. The later snapshot/runtime capability supplies durable state and recovery. Missing guarantees must prevent dependent work from starting.
- **Acceptance boundary:** kernel conformance may use synthetic operations and test services. Such evidence cannot establish production persistence, financial accuracy, GridCraft rendering, browser interaction or XLSX fidelity.
- **Constraints:** typed Python, mandatory Ruff/pre-commit/CI checks and reviewed code budgets apply through steering. Exact interfaces, library versions, database selection and code structure belong in Design. The later app workflow uses the latest official downloaded GridCraft release, without local compilation.

## Terms and References

- A **capability** is an explicitly enabled unit of supported behavior with an identity, version, compatibility declaration and dependencies.
- An **operation** declares its identity, contract version, input/result requirements, command/query kind, access scope, applicable limits and required capabilities.
- A **command** requests business work or change; a **query** inspects existing state without starting business work. Recording access/audit observations does not make a query a business mutation.
- **Retry identity** is scoped to the caller's authorized scope and operation identity. Equivalent content means the same contract-normalized input and applicable target/version preconditions.
- A **receipt** identifies an invocation's business operation, outcome and evidence. Acceptance or a handler acknowledgement alone does not prove an external effect.
- Acceptance references use requirement-number.criterion-number. Parent references point to the [umbrella requirements](../craftreport-reporting-facade/requirements.md).
- The [brief](brief.md) records scope provenance; the [roadmap](../../steering/roadmap.md) records downstream responsibilities.

## Requirements

### Requirement 1: Explicit and Compatible Capability Activation

**Objective:** As an operator, I want to activate compatible capabilities individually, so that optional modules do not silently change the service.

#### Acceptance Criteria

1. When a deployment selects installed capabilities for activation, the CraftReport kernel shall enable only the explicitly selected capabilities and require every dependency to be explicitly enabled.
2. If the selected capability set contains duplicate capability or operation identities, incompatible contracts, missing dependencies or dependency cycles, the CraftReport kernel shall reject that activation set before making its operations available.
3. If a selected capability has invalid required settings or fails initialization, the CraftReport kernel shall report the affected capability and reason without publishing a partially initialized activation set.
4. When a compatible capability is enabled, the CraftReport kernel shall make its declared supported operations discoverable without requiring unrelated optional domain or app capabilities.
5. When an operator inspects the enabled capability set, the CraftReport kernel shall identify its versions, compatibility declarations and unresolved verification status without equating installation with tested support.

### Requirement 2: Discoverable and Versioned Operation Contracts

**Objective:** As an integrator, I want explicit operation contracts, so that my application can discover and call supported behavior predictably.

#### Acceptance Criteria

1. When an authorized caller discovers available operations, the CraftReport kernel shall expose each permitted operation's identity, contract version, input/result requirements, command/query kind, required capabilities and applicable limits.
2. If a caller requests an unknown operation or unsupported contract version, the CraftReport kernel shall reject the request with a structured diagnostic without substituting a different operation or version.
3. When a caller submits invalid input or exceeds an advertised applicable limit, the CraftReport kernel shall identify the affected input location or limit before invoking the operation's behavior.
4. If an operation returns a result that violates its declared result contract, the CraftReport kernel shall withhold a complete-success result and identify the result-contract failure together with any known or unresolved effect status.
5. When a capability declares an operation that starts business work or changes business state, the CraftReport kernel shall require that operation to be classified as a command.

### Requirement 3: Consistent Access and Invocation Guards

**Objective:** As a deployment owner, I want the same guards on every invocation, so that switching callers or interfaces cannot bypass reporting policy.

#### Acceptance Criteria

1. When equivalent requests arrive through supported entry points, the CraftReport kernel shall apply the same input, access, capability, retry and version rules before the requested behavior executes.
2. If a caller lacks permission for an operation or referenced resource, the CraftReport kernel shall reject the request without exposing restricted content or a previous caller's protected receipt.
3. If an operation requires a capability or target mode that is unavailable, the CraftReport kernel shall report the unsupported requirement before starting the dependent effect.
4. If a required access, retry, version or evidence service is unavailable, the CraftReport kernel shall report that unavailability without starting work whose guarantees depend on that service.
5. When an installed capability exposes an operation through CraftReport, the CraftReport kernel shall apply the required shared guards regardless of that capability's requested configuration.
6. When a caller invokes a query, the CraftReport kernel shall return an inspection result without starting business work or changing canonical business state.

### Requirement 4: Retry Identity and Version Preconditions

**Objective:** As a software caller, I want safe retries and explicit conflicts, so that repeated or outdated requests do not create duplicate work.

#### Acceptance Criteria

1. When an authorized caller repeats a command with a retained retry identity and equivalent content, the CraftReport kernel shall return its existing operation identity and current permitted receipt without starting a second execution.
2. If a caller reuses a retry identity with different normalized content or preconditions, the CraftReport kernel shall report a conflict without executing the conflicting request.
3. When equivalent commands with the same scoped retry identity arrive concurrently, the CraftReport kernel shall admit at most one execution and associate accepted retries with that operation.
4. If a new command's required expected version conflicts with the authoritative current version, the CraftReport kernel shall reject that command before its dependent effect starts.
5. If a previous command has an unresolved external outcome, the CraftReport kernel shall return its ambiguous status for a repeated request rather than automatically replaying the effect.

### Requirement 5: Truthful Receipts and Scoped Evidence

**Objective:** As an operator, I want inspectable outcomes and evidence, so that acceptance, completion and uncertainty are distinguishable.

#### Acceptance Criteria

1. When an invocation is accepted, the CraftReport kernel shall return an operation identity and distinguish accepted or pending work from complete, partial, ambiguous and failed outcomes.
2. When a request is rejected, the CraftReport kernel shall return a structured reason and request correlation reference without claiming that business work was accepted.
3. When an authorized caller inspects an operation, the CraftReport kernel shall expose its recorded stage outcomes, relevant capability/contract versions, target/input references where applicable, and associated evidence references under the caller's visibility policy.
4. If required completion evidence is missing, failed or unresolved, the CraftReport kernel shall withhold complete-success status and identify the affected stage.
5. If retained operation or evidence content is unavailable, the CraftReport kernel shall report that condition without manufacturing a successful or reproducible outcome.
6. When an operation exposes failure diagnostics, the CraftReport kernel shall identify the affected operation, stage, reason and retry/recovery disposition while excluding credentials and unauthorized private content.

### Requirement 6: Ordinary Software Access and Optional AI

**Objective:** As an integrator, I want ordinary software and MCP access, so that automation does not depend on an AI service or notebook runtime.

#### Acceptance Criteria

1. When an ordinary software client or MCP client connects through a supported entry point, the CraftReport kernel shall support authorized discovery, invocation and receipt inspection for enabled operations using their declared contracts.
2. When equivalent requests use different supported entry points, the CraftReport kernel shall preserve the same normalized values, operation identity for retained retries, outcome meaning and error meaning.
3. When AI services are disabled or unavailable, the CraftReport kernel shall retain all enabled operations for ordinary software callers without requiring an AI service, notebook runtime or client SDK.
4. Where AI-originated requests are accepted, the CraftReport kernel shall subject them to the same contracts and access checks as other callers.
5. If a client disconnects before observing a result, the CraftReport kernel shall allow an authorized retry or inspection to resolve the retained operation's known status without treating the disconnect as proof of cancellation or failure.

### Requirement 7: Independently Verifiable Capability Contracts

**Objective:** As a capability author, I want repeatable conformance evidence, so that a new module can be assessed before joining the reporting workflow.

#### Acceptance Criteria

1. When a capability is checked for conformance, the CraftReport verification workflow shall record its identity/version, exercised operation contracts, fixture identities and observed results against the applicable kernel requirements.
2. When kernel acceptance verification runs, the CraftReport verification workflow shall exercise compatible and rejected activation, ordinary software/MCP parity, invalid and unauthorized input, conflicting and concurrent retries, stale preconditions, unavailable dependencies and partial or ambiguous outcomes with AI disabled.
3. If an enabled capability has not passed its declared conformance checks, the CraftReport kernel shall expose its verification as pending or failed rather than passed.
4. When kernel conformance uses synthetic effects or temporary test state, the CraftReport verification workflow shall identify that evidence scope and withhold claims of production durability, actual browser behavior or verified reporting artifacts.

## Parent Coverage and Adjacent Ownership

| Kernel area | Parent acceptance references supported | Remaining composed behavior |
| --- | --- | --- |
| 1–2 | 10.1, 12.1–12.2; modularity clarification | App capability probes and actual report operations arrive in their capability specs. |
| 3 | 10.2, 10.5, 10.8 | Target/pack rules, policy evaluation and effect enforcement require the respective implementations. |
| 4 | 3.5–3.7, 11.3–11.4 | Producer snapshot ordering, durable retry retention, binding serialization and reconciliation belong to snapshot/runtime and app integration. |
| 5 | 10.6–10.7, 11.1–11.3, 11.7, 12.4, 12.7 | Artifact readback, quality findings and restart/retention guarantees need their concrete capabilities. |
| 6 | 10.1–10.5 | Real publication, live report and export operations are not provided by the kernel alone. |
| 7 | 12.3–12.9 | The browser verification and composed app specs own actual screenshots/videos, visible updates, persistence/reopen and owned-resource cleanup. |

This is supporting coverage, not closure of parent criteria. The full umbrella remains open until the composed reporting journeys pass. Changes to contract identity, access scope, retry normalization, receipt states or evidence references require downstream revalidation.


