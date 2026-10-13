# Implementation Plan

Requirements, Design and Tasks are approved. The owner authorized implementation on 2026-10-13. All checks below remain planned until their tasks run with fresh evidence.

Tasks follow foundation, core, integration and validation order. Unmarked tasks are sequential; only the three independent core tasks marked (P) may overlap after their listed prerequisites complete. Each executable task is intended as a 1–3 hour unit. Scope follows the approved Design file plan; documentation updates accompanying a working contract are part of its implementation, not separate documentation-only tasks.

The kernel covers 36 criteria using synthetic capability effects and actual software clients. Durable storage/restart, GridCraft, browser recordings and XLSX acceptance remain downstream. No optional acceptance tests are marked.

## Tasks

- [ ] 1. Establish the executable engineering foundation
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

- [ ] 1.3 Enforce breadth ownership and allowed imports
  - Validate actual spec phases/counts, scoped approved ownership, most-specific owners, parked paths and overdue required retirements against the ledgers.
  - Enforce the inward dependency direction, including the prohibition on framework/app/storage imports in contracts/application and on adapter-interface cross-imports.
  - Done when disposable violation fixtures fail with exact ownership/import diagnostics and the current bootstrap passes; no future capability is activated to satisfy a gate.
  - Validate with focused gate fixtures and the fast check entry point; activation and all later packages remain subject to these checks.
  - _Boundary: Engineering boundary gates_
  - _Requirements: 1.4, 3.5, 7.2_

- [ ] 1.4 Install and prove the complete fast-check pipeline
  - Complete the common fast command with Ruff lint/format, Pyright strict across source/scripts/tests, budgets, breadth/import checks and focused tests.
  - Install pre-commit hooks and configure CI to run the same whole-scope checks plus scheduled retirement aging; define the separate integration stage without claiming it passes before its harness exists.
  - Done when the installed hook actually runs and both hook and direct fast command pass the bootstrap; a disposable lint/type/budget violation must cause rejection.
  - Record installed versus passing state accurately. Product implementation begins only after this engineering foundation passes.
  - _Boundary: Engineering check integration_
  - _Depends: 1.1, 1.2, 1.3_
  - _Requirements: 7.1, 7.2, 7.4_

- [ ] 2. Define the stable operation boundary
- [ ] 2.1 Define immutable identities, operation descriptions and outcomes
  - Express principal scope, capability/version identity, invocation metadata, resource preconditions, command/query declarations, receipts and evidence values without framework handles.
  - Represent rejection separately from accepted work and preserve explicit partial/ambiguous and unavailable states.
  - Done when strict typing and focused contract fixtures distinguish all declared states and reject inconsistent value combinations without importing concrete providers.
  - Validate through the fast command; registration, adapters and downstream modules consume these values.
  - _Boundary: ValueContracts_
  - _Depends: 1.4_
  - _Requirements: 1.5, 2.1, 2.5, 5.1, 5.2, 5.3, 5.6_

- [ ] 2.2 Define guarantee-provider and execution-context contracts
  - Define authorization, atomic operation admission/observations, version guards, capability resolution, evidence lookup and facade inspection contracts with typed unavailable/conflict outcomes.
  - Separate query inspection services from command services; keep canonical completion and registry mutation out of capability execution contexts.
  - Done when typed conformance doubles demonstrate required admission/guard/evidence outcomes and a query cannot receive the command-only service bundle.
  - Validate through focused port contract checks and the fast command; fixture providers and dispatch depend on these signatures.
  - _Boundary: ServicePorts_
  - _Requirements: 3.2, 3.3, 3.4, 3.6, 4.3, 4.4, 5.3, 5.5_

- [ ] 2.3 Register typed operations in an immutable catalog
  - Pair request/result conversion with the correct command or query behavior while retaining type safety behind common dispatch.
  - Resolve exact operation/version identities, expose schema/limit descriptors and reject invalid classifications, duplicate keys or incompatible binding descriptions.
  - Done when distinct typed fixture registrations can be discovered and invoked through their prepared boundary without unchecked heterogeneous-handler casts.
  - Validate registration/lookup fixtures and fast checks; activation and transport discovery use this catalog.
  - _Boundary: Registry_
  - _Requirements: 1.4, 2.1, 2.2, 2.5, 3.5_

