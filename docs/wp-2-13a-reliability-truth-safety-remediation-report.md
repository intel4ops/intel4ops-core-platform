# WP-2.13A — Reliability Truth and Safety Remediation Report

## Baseline and authorization

- Baseline: `main@79428743b945ba3b7756a1cb471af21585190fcb`
- Branch: `feature/wp-2-13a-reliability-truth-safety`
- Alembic head: `20260728_0023`
- Scope: WP-2.13A only
- Progressive Reliability registration: not authorized and not implemented
- Governed analytical-input work: not authorized and not implemented

## Finding-by-finding remediation

### Censoring capability

Before WP-2.13A, `WEIBULL_TWO_PARAMETER` advertised censoring support but fitted only observed
failures. WP-2.13A declares `supports_censoring=false`, rejects censored observations, preserves
the uncensored probability-plot fit, and reports the limitation in registry metadata and
execution evidence.

`KAPLAN_MEIER` continues to support right-censored observations.

### Discrete count validation

Failure and repair counts no longer use truncating `int(...)` conversion. Engine and Pydantic
boundaries reject fractional, boolean, string, negative, and non-finite count representations.
Integer-valued numeric engine inputs remain deterministic.

### Input validation

The public evaluation contract uses a bounded typed observation schema with forbidden extra
fields, finite bounded numerical fields, strict discrete counts and booleans, and
exposure/downtime consistency. Engine boundaries independently enforce finite values, strict
event flags, integral counts, nonnegative values, and method-specific censoring rules.

### Readiness, authorization, and tenancy

Reliability execution continues to require:

- a tenant-owned completed Trust assessment;
- a tenant-owned readiness decision for the `reliability` analytical level;
- `ready` or `ready_with_warnings` status;
- an active tenant-applicable OIKB definition;
- reliability feature entitlement and authorized organization role at the API boundary.

Cross-tenant resources fail through tenant-scoped service queries. Broader composite
database-enforced tenant relationships remain assigned to WP-2.TI.

### Idempotency and reproducibility

The existing organization-scoped reproducibility contract now includes asset-scope type, Trust,
orchestration request, dataset reference/fingerprint, source-lineage reference, exposure unit,
lifecycle, observation window, readiness, inputs, method package, and engine version.

The API does not expose a caller-provided reliability idempotency key. Canonical caller-key
conflict behavior remains outside this bounded package.

### Human-review safeguards

Every successful persisted reliability execution continues to state:

- `human_review_required=true`;
- `recommended_action_category=HUMAN_REVIEW`;
- exact method name/version and limitations.

Reliability results do not automatically trigger operational actions.

## Capability matrix

| Capability | Before | After |
|---|---|---|
| Kaplan-Meier right censoring | Supported | Supported |
| Weibull uncensored failures | Supported | Supported |
| Weibull censored fitting | Advertised but not modeled | Explicitly unsupported and rejected |
| Fractional failure/repair counts | Silently truncated at engine boundary | Rejected |
| Arbitrary evaluate dictionaries | Accepted | Typed and bounded |
| Reliability orchestrator adapter | Absent despite overstated documentation | Correctly documented as absent/manual |
| Human review | Persisted recommendation | Preserved and explicitly documented |

## Migration summary

No schema migration is required. Runtime registry metadata is code-backed and the
`reliability_method_registry` table is not seeded by the historical migration. Historical
migrations are unchanged.

## Files and symbols changed

- `app/engines/reliability_engine.py`: `_finite`, `_discrete_count`, `_strict_boolean`,
  `BasicReliabilityMethod`, `KaplanMeierMethod`, `WeibullTwoParameterMethod`, and the default
  registry metadata.
- `app/schemas/reliability.py`: strict persisted observation fields and
  `ReliabilityEvaluationObservation`.
- `app/services/reliability_service.py`: typed evaluation serialization and expanded
  reproducibility fingerprint inputs.
- Reliability engine, service, API, and disposable-PostgreSQL behavioral tests.
- Reliability censoring, registry, and orchestrator documentation.

## Validation requirements

- Ruff format and lint
- Mypy
- focused engine, service, and API tests
- full default test suite
- disposable PostgreSQL reliability behavior
- existing PostgreSQL migration lifecycle
- Alembic drift and offline SQL
- diff check, secret scan, and artifact review

Local results:

- Ruff format and lint: passed.
- Mypy (`app` and `tests`): passed.
- Focused tests: 28 passed before the authorization regression was added; final full suite
  includes all 29 focused tests.
- Full default suite: 328 passed, 13 PostgreSQL-only tests skipped.
- Offline PostgreSQL SQL generation: passed.
- Git diff check: passed.

`TEST_POSTGRES_URL` was not configured in the execution process. Disposable PostgreSQL
behavior, migration lifecycle, and drift remain mandatory recertification gates and have not
been claimed as passed.

## Remaining limitations

- Reliability input dataset and lineage references remain caller-asserted until WP-2.06A.
- Composite tenant-safe database foreign keys remain assigned to WP-2.TI.
- Censor-aware Weibull fitting is not implemented.
- Left truncation and interval censoring are not implemented.
- Reliability remains outside automatic progressive orchestration.
- No automatic financial, maintenance, or operational action is authorized.

## Independent recertification instructions

An independent reviewer must inspect the exact final diff and reproduce:

1. metadata/runtime consistency;
2. censored Weibull rejection;
3. uncensored Weibull regression fixtures;
4. Kaplan-Meier right-censoring fixtures;
5. fractional, malformed, contradictory, and non-finite input rejection;
6. readiness-level, blocked-status, tenant, authorization, and exact-replay tests;
7. disposable PostgreSQL behavioral and migration gates;
8. confirmation that no orchestrator registration or unrelated package work was added.

The reviewer must return `CERTIFY / APPROVE` or `REQUEST CHANGES`. Certification does not
authorize push or merge.
