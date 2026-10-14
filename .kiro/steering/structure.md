# Project Structure

Updated: 2026-10-14. This is the organization pattern for the approved reporting foundation. Kernel directories now exist; reporting and app-specific directories remain proposals until their scope is activated. The breadth ledger records actual ownership.

## Organization Philosophy

Use one installable Python package with cohesive responsibility boundaries. Feature breadth and physical structure are separate maps; `breadth.toml` assigns lifecycle and most-specific path ownership. Do not scaffold every future module/app shown in an exploratory map.

## Directory Patterns

### Value Contracts and Pure Preparation

**Location:** `src/craftreport/contracts`, `data`, `reporting`, `themes`, `policies`.

Keep typed request/result/value objects independent of concrete app/database/framework libraries. Data validation preserves supplied values/provenance; report compilation resolves content and styles without recomputing financial methods. Policy evaluation records reporting scope and draft/release findings without importing future GIPS or accounting engines.

### Use Cases and Runtime

**Location:** `src/craftreport/application`, `runtime`.

Application use cases own the reporting operation contract and narrow ports. Runtime coordinates jobs, refresh lifecycle and session/binding state. Persistent operation evidence and live-app effects have distinct owners; do not duplicate completion state in an HTTP handler or worksheet control watcher.

### External Adapters and Entry Points

**Location:** `src/craftreport/adapters`, `interfaces`, `composition`, and self-contained app/domain packages under `packages/` when activated.

Concrete app/storage adapters implement narrow application ports. An activated capability package carries its descriptor/settings, typed operations, implementation, tests and documentation. The GridCraft app package owns mode-specific drivers/framing; a generic transport module is introduced only when actual reuse warrants it. Entry points call the same facade. Composition allowlists/version-checks capability registrations and contains no business logic.

Example: a native GridCraft checkbox watcher translates a visible request into the same pause operation used by an MCP caller; it does not own another scheduler.

### Public Examples, Deployment and Verification

Use public/synthetic examples, generic deployment configuration, and requirement-derived tests. Private packs/datasets remain outside public distribution. Declare ownership for these paths before tasks expand; tests are measured separately from production source budgets.

Detailed concrete paths belong in the feature design's File Structure Plan, not this steering document.

## Naming Conventions

- Python files/functions: snake_case; typed contracts/classes: PascalCase.
- Stable report/capability identifiers are independent of filesystem names and native object IDs.
- Numeric requirement references are carried into design, tasks and evidence.
- Name app adapters by app and execution mode; session/document identity is not adapter identity.

## Import Organization and Allowed Dependencies

Contracts form the inward boundary. Pure preparation modules import contracts and their explicitly declared peers. Application use cases consume preparation services and their own ports. Runtime and external adapters depend on those contracts/ports. Interfaces depend on the facade; composition may import the concrete implementations it wires.

No pure contract/preparation/application module imports a concrete GridCraft transport, ORM session or HTTP/MCP SDK. No ingress or app control bypasses the facade to create alternate validation/retry/release behavior. Mechanical import checks are part of the approved foundation.

Commands and queries share typed operation registration and fixed middleware for access, capabilities, retries/version guards and stage receipts. Plugins own their behavior; they cannot reorder or bypass core guards. Templates remain declarative packs rather than executable plugins. The package boundary and dependency range are reviewed before each new capability activates.

## Code Organization Principles

Extract along a responsibility seam, not just to satisfy file caps. Feature totals remain accountable across files. New code in an existing pattern should not require editing steering.

Local portfolio calculations, GIPS packs and other parked domain/app implementations remain absent until their own scope is activated. General parent ownership does not authorize them. Use `overview.md`, `engineering.md`, `testing.md` and `breadth.md` for recurring project rules.