- [ ] 3. Build independent core collaborators
- [ ] 3.1 (P) Preserve wire values and canonical retry content
  - Implement the shared strict input/result conversion path, explicit serializers, versioned normalization and stable request fingerprinting.
  - Cover forbidden extra fields, unsafe integer/decimal representations, booleans versus integers, numeric strings, defaults, array order and object-key order. Enforce decoded-envelope size, nesting depth and the advertised serialized-output limit in the common conversion boundary.
  - Done when equivalent decoded requests have the same normalized content/fingerprint and altered preconditions conflict; invalid or over-depth inputs never reach behavior, and oversized results become result-contract failures with truthful effect status.
  - Validate codec cases through fast checks. Own only codec/canonicalization implementation and its cases; both transports later reuse it unchanged.
  - _Boundary: WireCodec_
  - _Depends: 1.4, 2.1, 2.2, 2.3_
  - _Requirements: 2.3, 2.4, 4.1, 4.2, 6.2_

- [ ] 3.2 (P) Determine completion from result and evidence
  - Validate effect disposition, result status, required evidence pins, safe diagnostics and allowed receipt transitions.
  - Keep missing/inaccessible/unavailable evidence distinct; require new reconciliation evidence to resolve ambiguity and preserve prior attempts.
  - Done when outcome fixtures with missing evidence, malformed results or partial/unknown effects cannot become complete, and unsafe diagnostics are removed.
  - Validate outcome cases through fast checks. Own only outcome rules and their cases; dispatch will provide actual codec/provider results during integration.
  - _Boundary: OutcomeRules_
  - _Depends: 1.4, 2.1, 2.2, 2.3_
  - _Requirements: 2.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 3.3 (P) Supply deterministic synthetic guarantee providers
  - Implement test-only authorization, atomic journal/observation state, guarded versions, capability/evidence lookup and an independently readable synthetic target.
  - Provide barriers and bounded failure controls for concurrent admission, lost acknowledgement, unavailable evidence and effect interruption.
  - Done when provider conformance cases show one atomic winner, monotone receipt revisions and explicit temporary retention/epoch; no production fallback is exported.
  - Validate provider fixtures through fast checks. Own the fixture-services boundary only; activation and client tests consume it later.
  - _Boundary: ConformanceRunner fixture services_
  - _Depends: 1.4, 2.1, 2.2, 2.3_
  - _Requirements: 3.4, 4.3, 4.4, 5.5, 7.2, 7.4_

- [ ] 4. Activate independently packaged capabilities
- [ ] 4.1 Package an independently installable conformance capability
  - Create the separate synthetic fixture distribution with discovery metadata, typed operations, settings and lifecycle instrumentation.
  - Produce selectable/unselected and incompatible/colliding variants from isolated fixture builds, without placing executable fixtures in public production plugin paths.
  - Done when a built fixture wheel installs alongside the kernel and its manifest/bindings match the author contract; update the author example with this executable contract.
  - Validate wheel metadata/install inspection and fast checks; activation tests must use actual installed distribution discovery rather than only registry mocks.
  - _Boundary: ConformanceRunner fixture packaging_
  - _Depends: 2.3, 3.1, 3.3_
  - _Requirements: 1.1, 1.2, 1.4, 2.5, 7.1, 7.4_

- [ ] 4.2 Validate and atomically activate the selected capability set
  - Select only configured distribution/entry-point identities and validate explicit dependencies, version compatibility, settings, reserved names, generated tool names and binding consistency.
  - Initialize in dependency order, publish only the complete registry and unwind acquired resources on initialization or cleanup failure.
  - Done when the activation matrix proves selected-only imports, collision/cycle/incompatibility rejection and no partially published registry or leaked fixture lifecycle resources.
  - Validate installed-fixture activation cases and fast checks; application assembly consumes only the successful immutable registry.
  - _Boundary: Activator_
  - _Depends: 2.3, 4.1_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.5_

- [ ] 4.3 Expose versioned conformance status accurately
  - Resolve operator-provided verification records against capability/build digest, core contract, fixture suite and dependency versions.
  - Make missing/stale evidence pending, matched failed evidence failed and matched passing evidence passed only within its recorded scope.
  - Done when catalog fixtures cannot gain passed status from plugin declarations or reused evidence for a different build.
  - Validate verification-record cases and fast checks; discovery and the final evidence writer share this identity contract.
  - _Boundary: Registry verification metadata_
  - _Depends: 4.2_
  - _Requirements: 1.5, 7.1, 7.3, 7.4_

- [ ] 5. Execute through fixed guards and truthful receipts
- [ ] 5.1 Guard invocation and inspection consistently
  - Apply coarse operation authorization before private validation diagnostics, followed by typed resource authorization, service/capability availability and query-context restrictions.
  - Protect catalog/receipt visibility and keep built-in inspection from recursively creating business work.
  - Done when invalid, denied, unsupported or unavailable requests produce structured rejection without behavior invocation or restricted disclosure; query fixtures preserve canonical target state.
  - Validate guard/query/privacy cases and fast checks; REST and MCP may only enter through this guarded facade.
  - _Boundary: Dispatcher guards_
  - _Depends: 2.2, 2.3, 3.1, 3.3, 4.3_
  - _Requirements: 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.2, 5.5, 6.4_

