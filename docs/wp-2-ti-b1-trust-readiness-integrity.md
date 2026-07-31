# WP-2.TI-B1 Trust and Readiness Referential Integrity

## Purpose and invariant

WP-2.TI-B1 adds database-enforced tenant consistency to the Trust and Analytical
Readiness domain. For each covered relationship:

`child.organization_id == parent.organization_id`

This is additive defense in depth. Existing service-level tenant validation remains
unchanged.

## Parent identities

The migration adds these unique `(organization_id, id)` constraints:

- `uq_trust_assessments_org_id`
- `uq_trust_rule_results_org_id`
- `uq_analytical_readiness_decisions_org_id`

The existing TI-A constraints `uq_datasets_org_id` and
`uq_ingestion_batches_org_id` are reused without modification.

## Tenant-aware foreign keys

The following composite foreign keys use `(organization_id, parent_id)`, reference
the parent `(organization_id, id)`, and retain `ON DELETE RESTRICT`:

- `fk_trust_assessments_org_dataset`
- `fk_trust_assessments_org_ingestion_batch`
- `fk_trust_rule_results_org_trust_assessment`
- `fk_trust_evidence_org_rule_result`
- `fk_trust_evidence_org_dataset`
- `fk_readiness_org_trust_assessment`

All historical single-column foreign keys remain present. They continue to enforce
parent existence, while the new composite keys enforce tenant equality.

## Supporting indexes

The migration adds:

- `ix_trust_assessments_org_dataset_id`
- `ix_trust_assessments_org_ingestion_batch_id`
- `ix_trust_rule_results_org_trust_assessment_id`
- `ix_trust_evidence_org_rule_result_id`
- `ix_trust_evidence_org_dataset_id`
- `ix_readiness_org_trust_assessment_id`

Existing single-column indexes remain unchanged. No equivalent composite index
existed before WP-2.TI-B1.

## ORM behavior

No `relationship()` declarations or relationship configuration were added. The
domain continues to expose the same columns, UUID types, defaults, nullability, and
public model attributes. `configure_mappers()` remains valid.

## Migration and diagnostics

Revision `20260731_0026` follows `20260731_0025`. Online upgrade first executes
bounded, read-only diagnostics for all six relationships. The checks reject missing
child tenant identifiers, orphaned parents, cross-tenant references, and duplicate
parent `(organization_id, id)` targets. The nullable
`trust_assessments.ingestion_batch_id` reference is checked only when populated.

Any violation raises `RuntimeError` with the affected constraint and count. The
migration does not repair data, fabricate identifiers, or continue after a failed
precondition. Offline SQL generation skips executable diagnostics.

Upgrade adds three parent constraints, six composite foreign keys, and six indexes.
Downgrade removes those objects in reverse order without deleting data or historical
single-column foreign keys. Upgrade, downgrade to `20260731_0025`, and re-upgrade are
tested on SQLite and disposable PostgreSQL.

## Tested behavior and validation evidence

The focused suite certifies exact metadata set equality and cardinality, mapper
configuration, retained single-column foreign keys, absence of duplicate implicit
indexes, diagnostic failure behavior, same-tenant inserts, cross-tenant raw SQL and
ORM rejection, wrong-tenant update rejection, rollback without partial rows, and
nullable ingestion-batch behavior.

PostgreSQL validation additionally inspects the live schema for all three unique
constraints, six `RESTRICT` composite foreign keys, six indexes, retained
single-column foreign keys, zero diagnostic violations, reversible migration
lifecycle, drift, offline SQL, and bounded concurrent same-tenant inserts. Exact
environment and test counts are recorded in the implementation report rather than
claimed as independent certification here.

SQLite remains an isolated test runtime with foreign-key enforcement enabled.
PostgreSQL 17 is the authoritative managed-runtime validation target.

## Scope and dependencies

WP-2.TI-B1 depends on TI-A because it reuses the composite parent identities on
`datasets` and `ingestion_batches`. It must precede TI-B2 and TI-B3.

WP-2.TI-B1 does not modify services, APIs, schemas, authorization, security,
observability, performance, historical migrations, Reliability, Statistics,
Forecasting, OIKB, orchestration, findings, economics, recovery, knowledge graph,
operational signatures, or asynchronous processing.
