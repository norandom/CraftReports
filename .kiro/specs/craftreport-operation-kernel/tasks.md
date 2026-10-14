# Implementation Plan

Requirements, Design and Tasks are approved. The owner authorized implementation on 2026-10-13. All checks below remain planned until their tasks run with fresh evidence.

Tasks follow foundation, core, integration and validation order. Unmarked tasks are sequential; only the three independent core tasks marked (P) may overlap after their listed prerequisites complete. Each executable task is intended as a 1–3 hour unit. Scope follows the approved Design file plan; documentation updates accompanying a working contract are part of its implementation, not separate documentation-only tasks.

The kernel covers 36 criteria using synthetic capability effects and actual software clients. Durable storage/restart, GridCraft, browser recordings and XLSX acceptance remain downstream. No optional acceptance tests are marked.

## Tasks

- [x] 1. Establish the executable engineering foundation
- [x] 1.1 Create the locked package and test environment
  - Initialize the local Git repository if still absent, without committing, configuring a remote or publishing; keep private/runtime artifacts ignored under the approved ownership rules.
  - Create the minimal kernel distribution, development dependency group and test collection using the approved runtime/tool versions; resolve and lock dependencies, and fail explicitly on incompatibility.
  - Establish the canonical check entry point and distinct fast/integration modes; an unimplemented check reports unavailable with a nonzero exit rather than passing.
  - Done when frozen environment synchronization, package build/import and a collected bootstrap check succeed with recorded runtime/tool identities; no reporting capability is scaffolded.
  - Validate using the approved environment/build tools and the initial focused bootstrap check. Later package and conformance consumers reuse this environment.
  - _Boundary: Engineering foundation_
  - _Requirements: 6.3, 7.1, 7.4_

- [x] 1.2 Enforce the approved size and branching budgets
  - Implement whole-scope function/module/capability measurement and strict failure for invalid extraction, unknown ownership or expired/overbroad waivers.
  - Exercise decorators, async and nested functions, multiline expressions, separately reported tests and unique-file capability aggregation under the approved measurement policy.
  - Done when fixtures at and above the 50/300/1,500 LLOC and McCabe 10 boundaries produce the expected result and moving a file cannot evade its capability total.
  - Validate with focused engineering fixtures and the available fast checks; these gates will cover all later kernel source.
  - _Boundary: Engineering quality gates_
  - _Requirements: 7.1, 7.2_

- [x] 1.3 Enforce breadth ownership and allowed imports
  - Validate actual spec phases/counts, scoped approved ownership, most-specific owners, parked paths and overdue required retirements against the ledgers.
  - Enforce the inward dependency direction, including the prohibition on framework/app/storage imports in contracts/application and on adapter-interface cross-imports.
  - Done when disposable violation fixtures fail with exact ownership/import diagnostics and the current bootstrap passes; no future capability is activated to satisfy a gate.
  - Validate with focused gate fixtures and the fast check entry point; activation and all later packages remain subject to these checks.
  - _Boundary: Engineering boundary gates_
  - _Requirements: 1.4, 3.5, 7.2_

- [x] 1.4 Install and prove the complete fast-check pipeline
  - Complete the common fast command with Ruff lint/format, Pyright strict across source/scripts/tests, budgets, breadth/import checks and focused tests.
  - Install pre-commit hooks and configure CI to run the same whole-scope checks plus scheduled retirement aging; define the separate integration stage without claiming it passes before its harness exists.
  - Done when the installed hook actually runs and both hook and direct fast command pass the bootstrap; a disposable lint/type/budget violation must cause rejection.
  - Record installed versus passing state accurately. Product implementation begins only after this engineering foundation passes.
  - _Boundary: Engineering check integration_
  - _Depends: 1.1, 1.2, 1.3_
  - _Requirements: 7.1, 7.2, 7.4_

- [x] 2. Define the stable operation boundary
- [x] 2.1 Define immutable identities, operation descriptions and outcomes
  - Express principal scope, capability/version identity, invocation metadata, resource preconditions, command/query declarations, receipts and evidence values without framework handles.
  - Represent rejection separately from accepted work and preserve explicit partial/ambiguous and unavailable states.
  - Done when strict typing and focused contract fixtures distinguish all declared states and reject inconsistent value combinations without importing concrete providers.
  - Validate through the fast command; registration, adapters and downstream modules consume these values.
  - _Boundary: ValueContracts_
  - _Depends: 1.4_
  - _Requirements: 1.5, 2.1, 2.5, 5.1, 5.2, 5.3, 5.6_

