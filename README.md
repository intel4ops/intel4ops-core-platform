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
- `POST /api/v1/trust/profile`
- `POST /api/v1/intelligence/maintenance/analyze?organization_id={uuid}`
- `GET /api/v1/command/findings?organization_id={uuid}`
- `POST /api/v1/recovery/actions?organization_id={uuid}`

Finding creation, listing, and recovery lookup require an explicit organization UUID.

## Migrations

```bash
alembic upgrade head
alembic downgrade -1
```

Current baseline revision: `20260724_0001`.

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
database (a local Docker container is suitable), set only `TEST_POSTGRES_URL`, and run:

```bash
pytest -m postgres tests/test_postgres_migrations.py
```

The test refuses non-PostgreSQL URLs and refuses a URL equal to `DATABASE_URL`.
The target database must be disposable because the test performs a complete
upgrade/downgrade/re-upgrade round trip. Never set `TEST_POSTGRES_URL` to Mobility
production or any shared environment.

## Required maintenance file columns

```text
asset_id,failure_code,downtime_hours,repair_cost
```
