# Findings, Evidence, and Explainability

WP-2.08 converts eligible WP-2.07 execution results into governed operational
findings. It does not execute formulas or rules. Publication is an internal
application-service operation; tenant APIs can query, review, and administer the
lifecycle but cannot manufacture arbitrary findings.

## Domain model

A WP-2.07 execution records an approved calculation or rule run and its scalar
result. Because WP-2.07 has no separate result table, a governed finding stores
`source_execution_id` and `source_result_id` as immutable references to the same
successful execution row. The finding also fixes the definition code, version, and
fingerprint, Trust assessment, arithmetic-readiness decision, dataset, measured
value, optional exposure, severity, confidence, warnings, and limitations.

Governed findings use these lifecycle states:

```text
draft -> published -> under_review -> confirmed -> resolved -> archived
                    \-> dismissed -> archived
                    \-> superseded -> archived
```

Direct transitions are controlled by the lifecycle service and recorded in
`finding_status_history`. Deletion is not a lifecycle operation. A published
finding cannot silently return to draft.

Finding types are KPI, leakage, exception, control failure, reconciliation, risk,
opportunity, and data quality. Severity is bounded to info, low, medium, high, or
critical. Confidence levels are unknown, low, moderate, high, and very high.
Confidence is not described as probability. An optional numeric confidence score
requires methodology code/version, component inputs, interpretation, and
limitations.

## Measured values and exposure

Measured value and exposure are independent `NUMERIC(38,12)` fields. Supported
value identities include count, integer, decimal, percentage, ratio, duration,
distance, volume, mass, energy, currency, boolean, and text category. The current
WP-2.07 source result is numeric, so WP-2.08 publication currently consumes the
numeric subset.

Currency values require one ISO currency and must match the source execution.
No FX or implicit unit conversion is supported. Exposure must equal the immutable
WP-2.07 exposure result; it is not inferred during publication.

## Evidence and explainability

Each published finding receives a finalized versioned evidence bundle. Mandatory
items identify the execution/result, OIKB definition/version, Trust assessment,
readiness decision, and dataset. Additional reference-only items may identify
source systems, ingestion batches, lineage nodes, raw-record references, bounded
canonical record identifiers, governed documents, benchmarks, or human
verification.

Evidence metadata is limited to 20 scalar entries. Raw source records, canonical
payloads, documents, secrets, and unrestricted nested objects are prohibited.
Calculation and rule traces contain bounded reference and parameter summaries,
the immutable output, warnings, and a SHA-256 content hash. They never contain
the submitted WP-2.07 record payload.

Finalized bundles, evidence items, traces, reviews, and status history are
append-only through the application model. New evidence requires a later
supplement/version; WP-2.08 does not expose a supplement-write API.

The finding detail plus explicit evidence, trace, review, and status-history
endpoints reconstruct:

- definition and version;
- execution/result and engine trace;
- data period and dataset;
- Trust and readiness decisions;
- measured result and exposure;
- severity and confidence assignment;
- warnings and limitations;
- evidence, review, and lifecycle history.

## Publication policy

`FindingPublicationService.publish_candidate_finding` is the only WP-2.08
publication entry point. It requires:

- an active organization;
- a completed, tenant-matched WP-2.07 execution with a result;
- `result_id` equal to the WP-2.07 execution identifier;
- an active registered calculation or rule definition;
- completed tenant-matched Trust assessment;
- ready or ready-with-warnings arithmetic decision;
- tenant-matched dataset and evidence references;
- exact measured result, unit, currency, exposure, and exposure currency;
- at least one calculation or rule trace;
- a bounded evidence policy code/version;
- a deterministic content fingerprint and deduplication key.

Blocked and failed executions remain in execution audit APIs and cannot publish.
Leakage findings additionally require exposure, affected records, and at least one
warning or limitation.

## Deduplication

The SHA-256 deduplication identity includes organization, definition code/version,
finding type, dataset reference, occurrence period, affected-record reference set,
and measured-value identity. Mutable narrative fields such as title and summary are
excluded. An exact retry returns the existing finding. A changed occurrence period
creates a distinct finding. Materially changed findings may be linked through
explicit supersession.

## Tenant and authorization boundaries

Every WP-2.08 table stores `organization_id`. Every query and relationship lookup
filters it. Cross-tenant objects return the same not-found or ineligible response
as missing objects.

- Existing organization read roles can query findings, evidence, traces, reviews,
  and history.
- Organization admins, analysts, and operators can submit reviews.
- Organization admins govern exceptional lifecycle commands.
- Platform services publish through the internal service contract.

No ordinary tenant publication endpoint exists.

## API

All endpoints are organization-scoped:

```text
GET  /api/v1/organizations/{organization_id}/findings
GET  /api/v1/organizations/{organization_id}/findings/{finding_id}
GET  /api/v1/organizations/{organization_id}/findings/{finding_id}/evidence
GET  /api/v1/organizations/{organization_id}/findings/{finding_id}/calculation-trace
GET  /api/v1/organizations/{organization_id}/findings/{finding_id}/rule-trace
POST /api/v1/organizations/{organization_id}/findings/{finding_id}/reviews
GET  /api/v1/organizations/{organization_id}/findings/{finding_id}/reviews
GET  /api/v1/organizations/{organization_id}/findings/{finding_id}/status-history
POST /api/v1/organizations/{organization_id}/findings/{finding_id}/{lifecycle-command}
```

The list response is paginated, ordered by detection time descending and UUID, and
supports bounded status, type, severity, domain, process, industry pack,
definition, date, exposure, currency, and review-state filters. Arbitrary sort
expressions are not accepted. Archived findings are excluded by default.

## End-to-end synthetic example

```text
WP-2.07 execution
  SHARED.QUALITY.DIRECT_QUALITY_COST@1.0.0
  measured result: USD 125.50
  exposure result: USD 86,500
    |
Candidate finding
  leakage / high / 14 affected synthetic references
    |
Evidence validation
  execution + definition + Trust + readiness + dataset + affected reference
    |
Finding publication
  immutable evidence bundle + calculation trace + fingerprints
    |
Authorized query
  tenant-scoped summary and explicit explainability endpoints
    |
Human review
  under_review -> confirmed -> resolved, with complete history
```

The example persists no input records.

## Migration and compatibility

Alembic revision `20260725_0008` adds governed columns to the starter `findings`
table and creates evidence-bundle/item, calculation-trace, rule-trace, review, and
status-history tables. It adds tenant/status/type/severity/date/definition/execution
indexes and a tenant-scoped unique deduplication index. PostgreSQL receives native
UUID, JSONB, numeric precision, foreign keys, and checks. SQLite uses compatible
migration behavior and service-level cross-reference enforcement where SQLite
cannot add foreign keys to an existing table.

The starter `finding_evidence` table and maintenance-analysis path remain for
backward compatibility but are not used by governed publication. Recovery tables
are unchanged.

## Limitations and deferred scope

- No database-backed organization/industry-pack registry exists yet, so
  organization-specific pack eligibility is retained as metadata but cannot be
  enforced.
- WP-2.07 produces one scalar result and no native grouped/candidate result or
  engine trace. WP-2.08 therefore accepts bounded trace summaries tied to the
  immutable execution.
- Evidence supplements, general finding links, sensitivity classification,
  notifications, dashboards, document storage, AI conclusions, recovery
  workflows, realized value, formulas, forecasting, prediction, optimization,
  simulation, and autonomous remediation are deferred.