- [x] 2.2 Define guarantee-provider and execution-context contracts
  - Define authorization, atomic operation admission/observations, version guards, capability resolution, evidence lookup and facade inspection contracts with typed unavailable/conflict outcomes.
  - Separate query inspection services from command services; keep canonical completion and registry mutation out of capability execution contexts.
  - Done when typed conformance doubles demonstrate required admission/guard/evidence outcomes and a query cannot receive the command-only service bundle.
  - Validate through focused port contract checks and the fast command; fixture providers and dispatch depend on these signatures.
  - _Boundary: ServicePorts_
  - _Requirements: 3.2, 3.3, 3.4, 3.6, 4.3, 4.4, 5.3, 5.5_

- [x] 2.3 Register typed operations in an immutable catalog
  - Pair request/result conversion with the correct command or query behavior while retaining type safety behind common dispatch.
  - Resolve exact operation/version identities, expose schema/limit descriptors and reject invalid classifications, duplicate keys or incompatible binding descriptions.
  - Done when distinct typed fixture registrations can be discovered and invoked through their prepared boundary without unchecked heterogeneous-handler casts.
  - Validate registration/lookup fixtures and fast checks; activation and transport discovery use this catalog.
  - _Boundary: Registry_
  - _Requirements: 1.4, 2.1, 2.2, 2.5, 3.5_

- [x] 3. Build independent core collaborators
- [x] 3.1 (P) Preserve wire values and canonical retry content
  - Implement the shared strict input/result conversion path, explicit serializers, versioned normalization and stable request fingerprinting.
  - Cover forbidden extra fields, unsafe integer/decimal representations, booleans versus integers, numeric strings, defaults, array order and object-key order. Enforce decoded-envelope size, nesting depth and the advertised serialized-output limit in the common conversion boundary.
  - Done when equivalent decoded requests have the same normalized content/fingerprint and altered preconditions conflict; invalid or over-depth inputs never reach behavior, and oversized results become result-contract failures with truthful effect status.
  - Validate codec cases through fast checks. Own only codec/canonicalization implementation and its cases; both transports later reuse it unchanged.
  - _Boundary: WireCodec_
  - _Depends: 1.4, 2.1, 2.2, 2.3_
  - _Requirements: 2.3, 2.4, 4.1, 4.2, 6.2_

- [x] 3.2 (P) Determine completion from result and evidence
  - Validate effect disposition, result status, required evidence pins, safe diagnostics and allowed receipt transitions.
  - Keep missing/inaccessible/unavailable evidence distinct; require new reconciliation evidence to resolve ambiguity and preserve prior attempts.
  - Done when outcome fixtures with missing evidence, malformed results or partial/unknown effects cannot become complete, and unsafe diagnostics are removed.
  - Validate outcome cases through fast checks. Own only outcome rules and their cases; dispatch will provide actual codec/provider results during integration.
  - _Boundary: OutcomeRules_
  - _Depends: 1.4, 2.1, 2.2, 2.3_
  - _Requirements: 2.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 3.3 (P) Supply deterministic synthetic guarantee providers
  - Implement test-only authorization, atomic journal/observation state, guarded versions, capability/evidence lookup and an independently readable synthetic target.
  - Provide barriers and bounded failure controls for concurrent admission, lost acknowledgement, unavailable evidence and effect interruption.
  - Done when provider conformance cases show one atomic winner, monotone receipt revisions and explicit temporary retention/epoch; no production fallback is exported.
  - Validate provider fixtures through fast checks. Own the fixture-services boundary only; activation and client tests consume it later.
  - _Boundary: ConformanceRunner fixture services_
  - _Depends: 1.4, 2.1, 2.2, 2.3_
  - _Requirements: 3.4, 4.3, 4.4, 5.5, 7.2, 7.4_

