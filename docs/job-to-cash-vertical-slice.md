# Job-to-Cash vertical slice

The Job-to-Cash pack accepts a small deterministic canonical record set containing customers,
resources, jobs, time, materials, expenses, documentation, invoices, invoice lines, payments,
allocations, and contracts. Records are tenant scoped, source referenced, integrity hashed,
and attached to an idempotent run.

The bounded deterministic rules detect completed-unbilled work, underbilling, missing
billable time, missing materials or expenses, invoice delay, payment delay, negative margin,
and documentation blockers. Each result retains the affected job, Decimal exposure, reason,
and evidence identifiers.

`POST /api/v1/organizations/{organization_id}/job-to-cash/runs` requires the
`industry.job_to_cash` entitlement. The same organization and idempotency key return the
original run. The included test dataset is synthetic and contains no customer information.

WP-2.18 establishes canonical ingestion and deterministic detection. Live ERP connectors,
foreign-exchange conversion, arbitrary rules, and other industry packs remain deferred.
