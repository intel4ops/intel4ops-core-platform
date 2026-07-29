# Phase 1B Migration Certification Record

## Identity

- Revision: `20260728_0023`
- Name: `foundation_hardening`
- Previous revision: `20260728_0022`
- File: `migrations/versions/20260728_0023_foundation_hardening.py`

## Added schema

Columns on `trust_assessments`:

- `idempotency_key VARCHAR(255) NULL`
- `request_fingerprint VARCHAR(64) NULL`

Constraints:

- `ck_organizations_status`: `active`, `inactive`
- `ck_findings_severity`: `info`, `low`, `medium`, `high`, `critical`
- `ck_findings_status`: `draft`, `published`, `under_review`, `confirmed`,
  `dismissed`, `superseded`, `resolved`, `archived`, `open`, `accepted`,
  `in_recovery`, `verified`
- `ck_recovery_actions_status`: `planned`
- `ck_processing_runs_data_anchor`: non-infrastructure run types require an ingestion batch or
  dataset version
- `ck_trust_assessment_idempotency_pair`: key and fingerprint are both null or both non-null
- `uq_trust_assessments_organization_idempotency`: organization-scoped key uniqueness

New indexes: **none**. PostgreSQL implements the unique constraint with its supporting unique
index as normal database behavior, but the migration does not create a separate named index.

## Pre-installation validation

Online upgrades query distinct non-null values for:

- `organizations.status`
- `findings.severity`
- `findings.status`
- `recovery_actions.status`

If any value is outside the allowed set, upgrade raises `RuntimeError` naming the table,
column, and unexpected state. The migration performs no coercion or destructive rewrite.
Offline mode omits data queries because no database is available and emits the DDL only.

## Lifecycle behavior

Upgrade validates existing state values, creates the four foundational state checks, creates
the ProcessingRun anchor check, adds the two nullable Trust columns, creates the idempotency
pair check, and creates the organization/key unique constraint.

Downgrade removes the Trust unique and check constraints, drops both Trust columns, then drops
the ProcessingRun, recovery-action, finding, and organization checks. Operations are symmetric
and use Alembic batch operations for portability.

Re-upgrade from `0022` repeats validation and restores the exact schema. PostgreSQL regression
tests explicitly inspect removal and restoration of the Trust columns and organization check.

## Compatibility and evidence

- PostgreSQL 17.10: upgrade, downgrade, re-upgrade, full lifecycle, drift, constraints,
  concurrency, and offline SQL generation passed.
- SQLite: ORM metadata enforces the checks in isolated tests; Alembic batch operations provide
  supported migration compatibility.
- Drift: `alembic check` reported no new upgrade operations.
- Offline SQL: `alembic upgrade head --sql` completed successfully.
- Primary tests:
  `tests/test_postgres_migrations.py::test_migrations_on_disposable_postgres` and
  `tests/test_foundation_constraints.py`.

## Data-loss and rollback risks

Upgrade does not rewrite or delete data. It can intentionally fail when unexpected historical
states exist, requiring a governed data decision before retry.

Downgrade drops `idempotency_key` and `request_fingerprint`; values in those columns are lost.
Assessment results remain, but post-downgrade retries can no longer be correlated by those
keys. Dropping checks also permits invalid future states. A rollback should therefore be
treated as an operational decision, backed up, and followed by application rollback to code
compatible with revision `0022`.