- [x] 4. Activate independently packaged capabilities
- [x] 4.1 Package an independently installable conformance capability
  - Create the separate synthetic fixture distribution with discovery metadata, typed operations, settings and lifecycle instrumentation.
  - Produce selectable/unselected and incompatible/colliding variants from isolated fixture builds, without placing executable fixtures in public production plugin paths.
  - Done when a built fixture wheel installs alongside the kernel and its manifest/bindings match the author contract; update the author example with this executable contract.
  - Validate wheel metadata/install inspection and fast checks; activation tests must use actual installed distribution discovery rather than only registry mocks.
  - _Boundary: ConformanceRunner fixture packaging_
  - _Depends: 2.3, 3.1, 3.3_
  - _Requirements: 1.1, 1.2, 1.4, 2.5, 7.1, 7.4_

- [x] 4.2 Validate and atomically activate the selected capability set
  - Select only configured distribution/entry-point identities and validate explicit dependencies, version compatibility, settings, reserved names, generated tool names and binding consistency.
  - Initialize in dependency order, publish only the complete registry and unwind acquired resources on initialization or cleanup failure.
  - Done when the activation matrix proves selected-only imports, collision/cycle/incompatibility rejection and no partially published registry or leaked fixture lifecycle resources.
  - Validate installed-fixture activation cases and fast checks; application assembly consumes only the successful immutable registry.
  - _Boundary: Activator_
  - _Depends: 2.3, 4.1_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.5_

- [x] 4.3 Expose versioned conformance status accurately
  - Resolve operator-provided verification records against capability/build digest, core contract, fixture suite and dependency versions.
  - Make missing/stale evidence pending, matched failed evidence failed and matched passing evidence passed only within its recorded scope.
  - Done when catalog fixtures cannot gain passed status from plugin declarations or reused evidence for a different build.
  - Validate verification-record cases and fast checks; discovery and the final evidence writer share this identity contract.
  - _Boundary: Registry verification metadata_
  - _Depends: 4.2_
  - _Requirements: 1.5, 7.1, 7.3, 7.4_

- [x] 5. Execute through fixed guards and truthful receipts
- [x] 5.1 Guard invocation and inspection consistently
  - Apply coarse operation authorization before private validation diagnostics, followed by typed resource authorization, service/capability availability and query-context restrictions.
  - Protect catalog/receipt visibility and keep built-in inspection from recursively creating business work.
  - Done when invalid, denied, unsupported or unavailable requests produce structured rejection without behavior invocation or restricted disclosure; query fixtures preserve canonical target state.
  - Validate guard/query/privacy cases and fast checks; REST and MCP may only enter through this guarded facade.
  - _Boundary: Dispatcher guards_
  - _Depends: 2.2, 2.3, 3.1, 3.3, 4.3_
  - _Requirements: 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.2, 5.5, 6.4_

- [x] 5.2 Admit retries and versioned effects exactly once within the journal scope
  - Look up authorized retained retries before current-version checks, then acquire the authoritative guard and atomically admit new command identity with its initial receipt.
  - Distinguish equivalent retries, content/precondition conflicts and admission acknowledgement loss; recheck guard validity before effect and release a race-losing guard safely.
  - Done when 20 equivalent concurrent requests yield one synthetic effect and one accepted identity; stale versions, different-content retries and cross-principal reuse cannot overwrite or disclose another operation.
  - Validate barrier-driven concurrency/admission cases and fast checks; downstream providers must satisfy the same contract without an implied remote exactly-once guarantee.
  - _Boundary: Dispatcher admission_
  - _Depends: 3.1, 3.3, 5.1_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1_

- [x] 5.3 Own execution independently of clients and finalize receipts
  - Retain admitted execution under application lifetime, enforce response deadlines/capacity and bounded shutdown, and require a recorded owner for any pending handoff.
  - Feed typed results/effect observations through outcome rules and conditional receipt updates; do not replay unknown effects or synthesize success after journal/evidence failure.
  - Done when local disconnect/cancellation and post-effect failure cases retain inspectable non-complete or completed evidence as observed; capacity rejection reserves no retry identity and still permits inspection/retries.
  - Validate execution/outcome cases and fast checks; the later socket tests repeat the same behavior across real client disconnects.
  - _Boundary: Dispatcher execution_
  - _Depends: 3.2, 3.3, 5.2_
  - _Requirements: 2.4, 4.5, 5.1, 5.3, 5.4, 5.5, 5.6, 6.5_

