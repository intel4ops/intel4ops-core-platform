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

The legacy C8–C10 single-column `SET NULL` foreign keys are removed. Each
analytical execution table has one authoritative composite tenant foreign key
using `RESTRICT`. Deleting a referenced orchestration request is rejected and the
execution's `orchestration_request_id` remains unchanged, preserving analytical
lineage. The column itself remains nullable so executions without an
orchestration request remain valid.

Seven new `(organization_id, referenced_fk_column)` indexes support C4–C10. The
existing indexes below support C1–C3 and are not duplicated:

- `ix_orchestration_decisions_organization_request`
- `ix_orchestration_steps_organization_request`
- `ix_orchestration_history_organization_request`

## ORM behavior

The existing request/decision, request/step, and request/history relationships
retain their names, `back_populates`, delete-orphan cascade, and passive-delete
configuration. Both sides of each pair explicitly identify
`orchestration_request_id`, producing six `foreign_keys` declarations. No new
relationships, `primaryjoin`, or `overlaps` configuration is introduced.

## Migration, diagnostics, and rollback

Revision `20260801_0029` follows `20260801_0028`. Online upgrades run
non-mutating diagnostics for missing tenant IDs, orphaned parents, cross-tenant
references, and duplicate `(organization_id, id)` orchestration-request targets.
Violations abort the migration with the affected constraint and count. Offline
SQL generation skips diagnostics.

Upgrade adds the parent unique, removes the three legacy single-column foreign
keys, adds ten composite foreign keys, and adds seven indexes. Downgrade removes
the TI-C1 objects and restores the legacy single-column `SET NULL` foreign keys
required by revision `20260801_0028`. SQLite uses a deterministic naming
convention for reflected legacy constraints. No data migration, repair, backfill,
or fabricated identifier occurs.

## Validation

The local certification suite covers exact metadata cardinality, mapper
configuration, authoritative composite execution foreign keys, runtime delete
restriction, lineage preservation, bidirectional ORM navigation, nullable
references, diagnostics, and SQLite upgrade/downgrade/re-upgrade.
PostgreSQL-marked tests add exact catalog inspection, runtime deletion checks,
authoritative drift validation, and bounded concurrent decision and step inserts.
PostgreSQL offline SQL generation is also supported.

## Boundaries

This package does not modify services, APIs, schemas, OIKB, Findings, Operational
Actions, economics, recovery, authorization, observability, asynchronous
processing, or historical migrations. Findings and Actions remain assigned to
TI-C2 or TI-D as approved.
