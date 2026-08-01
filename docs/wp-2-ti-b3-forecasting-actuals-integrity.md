# WP-2.TI-B3 Forecasting and Forecast Actual Referential Integrity

## Purpose

WP-2.TI-B3 adds database defense in depth to the existing forecasting schema. Every
eligible tenant-owned child reference now requires the child and parent to have the
same `organization_id`. Existing services, APIs, schemas, algorithms, and
single-column foreign keys remain unchanged.

## Schema contract

The migration adds parent uniqueness on `(organization_id, id)` through:

- `uq_forecast_executions_org_id`
- `uq_forecast_points_org_id`

Seventeen composite foreign keys enforce the tenant invariant across forecast
executions, points, scenarios, revisions, actuals, and accuracy results. Thirteen
use `RESTRICT`; the four execution/point child relationships use `CASCADE`. No
TI-B3 relationship uses `SET NULL`, and existing nullable provenance references
remain nullable.

Fourteen new `(organization_id, referenced_fk_column)` indexes support the new
constraints. The migration reuses:

- `ix_forecast_revision_org_prior`
- `uq_forecast_actual_point`
- `ix_forecast_accuracy_org_execution`

`uq_forecast_actual_point` is a unique constraint whose backing index supports the
forecast-actual-to-point composite foreign key. No equivalent duplicate index is
created.

`ForecastExecution.points` explicitly identifies
`ForecastPoint.forecast_execution_id` as its relationship foreign key. No other
relationships are introduced or altered.

## Migration and diagnostics

Revision `20260801_0028` follows `20260801_0027`. Online upgrades run
non-mutating diagnostics for missing tenant IDs, orphaned parents, cross-tenant
references, and duplicate composite parent targets. A violation aborts the
migration with the affected constraint name and count. Offline SQL generation
skips the data diagnostics.

Upgrade order is parent unique constraints, composite foreign keys, then indexes.
Downgrade reverses that order and returns the schema to `20260801_0027`. No data
repair, backfill, or fabricated identifier is performed.

## Validation

The local suite covers metadata cardinality, mapper configuration, single-column
FK retention, exact delete policies, exclusions, every diagnostic relationship,
orphan and missing-tenant detection, duplicate targets, and SQLite
upgrade/downgrade/re-upgrade. The PostgreSQL-marked suite adds live-object
inspection and authoritative migration drift validation. Offline PostgreSQL SQL
generation is also validated.

SQLite is used for isolated unit and migration regression tests. Authoritative
release validation uses a fresh disposable PostgreSQL 17 database with the
repository safety confirmation enabled.

## Prerequisites and exclusions

TI-A, TI-B1, and TI-B2 are migration prerequisites. This package does not change
forecast candidates, backtests, metrics, execution steps, method registry, OIKB,
orchestration, services, APIs, schemas, authorization, algorithms, replay,
idempotency, or sibling-consistency behavior. TI-C remains a separate work
package.
