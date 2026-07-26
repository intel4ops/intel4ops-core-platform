# Predictive-to-Action Orchestration

WP-2.14 preserves predictions as independently retrievable reliability or forecasting executions.
An operational action references its source; it never rewrites probability, horizon, confidence,
evidence, method, or model result. The action aggregate coordinates a deterministic recommendation,
approval, assignment, plan, dependencies, resources, evidence, execution, verification, value, and
feedback without becoming a CMMS, inventory system, workforce scheduler, or parallel intelligence
orchestration framework.

Routes authorize and delegate. `ActionService` owns tenant-scoped transactions, source validation,
idempotency, persistence, and audit events. `action_engine` owns deterministic transitions,
priority, approval, dependency/resource readiness, realized-value eligibility, and feedback
classification. Existing membership, Findings, Reliability, Forecasting, Trust, Recovery,
orchestration, JSONB, UUID, and evidence conventions are reused.

All action records are organization-owned. Cross-tenant sources, assignments, dependencies, reads,
and writes fail without disclosing record existence. Money uses `NUMERIC(38, 12)` and Python
`Decimal`. External work-order, inventory, permit, document, and reservation identifiers are opaque
references for future Connect adapters.
