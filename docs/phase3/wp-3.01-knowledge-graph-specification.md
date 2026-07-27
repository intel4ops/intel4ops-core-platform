# WP-3.01 — Enterprise Operational Knowledge Graph

## Status and baseline

- Document status: **approved architecture — implementation requires merged approval PR**
- Certified Core baseline: merge commit `9f459ed`
- Certified Alembic head: `20260727_0021`
- Proposed next revision after approval: `20260728_0022`
- Runtime: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2,
  PostgreSQL; SQLite remains isolated-test only

## 1. Purpose

WP-3.01 provides a governed semantic graph over existing Intel4Ops operational
records and reusable registry assets. It enables bounded questions such as:

- Which assets, processes, contracts, source records, findings, and signatures
  are connected to this operational outcome?
- What evidence supports each relationship?
- Which interventions addressed similar findings, and what verified outcomes
  followed?
- Which path led from a source observation through Trust, analytical execution,
  signature, finding, action, recovery measurement, and verified value?

The Knowledge Graph is a relationship and query layer. It is not a replacement
canonical model, lineage system, finding store, action engine, recovery ledger,
feature registry, signature registry, or model registry.

## 2. Scope

### In scope

- governed entity-type and relationship-type definitions;
- immutable semantic versions and lifecycle history;
- tenant-scoped graph nodes and edges referencing exact Phase 2 records;
- edge evidence, confidence, derivation, validity, and lineage references;
- graph versions and idempotent change/projection records;
- bounded point-in-time traversal and neighborhood queries;
- explainability traces for every returned path;
- integration adapters for Phase 2 registries and operational outcomes;
- authorization, entitlements, metering, audit, monitoring, retention, and
  release certification;
- PostgreSQL performance baselines and an optional future read-projection
  contract.

### Out of scope

- changing a Phase 2 table, lifecycle, API, or registry;
- arbitrary graph query languages;
- automatic ontology generation;
- cross-tenant graph facts or traversal;
- operational memory and intervention-effectiveness learning;
- benchmark aggregation;
- generative or autonomous reasoning;
- graph marketplace publication;
- a mandatory external graph database;
- ingestion of raw customer payloads into graph properties.

## 3. Architectural decisions

### AD-3.01-01 — PostgreSQL is the system of record

Initial graph persistence uses normalized PostgreSQL adjacency tables. Bounded
recursive CTEs support certified traversals. This minimizes operational
complexity, preserves transactional consistency and Alembic governance, and
allows tenant filters in every query.

A specialized graph engine may later receive a read-only projection. It cannot
become authoritative, accept writes, or bypass PostgreSQL authorization. Its
introduction requires measured evidence that approved query budgets cannot be
met with PostgreSQL.

### AD-3.01-02 — Graph nodes reference authoritative objects

A graph node stores a typed reference and bounded display metadata, never a copy
of the full authoritative object. The reference includes source registry,
object ID, exact version ID when one exists, stable code when useful, and a
content fingerprint. Services validate references before activation.

### AD-3.01-03 — Knowledge Graph and lineage remain distinct

- lineage expresses provenance and transformation of data and analytical
  artifacts;
- the Knowledge Graph expresses governed semantic operational relationships.

Edges may reference `lineage_nodes`, finding evidence bundles, signature
execution evidence, action evidence, and recovery evidence. A lineage edge is
not copied into the Knowledge Graph unless an approved semantic relationship
is derived from it, with the lineage reference retained as evidence.

### AD-3.01-04 — No cross-tenant edge

Every materialized node and edge is organization-scoped. Both edge endpoints
must have the same `organization_id` as the edge. Shared type definitions and
registry schemas contain no tenant facts. Cross-customer patterns are deferred
to privacy-preserving benchmark and reasoning work packages.

### AD-3.01-05 — Traversal is governed and bounded

Clients select an approved traversal operation, relationship allowlist,
direction, point in time, and budget. The service rejects arbitrary query text,
unbounded depth, unrestricted fan-out, and inaccessible evidence.

## 4. Domain model

### Shared definitions

| Proposed table | Purpose | Key constraints |
| --- | --- | --- |
| `knowledge_graph_entity_types` | Stable entity-type identity | unique code, canonical governance state |
| `knowledge_graph_entity_type_versions` | Immutable schema/reference contract | unique type/version, content hash |
| `knowledge_graph_relationship_types` | Stable relationship identity | unique code, direction and symmetry |
| `knowledge_graph_relationship_type_versions` | Endpoint rules, inverse, evidence and confidence policy | unique relationship/version, content hash |
| `knowledge_graph_governance_events` | Append-only approval/lifecycle history | actor, role, reason, idempotency |

