# WP-2.TI-B2 Reliability and Statistical Referential Integrity

## Purpose and invariant

WP-2.TI-B2 adds database-enforced tenant consistency to the bounded Reliability and
Statistical execution domains:

`child.organization_id == parent.organization_id`

Existing service validation remains unchanged. Historical single-column foreign keys
continue to enforce parent existence, while the new composite foreign keys enforce
tenant equality.

## Parent identities

The migration adds:

- `uq_reliability_executions_org_id`
- `uq_statistical_executions_org_id`
- `uq_statistical_observations_org_id`

It reuses the existing TI-A and TI-B1 `(organization_id, id)` constraints on
datasets, dataset versions, ingestion batches, source systems, Trust assessments,
and Analytical Readiness decisions.

## Composite foreign keys

The twelve RESTRICT relationships are:

- `fk_reliability_executions_org_dataset`
- `fk_reliability_executions_org_dataset_version`
- `fk_reliability_executions_org_ingestion_batch`
- `fk_reliability_executions_org_source_system`
- `fk_reliability_executions_org_trust_assessment`
- `fk_reliability_executions_org_readiness`
- `fk_statistical_executions_org_dataset`
- `fk_statistical_executions_org_dataset_version`
- `fk_statistical_executions_org_ingestion_batch`
- `fk_statistical_executions_org_source_system`
- `fk_statistical_executions_org_trust_assessment`
- `fk_statistical_executions_org_readiness`

The six CASCADE child relationships are:

- `fk_reliability_metrics_org_execution`
- `fk_reliability_model_results_org_execution`
- `fk_reliability_review_feedback_org_execution`
- `fk_statistical_baselines_org_execution`
- `fk_statistical_observations_org_execution`
- `fk_anomaly_review_feedback_org_observation`

The nullable execution provenance fields—dataset, dataset version, ingestion batch,
and source system—remain nullable. Trust and readiness references remain required.

## Indexes

The thirteen new indexes are:

- `ix_reliability_execution_org_dataset`
- `ix_reliability_execution_org_dataset_version`
- `ix_reliability_execution_org_ingestion_batch`
- `ix_reliability_execution_org_source_system`
- `ix_reliability_execution_org_trust_assessment`
- `ix_reliability_execution_org_readiness`
- `ix_reliability_model_result_org_execution`
- `ix_statistical_execution_org_dataset`
- `ix_statistical_execution_org_dataset_version`
- `ix_statistical_execution_org_ingestion_batch`
- `ix_statistical_execution_org_source_system`
- `ix_statistical_execution_org_trust_assessment`
- `ix_statistical_execution_org_readiness`

These five equivalent indexes are reused unchanged:

- `ix_reliability_metric_org_execution`
- `ix_reliability_review_org_execution`
- `ix_statistical_baseline_org_execution`
- `ix_statistical_observation_org_execution`
- `ix_anomaly_review_org_observation`

All existing single-column indexes remain present, and no equivalent composite index
is duplicated.

## ORM mapping

The existing `ReliabilityExecution.metrics`, `ReliabilityExecution.models`,
`StatisticalExecution.baselines`, and `StatisticalExecution.observations`
collections now declare their child foreign-key columns explicitly. No public
relationship was renamed, and no `primaryjoin` or `overlaps` configuration was
needed. The excluded steps and score-component relationships remain unchanged.

## Migration and diagnostics

Revision `20260801_0027` follows `20260731_0026`. Online upgrade first checks all
eighteen relationships for missing tenant identifiers, orphaned parents, and
cross-tenant references. It also checks the three new composite parent identities
for duplicates.

Any violation raises `RuntimeError` containing the affected constraint and count.
The migration performs no repair, backfill, identifier fabrication, or column
change. Offline SQL generation skips diagnostics.

Upgrade creates three parent unique constraints, eighteen composite foreign keys,
and thirteen indexes. Downgrade removes only those objects in reverse order,
preserving the five reused indexes and all historical single-column foreign keys.

## Validation

The focused suite verifies exact metadata cardinality, mapper configuration, all
eighteen diagnostic relationships, same-tenant and cross-tenant direct SQL,
wrong-tenant updates, rollback without partial rows, ORM collection loading,
nullable provenance, CASCADE behavior, index reuse, exclusions, and SQLite
upgrade/downgrade/re-upgrade.

Disposable PostgreSQL 17 validation inspects live constraints, indexes, nullability,
delete policies, retained single-column foreign keys, diagnostics, lifecycle,
drift, offline SQL, and bounded Reliability and Statistical concurrent inserts.
Exact executed gate counts belong in the implementation report; this document does
not claim independent certification.

## Scope and dependency order

WP-2.TI-B2 depends on TI-A and TI-B1. TI-B3 remains a separate package.

This package does not modify services, APIs, schemas, Forecasting, Forecast Actuals,
OIKB, orchestration references, anomaly suppression, method registries,
authorization, security, observability, asynchronous processing, algorithms,
commercial features, or historical migrations.