- [x] 6. Adapt ordinary clients to the shared facade
- [x] 6.1 Establish trusted principal adaptation
  - Map authenticated transport identity into immutable caller scope without accepting authority from payloads or unverified forwarding headers.
  - Supply generated loopback test credentials and deny production requests without the configured authenticating policy; refuse remote binding of the conformance profile.
  - Done when two principals, invalid/missing credentials and payload identity-spoofing fixtures produce the expected trusted scope or rejection.
  - Validate authentication boundary cases and fast checks; both protocol adapters reuse this boundary.
  - _Boundary: Trusted principal adaptation_
  - _Depends: 2.1, 2.2, 5.1_
  - _Requirements: 3.2, 6.1, 6.4_

- [x] 6.2 Expose guarded REST discovery, invocation and inspection
  - Implement the approved HTTP surface, raw-body limit/duplicate-key handling, private discovery, canonical response/status mapping and safe diagnostics; expose the configured decoded-size, nesting and output limits without replacing their shared codec enforcement.
  - Keep business validation in the shared codec/dispatcher and update executable client examples alongside the public contract.
  - Done when adapter checks show canonical successful/rejected/pending outcomes and no alternate mutation or public private-schema path.
  - Validate REST adapter cases and fast checks; real socket parity is completed after application assembly.
  - _Boundary: REST interface_
  - _Depends: 3.1, 5.3, 6.1_
  - _Requirements: 2.1, 2.3, 3.1, 3.2, 5.2, 5.6, 6.1, 6.2, 6.3, 6.4_

- [x] 6.3 Expose registry-driven MCP tools with identical semantics
  - Adapt ordinary MCP discovery/calls to the same registry, trusted principal and facade; preserve exact operation/version mapping and authorized deterministic tool ordering.
  - Return canonical structured results plus compatible JSON text, distinguishing protocol errors from rejected/failed/partial/ambiguous business outcomes.
  - Done when adapter checks demonstrate the same payload/error meanings as REST, no AI dependency and explicit unknown-tool rejection.
  - Validate MCP adapter cases and fast checks. Keep this task sequential with REST because their transport-parity test module is shared; assembly owns the host lifespan.
  - _Boundary: MCP interface_
  - _Depends: 3.1, 5.3, 6.1, 6.2_
  - _Requirements: 2.1, 2.2, 3.1, 3.2, 5.2, 5.6, 6.1, 6.2, 6.3, 6.4_

- [x] 6.4 Expose authorized retained-result readback
  - Implement the owner-approved result-readback-amendment.md through typed facade/inspection values, shared serialization, REST GET /v1/operations/{operation_id}/result and MCP craftreport.result.v1.
  - Authorize the receipt before resolving its retained reference; preserve scoped availability distinctions, exact content/reference identity and the current receipt state without new admission, mutation or re-execution.
  - Verify denial, missing/unavailable content, reference mismatch, non-mutation and non-complete receipt states. Supply executable ordinary-client examples.
  - Done when focused real-facade adapter tests, canonical fast checks and independent review pass; task 8.2 establishes installed socket parity. Commit separately with the installed hook.
  - _Boundary: Dispatcher inspection, ValueContracts, shared wire, REST and MCP_
  - _Depends: 7_
  - _Requirements: 3.2, 3.6, 5.2, 5.3, 5.5, 5.6, 6.1, 6.2, 6.4_

- [x] 7. Integrate capability activation, facade and application lifecycle
  - Compose the registry, supplied services, fixed pipeline and both interfaces without embedding request policy in assembly.
  - Manage MCP sessions and admitted execution from the host lifespan, preserve the intended route paths and enforce Host/Origin and loopback-profile settings.
  - Done when the assembled application reaches usable discovery with AI disabled, missing required providers prevent dependent effects, and shutdown closes owned resources.
  - Validate assembly/lifespan checks and fast checks; the installed-wheel runner uses this same composition rather than test-only replacement wiring.
  - _Boundary: Integration — Activator, Dispatcher, REST, MCP_
  - _Depends: 4.2, 4.3, 5.3, 6.2, 6.3_
  - _Requirements: 1.3, 3.4, 3.5, 6.1, 6.3, 6.5_

