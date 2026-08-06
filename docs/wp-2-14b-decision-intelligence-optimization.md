# WP-2.14B — Decision Intelligence and Optimization

WP-2.14B adds the governed recommendation layer between causal intelligence and
operational action. It evaluates fully materialized, tenant-scoped scenarios and
returns explainable solutions. It never autonomously executes work.

## Certified use cases

- Recovery portfolio selection uses `scipy.optimize.milp` and consumes persisted
  Economics values without recalculating expected value or priority.
- Technician/resource assignment uses `scipy.optimize.linear_sum_assignment`.
- Work and maintenance sequencing uses deterministic pure-Python DAG and
  critical-path logic.

Inventory allocation, cash-collection optimization, distributed solving,
multi-solver fallback, and genetic algorithms are not certified by this package.

## Governance

Scenario validation is a hard gate. Missing, stale, conflicting, low-confidence,
Trust-ineligible, temporally inconsistent, or economically incomplete inputs
block execution and persist structured reasons.

Recommendations cannot be converted into `OperationalAction` records without an
immutable approval having decision `approve`. Conversion locks the recommendation
and approval, verifies tenant ownership and recommendation identity, creates the
action idempotently, and preserves the exact approval and selected alternative.

## Outcome learning

`decision_outcome_links` directly binds a recommendation to its converted action
and optional action outcome. The same table supports bounded references to
recovery cases, recovery executions, verified-value ledger entries, and causal
outcome assessments. Services validate every bounded reference by organization.
Verified values are cited by ledger identity and are never copied or redefined.
Missing or conflicting verification remains explicit. No method is recalibrated
automatically.

## Persistence and migration

Migration `20260807_0033` creates exactly 17 decision tables:

- six governed definition/problem tables;
- eleven tenant-owned scenario, execution, solution, recommendation, approval,
  outcome, and audit tables.

Every tenant child uses a composite organization foreign key to its tenant parent.
The nullable recommendation-to-approval constraint is created after both tables
to resolve the circular dependency and is removed first during downgrade.

## Dependency boundary

SciPy is bounded to `>=1.12,<2.0`. Authorized optimization functions are:

- `scipy.optimize.milp`
- `scipy.optimize.linprog`
- `scipy.optimize.linear_sum_assignment`

The pure solver module has no database, authorization, or business-governance
dependency.

## Known limitations

- `fk_decision_recommendations_org_approval` (the circular composite FK described
  above) is created via a dialect-aware SQLite batch-table-recreate versus a
  direct PostgreSQL `ALTER TABLE` inside the Alembic migration, so both dialects
  enforce it when schema is provisioned through `alembic upgrade`. The ORM model
  itself declares this constraint with `.ddl_if(dialect="postgresql")`, because
  plain `Base.metadata.create_all()` (used by the SQLite-backed default test
  fixture) cannot perform Alembic's batch-recreate technique for a circular
  foreign key and would otherwise fail to build the schema on SQLite. The
  practical effect is that the fast, SQLite-backed default test suite does not
  get database-level enforcement of this one constraint; service-layer checks in
  `DecisionApprovalService` independently validate that an approval belongs to
  its recommendation and carries an `approve` decision before conversion, and
  the disposable-PostgreSQL suite exercises the real constraint directly.
- `work_maintenance_sequencing` (`sequence_work`) computes an unconstrained
  critical path over dependencies and deadlines only; it does not model
  workforce/equipment capacity (limiting how many tasks may run concurrently).
  Capacity-constrained scheduling is a materially harder problem (resource-
  constrained project scheduling) and is deferred rather than approximated.
- `DecisionRecommendation.expires_at` and the `superseded`/`expired` lifecycle
  statuses are defined on the model and CHECK-constrained, but no service method
  currently transitions a recommendation into either state — they are reserved
  for a future bounded extension, not yet reachable.

## Validation

Certification must include Ruff, Mypy, full SQLite tests, disposable PostgreSQL
tests, migration upgrade/downgrade/re-upgrade, Alembic drift, offline SQL,
deterministic solver cases, tenant-isolation adversarial cases, approval races,
idempotency, and regression coverage for Economics, Recovery, Actions, causal
intelligence, and tenant-integrity packages.
