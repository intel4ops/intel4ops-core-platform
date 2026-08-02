# WP-2.TI-C1 Orchestration Referential Integrity

## Purpose and invariant

WP-2.TI-C1 adds database defense in depth to the Orchestration domain. Every
eligible tenant-owned reference requires the child and parent to share the same
`organization_id`. Existing service, API, schema, authorization, and analytical
behavior remains unchanged.

## Schema contract

The migration adds `uq_orchestration_requests_org_id` on
`intelligence_orchestration_requests (organization_id, id)`.

Ten composite foreign keys enforce tenant consistency:

- C1–C3 connect decisions, steps, and status history to their orchestration
  request with `CASCADE`.
- C4–C7 connect orchestration requests to datasets, dataset versions, trust
  assessments, and readiness decisions with `RESTRICT`.
- C8–C10 connect reliability, statistical, and forecast executions to their
  orchestration request with `RESTRICT`.

All original single-column foreign keys remain. In particular, the C8–C10
single-column foreign keys retain `SET NULL`, while their new composite tenant
foreign keys use `RESTRICT`. The composite constraint prevents deletion while an
analytical execution references the request, so the older `SET NULL` behavior is
intentionally unreachable for those rows.

Seven new `(organization_id, referenced_fk_column)` indexes support C4–C10. The
existing indexes below support C1–C3 and are not duplicated:

- `ix_orchestration_decisions_organization_request`
- `ix_orchestration_steps_organization_request`
- `ix_orchestration_history_organization_request`

## ORM behavior

The existing request/decision, request/step, and request/history relationships
retain their names, `back_populates`, delete-orphan cascade, and passive-delete
configuration. Both sides of each pair now explicitly identify
`orchestration_request_id`, producing six `foreign_keys` declarations. No new
relationships, `primaryjoin`, or `overlaps` configuration is introduced.

## Migration, diagnostics, and rollback

Revision `20260801_0029` follows `20260801_0028`. Online upgrades run
non-mutating diagnostics for missing tenant IDs, orphaned parents, cross-tenant
references, and duplicate `(organization_id, id)` orchestration-request targets.
Violations abort the migration with the affected constraint and count. Offline
SQL generation skips diagnostics.

Upgrade adds the parent unique, ten composite foreign keys, and seven indexes.
Downgrade removes those objects in reverse order. No data migration, repair,
backfill, or fabricated identifier occurs.

## Validation

The local certification suite covers exact metadata cardinality, mapper
configuration, retained single-column foreign keys, `SET NULL`/`RESTRICT`
coexistence, real orchestration-row enforcement, bidirectional ORM navigation,
nullable references, diagnostics, and SQLite upgrade/downgrade/re-upgrade.
PostgreSQL-marked tests add exact catalog inspection, authoritative drift
validation, and bounded concurrent decision and step inserts. PostgreSQL offline
SQL generation is also supported.

## Boundaries

This package does not modify services, APIs, schemas, OIKB, Findings, Operational
Actions, economics, recovery, authorization, observability, asynchronous
processing, or historical migrations. Findings and Actions remain assigned to
TI-C2 or TI-D as approved.