### Tenant graph

| Proposed table | Purpose | Key constraints |
| --- | --- | --- |
| `knowledge_graph_versions` | Tenant graph snapshot/checkpoint identity | organization, monotonic version, lifecycle |
| `knowledge_graph_nodes` | Reference to one governed object in one graph version | organization, entity type version, reference identity |
| `knowledge_graph_edges` | Governed relationship between same-tenant nodes | organization, endpoint/type/version identity |
| `knowledge_graph_edge_evidence` | Bounded evidence/lineage references | organization, edge, source type and fingerprint |
| `knowledge_graph_changes` | Append-only idempotent projection/change record | organization, source event and fingerprint |
| `knowledge_graph_query_runs` | Auditable bounded traversal request and outcome | organization, user/client, budget, status |
| `knowledge_graph_query_steps` | Ordered explanation trace | query run, sequence, node/edge and evidence |
| `knowledge_graph_projection_checkpoints` | Adapter progress without changing source domains | organization, adapter, source cursor |

All tenant tables contain `organization_id`. A composite foreign-key strategy or
service plus database trigger must guarantee an edge cannot connect endpoints
from different organizations. Approval must select one enforcement design; an
application-only check is insufficient.

### Core node fields

- `id: UUID`
- `organization_id: UUID`
- `graph_version_id: UUID`
- `entity_type_version_id: UUID`
- `source_registry: str`
- `source_object_id: UUID`
- `source_version_id: UUID | null`
- `stable_code: str | null`
- `display_label: str | null`
- `reference_fingerprint: str`
- `valid_from`, `valid_to`
- `status`
- bounded `metadata_json`
- `created_at`

The uniqueness key is organization, graph version, entity-type version, source
registry, source object, and source version. `source_registry` is an allowlisted
enumeration, not a free-form table name.

### Core edge fields

- `id: UUID`
- `organization_id: UUID`
- `graph_version_id: UUID`
- `relationship_type_version_id: UUID`
- `from_node_id`, `to_node_id`
- `assertion_kind`: observed, declared, calculated, inferred, reviewed
- `derivation_method`: direct reference to a governed adapter/rule/model version
- `confidence_score` and confidence method/version
- `valid_from`, `valid_to`, `observed_at`
- `status`: proposed, active, disputed, superseded, expired, retired
- `definition_fingerprint`, `content_fingerprint`
- bounded `properties_json`
- `created_by_user_id`, `created_at`

An edge uniqueness key includes organization, graph version, endpoints,
relationship-type version, validity start, and derivation identity. Parallel
edges are permitted only when their governed derivation or temporal scope
differs.

### Evidence fields

Evidence rows store an allowlisted source type and exact source identifier:

- lineage node;
- finding evidence bundle/item;
- signature execution/evidence;
- analytical execution/evidence;
- Trust assessment/evidence;
- action evidence/outcome;
- recovery evidence, measurement, finance verification, or ledger entry;
- certified scenario/oracle result.

Every reference is checked against `organization_id`. Shared certification
evidence must be explicitly classified shared and cannot contain tenant data.
Evidence records include integrity fingerprint, relevance, observed time, and
bounded metadata; they do not embed source payloads.

## 5. Initial semantic vocabulary

### Entity types

The initial library maps to existing records:

- organization context (never another tenant);
- source system, ingestion batch, dataset and dataset version;
- canonical entity and operational event;
- Trust assessment and readiness decision;
- feature version and feature observation;
- OIKB/rule/model definition and analytical execution;
- signature version and signature execution;
- finding and evidence bundle;
- recommendation, operational action and action outcome;
- recovery opportunity, case, execution and measurement;
- finance verification and verified-value ledger entry;
- industry-pack version and tenant assignment.

Shared definitions are graph types; tenant graph nodes represent only references
the tenant is authorized to access.

### Relationship types

Initial relationships include:

