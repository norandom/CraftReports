# Approved amendment: authorized retained-result readback

Status: approved by the owner on 2026-10-14. Implementation and verification remain task 6.4.

## Decision

Add one guarded, read-only result retrieval operation to the existing facade, exposed through REST and MCP. Keep invocation receipts unchanged. An ordinary client can invoke a query, receive its operation identity, and retrieve the retained result through the same authenticated service.

This resolves the tension between requirement 3.6 (the caller receives an inspection result), the original actual-client query-readback journey, and the approved `Receipt | Rejection` invocation response. A private test observation remains an independent oracle; it cannot substitute for ordinary-client retrieval.

## Approved contract

- Application: `Facade.read_result(principal, operation_id)` returns a typed retained-result response or a safe rejection.
- REST: `GET /v1/operations/{operation_id}/result`.
- MCP: built-in `craftreport.result.v1`, accepting only `operation_id`.
- Successful response: the current authorized receipt plus the exact retained JSON result associated with that receipt's `result_ref`.
- Invocation and receipt-inspection responses remain unchanged. No arbitrary result-reference or filesystem-path lookup is exposed.

The response carries the receipt's existing state. Retrieving content does not turn partial, ambiguous or failed work into complete work. REST and MCP expose equivalent canonical content; MCP preserves the receipt's existing error-state meaning.

## Ownership and safeguards

1. The application inspection boundary authorizes the operation receipt before looking up its contents. The existing principal-scoped `ResultStore.read` remains responsible for retained-content visibility.
2. Resolve the result reference from the authorized journal receipt. Do not trust a caller-supplied reference or regenerate a missing result.
3. Verify the returned reference and availability. Preserve safe distinctions for missing, inaccessible and unavailable content; no result bytes are disclosed after denial.
4. A receipt without a retained result returns a structured, inspectable rejection. It does not invent an empty successful result.
5. Return the retained value as stored. Do not rerun the operation, change target state, admit a new business operation, or recompute financial methods.
6. Shared contracts and serialization define the response. REST and MCP only adapt it. Retained result limits remain the operation's declared limits; transport framing is distinct.
7. Preserve the existing dependency direction, typed code and approved engineering budgets. A budget change is not part of this proposal.

The existing result store and receipt inspection already provide the principal, operation, reference and availability seams. This proposal adds a public read path, not a new persistence provider, storage backend, export system or reporting capability.

## Approved task amendment

Add task **6.4: Expose authorized retained-result readback**, dependent on task 7's assembled host. It repairs the owning application/transport contract before task 8.2 resumes. Task 8.2 then depends on 6.4 as well as 8.1.

Task 6.4 includes:

- Typed result-readback values and facade/inspection behavior.
- Shared serialization, REST route and MCP built-in.
- Authorization, missing/unavailable content, exact-reference, non-mutation and truthful receipt-state tests.
- Executable ordinary-client examples and documentation.
- Fresh independent review, fast checks and a separate commit with the installed hook.

Task 8.2 must retrieve query values through the public REST/MCP interfaces, compare them with the private independent target observation, and verify that foreign callers cannot retrieve them. Its existing private observation channel remains a test oracle only.

## Acceptance evidence

An installed ordinary client invokes the synthetic query and retrieves its result over REST. The official MCP client retrieves the same retained content, and the reverse transport order works too. Both preserve operation/result identity and canonical values. Query and retrieval leave target value, version and effect count unchanged.

Denied callers, unavailable storage, absent results and mismatched references disclose no retained values and never create successful content. Valid content associated with a non-complete receipt retains that non-complete state.

The evidence remains synthetic and temporary. No production durability, browser behavior, XLSX artifact or financial-method assurance is implied.

## Alternative

Keep the API receipt-only and explicitly narrow the caller-result requirement and actual-client journey. This would leave ordinary result retrieval for a later spec. It is not recommended for the requested app-to-app reporting foundation.

## Approval scope

Approval authorizes this design and task amendment under the existing kernel requirements. The requirements themselves are not weakened. Task 8.2 must use the approved retrieval endpoint before claiming ordinary-client query-result readback.