- [x] 8. Prove the installed system through actual clients
- [x] 8.1 Establish owned installed-wheel execution and evidence capture
  - Install kernel and fixture wheels into an isolated environment and launch the actual composed service on an owned loopback port with generated credentials and run-specific artifacts.
  - Provide real HTTP and official MCP client fixtures, negotiated protocol identity, sanitized transcripts and deterministic process cleanup.
  - Done when the integration command boots the installed service, discovers the selected fixture and records wheel/lock/environment identities; readiness alone is not reported as conformance.
  - Validate the harness smoke and forced startup/cleanup failures; later journeys consume these fixtures without mocking internal collaborators.
  - _Boundary: ConformanceRunner process integration_
  - _Depends: 1.4, 4.1, 7_
  - _Requirements: 6.1, 6.3, 7.1, 7.4_

- [x] 8.2 Verify cross-transport behavior and permission boundaries
  - Retrieve query content through public REST/MCP result readback and compare it with the private independent target oracle. Exercise discovery, command invocation, query readback and an equivalent retry through the other transport, using the real installed composition with AI disabled.
  - Compare normalized values, accepted identity, result/error meanings and evidence; exercise hidden schemas, denied resources, wrong versions, malformed input and both principals. Verify advertised input size, nesting depth and serialized-output caps at and beyond each boundary through both transports, including the recorded effect status after an oversized result.
  - Done when independent target inspection confirms one intended effect and the same retained retry identity, while negative cases produce no effect or private disclosure.
  - Run the integration command and relevant fast regressions; keep executable examples and supported-contract descriptions consistent with observed responses.
  - _Boundary: Integration verification — REST, MCP, Dispatcher_
  - _Depends: 8.1, 6.4_
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.6, 4.1, 4.2, 5.2, 5.3, 5.6, 6.1, 6.2, 6.3, 6.4, 7.2_

- [x] 8.3 Verify disconnect, ambiguity and concurrent admission over sockets
  - Use barriers to prove admission before client disconnect, then retry/inspect through a new client and independently read the synthetic target.
  - Exercise concurrent equivalent/conflicting commands, stale versions, unavailable required services, post-effect journal failure and bounded shutdown/capacity.
  - Done when there is one admitted effect per retry scope, unknown effects are never automatically replayed and temporary state/restart epochs are reported without a durability claim.
  - Run integration failure journeys and fast regressions; record prior failures rather than hiding them behind successful reruns.
  - _Boundary: Integration verification — Dispatcher, ServicePorts, interfaces_
  - _Depends: 8.2_
  - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.4, 5.5, 6.5, 7.2, 7.4_

- [x] 8.4 Finalize conformance evidence and test its sensitivity
  - Aggregate case results, all requirement references, build/contract identities and cleanup outcomes into the scoped conformance record consumed by catalog verification.
  - Prove that a disposable disconnected-handler variant fails actual-effect assertions and that a deliberately misclassified query which changes canonical synthetic state fails conformance. Verify stale/failed/wrong-build records cannot report passed; restore correct wiring/classification and verify it.
  - Complete CI's installed-wheel integration stage and retain diagnostics/artifacts on failure; required cleanup failure prevents conformance acceptance.
  - Done when the full synthetic conformance run produces a verifiable evidence packet and matched catalog status, with browser, durability and reporting artifacts explicitly outside its claim.
  - Run both canonical commands and the actual installed hook; these results support only the kernel's declared boundary.
  - _Boundary: ConformanceRunner and engineering integration_
  - _Depends: 4.3, 8.1, 8.2, 8.3_
  - _Requirements: 1.5, 2.4, 2.5, 3.5, 5.4, 5.6, 7.1, 7.2, 7.3, 7.4_

- [x] 9. Verify complete kernel integration and boundary closure
  - Run the full kernel validation against fresh code, locked dependencies, usable installed-wheel boot, actual client journeys and all 36 criteria; resolve findings at their owning boundary.
  - Reconcile actual source/spec counts and installed/enforced states with recorded evidence; preserve the umbrella's open reporting acceptance and downstream module boundaries.
  - Done when engineering checks, contract tests, actual-client integration and owned cleanup pass with no blocked kernel work, and the completion assessment names its synthetic scope.
  - Use the canonical fast/integration commands, installed hook, Kiro implementation validation and fresh-evidence completion gate; do not substitute documentation checks or screenshots for kernel execution.
  - _Boundary: Integration verification — complete kernel_
  - _Depends: 8.4_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4_

