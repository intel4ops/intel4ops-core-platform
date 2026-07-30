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

Disposable PostgreSQL validation completed against PostgreSQL 17.10 using the local database
`intel4ops_wp213a_validation` with `CONFIRM_DISPOSABLE_POSTGRES=1`. No credentials were
printed or committed.

- Full PostgreSQL suite: 13 passed.
- WP-2.13A reliability behavior: passed.
- Authorization, tenant-isolation, orchestration idempotency, and Trust concurrency coverage:
  passed within the PostgreSQL suite.
- Upgrade to `20260728_0023`: passed.
- Downgrade to `20260728_0022`: passed.
- Re-upgrade to `20260728_0023`: passed.
- Alembic drift: none (`No new upgrade operations detected`).
- Offline PostgreSQL SQL generation: passed.

WP-2.13A introduced no migration; the downgrade validates the current repository lifecycle
across the preceding migration boundary.

## Remaining limitations

- Reliability input dataset and lineage references remain caller-asserted until WP-2.06A.
- Composite tenant-safe database foreign keys remain assigned to WP-2.TI.
- Censor-aware Weibull fitting is not implemented.
- Left truncation and interval censoring are not implemented.
- Reliability remains outside automatic progressive orchestration.
- No automatic financial, maintenance, or operational action is authorized.

## WP213A-IR-001 — Exact Governed-Definition Idempotency Binding

Independent recertification reopened reliability idempotency after reproducing a collision
between two distinct governed definitions that shared a permitted content fingerprint. The
previous execution package bound the immutable version fingerprint, method/version, failure
definition, exposure basis, and censoring policy, but it did not bind the stable definition
code, persisted definition ID, semantic version, or persisted version ID.

The execution package now binds both semantic content identity and persisted governed-object
identity:

- stable definition code and persisted definition ID;
- semantic version, persisted version ID, and immutable version fingerprint;
- reliability method code/version;
- failure-definition code/version, exposure basis, and censoring policy.

The tenant-scoped reproducibility fingerprint continues to bind the organization, Trust and
readiness decisions, orchestration request, dataset reference and fingerprint, source-lineage
reference, lifecycle state, asset scope/type, observation window, exposure unit, typed inputs,
execution package, and engine version. Canonical hashes use SHA-256 over UTF-8 JSON with sorted
field names and compact separators. Definition and version identity comes only from
tenant-applicable persisted records resolved by the service.

Before returning a replay, the service verifies the persisted definition ID, version ID, and
execution-package fingerprint against the current trusted definition/version context. A
collision or mismatched persisted identity returns deterministic
`IDEMPOTENCY_CONFLICT` (`409`) and never returns the mismatched execution. The existing
organization-scoped unique reproducibility constraint is handled safely under concurrent
identical requests.

Disposable PostgreSQL concurrency coverage verifies:

- two concurrent identical requests resolve to one correctly bound execution;
- a forced identical system idempotency fingerprint across different definitions yields one
  success and one deterministic conflict without returning the winner to the loser;
- concurrent distinct-definition requests create separate executions retaining their exact
  definition and version identities.

Bounded-remediation validation results:

- Focused Reliability suite: 34 passed.
- Default non-PostgreSQL suite: 333 passed, 14 PostgreSQL tests deselected.
- Full PostgreSQL suite: 14 passed on PostgreSQL 17.10.
- Alembic upgrade to `20260728_0023`, downgrade to `20260728_0022`, and re-upgrade: passed.
- Alembic drift: none.
- Offline PostgreSQL SQL generation: passed.

Reliability does not expose a caller-supplied idempotency-key field; its idempotency key is the
derived tenant-scoped reproducibility fingerprint. Adding a separate caller-key persistence
contract is outside this bounded remediation and would require separate schema authorization.
Dataset and lineage references remain caller-asserted pending WP-2.06A.

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
