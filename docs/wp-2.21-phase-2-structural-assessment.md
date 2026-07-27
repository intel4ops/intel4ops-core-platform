# WP-2.21 Phase 2 Structural Assessment

## Baseline

- Baseline commit: `e8a8be1e4c3f5dd68d0f3cba978a9e6fdbdcbfeb`
- Baseline Alembic head: `20260727_0020`
- Baseline branch: `main`
- WP-2.21 branch: `feature/wp-2-21-operational-signatures`
- Merged-main GitHub Actions: passed
- Post-WP-2.20 local gate: Ruff, Mypy, 266 SQLite/application tests, 10
  PostgreSQL tests, migration downgrade/re-upgrade, drift, offline SQL, and
  commit-bound release certification passed

## Executive assessment

WP-2.01 through WP-2.20 form a coherent tenant-safe operational-intelligence
platform. The architecture consistently uses FastAPI routes, application services,
SQLAlchemy models, Alembic migrations, UUID identifiers, organization-scoped
operational records, evidence references, deterministic registries, immutable
history where material, and disposable PostgreSQL lifecycle validation.

Phase 2 is not yet complete. WP-2.20 deliberately prepared signature contracts but
did not implement operational signatures. A standalone governed feature registry is
also absent: feature inputs exist inside OIKB, statistical, forecasting, reliability,
pack, and simulation contracts, but there is no reusable versioned feature asset.
Lifecycle vocabulary is intentionally domain-specific in older subsystems and cannot
be destructively rewritten in WP-2.21. The correct consolidation is a common
governance contract for new and future platform assets, adapters for existing
registries, and explicit documentation of legacy lifecycle mappings.

## Work-package assessment

| WP | Capability | Status | Gaps and debt relevant to Phase 2 closure |
|---|---|---|---|
| 2.01 | Organizations and PostgreSQL | Complete | Organization is the effective tenant boundary. No blocking gap. Large-scale tenant placement and sharding belong after Phase 2. |
| 2.02 | Membership and authorization | Complete with deployment dependency | Roles, membership status, permissions, and tenant checks are implemented. Production identity-provider integration intentionally fails closed and remains a deployment integration, not a replacement auth platform. |
| 2.03 | Source-system registry | Complete | Tenant-scoped lifecycle, validation, duplicate handling, and secret rejection exist. Lifecycle names differ from analytical assets and require documented mapping, not schema replacement. |
| 2.04 | Ingestion batches and datasets | Complete | Idempotency, dataset versions, counts, failure, quarantine, and retry exist. Processing is synchronous and will require worker infrastructure for very high volume. |
| 2.05 | Raw storage and lineage | Complete | Immutable references, processing runs, lineage graph, legal hold, retention metadata, and secret-safe validation exist. Physical object-store adapters remain deployment-specific. |
| 2.06 | Trust Engine | Complete | Assessments, rules, evidence, readiness, and pack integration exist. Rule policies are governed but do not need conversion into signatures. |
| 2.07 | Arithmetic intelligence and seed library | Complete | Deterministic definitions and validation exist. Feature inputs are embedded in definitions; reusable feature assets are missing. |
| 2.08 | Findings, evidence, explainability | Complete | Findings retain evidence, confidence, exposure, traces, reviews, lifecycle, and tenant-safe queries. Signature references are missing and must be additive. |
| 2.09 | Progressive Intelligence Orchestrator | Complete | Governed selection, readiness, idempotency, steps, and engine registry exist. A signature execution adapter is missing. |
| 2.10 | OIKB | Complete | Definitions, immutable versions, provenance, requirements, validation, approval, lifecycle, and resolution exist. It remains the formula/rule knowledge authority and must not be duplicated. |
| 2.11 | Statistical intelligence | Complete | Methods, baselines, observations, explainability, suppression, and feedback exist. Method registry lifecycle differs from OIKB but is compatible through a governance adapter. |
| 2.12 | Forecasting | Complete | Backtesting, selection, intervals, revisions, actuals, accuracy, governance, and orchestration exist. Scaling long histories requires partitioning or archival later. |
| 2.13 | Reliability intelligence | Complete | Reliability methods, execution, metrics, results, censoring, reviews, and forecasting integration exist. Initial servo signature can reuse this engine. |
| 2.14 | Predictive-to-action | Complete | Tenant ownership, action lifecycle, evidence, dependencies, resources, outcomes, feedback, and idempotency exist. Signature-to-action recommendation linkage is missing. |
| 2.15 | Exposure and recovery economics | Complete | Expected exposure, scenarios, prioritization, assumptions, decisions, overlap, and baselines exist. Signature economic-impact policy should reference these records. |
| 2.16 | Recovery execution and verified value | Complete | Expected, realized, verified, adjustment, and reversal states are distinct and auditable. Signature performance must learn only from governed outcome links, not infer recovery from findings alone. |
| 2.17 | Commercial platform | Complete | Products, plans, versions, entitlements, limits, usage, assignments, and audits exist. Signature execution and marketplace-ready capabilities need catalog keys and metering bindings. |
| 2.18 | API gateway and Job-to-Cash | Complete | Application clients, stable errors, audit, Command APIs, and full Job-to-Cash path exist. Signature APIs must reuse these transport and authorization patterns. |
| 2.19 | Industry packs | Complete | Versioned packs, components, validation, assignment, entitlement, execution, and governance exist. Signature applicability must bind to exact pack versions without copying pack definitions. |
| 2.20 | Simulation and release certification | Complete for its implemented scope | Scenarios, oracles, validation suites, artifact governance, release candidates, gates, waivers, reports, and CI exist. It intentionally provides only signature-candidate readiness. |