- `originated_from`, `derived_from`, `validated_by`, `supported_by`;
- `describes`, `affects`, `occurred_on`, `participates_in`;
- `detected_by`, `produced_finding`, `explained_by`;
- `recommended`, `addressed_by`, `executed_as`;
- `resulted_in`, `measured_by`, `verified_by`, `posted_as`;
- `uses_feature`, `uses_rule`, `uses_model`, `uses_signature`;
- `belongs_to_process`, `governed_by_pack`, `supersedes`;
- `correlated_with` only when explicitly labeled non-causal.

Relationship definitions state allowed endpoint types, inverse relationship,
directionality, temporal semantics, required evidence, confidence policy,
expiry/revalidation, and whether human approval is required. `caused_by` is not
an initial relationship type.

## 6. Graph versioning and temporal behavior

- Type definitions use immutable semantic versions.
- Tenant graphs use monotonic integer versions/checkpoints.
- Nodes and edges have business validity intervals separate from record time.
- Corrections append a superseding edge/change; they do not rewrite historical
  query evidence.
- Point-in-time traversal filters graph version and validity consistently.
- A published graph version is immutable. Projection builds a new version, then
  atomically activates it after validation.
- Query runs retain the exact graph version, type versions, policies, budgets,
  and evidence visible at execution time.

WP-3.01 is not a full bitemporal database. Record timestamps plus business
validity and immutable graph versions provide the required initial temporal
contract.

## 7. Integration contracts

| Phase 2 capability | WP-3.01 integration |
| --- | --- |
| Canonical model | Node reference types and approved semantic mappings |
| Sources/datasets | Origin and context nodes; no source payload copying |
| Lineage | Evidence and derivation references |
| Trust/readiness | Edge activation policy and explainability citation |
| Feature registry | Exact feature-version dependency references |
| OIKB/rules/models | Exact definition/method/version derivation |
| Signatures | Signature-version/execution nodes and evidence |
| Findings | Finding nodes, affected-entity edges and evidence bundles |
| Actions | Intervention nodes, dependencies and outcomes |
| Recovery/verified value | Outcome and value nodes; append-only ledger references |
| Industry packs | Applicability and semantic component bindings |
| Commercial engine | Entitlement, limits, usage and audit |
| API gateway | Registered clients, request context and stable errors |
| Simulation/certification | Graph scenarios, oracles and mandatory release gate |

Projection adapters read through domain services or stable read contracts. They
must not import route functions or mutate authoritative source records.

## 8. Application services

- `GraphTypeCatalogService`: type/version reads, governance transitions,
  validation and search.
- `GraphProjectionService`: idempotent source-event projection, reference
  validation, checkpoints and graph-version publication.
- `GraphAssertionService`: reviewed/manual assertions with evidence and
  approval policy.
- `GraphQueryService`: tenant-safe neighborhood, path and impact traversals.
- `GraphExplainabilityService`: converts traversal steps into citations,
  confidence, limitations and excluded-path reasons.
- `GraphMonitoringService`: size, freshness, invalid references, orphan nodes,
  fan-out, latency, timeouts and evidence completeness.

FastAPI routes remain thin and call these services.

## 9. API specification

### Shared catalog — platform administration

- `GET /api/v1/enterprise-intelligence/knowledge-graph/entity-types`
- `GET /api/v1/enterprise-intelligence/knowledge-graph/entity-types/{id}/versions`
- `GET /api/v1/enterprise-intelligence/knowledge-graph/relationship-types`
- `GET /api/v1/enterprise-intelligence/knowledge-graph/relationship-types/{id}/versions`
- `POST /api/v1/enterprise-intelligence/knowledge-graph/types/{id}/transition`

### Tenant graph

- `GET /api/v1/organizations/{organization_id}/knowledge-graph/versions`
- `GET /api/v1/organizations/{organization_id}/knowledge-graph/nodes`
- `GET /api/v1/organizations/{organization_id}/knowledge-graph/nodes/{node_id}`
- `GET /api/v1/organizations/{organization_id}/knowledge-graph/nodes/{node_id}/neighbors`
- `POST /api/v1/organizations/{organization_id}/knowledge-graph/traversals`
- `GET /api/v1/organizations/{organization_id}/knowledge-graph/traversals/{run_id}`
- `GET /api/v1/organizations/{organization_id}/knowledge-graph/traversals/{run_id}/explanation`
- `POST /api/v1/organizations/{organization_id}/knowledge-graph/projections`
- `GET /api/v1/organizations/{organization_id}/knowledge-graph/health`

### Traversal request

A traversal request contains:

- idempotency key;
- start node or governed object reference;
- approved operation: neighborhood, shortest governed path, upstream evidence,
  downstream impact, intervention-to-outcome, or value trace;
- relationship allowlist and direction;
- graph version and point-in-time;
- maximum depth, nodes, edges, paths and execution milliseconds;
- evidence and confidence thresholds;
- include/exclude disputed or expired edges.

Initial hard limits:

- depth: 1–6;
- returned nodes: at most 1,000;
- returned edges: at most 2,500;
- returned paths: at most 100;
- synchronous execution budget: at most 5 seconds.

Lower plan or deployment limits may apply. Larger approved jobs run
asynchronously in a later operational extension; WP-3.01 will not hide an
unbounded query behind a synchronous endpoint.

### Response and explanation

Responses include graph version, nodes, edges, path ordering, truncation,
confidence, evidence references, excluded relationships, warnings, limitations,
request/correlation IDs, and an explanation-run ID. A path without accessible
supporting evidence is not returned as an explained result.

## 10. Authorization and commercial policy

Proposed permissions:

- graph read: viewer, analyst, operations_manager, finance_reviewer, admin;
- traversal: analyst, operations_manager, finance_reviewer, admin;
- projection: operations_manager, admin;
- reviewed assertion: analyst proposer plus operations_manager/admin approver;
- shared type governance: platform administrator.

Proposed commercial keys:

- feature: `intelligence.enterprise_knowledge_graph`;
- meters: `graph_nodes_materialized`, `graph_edges_materialized`,
  `graph_traversals`;
- limits: graph nodes, graph edges, traversal runs, depth, result size and
  retained query evidence.

Authorization precedes entitlement evaluation. Platform administration of shared
types does not grant access to tenant graph facts.

## 11. Query implementation and performance budgets

PostgreSQL queries begin from an organization-scoped node selection and carry
`organization_id` through every recursive term. Relationship type, validity,
status, confidence, and graph version are filtered before expansion.

Required indexes include:

- nodes: organization/type/source identity; organization/graph/status;
- edges: organization/graph/from/type/status and organization/graph/to/type/status;
- evidence: organization/edge/source type;
- changes: organization/adapter/source event and organization/time;
- query runs: organization/request time/status.

Initial certification datasets:

| Profile | Nodes | Edges | Required evidence |
| --- | ---: | ---: | --- |
| Small tenant | 100,000 | 500,000 | complete functional and security suite |
| Medium tenant | 1,000,000 | 5,000,000 | p95 depth-3 neighborhood within 2 seconds |
| Large validation profile | 10,000,000 | 50,000,000 | partition and projection decision evidence |

These are test targets, not production capacity claims. Approval must define
hardware, concurrency and warm/cold-cache conditions. Query plans, row counts,
timeouts and truncation are captured as certification evidence.

## 12. Projection consistency

Projection is incremental, idempotent and replayable:

1. read an authoritative source event or bounded source change;
2. validate organization, object/version, lifecycle and evidence access;
3. compute a deterministic projection fingerprint;
4. return the prior change when the source and fingerprint match;
5. return `409` if an idempotency key/source event is reused with different
   content;
6. create nodes/edges/evidence in one transaction;
7. append the graph change and checkpoint;
8. validate candidate graph version before publication.

Projection failure never rolls back or alters the Phase 2 source record.
Checkpoint advancement is atomic with committed graph changes.

## 13. Migration specification

After approval, one additive migration should:

1. create shared type/version and governance tables;
2. create tenant graph version, node, edge, evidence, change, query and
   checkpoint tables;
3. create named checks, unique constraints, composite tenant indexes and exact
   foreign keys where authoritative relationships permit;
4. seed the bounded initial entity and relationship vocabulary with
   deterministic UUIDs;
5. seed commercial feature/meter definitions and a mandatory non-waivable
   `KNOWLEDGE_GRAPH` certification suite/gate;
6. add no columns to Phase 2 tables unless a later explicit architecture review
   proves a reference cannot be represented from the graph side.

Downgrade removes only WP-3.01 seeds and tables. It must not delete or alter any
Phase 2 object. No graph backfill runs inside Alembic.

## 14. Validation and certification

### Functional

- deterministic type seeds and projection fingerprints;
- node/edge uniqueness and version publication;
- point-in-time traversal and inverse/directional behavior;
- confidence, evidence and expiry filters;
- exact explainability reconstruction;
- idempotent replay and changed-request conflicts.

