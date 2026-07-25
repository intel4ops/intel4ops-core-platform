# WP-2.08 Architecture Assessment

This assessment was completed against synchronized `main` commit
`1779fb6824aa701dfba150faee8fc311e63beb8f` before the WP-2.08 feature
branch was created.

## Current capabilities

WP-2.07 persists a single scalar result per execution together with execution
status, definition code/version/fingerprint, measured unit/currency, exposure,
affected counts, Trust/readiness references, warnings, limitations, and bounded
evidence references. Blocked and failed executions remain auditable.

WP-2.07 does not produce grouped result rows, candidate-finding payloads, severity
recommendations, exposure-calculation traces, calculation traces, or rule traces.
There is no separate result table: the execution row contains the result.

## Existing reusable components

- UUID organization tenancy and membership-based authorization;
- FastAPI thin-route and SQLAlchemy service conventions;
- Decimal execution and PostgreSQL `NUMERIC(38,12)`;
- portable JSON/JSONB;
- source system, ingestion batch, dataset, raw-record, and lineage references;
- completed Trust assessments and analytical-readiness decisions;
- immutable static calculation/rule definition registries;
- deterministic execution fingerprints;
- pagination bounds and safe not-found behavior;
- guarded disposable PostgreSQL and Alembic lifecycle tests.

No industry-pack registry or persisted OIKB definition/version tables currently
exist.

## Missing finding-layer capabilities

The starter `findings` table uses floating exposure fields and a recovery-oriented
lifecycle. The starter `finding_evidence` table permits unrestricted payload JSON.
Neither provides publication eligibility, evidence bundles, immutable traces,
deduplication, human review, lifecycle history, supersession, typed values,
explainability, or bounded tenant-safe filtering.

## Final WP-2.08 specification

WP-2.08 adds an internal governed publication path and tenant APIs for query,
evidence, traces, review, history, and controlled lifecycle commands. It consumes
but never evaluates WP-2.07 calculations or rules.

The result reference is resolved as follows: `source_execution_id` and
`source_result_id` both reference the same successful WP-2.07 execution row and
must be equal. Definition identity is stored as immutable code, version, and
fingerprint because definitions are code-backed rather than database entities.

The initial implementation uses additive governed fields on `findings` plus:

- `finding_evidence_bundles`;
- `finding_evidence_items`;
- `finding_calculation_traces`;
- `finding_rule_traces`;
- `finding_reviews`;
- `finding_status_history`.

Supersession is stored directly on the finding. A general finding-links table is
deferred because no other relationship is required for this work package.

## Scope boundaries

In scope are publication governance, typed measured values/exposure, severity,
confidence, reference evidence, immutable traces, deterministic deduplication,
reviews, lifecycle history, supersession, tenant-safe filtering, migration,
SQLite/PostgreSQL validation, and documentation.

Out of scope are formulas, new rule execution, statistics, forecasting,
prediction, optimization, simulation, recovery, assignment, realized value,
billing, notifications, document storage/upload, AI conclusions, remediation,
dashboards, cross-tenant benchmarking, and raw canonical payload persistence.

The legacy maintenance-analysis and recovery paths remain compatible but are not
converted into governed WP-2.08 publication flows.

## Evidence and publication contracts

Evidence is reference-only. Mandatory publication evidence identifies execution
and result, definition/version, Trust assessment, readiness decision, and dataset.
Leakage additionally requires exposure, affected-record evidence, currency policy,
and warnings or limitations. At least one calculation or rule trace is required.
Metadata is limited to 20 scalar entries. Raw records, source documents, secrets,
and unrestricted nested payloads are prohibited.

Publication requires an active organization, successful tenant-matched execution
with result, active registered definition, completed Trust assessment, ready or
ready-with-warnings decision, tenant-matched dataset/evidence, exact value/unit/
currency/exposure agreement, completed evidence policy, fingerprint, and
deduplication. Blocked and failed executions cannot publish. No public
candidate-publication endpoint exists.

Finalized evidence, traces, reviews, and status history are append-only through
the application model.

## Tenant and authorization rules

Every new table stores `organization_id`; all service lookups, filters,
deduplication, evidence references, review actions, and lifecycle transitions
apply it. Cross-tenant and missing references return non-disclosing errors.

- organization read roles: finding/evidence/trace/review/history reads;
- organization admin, analyst, operator: reviews;
- organization admin: lifecycle exceptions and archival;
- platform service: internal publication.

Industry-pack eligibility cannot yet be enforced because the repository has no
industry-pack registry. Pack code is retained as governed metadata and the
limitation is explicit.

## Migration plan and risks

Revision `20260725_0008` is additive to the starter findings schema and does not
alter WP-2.07 tables. It adds precise numeric fields, JSONB variants, foreign keys,
checks, tenant/status/type/severity/date/definition/execution indexes, and a
tenant-scoped unique deduplication index.

Legacy finding rows remain valid through nullable governed columns. PostgreSQL
receives all new foreign keys and checks. SQLite cannot add foreign keys to an
existing table without rebuilding it, so SQLite migration adds the governed
columns without those new parent references while service-level tenant checks and
new-table foreign keys remain active. PostgreSQL is the authority for production
constraint behavior.

Downgrade removes WP-2.08 tables, indexes, constraints, and additive columns, then
restores the legacy confidence-score type. No data backfill is performed.

## Backward-compatibility and testing risks

- Legacy findings may not validate as governed `FindingRead`; new endpoints query
  only rows with a governed finding code.
- `source_result_id` is an execution reference until a future separate result
  entity exists.
- Trace summaries are supplied by a governed caller because WP-2.07 does not yet
  emit engine traces.
- Evidence immutability is application-enforced; direct database administrators
  remain outside the application threat model.

## Acceptance tests

The test plan covers:

- eligible publication and blocked/failed/cross-tenant rejection;
- immutable definition, result, Trust, readiness, dataset, evidence, and trace;
- measured value/exposure separation, Decimal precision, units, and currencies;
- bounded evidence metadata and no raw payload persistence;
- deterministic duplicate retry and distinct occurrence periods;
- lifecycle, supersession, archival, invalid transitions, and complete history;
- review authorization and tenant isolation;
- paginated deterministic filtering and archived-default behavior;
- SQLite migration upgrade/downgrade/re-upgrade;
- PostgreSQL UUID/JSONB/numeric/index/FK/uniqueness behavior;
- PostgreSQL publication and tenant-safe queries;
- Alembic drift, downgrade, re-upgrade, base lifecycle, and offline SQL.

## Recommended implementation sequence

1. additive models and migration;
2. typed publication/evidence contracts;
3. internal publication and deduplication services;
4. tenant-safe query/evidence services;
5. review and lifecycle services;
6. thin organization-scoped APIs;
7. unit/API/migration/PostgreSQL tests;
8. operational documentation;
9. local gates, draft PR, and GitHub CI.