- [ ] 5.2 Admit retries and versioned effects exactly once within the journal scope
  - Look up authorized retained retries before current-version checks, then acquire the authoritative guard and atomically admit new command identity with its initial receipt.
  - Distinguish equivalent retries, content/precondition conflicts and admission acknowledgement loss; recheck guard validity before effect and release a race-losing guard safely.
  - Done when 20 equivalent concurrent requests yield one synthetic effect and one accepted identity; stale versions, different-content retries and cross-principal reuse cannot overwrite or disclose another operation.
  - Validate barrier-driven concurrency/admission cases and fast checks; downstream providers must satisfy the same contract without an implied remote exactly-once guarantee.
  - _Boundary: Dispatcher admission_
  - _Depends: 3.1, 3.3, 5.1_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1_

- [ ] 5.3 Own execution independently of clients and finalize receipts
  - Retain admitted execution under application lifetime, enforce response deadlines/capacity and bounded shutdown, and require a recorded owner for any pending handoff.
  - Feed typed results/effect observations through outcome rules and conditional receipt updates; do not replay unknown effects or synthesize success after journal/evidence failure.
  - Done when local disconnect/cancellation and post-effect failure cases retain inspectable non-complete or completed evidence as observed; capacity rejection reserves no retry identity and still permits inspection/retries.
  - Validate execution/outcome cases and fast checks; the later socket tests repeat the same behavior across real client disconnects.
  - _Boundary: Dispatcher execution_
  - _Depends: 3.2, 3.3, 5.2_
  - _Requirements: 2.4, 4.5, 5.1, 5.3, 5.4, 5.5, 5.6, 6.5_

- [ ] 6. Adapt ordinary clients to the shared facade
- [ ] 6.1 Establish trusted principal adaptation
  - Map authenticated transport identity into immutable caller scope without accepting authority from payloads or unverified forwarding headers.
  - Supply generated loopback test credentials and deny production requests without the configured authenticating policy; refuse remote binding of the conformance profile.
  - Done when two principals, invalid/missing credentials and payload identity-spoofing fixtures produce the expected trusted scope or rejection.
  - Validate authentication boundary cases and fast checks; both protocol adapters reuse this boundary.
  - _Boundary: Trusted principal adaptation_
  - _Depends: 2.1, 2.2, 5.1_
  - _Requirements: 3.2, 6.1, 6.4_

- [ ] 6.2 Expose guarded REST discovery, invocation and inspection
  - Implement the approved HTTP surface, raw-body limit/duplicate-key handling, private discovery, canonical response/status mapping and safe diagnostics; expose the configured decoded-size, nesting and output limits without replacing their shared codec enforcement.
  - Keep business validation in the shared codec/dispatcher and update executable client examples alongside the public contract.
  - Done when adapter checks show canonical successful/rejected/pending outcomes and no alternate mutation or public private-schema path.
  - Validate REST adapter cases and fast checks; real socket parity is completed after application assembly.
  - _Boundary: REST interface_
  - _Depends: 3.1, 5.3, 6.1_
  - _Requirements: 2.1, 2.3, 3.1, 3.2, 5.2, 5.6, 6.1, 6.2, 6.3, 6.4_

- [ ] 6.3 Expose registry-driven MCP tools with identical semantics
  - Adapt ordinary MCP discovery/calls to the same registry, trusted principal and facade; preserve exact operation/version mapping and authorized deterministic tool ordering.
  - Return canonical structured results plus compatible JSON text, distinguishing protocol errors from rejected/failed/partial/ambiguous business outcomes.
  - Done when adapter checks demonstrate the same payload/error meanings as REST, no AI dependency and explicit unknown-tool rejection.
  - Validate MCP adapter cases and fast checks. Keep this task sequential with REST because their transport-parity test module is shared; assembly owns the host lifespan.
  - _Boundary: MCP interface_
  - _Depends: 3.1, 5.3, 6.1, 6.2_
  - _Requirements: 2.1, 2.2, 3.1, 3.2, 5.2, 5.6, 6.1, 6.2, 6.3, 6.4_

