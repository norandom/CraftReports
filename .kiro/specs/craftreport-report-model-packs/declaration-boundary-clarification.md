# Declaration and wire validation task boundary

Accepted 2026-10-15 under the bounded overnight authorization. Independent reviewer
`/root/review_declaration_boundary` returned PASS for proposal SHA-256
`27210828A2E4F0C8D14F7D2DB8AA532FD17D3301A03833248E8FE6CE97262C15`.
No new capability,
dependency, import permission or numeric budget is proposed.

The accepted Design places frozen inward report declarations and semantic
validation in reporting, and strict Pydantic transport schemas in adapters.
Task 2.2 currently says to implement the closed schema "using installed Pydantic
support and frozen inward values", while task 7 owns the wire integration.
The pure reporting import gate correctly forbids Pydantic/adapters.

Clarify task 2.2 to implement frozen declarations, intrinsic and cross-reference
validation, typed parameter resolution and upstream input requirements. Unknown
typed constructor fields and unsupported typed content kinds reject at this seam;
it must not introduce a parallel JSON parser or claim raw JSON validation.
Task 7 owns raw unknown/executable JSON field rejection, closed Pydantic schemas
and shared scalar conversion. Its acceptance must explicitly prove these cases
before public operations are exposed. No requirement is removed or made optional.

Use only the existing planned files: reporting/definitions.py for declarations
and their authoritative invariants; reporting/prepare.py for parameter resolution,
requirements merging and injected canonical template identity checks. Task 4 later
adds projection in that same preparation responsibility. A minimal package
initializer and tests/reporting/test_definitions.py complete task 2.2's scope.
Reuse existing Scalar, FieldRequirement, MetricRequirement, InputRequirements,
VersionPin, CapabilityRequirement and accepted theme/policy contracts.

Preserve all reviewed type/range/default/reference, cardinality and serialized
size constraints. Resolve repeated source requirements by compatible intersection,
reject conflicts, and require explicitly numeric series for charts before snapshot
selection. Template identity checks use the injected existing canonical identifier;
no new hashing implementation or schema registry is authorized.

Planning estimate: declarations 240–280 LLOC, initial parameter/requirements
preparation 100–150, plus the package initializer. These are forecasts within the
unchanged reporting aggregate and local limits, not reserved exceptions. Review
measured growth against remaining projection/operation needs before acceptance.

Independent plan review is complete; root may start task 2.2 after accepted task
2.1. This document does not mark either implementation task complete.
