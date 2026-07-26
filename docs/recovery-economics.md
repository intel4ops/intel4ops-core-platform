# Recovery economics

WP-2.15 provides the governed economic decision layer between findings and proposed
actions. It calculates expected economics only. It does not create realized or verified
value, a recovery ledger, billing records, or finance verification.

## Deterministic formulas

All monetary and rate calculations use `Decimal` and version `1.0`:

```text
addressable_exposure = gross_exposure * addressability_rate
expected_recoverable_value = addressable_exposure * recoverability_rate
probability_adjusted_value = expected_recoverable_value * success_probability
expected_net_benefit = probability_adjusted_value - recovery_cost
expected_roi = expected_net_benefit / recovery_cost
```

ROI is `null` when recovery cost is zero. Payback is `null` when the benefit period is
unknown or probability-adjusted value is zero. Currencies are never converted or
silently combined.

## Priority

The default model is a transparent weighted score. It persists normalized economics,
net benefit, ROI, payback, urgency, confidence, feasibility, strategic alignment, and
inverse-risk factors together with weights and factor contributions. Dependency or
resource blocks override the numerical category. Low confidence is explicit.

Profiles are shared-core configuration (`default_enterprise`, `cash_recovery`, and
`safety_critical`); they contain no industry-specific detection rules.

## Overlap and portfolio behavior

An organization-scoped economic source key prevents duplicate opportunity creation.
Overlap groups preserve duplicate, partial, mutually exclusive, dependent, parent-child,
and shared-source decisions. Each included member has an allocation percentage; excluded
or superseded members contribute zero. Portfolio summaries apply those allocations and
remain separated by currency.

Rejected, superseded, and cancelled opportunities are excluded from portfolio totals by
default.

## Governance

Opportunities progress through draft, review, qualification, approval, defer, monitor,
reject, supersede, or cancel states. Qualification requires a matching scenario,
calculation, and prioritization. Approval requires an organization administrator and
freezes a versioned baseline containing the economic snapshot and active assumption
versions. Approved records are not mutated in place.

All relationship lookups include `organization_id`. Material decisions record actor,
role, reason, timestamp, idempotency key, scenario, conditions, and baseline version.

## Boundaries

WP-2.16 will consume approved baselines for execution confirmation, realized-value
measurement, evidence-backed verification, finance approval, adjustments, reversals,
and the verified-value ledger. None of those outcomes are claimed by this module.
