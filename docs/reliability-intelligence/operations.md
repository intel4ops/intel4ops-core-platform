# Reliability Operations

Requests are capped at 10,000 summarized observations and execute in deterministic order.
Equivalent immutable inputs reuse the tenant-scoped reproducibility fingerprint. Operators should
monitor failed readiness, invalid lifecycle/exposure, model rejection, review backlog, and evidence
coverage. Alembic is the only managed schema mechanism; validate upgrade, downgrade, re-upgrade,
offline SQL, and drift on SQLite and a disposable PostgreSQL 17 database.