- [ ] 7. Integrate capability activation, facade and application lifecycle
  - Compose the registry, supplied services, fixed pipeline and both interfaces without embedding request policy in assembly.
  - Manage MCP sessions and admitted execution from the host lifespan, preserve the intended route paths and enforce Host/Origin and loopback-profile settings.
  - Done when the assembled application reaches usable discovery with AI disabled, missing required providers prevent dependent effects, and shutdown closes owned resources.
  - Validate assembly/lifespan checks and fast checks; the installed-wheel runner uses this same composition rather than test-only replacement wiring.
  - _Boundary: Integration — Activator, Dispatcher, REST, MCP_
  - _Depends: 4.2, 4.3, 5.3, 6.2, 6.3_
  - _Requirements: 1.3, 3.4, 3.5, 6.1, 6.3, 6.5_

- [ ] 8. Prove the installed system through actual clients
- [ ] 8.1 Establish owned installed-wheel execution and evidence capture
  - Install kernel and fixture wheels into an isolated environment and launch the actual composed service on an owned loopback port with generated credentials and run-specific artifacts.
  - Provide real HTTP and official MCP client fixtures, negotiated protocol identity, sanitized transcripts and deterministic process cleanup.
  - Done when the integration command boots the installed service, discovers the selected fixture and records wheel/lock/environment identities; readiness alone is not reported as conformance.
  - Validate the harness smoke and forced startup/cleanup failures; later journeys consume these fixtures without mocking internal collaborators.
  - _Boundary: ConformanceRunner process integration_
  - _Depends: 1.4, 4.1, 7_
  - _Requirements: 6.1, 6.3, 7.1, 7.4_

- [ ] 8.2 Verify cross-transport behavior and permission boundaries
  - Exercise discovery, command invocation, query readback and an equivalent retry through the other transport, using the real installed composition with AI disabled.
  - Compare normalized values, accepted identity, result/error meanings and evidence; exercise hidden schemas, denied resources, wrong versions, malformed input and both principals. Verify advertised input size, nesting depth and serialized-output caps at and beyond each boundary through both transports, including the recorded effect status after an oversized result.
  - Done when independent target inspection confirms one intended effect and the same retained retry identity, while negative cases produce no effect or private disclosure.
  - Run the integration command and relevant fast regressions; keep executable examples and supported-contract descriptions consistent with observed responses.
  - _Boundary: Integration verification — REST, MCP, Dispatcher_
  - _Depends: 8.1_
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.6, 4.1, 4.2, 5.2, 5.3, 5.6, 6.1, 6.2, 6.3, 6.4, 7.2_

- [ ] 8.3 Verify disconnect, ambiguity and concurrent admission over sockets
  - Use barriers to prove admission before client disconnect, then retry/inspect through a new client and independently read the synthetic target.
  - Exercise concurrent equivalent/conflicting commands, stale versions, unavailable required services, post-effect journal failure and bounded shutdown/capacity.
  - Done when there is one admitted effect per retry scope, unknown effects are never automatically replayed and temporary state/restart epochs are reported without a durability claim.
  - Run integration failure journeys and fast regressions; record prior failures rather than hiding them behind successful reruns.
  - _Boundary: Integration verification — Dispatcher, ServicePorts, interfaces_
  - _Depends: 8.2_
  - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.4, 5.5, 6.5, 7.2, 7.4_

- [ ] 8.4 Finalize conformance evidence and test its sensitivity
  - Aggregate case results, all requirement references, build/contract identities and cleanup outcomes into the scoped conformance record consumed by catalog verification.
  - Prove that a disposable disconnected-handler variant fails actual-effect assertions and that a deliberately misclassified query which changes canonical synthetic state fails conformance. Verify stale/failed/wrong-build records cannot report passed; restore correct wiring/classification and verify it.
  - Complete CI's installed-wheel integration stage and retain diagnostics/artifacts on failure; required cleanup failure prevents conformance acceptance.
  - Done when the full synthetic conformance run produces a verifiable evidence packet and matched catalog status, with browser, durability and reporting artifacts explicitly outside its claim.
  - Run both canonical commands and the actual installed hook; these results support only the kernel's declared boundary.
  - _Boundary: ConformanceRunner and engineering integration_
  - _Depends: 4.3, 8.1, 8.2, 8.3_
  - _Requirements: 1.5, 2.4, 2.5, 3.5, 5.4, 5.6, 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Verify complete kernel integration and boundary closure
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

- Task 1.1: approved pins resolve on CPython 3.12.10; independent review and fresh bootstrap, Ruff and Pyright checks pass. Fast/integration modes remain explicitly unavailable until tasks 1.4/8.1. On this host use uv.exe directly: the PowerShell uv wrapper can mis-forward arguments in multi-command calls.
- Task 1.2: independent review and fresh standalone quality check pass; 21 tests/15 subtests. Parenthesized decorators use token positions; only approved test roots receive separate accounting. quality_policy.py and quality_measurement.py separate policy/extraction responsibilities. Full pipeline remains pending task 1.4.
