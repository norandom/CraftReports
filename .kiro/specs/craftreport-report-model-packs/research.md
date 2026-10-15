# Research and Design Decisions

## Summary

- **Feature:** craftreport-report-model-packs.
- **Discovery scope:** new preparation feature integrated into the installed operation kernel; full discovery with bounded first table/line-chart slice.
- **Key findings:** the kernel already owns strict ingress, version compatibility, identity, immutable results and ordinary REST/MCP readback; duplicating these would add infrastructure without reporting behavior. The snapshot representation and completeness checker must be upstream, independent of report compilation. Preparation cannot establish physical layout, numerical accuracy or export/reopen evidence.
- **Skills consulted:** kiro-spec-batch, requirements/design/tasks phase skills and their review/synthesis/generation rules; financial-modeling-sheet for semantic classification and presentation-only boundaries; COBESY for task-centered quickstart structure as required by documentation steering. No workbook is edited and no house palette becomes a mandatory finance policy.

## Research Log

### Existing kernel and engineering scope

Inspected contracts/identity, outcomes, immutable values, operation descriptors, PydanticCodec/StrictWireModel, canonical wire adapter, operation registry, activation composition, REST/MCP interfaces, root quality/breadth policy and engineering boundary fixtures on 2026-10-15. Pydantic BaseModel instances cannot be retained as domain results because kernel require_immutable accepts frozen dataclasses and recursively immutable values. Reuse the established frozen-domain/strict-boundary codec convention and typed operations. Existing canonical profile rejects unsafe JSON integers beyond 2**53-1: consume upstream exact scalar serialization rather than leak unsupported int64 JSON values into prepared output.

The live import policy still recognizes kernel layers only. Proposed reporting/themes/policies source requires a preceding root-coordinated activation task with negative import fixtures and unchanged 50 function / 300 module / 1,500 capability / complexity 10 defaults. Public content ownership and executable adopter code remain separate.

### Mature schema and compatibility facilities

Official documentation checked 2026-10-15:

- [Pydantic discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/) provides tagged union validation. Use it for concrete table/line-chart sources and parameter references; do not write a parser or expression language.
- [Pydantic dataclasses](https://docs.pydantic.dev/latest/concepts/dataclasses/) and [TypeAdapter](https://docs.pydantic.dev/latest/api/type_adapter/) provide validation/schema facilities for typed values. Installed Pydantic is 2.14.1 in pyproject/lock; implementation must verify the selected installed API rather than infer runtime compatibility from current website documentation. Follow the existing PydanticCodec unless a smaller equivalent adapter can preserve its strict/immutable safety contract.
- [Packaging specifiers](https://packaging.pypa.io/en/stable/specifiers.html) provides version compatibility checks. Reuse installed packaging 26.3 for exact pack version syntax and engine ranges; no homegrown semver parser.
- [Python 3.12 pathlib](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.resolve) supplies canonical path resolution. It does not by itself authorize access or defeat every filesystem race: the implementation reads manifest-listed content once into an immutable activation snapshot, verifies digest and containment, and rejects escapes. Packs are configured local JSON directories; no archive extraction or remote URL resolution.

No new dependency, ORM, database, schema registry or plugin loader is justified for preparation. Standard JSON plus the installed validation library serves the bounded vocabulary. Jinja/SQL/formula engines would introduce unsupported executable meaning.

### Semantic house presentation

The financial-modeling-sheet skill separates imported source data, editable assumptions, external results, ordinary output, key results and findings. Adopt semantic role classification, separate units, leading-minus formats, visible nulls and external method markers as configurable theme content. Do not implement its live Excel editing workflow, worksheet-position mandates or arithmetic verification here. Actual GridCraft style mapping and XLSX preservation remain target-owned evidence.

### Shared contracts with snapshot-runtime

Agreed by direct sibling coordination: one upstream data.values Snapshot/SnapshotRef, Scalar/Field/ImportedMetric vocabulary, data.requirements InputRequirements/check_completeness and data.ports SnapshotReader. Shared VersionPin(identity,version,content_digest) belongs to contracts.pins, created solely by snapshot-runtime's contract task. Runtime stores generic pins and never imports themes/reporting. Report-model owns PackPin attribution/artifact policy, prepared table/chart and quality values. Prepared content excludes target/run/session identity; runtime pins those separately. This removes a proposed runtime-to-theme dependency cycle. The data.ports boundary alone imports exact kernel Missing/VersionConflict/ServiceUnavailable values; pure data remains inward.

Independent Design review identified missing declared field/metric constraints, title, external statement input and shared application budget pressure. Remediation places feature operations/ports under reporting, leaves kernel application unchanged at 1,449/1,500 and adds explicit pure/orchestration module import rules. Metric chart requirements specify numeric kinds and series shape before latest-complete selection. Guide index is docs/quickstarts/index.md. The upstream finalized snapshot-size invariant plus closed cardinality/metadata bounds permits an 8 MiB preparation result cap without new admission machinery or weakening the approved pre-acceptance limit requirement; numerical operation-load settings do not alter engineering budgets.

Upstream wire decision: all int64 cells and producer_version use canonical decimal strings; inward values remain int. Decimal/date/datetime also use exact strings with declared field kind, and bool/null remain JSON literals. Reuse adapters.snapshot_wire.encode_scalar/decode_scalar; decode never infers a kind from string contents. Resolved parameter wire values need explicit kind tags so typed int/date/text remain distinguishable outside the definition document. ImportedMetric has explicit scalar/series shape, allowing an empty ordered series without ambiguity.

## Architecture Pattern Evaluation

| Option | Strength | Limitation / decision |
| --- | --- | --- |
| Direct app commands per report | Small isolated edits | Does not supply reusable definitions, exact input pins or one release-policy owner |
| Small typed schema and pure functions | Fits first reusable table/chart; testable exact output | Selected; closed supported vocabulary limits breadth deliberately |
| General DSL, template executable plugins or policy engine | Flexible future syntax | Rejected: no scoped requirement, parsing/security/budget cost and duplicated framework work |

## Design Decisions

### One input representation and one prepared content value

Use upstream immutable snapshots directly; derive metric label/value presentation without creating another snapshot type. Produce target-neutral prepared cells/series and resolved semantic requirements. Generic source/parameter selection is a concrete tagged reference, not an expression. No unrequested sorting, financial aggregation, sign/scale change or interpolation occurs.

### Separate prepared identity from quality observations

Content identity binds exact input, definition, parameter, template/theme/pack and validation policy selections. Execution time, operation ID and later target observations do not change prepared content. Quality evaluation separately consumes pinned trusted observations; changed/missing observations stay unevaluated. Required checks must pass internally to permit a scoped validated-release label; external method/standards claims cannot satisfy that gate.

### Reuse public operation contracts

Register validation/discovery/preparation operations behind existing kernel guards and readback rather than add routes, a client SDK or second receipt. Preparation's retained result is a command with a retry identity. The adopter recipe uses installed-wheel ordinary REST and MCP clients and two public synthetic datasets published through accepted production snapshot-runtime providers with AI disabled; it proves preparation only. Pure preparation fixtures can precede durable storage work, but a synthetic reader/journal or another test-only host cannot substitute for the product adopter workflow.

### Complete resource readback and trusted preparation facts

Bounded cross-spec repair inspected the actual `application.ports` ResourceReader/ExecutionGuard/EvidenceReader contracts, `execution._observations` and `outcomes._evidence_failure`: completion rereads every declared receipt resource, and every required stage EvidenceRef must match the complete authoritative set exactly. Snapshot storage owns only feed/snapshot/binding/run observations; reader injection alone did not provide authoritative pack observations or trusted retained preparer facts. The selected correction makes the already immutable configured pack snapshot serve two report-owned resource observations (source and artifact scope), delegates existing storage kinds, and composes those providers before open_application. Prepare declares snapshot plus both pack resources; definition/template/theme pins stay bound by the pack manifest and content identity. This uses existing public ports without adding application code or a provider framework.

PreparationFactWriter is private to trusted preparation. Its adapter converts closed typed check/decision facts to generic kernel values/canonical bytes for a restricted retention method in snapshot-storage's existing results/evidence files. That method binds retained command ownership and independently rereads exact facts from the existing evidence table; the existing EvidenceReader handles their refs. Storage never imports report types. Separate prepared and quality decision facts preserve requested validated rejection and do not certify unperformed target checks. Full-set missing/altered pack pins and unavailable fact readback become required installed-client negative cases. No evidence is reconstructed from expectations. This is the smallest extension of the existing retained-evidence responsibility; separate journals/tables and public trusted-fact submission were rejected.

The matching lifecycle correction distinguishes runtime's per-binding start fence from selection SQL/kernel leases. Actual Facade.invoke has bounded response semantics, not an admission-only API. Start holds only the lifecycle fence through the bounded invocation/operation-ID handoff and releases it before inspection; pause/stop use the same ordering. Immutable run pins replace a mutable binding lease in app-start resources to avoid inversion with runtime.control. Deterministic tests must cover both race orders, failure release and acknowledged pause blocking later starts. Registry names remain unversioned with contract version 1; only MCP tool names append `.v1`. These repairs apply the design/tasks skills' explicit-boundary and prerequisite checks; root retains independent review and phase metadata ownership.

## Risks and Mitigations

- Pack source authorization is distinct from artifact distribution. Carry separate scopes and verify source disclosure/private sentinel exclusion in diagnostics and distributions.
- Physical layout and target decimal/date/chart fidelity are unknown until observed. Keep target-related checks unevaluated and require downstream evidence before release.
- Broad domain/framework reuse can consume budgets before useful reports exist. Keep the vocabulary closed, share existing codecs/fixtures and review actual added/deleted LLOC alongside the delivered behavior.
- Independent phase and task reviews remain mandatory under overnight fast-track. Record actual reviewer/verdict provenance; never infer a review from dispatch or elapsed time.

## References

Project context: [brief](brief.md), [umbrella requirements](../craftreport-reporting-facade/requirements.md), [overnight authorization](../craftreport-reporting-facade/overnight-run-2026-10-15.md), required steering and root breadth/quality policies. These decisions authorize no production source until reviewed Design/Tasks and exact gate activation are complete.
