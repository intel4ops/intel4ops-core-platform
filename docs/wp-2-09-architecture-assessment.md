# WP-2.09 architecture assessment

This assessment was completed against clean merged `main` at
`59d546a1bb3a92155149bc2d596aa6cbbe7d3b48` before the WP-2.09 feature branch
was created.

## Current orchestratable capabilities

WP-2.07 synchronously executes registered calculations and deterministic rules.
It persists one `intelligence_executions` row per attempt with a result embedded
in the execution row. Completed, blocked, and failed states are distinct.
WP-2.08 publishes a governed candidate finding only from an eligible completed
execution and independently validates evidence, Trust, readiness, measurement,
definition identity, and tenant ownership.

## Existing reusable services

- Organization membership and platform-administrator authorization
- Tenant-scoped dataset and dataset-version lookup
- Trust assessments and persisted analytical-readiness decisions
- Static immutable calculation and deterministic-rule registries
- `IntelligenceExecutionService`
- `FindingPublicationService`
- Existing UUID, JSON/JSONB, timestamp, error, route, and test conventions

There is no industry-pack registry, persisted OIKB definition/version model,
service identity, shared engine interface, engine registry, correlation ID, or
method-selection policy.

## Analytical engines and readiness

Only arithmetic and deterministic rules are implemented. Definitions are
code-backed and versioned. Calculation definitions are arithmetic. Rule
definitions have legacy `arithmetic` metadata, but orchestration treats their
method as `rule_based` and uses arithmetic readiness because no separate
rule-based readiness is persisted.

Persisted readiness currently covers `arithmetic`, `statistical`, `predictive`,
`optimization`, and `economic_recovery`. Orchestration exposes the complete
logical vocabulary: arithmetic, rule-based, statistical, forecasting,
predictive, reliability, optimization, simulation, and recovery.

Forecasting, reliability, and simulation have no readiness decision or engine.
Recovery maps to the legacy `economic_recovery` readiness value only for
eligibility inspection. Missing readiness is never fabricated.

## WP-2.07 and WP-2.08 contracts

WP-2.07 accepts bounded canonical records through a typed request but never
persists them. It persists input and definition fingerprints, evidence
references, exact numeric outputs, warnings, limitations, and idempotency.
There is no separate result row; `source_result_id` therefore equals
`source_execution_id`.

WP-2.08 accepts a typed candidate through an internal service. The orchestrator
may populate the candidate's execution/result references only after WP-2.07
returns. Publication failure does not invalidate the analytical result and
produces a partially-completed orchestration.

## Missing components and required persistence

The missing components were governed request, decision, step, status-history,
engine-capability records, deterministic selection/sufficiency/escalation
policies, adapters, correlation, idempotency conflict detection, explainability
queries, and the publication handoff.

Revision `20260725_0009` adds:

- `intelligence_orchestration_requests`
- `intelligence_orchestration_decisions`
- `intelligence_orchestration_steps`
- `intelligence_engine_registrations`
- `intelligence_orchestration_status_history`

Step rows already connect executions, results, and findings; a separate links
table would duplicate those relationships. The migration is additive and does
not backfill or alter WP-2.07/WP-2.08 data. It uses tenant idempotency and
correlation constraints, organization-scoped indexes, UUID foreign keys,
portable JSON/JSONB, bounded strings, reversible downgrade, and explicit
application seed synchronization for real engines.

## Service, API, tenant, and authorization contracts

The service resolves an existing code-backed definition, validates tenant
references, evaluates Trust/readiness, selects an explicit adapter, invokes
WP-2.07, evaluates deterministic sufficiency/escalation, optionally calls
WP-2.08, and finalizes an auditable outcome.

Every request, decision, step, history, dataset, Trust/readiness, execution,
result, and finding read includes `organization_id`. Cross-tenant references
return a generic ineligible/not-found result. Idempotency and correlation are
unique within an organization.

Organization administrators, analysts, and operators can submit governed
requests. Organization readers can view outcomes. Operators and organization
administrators can inspect detailed steps/history. Engine discovery is
platform-administrator-only. No engine-write API, dynamic import, arbitrary SQL,
arbitrary code, or workflow scripting is exposed.

## Backward compatibility and testing risks

Existing execution and finding APIs are unchanged. The orchestration enum is
intentionally separate from the incomplete legacy readiness enum. SQLite cannot
prove PostgreSQL UUID, JSONB, and unique-index behavior, so disposable
PostgreSQL validation covers them explicitly.

The orchestration service depends on the normalized `DefinitionResolver`
protocol. `CodeBackedOIKBDefinitionResolver` is the temporary adapter over the
static WP-2.07 registries and is the replacement boundary for a future
persisted OIKB.

`LEGACY_RULE_TO_ARITHMETIC_V1` makes the temporary rule-readiness bridge
explicit in each affected decision. `AnalyticalOutputReference` similarly
isolates embedded-result compatibility from a future multi-result persistence
model. Engine registration and adapter metadata must match deterministically;
persisted metadata alone never enables execution.

The specification requires `mypy .`; merged main had two pre-existing generic
typing errors in the WP-2.08 migration while CI checked only `app tests`. The
WP-2.09 branch corrects those annotations without changing migration behavior.

Tests cover arithmetic and rules, deterministic engine selection, Trust and
readiness blocks, unsupported advanced paths, arithmetic fallback, execution
references, stable hashes, idempotent retry/conflict, tenant isolation,
publication/partial completion, lifecycle history, filters/pagination,
authorization, migration lifecycle, PostgreSQL constraints, and JSONB.

Implementation order: schemas and enums; persistence and migration; registry
and adapters; policies; orchestration/query services; APIs and authorization;
WP-2.08 handoff; tests and documentation.
