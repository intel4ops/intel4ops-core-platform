# WP-3.01 Enterprise Knowledge Graph Operations

## Runtime boundary

PostgreSQL is the authoritative graph store. The graph is a governed projection
of Phase 2 records; it does not replace those records or copy raw customer
payloads. SQLite is supported only for isolated unit and migration tests.

Apply schema revision `20260728_0022` with Alembic. Application startup does not
create graph tables or seed definitions.

## Access and commercial controls

All tenant APIs require a registered application client and active organization
membership. Projection and traversal additionally require the
`intelligence.enterprise_knowledge_graph` entitlement.

Usage is recorded under:

- `graph_nodes_materialized`
- `graph_edges_materialized`
- `graph_traversals`

No pricing or plan allocation is embedded in the platform seed.

## Certified projection

The first adapter is `finding_evidence@1.0.0`. It projects an authoritative
finding and, when present, its same-tenant signature execution. It creates the
governed `produced_finding` edge and cites the finding as evidence. Projection
is idempotent by organization, source event, and request key. Reuse with a
different source fingerprint returns a conflict.

Manual assertions are not accepted in this release.

## Traversal safety

Traversal requests use approved operations and relationship codes. Hard
ceilings are depth 6, 1,000 nodes, 2,500 edges, 100 paths, and 5 seconds.
Organization and graph-version predicates are applied to every expansion.
Results include an immutable query run and ordered explanation steps.

`caused_by` is intentionally absent. `correlated_with` remains explicitly
non-causal.

## Retention

- Edge evidence: source policy plus seven years.
- Query details and explanations: 90 days.
- Query audit summaries: one year.
- Projection checkpoints: two years after supersession.
- Governance and certification evidence: seven years.

Legal hold overrides normal expiry.

## Validation

Run:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy app tests
python -m pytest -p no:cacheprovider
python -m alembic upgrade head --sql
```

For live PostgreSQL, provide only an explicitly disposable
`TEST_POSTGRES_URL`, set `CONFIRM_DISPOSABLE_POSTGRES=1`, and run the repository
PostgreSQL migration suite. Never point these checks at Mobility, a customer
database, or another production database.
