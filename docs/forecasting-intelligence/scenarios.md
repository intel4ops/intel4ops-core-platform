# Scenarios and reconciliation

BASE points are immutable inputs to LOW, HIGH, STRESS, or CUSTOM scenario projections.
Percentage and additive adjustments create separate points and retain their assumptions.
Scenario creation is tenant-authorized and never overwrites baseline points.

Bounded reconciliation supports `BOTTOM_UP` and `TOP_DOWN_PROPORTIONAL` for explicit
parent-child sets with compatible units and tenant scope. Pre-reconciliation values and the
residual remain visible. Deep optimal hierarchy reconciliation is deferred.
