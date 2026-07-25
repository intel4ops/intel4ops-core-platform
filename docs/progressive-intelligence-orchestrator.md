# Progressive Intelligence Orchestrator

WP-2.09 adds the governed decision layer between OIKB/readiness and analytical
execution. It coordinates existing engines; it does not replace Trust,
readiness, OIKB, WP-2.07 execution, or WP-2.08 publication.

## Arithmetic first

The orchestrator selects the lowest sufficient method permitted by the resolved
definition, Trust assessment, readiness decision, engine registry, input
contract, and authorization. Arithmetic remains the default. A requested
advanced method does not bypass an eligible arithmetic definition. When policy
allows an arithmetic fallback, the arithmetic result is preserved and the
unavailable advanced method is reported as a limitation—not as completed
advanced analysis.

Only these adapters are available:

- `ARITHMETIC_ENGINE` — arithmetic definitions through WP-2.07
- `DETERMINISTIC_RULE_ENGINE` — deterministic rules through WP-2.07

Statistical, forecasting, predictive, reliability, optimization, simulation,
and recovery engines are not registered or executable.

## Request, decision, and step model

An orchestration request identifies the tenant, immutable definition
code/version, dataset, Trust assessment, readiness decision, requested level,
correlation ID, and idempotency key. Raw canonical records pass only through the
existing bounded WP-2.07 call and are not persisted. Persisted parameter
summaries contain keys, counts, and fingerprints rather than record payloads.

Decisions record the requested and selected method, engine identity, Trust and
readiness results, alternatives, sufficiency, escalation, reason code, policy
version, and content hash.

Ordered steps record validation, definition resolution, Trust/readiness checks,
engine selection, execution, sufficiency, escalation, optional publication,
and completion. Execution and result IDs point to WP-2.07; because WP-2.07
embeds the result in the execution, those IDs are equal.

## Deterministic policies

Sufficiency values are `sufficient`, `sufficient_with_limitations`,
`insufficient`, and `not_evaluated`. The initial policy considers successful
implemented-engine output sufficient. An arithmetic fallback or execution
warnings produces sufficient-with-limitations. No unrestricted AI judgment is
used.

Escalation values are `not_required`, `eligible`, `not_ready`, `not_supported`,
`not_authorized`, `blocked_by_trust`, `blocked_by_policy`, and `deferred`.
Advanced execution requires an OIKB definition, matching readiness, and an
explicitly registered active adapter. The initial OIKB definitions do not
declare multi-method dependencies, so the orchestrator never invents them.

## Integration and tenant safety

Trust assessments must be completed and belong to the request organization and
dataset. The supplied readiness decision must belong to the same assessment and
cover the requested method. Rule-based execution maps to existing arithmetic
readiness because WP-2.06 has no separate rule readiness level.

The orchestrator depends on a typed normalized definition-resolution interface,
not directly on the existing immutable calculation/rule registries.
`CodeBackedOIKBDefinitionResolver` is the temporary adapter and supplies
knowledge class, analytical/readiness levels, required engine capability,
active/publication state, policy references, evidence policy, scope metadata,
and a definition fingerprint. A persisted OIKB can replace the adapter without
redesigning orchestration.

Deterministic rules use the versioned
`LEGACY_RULE_TO_ARITHMETIC_V1` compatibility policy. Decisions explicitly store
requested level `rule_based`, evaluated readiness level `arithmetic`, mapping
policy code/version, and a limitation warning. Arithmetic readiness blocks the
rule when unsatisfied; no rule readiness row is fabricated. Recovery can inspect
`economic_recovery` only through
`LEGACY_RECOVERY_TO_ECONOMIC_RECOVERY_V1`.

Persisted engine registration is necessary but cannot execute code. Eligibility
also requires an explicit adapter with matching code, version, analytical
level, capability, input/output contract versions, active status, and
availability. No caller-selected module is imported and database values are
never used for dynamic imports.

Adapters construct the existing typed `IntelligenceExecutionCreate` contract
and call `IntelligenceExecutionService`; calculation, rule, block, evidence,
and execution persistence logic is not copied.

When a typed finding candidate is supplied, the orchestrator attaches the
successful execution/result IDs and calls `FindingPublicationService`. WP-2.08
continues to own evidence, deduplication, persistence, review, and lifecycle.
Publication failure yields `partially_completed` without deleting the result.

All tenant data and relationships are queried by `organization_id`. Cross-
tenant references are reported as ineligible without revealing existence.

## Lifecycle, errors, and idempotency

The normal lifecycle is:

`received → validating → deciding → executing → terminal outcome`