### Tenant and authorization

- cross-tenant node, endpoint, evidence, traversal and query-run rejection;
- no shared-definition payload contains tenant facts;
- role, registered-client, entitlement, limit and pack enforcement;
- inaccessible evidence is excluded and explained;
- audit records contain no secrets or raw customer payloads.

### Integrity and governance

- invalid endpoint types, missing versions, unapproved relationships and
  evidence-incomplete assertions fail closed;
- active versions are immutable;
- lifecycle transitions are audited and idempotent;
- disputed/superseded/expired edges behave correctly at each point in time.

### Resilience and performance

- transaction rollback, retry, checkpoint replay and partial-projection failure;
- query timeout, fan-out, depth and result-size controls;
- index and recursive-query plans at approved profiles;
- concurrent graph-version publication;
- backup/restore and projection rebuild procedure.

### Migration and release

- Ruff, Mypy and complete Pytest;
- SQLite compatibility only for isolated tests;
- disposable PostgreSQL upgrade from `20260727_0021`, schema inspection,
  downgrade, re-upgrade and repeat-upgrade;
- migration drift and offline SQL;
- graph golden scenarios for Job-to-Cash and servo degradation;
- non-waivable tenancy, security, evidence, migration, performance and
  `KNOWLEDGE_GRAPH` release gates.

## 15. Observability and operations

Metrics:

- nodes/edges/changes by organization and type;
- projection lag, throughput, retry and failure category;
- orphan/invalid reference and evidence completeness counts;
- graph versions awaiting validation/publication;
- traversal latency, expansion, truncation, timeout and denial;
- high-fan-out nodes and relationship distributions;
- entitlement/limit denials and usage events.

Logs use request, correlation, organization, graph version, query run and adapter
identifiers. They exclude evidence payloads, credentials and unrestricted graph
properties. Alerts cover projection stagnation, repeated invalid references,
tenant-scope violations, query-budget abuse and published-version validation
failure.

## 16. Controlled implementation sequence

1. Confirm type vocabulary, registry ownership and same-tenant database
   enforcement decision.
2. Add typed schemas, shared type/version models and governance service.
3. Add tenant graph version, node, edge, evidence and change persistence.
4. Add reference validation and deterministic projection adapters for the two
   golden Phase 2 flows.
5. Add bounded query and explainability services.
6. Add thin APIs, permissions, commercial controls, usage and audit.
7. Add monitoring, retention and projection rebuild operations.
8. Add migration lifecycle, functional, security, performance and certification
   suites.
9. Run the complete SQLite and disposable PostgreSQL gates.
10. Publish documentation, measured performance evidence and rollback plan.

## 17. Definition of Done

WP-3.01 is complete only when:

- no Phase 2 contract or authoritative registry was redesigned;
- all Phase 2 registries named in the Phase 3 charter have validated reference
  adapters;
- every tenant node, edge, evidence row and query is organization-scoped;
- cross-tenant endpoints and evidence are impossible at service and database
  boundaries;
- graph versions and type versions are immutable and governed;
- every returned path has accessible evidence, derivation, confidence and
  limitations;
- bounded traversal meets approved performance budgets;
- projection is idempotent, replayable and rebuildable;
- commercial entitlement, limits, metering and audit pass;
- upgrade/downgrade/re-upgrade and drift checks pass on disposable PostgreSQL;
- security, performance, scalability and `KNOWLEDGE_GRAPH` certification gates
  pass;
- documentation, runbooks, API contracts and known limitations are approved.

## 18. Approved architecture decisions

The eight architecture decisions are resolved in
[`wp-3.01-architecture-approval-record.md`](wp-3.01-architecture-approval-record.md):

1. PostgreSQL is authoritative; any specialized graph engine is a read-only,
   rebuildable projection.
2. The bounded initial entity and relationship vocabulary is approved.
3. `caused_by` is excluded.
4. Composite foreign keys enforce same-tenant, same-graph-version endpoints.
5. The traversal ceilings and three performance profiles are approved.
6. The feature, meter, and limit keys are approved without pricing assumptions.
7. Evidence, query, audit, projection, governance, and legal-hold retention
   defaults are approved.
8. Manual assertion creation is deferred from the first release.

No implementation code or migration should be created until the approval record
and architecture documents are merged into `main`.