## Execution Notes

The approved Design owns concrete file paths and signatures. Each implementer receives its task boundary and those paths, including exclusive test-file ownership for parallel tasks. Required reviews and engineering checks are not bypassed by (P). No runtime or external deployment occurs during task generation.

Browser verification remains the next bounded spec: latest official GridCraft download, no local build, owned browser/Compose environment, screenshots/videos and actual XLSX save/reopen evidence. Passing this kernel plan cannot close that work.

## Implementation Notes

- Task 9: independent review APPROVED, feature validation GO and completion VERIFIED for the approved synthetic kernel boundary. Fresh fast passed 590 tests and 39 subtests; full integration passed 611 tests plus ten catalog proofs. All 36 criteria, 588 required cases, 660 artifact hashes and 69 helper hashes verified. Cleanup covered 76 actual hosts and 146 distinct process IDs with no survivors, only intentional lifecycle failures. See implementation-validation.md and closure-evidence.json for candidate identity and scope. Final closure metadata is subject to the actual installed commit hook; production providers, browser mutation, live reporting, XLSX fidelity, financial accuracy and hosted CI remain downstream.

- Task 8.4: independent final review approved canonical fast (590 tests, 39 subtests) and two-phase integration (611 tests plus 10 fresh-host catalog proofs). Fixed required cases, all 36 criteria, exact artifact/build identities, actual helper trees, profile and cleanup determine scoped evidence; stale helper/core/profile or altered evidence cannot reuse passing status. Installed disconnected-handler and mutating-query variants fail actual oracles; restored variants pass. Review validated 660 artifact hashes and 76 actual host cleanup records, with only two intentional lifecycle failures and no forced/unclosed/surviving processes. CI integration is enabled; hosted execution remains unverified. A recurring execution test failure was deterministically traced to leaking its injected 20 ms budget into a separate retained retry; restoring the normal test budget preserves initial timeout/no-effect assertions and guard-removal sensitivity. No production timeout changed. Earlier failed packets remain retained.

- Task 8.3: independent review approved fresh canonical fast (565 tests, 39 subtests) and integration (57 tests). Installed journeys prove atomic admission before disconnect, 20 mixed-transport equivalent requests with one effect, conflicts/stale versions, prerequisite outages, partial/unknown outcomes, retained-content loss, capacity, bounded shutdown and new temporary epochs. Private controls only inject failures/checkpoints and observe; business calls use public clients. Query immutability compares canonical target fields rather than added journal audit receipts. Evidence loss returns its public rejection while private state proves no replay. Cleanup audited 58 process records: only two intentional lifecycle injections failed, no forced terminations, unclosed providers or surviving processes. Failed oracle runs remain preserved; final conformance remains 8.4.

- Task 8.2: independent rereview approved canonical fast (560 tests, 39 subtests) and installed integration (20 tests). Both transport orders publicly retrieve command/query results through REST and MCP, compared with private retained-content and independent target observations; foreign-principal reads disclose no value. Exact advertised input/output/depth limits and over-limit effect status are exercised. Integration command selects all marked kernel tests; bootstrap assertions retain marker/run-directory/JUnit checks. All 20 cleanup records inspected, only intentional lifecycle injections failed, no forced termination or surviving owned processes. Full conformance remains pending tasks 8.3–8.4.

- Task 6.4: owner-approved result-readback amendment implemented and independently approved. Fresh canonical fast passed 559 tests and 39 subtests; 27 focused checks exercise real facade, REST and official MCP over ASGI, public schemas and executable examples. Retrieval authorizes the receipt before scoped content lookup, preserves exact reference/value and existing state, and creates no business work. Existing invoke/inspect status semantics remain unchanged. Application 1,449/1,500 LLOC; installed socket parity remains task 8.2.

- Task 8.1: independent review passed fresh canonical fast (532 tests, 39 subtests) and integration (3 tests). Installed kernel/plugin origins, real REST and official MCP discovery, negotiated protocol, wheel/lock identities and graceful owned cleanup were verified; no recorded processes remained. Generated credentials are excluded from persisted evidence. Windows launcher/runtime PIDs differ and require verified parentage. Injected startup/cleanup failures retain failed records without forced termination. Full conformance remains 8.2–8.4. When extending failure cases, assert their specific injected diagnostics; task 8.4 must update stale CI wording while enabling integration.

