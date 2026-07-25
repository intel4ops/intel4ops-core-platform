# OIKB Architecture

The Operational Intelligence Knowledge Base (OIKB) is Intel4Ops' governed analytical
knowledge authority. It stores stable definition identities separately from immutable
versions, declarative expressions, inputs, evidence contracts, sources, validation
history, approvals, relationships, and lifecycle audit entries.

OIKB does not assess data Trust, compute analytical readiness, store raw operational
records, publish findings, or execute arbitrary code. The Trust Engine and readiness
decisions remain independent. WP-2.07 remains the bounded arithmetic/rule executor,
WP-2.08 remains the findings authority, and WP-2.09 remains the coordinator.

The service boundary is:

```text
tenant-safe API -> OIKB services -> SQLAlchemy/Alembic
WP-2.09 -> resolver protocol -> governed OIKB -> legacy fallback
governed package -> bounded WP-2.07 primitive -> WP-2.08 reference
```

Shared, industry, regional, and organization scopes use a non-null specialization key
so database uniqueness remains correct across PostgreSQL null semantics. Organization
definitions always carry an organization foreign key. Shared system definitions have no
tenant owner and require platform administration to mutate.

Advanced knowledge classes and analytical levels are representable, but only arithmetic
and rule-based active versions can be exported in WP-2.10.