## Structural audit

### Registries

Existing registries are not duplicates: OIKB governs operational definitions;
engine and method registries govern executable analytical methods; the industry-pack
registry governs vertical composition; commercial registries govern entitlements;
release certification governs deployability. WP-2.21 must add:

1. a feature registry for reusable input semantics and computation references;
2. a signature registry for event/feature/condition patterns and outcomes;
3. adapters that expose common governance metadata without copying registry rows.

### Identifiers and versions

Persisted entities use UUIDs. Shared deterministic seeds use namespace UUIDs.
Operational records use generated UUIDs. Version fields vary between integer and
semantic-string forms by domain. WP-2.21 will use semantic versions for feature and
signature assets and retain exact foreign keys in executions and findings. Existing
version formats will not be migrated.

### Lifecycles

OIKB, packs, actions, ingestion, findings, commercial objects, and release
certification have valid domain-specific lifecycles. Replacing them with one database
enum would be destructive and would erase domain meaning. WP-2.21 will establish a
canonical governance-state mapping:

- authoring: `draft`, `hypothesis`, `candidate`;
- review: `under_review`, `observed`, `validated`;
- approved: `approved`;
- executable: `active`, `production`, `published`;
- blocked: `suspended`;
- end-of-life: `deprecated`, `retired`.

New feature assets use the canonical analytical lifecycle. Signatures retain the
required hypothesis-to-retired lifecycle and expose its canonical mapped state.

### APIs

Newer APIs use organization path scope, gateway context, stable errors, pagination,
and thin routes. Some original WP-2.01 endpoints use query-scoped organization IDs and
older error envelopes. They remain backward compatible. WP-2.21 APIs will use
organization path scope for tenant execution/deployment and a platform-governed
catalog namespace for shared assets.

### Metadata and audit

Material operational records consistently retain timestamps and evidence. Tags,
search, documentation, approval, and history are strongest in OIKB and pack
registries but not universal in early operational entities. Requiring versioning and
approval on every transaction would be inappropriate. WP-2.21 standardization applies
to major reusable platform assets, not organizations, ingestion attempts, or ledger
transactions.

## Blocking WP-2.21 gaps

1. No operational feature definition/version registry.
2. No signature definition/version registry.
3. No signature feature, event, condition, evidence, algorithm, rule, model,
   dependency, pack-applicability, or ownership bindings.
4. No signature validation, approval, deployment, execution, result, evidence,
   lineage, monitoring, performance, revalidation, or retirement history.
5. No signature service, engine contract, SDK, API, entitlement, usage meter, finding
   trace, or release-certification suite.
6. No Phase 2 structural audit, enterprise-readiness report, completion report, or
   official v1.0 certification report.

## Non-blocking debt and future compatibility

- Synchronous services are suitable for controlled pilots but require durable
  background workers, queues, backpressure, and workload isolation for billions of
  events.
- PostgreSQL relational indexes support initial scale. Partitioning, archival,
  read replicas, and tenant placement are required before millions of signatures or
  billions of observations.
