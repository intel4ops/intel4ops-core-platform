# Arithmetic and Rule-Based Intelligence

WP-2.07 adds Intel4Ops' first Progressive Intelligence execution layer. It evaluates
bounded canonical records supplied by an authorized governed caller, applies only
registered arithmetic calculations or deterministic rules, and records reproducible
results linked to the dataset, Trust assessment, arithmetic-readiness decision, and
bounded evidence references.

Submitted records are never persisted. Their deterministic SHA-256 fingerprint is
stored with the definition fingerprint, parameters, result, and lineage references.
Canonical record persistence remains a future mapping concern.

## Safety model

- Calculations convert numeric operands directly to `Decimal`; currency never passes
  through binary floating point.
- PostgreSQL stores results and exposure with `NUMERIC(38, 12)`.
- Null aggregate values are explicitly excluded and counted. An aggregate with no
  usable values fails rather than silently returning zero.
- Division by zero and non-finite or invalid operands produce a structured failed
  execution.
- Currency and exposure currency must match. Currency conversion is not supported.
- Inputs are limited to 1,000 records, 30 parameters, and 200 evidence references.
- Definition lookup uses immutable code/version registrations. There is no `eval`,
  dynamic code loading, caller SQL, or arbitrary expression language.

The shared calculation registry initially contains count, distinct count, sum,
average, minimum, maximum, ratio, percentage, absolute variance, percentage variance,
and reconciliation difference. Representative deterministic rules cover threshold
breaches, unmet thresholds, outside-range checks, and reconciliation mismatches.
Industry packs can register future typed definitions without changing the evaluator.

## Progressive Intelligence

An execution resolves a completed Trust assessment for the same organization and
dataset, then consumes only its `arithmetic` readiness decision:

- `ready` and `ready_with_warnings` execute;
- `blocked` and `insufficient_data` persist an auditable non-execution containing
  blocker codes, warning codes, and explanation;
- statistical, predictive, optimization, and economic-recovery readiness do not
  prevent valid arithmetic.

## API

All routes require organization membership and are scoped by `organization_id`:

```text
POST /api/v1/organizations/{organization_id}/intelligence-executions
GET  /api/v1/organizations/{organization_id}/intelligence-executions
GET  /api/v1/organizations/{organization_id}/intelligence-executions/{execution_id}
GET  /api/v1/organizations/{organization_id}/calculation-definitions
GET  /api/v1/organizations/{organization_id}/rule-definitions
```

Organization administrators, analysts, and operators may execute. All active
organization roles may read definitions and results. Cross-tenant identifiers are
hidden as not found.

## Findings boundary

WP-2.07 does not create or expand operational findings, recommendations, causal
links, or recovery claims. WP-2.08 can consume the stable execution contract:
definition code/version, exact result, unit/currency, breach, affected count,
exposure, Trust/readiness references, warnings, limitations, fingerprints, and
evidence references.

## Validation

Migration `20260724_0007` adds `intelligence_executions` and
`intelligence_execution_evidence`. Validate SQLite normally and use only the guarded
disposable PostgreSQL workflow documented in the README for native UUID, JSONB,
NUMERIC, constraint, upgrade, and downgrade coverage.
