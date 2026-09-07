# AC-002C — Approved Codex Implementation Dispatch

AC-002C converts the AC-002B engineering handoff into one durable, auditable `CODEX_IMPLEMENTATION` work item only after an explicit owner decision.

## Flow

1. AC-002B produces a batch-scoped decision package and engineering handoff.
2. The batch stops at `OWNER_REVIEW_REQUIRED` with `dispatch_allowed=false`.
3. An authorized owner submits the engineering-handoff decision.
4. Rejection closes the handoff without creating an implementation job.
5. Approval creates exactly one `AgentJob` with:
   - `job_type=CODEX_IMPLEMENTATION`
   - `risk_class=R2`
   - `assigned_worker=CODEX_IMPLEMENTATION`
   - `owner_approval_required=true`
   - `owner_approval_status=approved`
   - validation evidence limited to the summarized AC-002B decision/handoff artifacts.
6. The approved job is queued for a future premium Codex dispatcher. AC-002C itself does not call a provider.

## Non-negotiable controls

- No Codex work item exists before owner approval.
- The generic R0/R1 Local Worker Bridge is unchanged and its credential endpoint remains restricted to R0/R1.
- AC-002C does not change the global Agent Routing Policy; R2/R3 continue to route to Claude under the generic route.
- The specialized Codex path is explicit and auditable rather than hidden inside the global router.
- Codex evidence may reference only the summarized decision package and engineering handoff. It must not read hidden-truth simulation package files.
- No validation-plane dependency may be introduced into production execution.
- Automatic merge and deployment remain prohibited.
- Rejection creates no `CODEX_IMPLEMENTATION` job.
- No database schema migration is required.

## API

`POST /api/v1/organizations/{organization_id}/simulation-controller/batches/{batch_id}/engineering-handoff/owner-decision`

Body uses the existing owner decision contract:

```json
{
  "approve": true,
  "note": "Approved bounded implementation"
}
```

An approved response returns the created implementation job id and reports `provider_execution_started=false`. This is intentional: AC-002C authorizes and records the implementation work item, but does not yet connect the premium Codex provider runtime.