- Production identity provider, secrets manager, object store, telemetry collector,
  alert routing, backup, restore, and disaster-recovery infrastructure are deployment
  responsibilities and must fail closed until configured.
- Full feature-store materialization, cross-tenant knowledge graphs, privacy-safe
  benchmarks, operational memory, intervention learning, AI reasoning, and marketplace
  publication are Phase 3 and explicitly excluded from WP-2.21.

## Enterprise scale assessment

| Scale | Readiness | Assessment |
|---|---|---|
| 10 customers | Ready for controlled deployment | Current tenant filtering, PostgreSQL, APIs, certification, and audit patterns are sufficient with production integrations. |
| 100 customers | Architecturally ready with operational hardening | Requires monitored background jobs, connection-pool sizing, retention, backup drills, and capacity testing. |
| 1,000 customers / 10,000 organizations | Not certified by Phase 2 evidence | Requires tenant placement, noisy-neighbor controls, partitioning, asynchronous execution, rate limits, and SLO evidence. |
| Millions of findings | Data model compatible, performance unproven | Requires workload tests, partition/index review, archival, and query budgets. |
| Millions of signature executions | Data model target only | Requires partitioning and asynchronous signature execution. |
| Billions of events | Not a Phase 2 operating target | Requires streaming ingestion, tiered storage, distributed processing, and explicit Phase 3/operations architecture. |

## Maturity scores before WP-2.21 implementation

| Dimension | Score | Basis |
|---|---:|---|
| Architecture | 88 | Strong service boundaries and composable subsystems; signature and feature assets missing. |
| Security | 84 | Tenant and authorization tests are strong; production identity and infrastructure integrations remain external. |
| Governance | 86 | OIKB, packs, actions, recovery, and certification are governed; lifecycle vocabulary is fragmented. |
| Testing | 92 | Broad SQLite and PostgreSQL lifecycle coverage plus CI; high-scale and production-failure tests are limited. |
| API consistency | 82 | New APIs are consistent; earliest endpoints retain legacy scope and error patterns. |
| Commercial readiness | 86 | Entitlements, usage, gateway, packs, and verified value exist; signatures need commercial bindings. |
| Operational readiness | 78 | Release certification exists; production SLO, DR, telemetry, and worker infrastructure remain deployment work. |
| Scalability evidence | 65 | Correct relational design but no evidence for 10,000 organizations or billions of events. |

## WP-2.21 implementation decision

WP-2.21 requires one additive migration after `20260727_0020`. It will add a bounded
feature registry and the complete operational-signature platform while referencing
existing OIKB, model/method, finding, evidence, lineage, action, recovery, pack,
commercial, simulation, and certification assets.

It will not create a knowledge graph, operational memory, cross-tenant benchmark,
intervention-learning system, AI reasoning layer, marketplace, streaming platform, or
new identity system.

## Controlled implementation sequence

1. Add canonical platform-asset governance contracts and legacy lifecycle mapping.
2. Add reusable feature definitions and immutable feature versions.
3. Add signature definitions, immutable versions, typed requirements, applicability,
   dependencies, validation, approval, and lifecycle history.
4. Add tenant-scoped deployments, executions, evidence/lineage, results, monitoring,
   performance, and revalidation.
5. Add deterministic signature evaluator/SDK and initial Oilfield leakage and servo
   degradation signatures using WP-2.20 scenarios.
6. Integrate findings, orchestration, actions, outcomes, industry packs,
   entitlements, usage metering, and release certification.
7. Add thin platform and tenant APIs, documentation, Phase 2 reports, migration tests,
   security tests, and final v1.0 certification.

## Key safeguards

- Shared signature and feature definitions contain no tenant data.
- Tenant calibration and execution always require `organization_id`.
- Unapproved, suspended, deprecated, or retired signatures cannot execute.
- Findings retain the exact signature version and evidence used.
- Performance histories retain negative and neutral outcomes.
- Fraud signatures produce governed risk findings, never autonomous allegations.
- Predictive and prescriptive signatures disclose uncertainty and limitations.
- Cross-domain signatures require explicit pack and canonical-object applicability.
- Active versions are immutable and changes require new versions.
- Release certification must reject missing signature validation or tenancy evidence.

## Assessment conclusion

Implementation may begin after this assessment. WP-2.21 should complete the missing
signature and feature foundations and provide honest Phase 2 certification. It must
not claim demonstrated billion-event or 10,000-organization capacity without measured
evidence.