- Task 7: independent review approved the canonical fast pipeline with 532 tests and 40 subtests. Explicit provider and activation contexts assemble one Execution for REST/MCP; activation snapshots retain manifests and shared catalogs expose actual execution settings. The host validates its retained socket, applies interface-owned Host/Origin and bounded MCP framing checks, and propagates lifecycle failures even if Uvicorn only logs them. Missing guarantees prevent effects; unsuccessful execution shutdown fails cleanup while remaining owned resources unwind. Task 8 must use this production assembly with installed wheels and real clients; current evidence is synthetic ASGI integration.

- Task 6.3: independent review approved the canonical fast pipeline with 489 tests and 40 subtests. Official MCP clients over ASGI exercise the shared Execution and independently observed synthetic effects, including a retained REST retry. Explicit tool-to-envelope identity checks supplement published schema constants; private discovery uses the current principal. Schema embedding preserves recursive local references and resource scopes. Post-effect serialization failure reports unavailable while retaining the operation for inspection. Composition owns framing, Host/Origin and session lifespan; installed socket acceptance remains downstream.

- Task 6.2: independent rereview approved the canonical fast pipeline with 445 tests and 40 subtests. REST uses the injected application-owned TransportWire contract and shared codecs, with no interface-to-adapter imports. Actual ASGI cases prove guarded effects, safe field/limit diagnostics, private discovery and canonical outcomes; duplicate preconditions retain their affected location. Raw framing limits are separately advertised. MCP parity, runtime-limit discovery and installed socket verification remain tasks 6.3, 7 and 8.

- Task 5.3: independent review passed the canonical fast pipeline with 375 tests and 40 subtests. Execution owns shielded tasks, admission leases, capacity, bounded shutdown and result/evidence/CAS readback. Recorded handoff metadata requires exact scoped readback; it proves no production durability or distributed fencing. A regression prevents cancellation-resistant admission from starting an effect after shutdown. Cancellation-resistant effects remain owned and shutdown reports false until they exit. Application size is 1,401/1,500 LLOC. Transport assembly must use Execution as Facade and treat unsuccessful shutdown as failed cleanup; real socket verification remains downstream.

- Task 6.1: independent review approved trusted principal adaptation; fresh focused22tests, strict typing and boundary checks passed. Whole-workspace checkpoint363tests40subtests includes unaccepted5.3 work; the task commit's installed hook validates its isolated accepted scope. Authentication derives identity from a supplied verifier and deployment configuration; generated conformance credentials require exact127.0.0.1. Server startup must call validate_bind and wire access_policy in task7. Owner explicitly requested independent parallel implementation on2026-10-14; reviews and task commits remain separate.

- Task 5.2: independent review approved canonical325tests40subtests; parent fresh admission22tests pass. Atomic admission grants one execution owner; lost acknowledgements return retained receipts without replay. Command resources require complete expected-version coverage after retry lookup. Execution must hold admission context through effects in5.3. Application1150LLOC leaves350 under currentcap. RED evidence is retained in the implementer transcript, not an artifact directory.

- Task 1.1: approved pins resolve on CPython 3.12.10; independent review and fresh bootstrap, Ruff and Pyright checks pass. Fast/integration modes remain explicitly unavailable until tasks 1.4/8.1. On this host use uv.exe directly: the PowerShell uv wrapper can mis-forward arguments in multi-command calls.
- Task 1.2: independent review and fresh standalone quality check pass; 21 tests/15 subtests. Parenthesized decorators use token positions; only approved test roots receive separate accounting. quality_policy.py and quality_measurement.py separate policy/extraction responsibilities. Full pipeline remains pending task 1.4.
- Task 1.3: independent rereview passed after repairing generated-stage consistency and shared-namespace plugin ownership. Fresh breadth/import gates pass; independent suite36tests41subtests. Full suite currently roughly3minutes; direct real check(root) fixture calls proved much faster than subprocess-per-case. Task1.4 can optimize that measured overhead while retaining CLI smoke coverage.
- Task 1.4: independent review passed canonical fast and pre-commit all-files (40 tests/40 subtests), verified installed-hook and all six deliberate rejections plus clean-checkout evidence. Full fast command is now canonical; integration remains unavailable until8.1. Direct gate fixture calls and pinned Ruff executable reduce process overhead. CI configured, not remotely executed.
- Task 2.1: independent review verified90tests40subtests, immutable value contracts and wheel py.typed/exports. Disposable engineering fixture now counts its own source tree, preserving deliberate stale-count checks. Contract results retain immutable Decimal/date/frozen data classes; wire conversion and outcome policy remain later tasks.
- Task 2.2: resumed 2026-10-14 with fresh independent approval and canonical98tests40subtests. Public success signatures preserve Design; structured exceptions distinguish unavailable/guard/catalog failures, and admission retains its explicit result union. Read/command contexts are disjoint; provider atomicity remains later verification.

