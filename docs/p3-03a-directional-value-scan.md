# P3.03A Directional Value Scan

## Customer promise

The Directional Value Scan answers: “Based on the operational data Intel4Ops can safely
analyze, where should management focus first?” It is a synchronous, deterministic projection
of governed platform truth. It does not create new analytical truth or financial assumptions.

No LLM or external AI provider is used by P3.03A.

## Contract and boundaries

A scan is one immutable `directional_value_scans` row containing bounded opportunity, data-gap,
context, Trust/readiness, coverage, and provenance snapshots. It is not a Finding, causal
analysis, Decision Intelligence scenario, Action, Recovery workflow, scheduled scan, or new
economics calculation. It never changes source Findings or their lifecycle.

Only `published` and `confirmed` Findings are customer-visible candidates. Draft,
`under_review`, dismissed, superseded, resolved, and archived Findings are excluded. A maximum
of 1,000 governed candidates is evaluated and no more than 10 opportunities is returned. A
truncated candidate universe makes the scan partial and is disclosed explicitly.

## Truth, Trust, and evidence

Each candidate receives one support state:

- `SUPPORTED`: completed Trust, ready analytical readiness, exact governed dataset provenance,
  and complete finalized evidence.
- `PARTIAL`: authoritative readiness with warnings and otherwise valid governed evidence.
- `UNSUPPORTED`: blocked or insufficient readiness, or mandatory governed inputs are absent.
- `STALE`: a referenced lifecycle, evidence contract, execution, or provenance relationship no
  longer matches the governed input.

Unsupported and stale candidates never enter the opportunity snapshot; they become bounded,
actionable data gaps. Partial candidates retain explicit warnings. If nothing is supportable,
the persisted terminal result is `refused`, not a fabricated success. A completed scan with zero
eligible opportunities is explicitly not a declaration that no problems exist.

Evidence snapshots contain bounded identifiers and fingerprints, never unrestricted raw source
records. Every Finding, Trust assessment, readiness decision, source execution, dataset version,
evidence item/reference, economics object, prioritization, overlap record, and workspace context
record is revalidated against the organization boundary.

## Economics and ranking

The customer-facing truth labels are `OBSERVED_VALUE`, `POTENTIAL_EXPOSURE`,
`EXPECTED_RECOVERY`, and `RECOMMENDATION`. Directional scans do not claim Verified Value.
Realized and Verified Value remain Recovery-domain truth.

Potential exposure is copied only from an existing Finding or authoritative Economic
Calculation. Expected recovery is copied only from authoritative existing Economics with its
calculation and model identities. The scan performs no new formula, probability calculation,
currency conversion, or FX normalization. Conflicting currencies produce a limitation, and
currency summaries remain separate.

Ranking first uses the latest eligible persisted Economics prioritization. Multiple linked
Recovery Opportunities are resolved by persisted priority score, prioritization time, and UUID.
Remaining Findings use existing Finding priority, severity, confidence, detection time, and UUID
as stable deterministic tie-breakers. Rejected, superseded, cancelled, or overlap-excluded
economics are ignored. Customer workspace context never changes numerical ranking in v1.

## Context, gaps, and next investigation

P3.02 industry, objective, challenge, and system codes are optional display context. Missing
context is normal and is not a data gap. Exact codes and the context hash are included in the
input fingerprint.

Data gaps describe only governed limitations that affect business-value analysis, such as
blocked readiness, stale evidence, unavailable governed provenance, absent authoritative
economics, or candidate truncation. Existing Trust remediation guidance is reused when present.

Exactly one deterministic next investigation is stored. A supported scan directs the user to
affected records when such evidence exists, otherwise to the Finding evidence and calculation
trace. A refused scan directs the user to its highest-priority blocking data gap. No AI narrative,
decision scenario, action, or recovery process is generated.

## Lifecycle, reproducibility, and freshness

Scan statuses are `completed`, `partial`, and `refused`. Stored rows reject ordinary ORM update
and delete operations. Historical GET reads the stored snapshot and never rebuilds it from live
mutable records. The response derives `is_current` separately by comparing the stored input
fingerprint with the current governed input fingerprint.

Provenance records the policy/version, actor, context/hash, Findings and fingerprints, source
executions, definitions, governed datasets and versions, Trust/readiness decisions, evidence
bundles and bounded evidence items, economics calculations, prioritization, overlap treatment,
generation time, input fingerprint, and result content hash.

Idempotency and freshness are tenant-scoped:

- same key and same fingerprint returns the existing scan;
- same key and a different fingerprint returns HTTP 409;
- a different key and identical input fingerprint returns the existing scan;
- database uniqueness plus `IntegrityError` recovery makes concurrent creation safe.

There is no arbitrary freshness timeout.

## Security, entitlement, and API

All queries and reads are scoped by `organization_id`. A cross-tenant reference rejects the
entire creation transaction and persists no scan. Platform-admin behavior is unchanged.
Execution requires the existing `intelligence.findings` entitlement and an
`INTELLIGENCE_EXECUTION_ROLES` role. Reading requires the same entitlement and a
`FINDING_READ_ROLES` role. Viewers may read but cannot execute; invited, suspended, revoked, or
missing members can do neither. P3.03A adds no entitlement or usage meter.

The API surface is intentionally limited:

- `POST /api/v1/organizations/{organization_id}/value-scans`
- `GET /api/v1/organizations/{organization_id}/value-scans/{scan_id}`

POST accepts only `idempotency_key`; the server owns policy, limits, ranking, and financial
rules. A successful new or replayed result—including a governed refusal—returns 200.
Authorization/entitlement denial returns 403, a tenant-mismatched or missing scan returns 404,
an idempotency conflict returns 409, and request-schema failure returns 422.

## Frontend contract

The frontend must display stored truth/support labels, warnings, limitations, evidence and
calculation references, separate currencies, the single next investigation, and the `is_current`
indicator without relabeling potential exposure as verified value. It must preserve the explicit
zero-opportunity warning and must not imply enterprise coverage when truncation is disclosed.

## Known limitations and deferred capabilities

P3.03A is synchronous, organization-scoped, deterministic, and limited to current governed
Findings and existing Economics. It does not aggregate multiple sites, schedule scans, execute
predictive or optimization models, infer or confirm context, or provide an AI narrative.

Deferred work includes the P3.03B/C/D AI Operational Profiler and provider abstraction,
Operational Memory and governed learning, broader Connect capabilities, and separately approved
causal, Decision, Action, Recovery, scheduled, predictive, optimization, and multi-site scan
capabilities.
