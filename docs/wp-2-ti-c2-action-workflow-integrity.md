# WP-2.TI-C2 — Action Workflow Referential Integrity

## Purpose

WP-2.TI-C2 makes the organization boundary database-enforceable across the Action Workflow
domain. Every in-scope child reference must resolve to a parent owned by the same organization:

```text
child.organization_id = parent.organization_id
```

The implementation is additive. Existing columns, nullability, public model attributes,
single-column foreign keys, and application behavior remain unchanged.

## Schema contract

The package adds one parent target:

- `uq_operational_actions_org_id` on
  `operational_actions (organization_id, id)`.

It adds 12 composite tenant foreign keys:

| Child reference | Parent | Delete |
| --- | --- | --- |
| `action_plan_steps.action_id` | `operational_actions` | `CASCADE` |
| `action_dependencies.action_id` | `operational_actions` | `CASCADE` |
| `action_dependencies.prerequisite_action_id` | `operational_actions` | `RESTRICT` |
| `action_resource_requirements.action_id` | `operational_actions` | `CASCADE` |
| `action_events.action_id` | `operational_actions` | `CASCADE` |
| `action_evidence.action_id` | `operational_actions` | `CASCADE` |
| `action_outcomes.action_id` | `operational_actions` | `CASCADE` |
| `action_model_feedback.action_id` | `operational_actions` | `CASCADE` |
| `action_model_feedback.reliability_execution_id` | `reliability_executions` | `RESTRICT` |
| `operational_actions.reliability_execution_id` | `reliability_executions` | `RESTRICT` |
| `operational_actions.forecast_execution_id` | `forecast_executions` | `RESTRICT` |
| `operational_actions.orchestration_request_id` | `intelligence_orchestration_requests` | `RESTRICT` |

The seven `CASCADE` relationships preserve aggregate child lifecycle behavior. The five
`RESTRICT` relationships preserve prerequisite and analytical lineage.

The three optional execution/orchestration references on `operational_actions` remain nullable.
When present, both the identifier and organization must match the parent.

## Indexes

Five indexes are added for newly composite lookup paths:

- `ix_action_dependency_org_prerequisite`
- `ix_action_feedback_org_reliability_execution`
- `ix_action_org_reliability_execution`
- `ix_action_org_forecast_execution`
- `ix_action_org_orchestration_request`

Seven existing indexes are reused without duplication:

- `ix_action_plan_step_org_action`
- `ix_action_dependency_org_action`
- `ix_action_resource_org_action`
- `ix_action_event_org_action`
- `ix_action_evidence_org_action`
- `ix_action_outcome_org_action`
- `ix_action_feedback_org_action`

## ORM compatibility

No SQLAlchemy `relationship()` declarations, joins, back-population behavior, or mapper
navigation were added. The Action Workflow models continue to use mapped scalar attributes.
`configure_mappers()` is part of the certification suite.

The original single-column foreign keys remain in place with their original delete actions.
The composite keys add tenant consistency; they do not rename or replace public fields.
`uq_action_idempotency` is unchanged.

## Migration and diagnostics

Alembic revision `20260802_0030` follows `20260801_0029`.

Before an online upgrade mutates schema, the migration checks every in-scope reference for:

- a missing child organization;
- an orphan parent reference;
- a cross-tenant parent reference; and
- duplicate `(organization_id, id)` operational-action targets.

Violations raise `RuntimeError` with the constraint name and count. The migration performs no
repair, backfill, or identifier fabrication. Offline PostgreSQL SQL generation skips data
diagnostics and emits schema DDL only.

Historical revision `20260725_0014` now contains a static snapshot of the original Action
Workflow schema. It no longer imports application models or constructs tables from mutable
`Base.metadata`. An empty database therefore receives only the original eight tables, original
single-column foreign keys, six original unique constraints, and ten original indexes at that
revision.

Later tenant-integrity objects remain owned by their additive revisions:

- `20260801_0027` introduces TI-B2 reliability and statistical integrity;
- `20260801_0028` introduces TI-B3 forecasting integrity;
- `20260801_0029` introduces TI-C1 orchestration integrity; and
- `20260802_0030` introduces TI-C2 Action Workflow integrity.

The `0030` online object checks remain defensive for databases created before the determinism
remediation. Offline SQL retains the complete one-unique, 12-foreign-key, five-index TI-C2
contract.

## Rollback

Downgrade removes the five new indexes, 12 composite foreign keys, and one parent unique in
reverse dependency order. It does not delete or transform data. Re-upgrade restores the same
objects exactly once. The seven reused indexes and all original single-column foreign keys remain
throughout the round trip.

## Validation

The bounded certification suite verifies:

- exact metadata cardinality and names;
- one occurrence of every new constraint and index;
- absence of equivalent duplicate indexes;
- all original single-column foreign keys and delete actions;
- all 12 same-tenant, cross-tenant, update, and rollback paths through real SQL;
- mapped-attribute ORM commit and rollback behavior;
- nullable analytical lineage;
- dual action/prerequisite references;
- seven `CASCADE` and five `RESTRICT` runtime behaviors;
- diagnostics for cross-tenant, orphan, missing-tenant, and duplicate-parent data;
- the frozen `0014` column, nullability, default, unique, index, and single-FK contract;
- absence of mutable application-model imports from revision `0014`;
- temporal ownership of TI-B2, TI-B3, TI-C1, and TI-C2 schema objects;
- SQLite upgrade, downgrade, and re-upgrade;
- PostgreSQL catalog shape, diagnostics, downgrade/re-upgrade, and bounded concurrent inserts
  when an approved disposable PostgreSQL database is available.

SQLite tests run with foreign-key enforcement enabled. PostgreSQL validation must use
`TEST_POSTGRES_URL` and the repository’s disposable-database confirmation guard; production and
customer databases are excluded.

## Scope boundaries

WP-2.TI-C2 changes only Action Workflow model constraints, migration management, certification
tests, and this documentation. It does not change services, APIs, schemas, authorization,
Findings, OIKB, intelligence engines, Economics, Recovery Ledger, observability, async
processing, or commercial behavior.

TI-D remains outside this package.

This package depends on:

- TI-B2 for reliability execution tenant targets;
- TI-B3 for forecast execution tenant targets; and
- TI-C1 for orchestration request tenant targets.

This document records implementation evidence only. It does not claim independent
certification.
