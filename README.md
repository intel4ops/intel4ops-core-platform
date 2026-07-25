# Intel4Ops Core Platform — Phase 2

Executable foundation for Connect, Trust, Intelligence, Command, and Recovery.

## Local setup

Python 3.12+ and a local or otherwise disposable PostgreSQL instance are required.
Do not use the Mobility production database.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Set `DATABASE_URL` in `.env` to a SQLAlchemy psycopg 3 URL:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Application startup never creates tables. Alembic is the only managed schema
mechanism.

## API

- `GET /api/v1/health`
- `POST /api/v1/organizations`
- `GET /api/v1/organizations`
- `GET /api/v1/organizations/{organization_id}`
- `PATCH /api/v1/organizations/{organization_id}`
- `POST /api/v1/organizations/{organization_id}/deactivate`
- `POST /api/v1/organizations/{organization_id}/members`
- `GET /api/v1/organizations/{organization_id}/members`
- `GET /api/v1/organizations/{organization_id}/members/{membership_id}`
- `PATCH /api/v1/organizations/{organization_id}/members/{membership_id}/role`
- `POST /api/v1/organizations/{organization_id}/members/{membership_id}/activate`
- `POST /api/v1/organizations/{organization_id}/members/{membership_id}/suspend`
- `POST /api/v1/organizations/{organization_id}/members/{membership_id}/revoke`
- `POST /api/v1/organizations/{organization_id}/source-systems`
- `GET /api/v1/organizations/{organization_id}/source-systems`
- `GET /api/v1/organizations/{organization_id}/source-systems/{source_system_id}`
- `PATCH /api/v1/organizations/{organization_id}/source-systems/{source_system_id}`
- `POST /api/v1/organizations/{organization_id}/source-systems/{source_system_id}/pause`
- `POST /api/v1/organizations/{organization_id}/source-systems/{source_system_id}/reactivate`
- `POST /api/v1/organizations/{organization_id}/source-systems/{source_system_id}/decommission`
- `POST /api/v1/organizations/{organization_id}/source-systems/{source_system_id}/connection-success`
- `POST /api/v1/organizations/{organization_id}/source-systems/{source_system_id}/connection-failure`
- `POST /api/v1/organizations/{organization_id}/source-systems/{source_system_id}/health`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches`
- `GET /api/v1/organizations/{organization_id}/ingestion-batches`
- `GET /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/transition`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/retry`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/quarantine`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/release`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/cancel`
- `PATCH /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/counts`
- `POST /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/failure`
- `GET /api/v1/organizations/{organization_id}/ingestion-batches/{batch_id}/dataset-versions`
- `POST /api/v1/organizations/{organization_id}/datasets`
- `GET /api/v1/organizations/{organization_id}/datasets`
- `GET /api/v1/organizations/{organization_id}/datasets/{dataset_id}`
- `PATCH /api/v1/organizations/{organization_id}/datasets/{dataset_id}`
- `POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/activate`
- `POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/pause`
- `POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/deprecate`
- `POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/decommission`
- `POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/versions`
- `GET /api/v1/organizations/{organization_id}/datasets/{dataset_id}/versions`
- `GET /api/v1/organizations/{organization_id}/datasets/{dataset_id}/versions/{version_id}`
- `POST /api/v1/organizations/{organization_id}/datasets/{dataset_id}/versions/{version_id}/transition`
- `PATCH /api/v1/organizations/{organization_id}/datasets/{dataset_id}/versions/{version_id}/counts`
- `POST /api/v1/trust/profile`
- `POST /api/v1/organizations/{organization_id}/intelligence-executions`
- `GET /api/v1/organizations/{organization_id}/intelligence-executions`
- `GET /api/v1/organizations/{organization_id}/intelligence-executions/{execution_id}`
- `GET /api/v1/organizations/{organization_id}/calculation-definitions`
- `GET /api/v1/organizations/{organization_id}/rule-definitions`
- `POST /api/v1/intelligence/maintenance/analyze?organization_id={uuid}`
- `GET /api/v1/command/findings?organization_id={uuid}`
- `POST /api/v1/recovery/actions?organization_id={uuid}`

Organization-scoped endpoints require both an explicit organization UUID and an
authenticated user authorized for that organization. Supplying an `organization_id`
alone never grants access. See [Membership and authorization](docs/authorization.md).
The governed registry and its credential boundary are documented in
[Source systems registry](docs/source-systems.md).
Ingestion governance, lifecycle, idempotency, and reconciliation are documented in
[Ingestion control](docs/ingestion-control.md).
Raw artifact identity, integrity, retention, processing history, and bounded lineage
are documented in [Raw storage and lineage](docs/raw-storage-lineage.md).
Shared data-quality rules, scoring, evidence sampling, and Progressive Intelligence
readiness gates are documented in [Shared Trust Engine](docs/trust-engine.md).
Decimal-safe arithmetic, deterministic rules, readiness enforcement, and execution
evidence are documented in
[Arithmetic and Rule-Based Intelligence](docs/arithmetic-intelligence.md).

## Migrations

```bash
alembic upgrade head
alembic downgrade -1
```

Current head revision: `20260724_0007`.

## Tests and quality checks

The normal test suite uses in-memory SQLite through an explicit dependency override.
SQLite is not a runtime default.

```bash
ruff format .
ruff check .
mypy app tests
pytest
```

### Disposable PostgreSQL migration test

No production credentials are required. Create a separate empty local PostgreSQL
database (a local Docker container is suitable), give it a name containing `test`,
`testing`, `disposable`, or `validation`, and set:

```text
TEST_POSTGRES_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/TEST_DATABASE
CONFIRM_DISPOSABLE_POSTGRES=1
```

The confirmation flag explicitly permits the destructive downgrade portion of the
migration lifecycle. Then run:

```bash
pytest -m postgres tests/test_postgres_migrations.py
```

The test refuses non-PostgreSQL URLs, a URL equal to `DATABASE_URL`, database names
without a disposable safety marker, or a missing confirmation flag. The target database
must be disposable because the test performs a complete upgrade/downgrade/re-upgrade
round trip. Never set `TEST_POSTGRES_URL` to Mobility production or any shared
environment.

## Required maintenance file columns

```text
asset_id,failure_code,downtime_hours,repair_cost
```

## Authentication status

Production authentication intentionally fails closed until a real identity provider is
configured. The test identity dependency used by the test suite is not a production
authentication implementation and must never be enabled in a deployed environment.

## Findings and explainability

WP-2.08 governed findings, immutable evidence, trace, review, lifecycle,
deduplication, and tenant-safe API contracts are documented in
[`docs/findings-evidence-explainability.md`](docs/findings-evidence-explainability.md).