Policy blocks, unsupported methods, technical failures, partial completion,
completed-with-limitations, and completion remain distinct. Every transition is
stored in history; terminal states are not silently overwritten.

The tenant-scoped fingerprint covers definition version, dataset,
Trust/readiness, requested level, material parameters, bounded evidence
references, and publication intent. It excludes raw record payloads. An
identical retry returns the existing request. A changed request under the same
key returns `INVALID_IDEMPOTENCY_KEY`.

## APIs

Organization-scoped:

- `POST /api/v1/organizations/{organization_id}/intelligence/orchestrations`
- `GET /api/v1/organizations/{organization_id}/intelligence/orchestrations`
- `GET /api/v1/organizations/{organization_id}/intelligence/orchestrations/{id}`
- `GET .../{id}/decisions`
- `GET .../{id}/steps`
- `GET .../{id}/history`

Platform administrator:

- `GET /api/v1/intelligence/engines`
- `GET /api/v1/intelligence/engines/{engine_code}`

Lists use bounded filters, deterministic ordering, and pagination. Arbitrary
sorting and workflow definitions are not accepted.

## Synthetic end-to-end example

- Definition: `SHARED.QUALITY.DIRECT_QUALITY_COST`
- Requested level: arithmetic
- Trust: completed
- Arithmetic readiness: ready
- Selected engine: Arithmetic Engine
- Synthetic result: USD 125.50
- Sufficiency: sufficient
- Escalation: not required
- Finding: optionally published through WP-2.08 with typed synthetic evidence

## Known limitations and future integration

- OIKB definitions are code-backed; persisted tenant/industry definition
  eligibility does not exist.
- Readiness has no rule-based, forecasting, reliability, or simulation rows.
- WP-2.07 is synchronous and embeds results in execution rows.
- `AnalyticalOutputReference` isolates that compatibility behavior with
  `result_id = execution_id`, locator `embedded_result`, and output index `0`.
  Orchestration and WP-2.08 publication consume the reference rather than
  spreading the ID-equality assumption.
- No distributed jobs, message broker, cancellation worker, or advanced engine
  is included.
- Future engines must implement the typed adapter contract, be explicitly
  registered, declare contract versions, and receive matching OIKB/readiness
  support before becoming available.

## Deferred architecture and replacement boundaries

| Deferred item | Current compatibility behavior | Limitation | Required future work package | Replacement boundary | Expected migration impact |
| --- | --- | --- | --- | --- | --- |
| Persisted OIKB definitions and versions | Code-backed resolver normalizes static registries | No tenant-specific or persisted lifecycle | Future OIKB governance package | Implement `DefinitionResolver`; orchestration remains unchanged | Definition/version/policy tables and orchestration foreign keys |
| Industry-pack registry | Scope metadata is code-backed and informational | Persisted industry eligibility cannot be proven | Industry-pack governance package | Definition resolver eligibility hook | Pack, assignment, and definition-link tables |
| Dedicated rule-based readiness | `LEGACY_RULE_TO_ARITHMETIC_V1` evaluates arithmetic readiness | Rule-specific history and requirements cannot be expressed | Readiness expansion package | Compatibility policy returns direct `rule_based` | Expand readiness constraint and generate rule rows |
| Forecasting readiness | Governed `UNSUPPORTED` unless approved arithmetic fallback applies | No history/horizon eligibility | Forecasting foundation package | Compatibility policy and future adapter | Readiness expansion and history-profile tables |
| Reliability readiness | Governed `UNSUPPORTED` unless approved arithmetic fallback applies | No reliability population/exposure eligibility | Reliability foundation package | Compatibility policy and future adapter | Readiness expansion and reliability profiles |
| Simulation readiness | Governed `UNSUPPORTED` unless approved arithmetic fallback applies | No scenario/distribution eligibility | Simulation foundation package | Compatibility policy and future adapter | Readiness expansion and simulation configuration |
| Service identity | Internal calls retain authenticated user actor | No workload identity or service grant | Platform identity package | Authorization dependency and internal context | Service principals, grants, and actor-type audit fields |
| Multi-result execution | Output reference uses `embedded_result`, index `0` | One scalar result per execution | Advanced-engine result package | Adapters return output references | Result/output table and reference foreign-key transition |

## Quality-gate alignment

Both local validation and `.github/workflows/quality-gate.yml` run:

```text
mypy .
```

The WP-2.08 migration annotation edit changes `Column[object]` to
`Column[Any]` so its existing helper is type-correct under the expanded gate.
It does not change generated SQL or migration behavior.
