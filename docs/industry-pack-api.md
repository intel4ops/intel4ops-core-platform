# Industry-Pack API

Platform administrators use `/api/v1/industry-packs` to list packs and versions,
create drafts, inspect components, validate, approve, publish, deprecate, and retire.

Authorized tenant users use
`/api/v1/organizations/{organization_id}/industry-packs` to list or create
assignments, activate or suspend them, and submit executions at
`/{assignment_id}/executions`.

Errors return stable codes including `PACK_NOT_FOUND`, `PACK_VERSION_NOT_ASSIGNABLE`,
`INVALID_PACK_TRANSITION`, `PACK_VERSION_IN_USE`, `PACK_NOT_ACTIVE`,
`PACK_RULE_NOT_FOUND`, and commercial entitlement denial codes. Execution retries use
the tenant plus idempotency key and produce one usage event.
