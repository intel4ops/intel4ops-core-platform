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

## Approved OIKB seed library

The governance-approved WP-2.07 seed library registers 13 immutable version `1.0.0`
profiles over the bounded primitives above. `SHARED.QUALITY.DIRECT_QUALITY_COST` is
the first implementation seed, followed by shared scalar variances, shared
reconciliations, and industry balance specializations. Definition-list responses
include canonical fields, evidence contract, unit and currency policies, corrected
v1 scope, and accountable domain-owner role.

Composite preparation remains the caller's governed responsibility: filtering,
matching, grouping, unit normalization, and construction of input totals occur
before the registered primitive executes. The engine does not infer joins, convert
units or currencies, evaluate dates, or perform fuzzy matching.

`MINING.QUALITY.GRADE_VALUE_VARIANCE` and
`PORTS.VESSEL.PORT_CALL_DURATION_DECOMPOSITION` remain deferred and are not
registered in WP-2.07 because they require composite valuation or date arithmetic
outside the approved primitive boundary.

### Work-package terminology

WP-2.07 owns the bounded arithmetic and deterministic-rule runtime, including the
early governance-reviewed "OIKB seed library" represented by immutable code-backed
calculation profiles. That wording did not mean that WP-2.07 introduced the
persisted governed OIKB.

WP-2.10 later introduced the database-backed OIKB authority, versioned governance
records, resolution services, and its own provisional shared-core migration seeds.
Those governed definitions map approved expressions to the existing WP-2.07
primitives; they do not replace or renumber the WP-2.07 executor. References to the
WP-2.07 seed library and the WP-2.10 governed OIKB therefore describe successive,
complementary implementation layers.

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
