# Shared Trust Engine Foundation

WP-2.06 implements Intel4Ops' industry-neutral Trust layer. It evaluates bounded
record samples for completeness, validity, consistency, uniqueness, timeliness,
lineage, and referential integrity. It persists assessment summaries, rule results,
sampled evidence, and readiness decisions without persisting the submitted record
sample.

The Trust Engine does not claim statistical significance. It supplies deterministic
data-readiness facts that Progressive Intelligence uses to decide which analytical
methods are supportable.

## Rule interface and registry

Every rule declares a stable code/version, name, dimension, severity, description,
supported dataset types, required configuration, applicability, thresholds,
execution, and remediation guidance. `TrustRuleRegistry` keys registrations by
code/version, rejects conflicting duplicates, and returns only configured applicable
rules.

Future industry packs register additional implementations through the registry.
Shared routes never select Mobility, Ports, Manufacturing, Job-to-Cash, Mining, or
Energy behavior.

The initial shared rules are:

1. required-field completeness;
2. primary-identifier uniqueness;
3. referential integrity;
4. date/timestamp validity;
5. numeric-range validity;
6. currency-code validity;
7. record freshness;
8. lineage completeness;
9. duplicate business-event detection;
10. schema conformance.

Each request provides generic configuration for the rules it wants to run. Assessment
input is capped at 1,000 records and 50 rule configurations. Evidence is deterministically
sampled to 25 rows per rule and capped at 500 rows per assessment.

## Scoring

Rule score is `100 - affected percentage`, bounded to 0–100. Rules compare the
affected percentage with an inspectable threshold to produce passed, warning, or
failed status. Skipped and not-applicable results do not contribute to scores.

Dimension scores are arithmetic means of executed applicable rule scores. Overall
score is a normalized weighted mean over only assessed dimensions:

| Dimension | Weight |
| --- | ---: |
| completeness | 20% |
| validity | 20% |
| consistency | 15% |
| uniqueness | 15% |
| timeliness | 10% |
| lineage | 15% |
| referential integrity | 5% |

Normalization prevents absent dimensions from counting as perfect. A high average
never overrides a failed critical rule.

## Progressive analytical readiness

Five decisions are persisted for every assessment:

- arithmetic: minimum 1 row and completeness/validity at 60;
- statistical: minimum 30 rows and completeness/consistency at 70;
- predictive: minimum 100 rows and completeness/validity/lineage at 80;
- optimization: minimum 20 rows and completeness/validity/consistency at 80;
- economic recovery: minimum 1 row and completeness/validity/lineage at 85.

Critical failures always produce `blocked`. Without a critical failure, inadequate
sample size produces `insufficient_data`, which is distinct from bad data. Missing or
low required dimensions produce `blocked`; otherwise the decision is `ready` or
`ready_with_warnings`. This lets valid arithmetic continue while more demanding
methods remain gated.

## API

All endpoints are organization-scoped:

```text
POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/trust-assessments
GET  /api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}
GET  /api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}/rules
GET  /api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}/evidence
GET  /api/v1/organizations/{organization_id}/trust-assessments/{assessment_id}/readiness
GET  /api/v1/organizations/{organization_id}/datasets/{dataset_id}/latest-trust-assessment
```

Evidence pagination defaults to 100 and caps at 200. Organization administrators,
analysts, and operators may execute assessments. All active organization roles may
read results. Platform administrators follow the existing bypass policy. Cross-tenant
identifiers return not found and never disclose ownership.

Example configuration:

```json
{
  "records": [{"id": "1", "amount": 25, "currency": "USD"}],
  "rule_configurations": {
    "required_field_completeness": {
      "required_fields": ["id", "amount", "currency"],
      "identifier_field": "id"
    },
    "numeric_range_validity": {
      "numeric_ranges": {"amount": {"minimum": 0}}
    }
  }
}
```

## Persistence and migration

Migration `20260724_0006` adds `trust_assessments`, `trust_rule_results`,
`trust_evidence`, and `analytical_readiness_decisions`. PostgreSQL uses UUID and JSONB;
SQLite uses its portable JSON variant for isolated tests. Alembic owns managed schema
creation and downgrade.

Assessment creation accepts an optional caller idempotency key scoped to the
organization. An identical replay returns the existing assessment without
duplicating rule results, evidence, or readiness decisions. Reuse for a
different request returns HTTP 409. Callers omitting a key retain prior
behavior.

## Limitations

Canonical record persistence is not yet present, so the API accepts a bounded sample
from the governed caller. The sample is not stored. Initial readiness thresholds are
shared conservative defaults, not industry policies. There is no asynchronous rule
worker, distribution-shift analysis, statistical significance testing, learned
quality model, or industry-pack discovery mechanism yet.

The bounded sample is explicitly inline/manual input and is not represented as
governed stored-data input. The foundation proposal describes the future
lineage-to-Trust and canonical-mapping design.
