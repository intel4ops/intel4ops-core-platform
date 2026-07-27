# WP-3.01 Architecture Approval Record

## Approval

- Decision date: 2026-07-27
- Baseline: Intel4Ops Phase 2 Core Platform at `9f459ed`
- Architecture commit under review: `29baf74`
- Decision: **approved for a separate implementation work package**
- Constraint: approval authorizes implementation of the specification; it does
  not authorize redesign of the certified Phase 2 Core Platform.

## Approved decisions

### 1. Authoritative graph store

**Approved:** PostgreSQL is the authoritative WP-3.01 graph store.

Normalized adjacency tables and bounded recursive CTEs are the initial runtime.
A specialized graph engine may be introduced only as a rebuildable, read-only
projection after measured PostgreSQL performance evidence demonstrates a need.
It cannot accept authoritative writes or bypass Intel4Ops tenancy,
authorization, evidence, commercial, or audit controls.

### 2. Initial entity and relationship vocabulary

**Approved with the bounded vocabulary in the WP-3.01 specification.**

Initial entity types reference existing canonical, source, dataset, lineage,
Trust, feature, OIKB, rule, model, signature, finding, action, recovery,
verified-value, industry-pack, and commercial records. Initial relationship
types are limited to provenance, support, operational context, governed
detection, recommendation, intervention, outcome, measurement, verification,
registry dependency, pack governance, and supersession.

New types require a versioned registry record, endpoint contract, owner,
validation evidence, security classification, lifecycle approval, and release
certification. Customer-specific types remain tenant scoped and cannot silently
become shared vocabulary.

### 3. Causal relationship exclusion

**Approved:** `caused_by` is excluded from WP-3.01.

WP-3.01 may represent `correlated_with` only when it is explicitly non-causal,
time-bounded, evidence-backed, and confidence-labeled. A causal relationship
requires a future governed causal-inference contract, assumptions, validation,
counterfactual limitations, and independent approval. No traversal or
explanation may translate correlation, temporal ordering, or graph proximity
into causation.

### 4. Database-enforced tenant-safe edges

**Approved:** use composite foreign keys.

`knowledge_graph_nodes` exposes a unique key over
`(organization_id, graph_version_id, id)`. Each edge endpoint uses a composite
foreign key from `(organization_id, graph_version_id, from_node_id)` and
`(organization_id, graph_version_id, to_node_id)` to that node key. This
enforces both same-tenant and same-graph-version endpoints in PostgreSQL.

Service-layer validation remains mandatory for clear errors and evidence
authorization, but it is not the only tenant boundary. SQLite isolated tests
must emulate and test the contract; disposable PostgreSQL certification must
prove the database constraints directly.

### 5. Traversal and performance budgets

**Approved as initial hard ceilings:**

- maximum depth: 6;
- maximum returned nodes: 1,000;
- maximum returned edges: 2,500;
- maximum returned paths: 100;
- maximum synchronous execution budget: 5 seconds.

Plans, deployments, or operations may set lower limits. Raising a hard ceiling
requires measured performance evidence, security review, limit-version change,
and release certification.

Approved certification profiles:

- small: 100,000 nodes and 500,000 edges;
- medium: 1,000,000 nodes and 5,000,000 edges, with p95 depth-three
  neighborhood latency at or below two seconds under the approved test
  environment;
- large validation: 10,000,000 nodes and 50,000,000 edges, used to decide
  partition and read-projection requirements rather than to claim production
  capacity.

Every performance report must state hardware, PostgreSQL version, concurrency,
cache state, data distribution, query class, truncation, and timeout behavior.

### 6. Commercial keys

**Approved:**

- feature: `intelligence.enterprise_knowledge_graph`;
- meters:
  - `graph_nodes_materialized`;
  - `graph_edges_materialized`;
  - `graph_traversals`;
- limits:
  - `limits.graph_nodes`;
  - `limits.graph_edges`;
  - `limits.graph_traversals`;
  - `limits.graph_depth`;
  - `limits.graph_result_nodes`;
  - `limits.graph_result_edges`;
  - `limits.graph_result_paths`;
  - `limits.graph_query_evidence_retention_days`.

WP-3.01 may seed definitions but must not invent billing prices or plan
allocations. Pricing and default plan quantities require a separate commercial
approval. Authorization is evaluated before entitlement or limit checks.

### 7. Evidence and query retention

**Approved defaults:**

- graph edge evidence references: retained for the edge validity/lifecycle plus
  seven years, subject to the underlying record’s legal and privacy policy;
- query-run request, result summary, and explanation steps: 90 days;
- security/audit summary for a query run: one year;
- projection changes and checkpoints: two years after supersession;
- type/version governance and release-certification evidence: seven years after
  retirement;
- legal hold: overrides deletion until released.

Evidence references do not preserve a source payload beyond its authorized
retention. When an underlying record must be erased, the graph retains only the
minimum non-identifying tombstone and integrity/audit facts permitted by policy.
Tenant contract, jurisdiction, classification, or incident policy may shorten
or extend these defaults through governed configuration. Retention changes are
audited and cannot silently rewrite issued explanations.

### 8. Manual assertions

**Deferred from the first WP-3.01 release.**

The first release is projection-only: graph assertions are produced by approved,
versioned adapters over governed Phase 2 records. Human review may dispute,
suspend, or approve projected relationships through governance workflows, but
users cannot create free-form semantic edges.

Reviewed manual assertion creation may enter a later WP-3.01 extension after
typed forms, maker-checker approval, evidence requirements, conflict handling,
retention, abuse controls, and certification scenarios are approved.

## Conditions on implementation

Implementation must:

1. start from merged `main` after the architecture PR closes;
2. use a new branch dedicated to WP-3.01 implementation;
3. remain additive after Alembic head `20260727_0021`;
4. make no Phase 2 contract or schema-meaning change;
5. implement composite database tenant constraints and adversarial tests first;
6. deliver the two Phase 2 golden-flow projections before broader vocabulary;
7. pass the complete SQLite, disposable PostgreSQL, migration, security,
   performance, and release-certification gates;
8. report measured performance without converting test profiles into unsupported
   production capacity claims.

## Approval outcome

The architecture is sufficiently bounded and aligned with the Enterprise
Intelligence Network vision. WP-3.01 implementation may begin only after this
approval record and its referenced architecture documents are merged into
`main`.