- Task 2.3: independent review and fresh canonical110tests40subtests passed. Typed closures preserve request/result pairing and command observations across encoding failure; immutable catalog resolves exact keys and checks advertised descriptors. Wire validation and outcome policy remain downstream.

- Task 3.1: independent rereview verified163tests40subtests after correcting fingerprint wrapper-depth and strict float coercion. Explicit PydanticCodec.for_input() gives request normalization its input budget; result codecs keep output budgets. Hashing consumes already validated normalized content without a second depth admission cap.

- Task 3.2: independent review verified214tests40subtests. Pure OutcomeFacts require dispatcher-supplied codec/provider facts; authoritative completion pins can differ from admission versions. Required-stage refs also occur in top-level evidence, and stage pass labels reflect inspected evidence. New scoped reconciliation resolves ambiguity; journal CAS/provider provenance remain later tasks.

- Task 3.3: independent review verified234tests40subtests. Fixture providers stay under tests/kernel with temporary single-event-loop state and explicit epochs. Target-wide non-reentrant guard is bounded; lost acknowledgements follow actual retained writes. Later installed fixture assembly must wire providers explicitly; plugin code depends only on public contracts.

- Task 4.1: independent review verified240tests40subtests with real offline wheel installs/origin checks and executable author docs. Generic CapabilityFactory/CapabilityInstance defines the public author boundary; closer/context share one idempotent resource owner. Pyright fixture source extraPath is typing-only. Variant builds and lifecycle probes remain test-only; activation follows in4.2.

- Task 4.2: independent review verified241tests40subtests including actual installed activation matrix. Typed configured closures preflight before opens; AsyncExitStack reverses cleanup and registry publication follows all binding checks. Installed MCP2.3 limit is128;128/129 tested. Nonblocking review suggestion: extend exact diagnostic assertions in graph/lifecycle cases when those cases change.

- Task 4.3: independent review verified267tests40subtests. VerificationIdentity and resolve_verification match exact operator expectations and unique order-independent dependencies, retaining only matched scoped records. Metadata matching does not inspect evidence contents; discovery/writer integration remains later.

- Task 5.1: independent review verified303tests40subtests. Guards, Inspection and QueryDispatcher implement authorization/privacy and actual retained query readback. Narrow ServiceHealth, InvocationLimits/WireFailure and ResultStore contracts clarify existing guarantees; no public result endpoint or durability added. Full Facade command composition follows5.2-5.3. Application1026LLOC leaves474 under currentcap.

- 2026-10-14 hosted-CI cold-cache follow-up accepted and committed as `44d3101` at the fixture-packaging boundary (Tasks 1.1/1.4 and supporting 4.1/8.1/8.4): frozen URL/hash-aware pylock offline sync precedes the original constrained wheel installation and dependency check. No lock/dependency/runtime API changes. Baseline cold Linux install failed; repaired and independent fresh Linux checks each passed 11 packaging/activation/fault tests with unchanged registry metadata. Canonical fast 741 passed/88 subtests; integration 620 passed plus ten catalog proofs. Independent audit checked 31 runtime versions, 160 locked artifacts, 660 conformance hashes and 76 cleanup records (two intentional lifecycle failures). Evidence `artifacts/ci-first-push/kernel-cache` and `artifacts/kernel-20261014T183324-32f94ff4`. Hosted workflow confirmation remains pending.
