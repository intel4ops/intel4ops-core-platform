# Intel4Ops Core Platform — Phase 2

Executable foundation for Connect, Trust, Intelligence, Command, and Recovery.

WP-2.16 carries approved recovery economics into evidence-backed execution, realized-value
measurement, privileged finance verification, and an append-only verified-value ledger. Expected,
realized, verified, and net verified values remain distinct, and mixed currencies are never
aggregated. See [Recovery execution and verified-value ledger](docs/recovery-ledger.md).

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

Current head revision: `20260726_0015`.

## Exposure, prioritization, and recovery economics

WP-2.15 converts tenant findings and proposed actions into governed recovery
opportunities with Decimal-safe scenarios, versioned assumptions, expected economics,
explainable priority, overlap allocation, currency-separated portfolios, approval
decisions, and immutable baseline versions. Expected economics are not realized or
verified value. See [Recovery economics](docs/recovery-economics.md).

## Predictive-to-action orchestration

WP-2.14 preserves predictive assessments and connects them to governed operational actions,
recommendations, approvals, plans, assignments, dependencies, resource confirmations, execution
evidence, separate completion and verification, expected and realized value, and structured model
feedback. Organization-scoped APIs use
`/api/v1/organizations/{organization_id}/actions`. See
[`docs/predictive-action-orchestration/architecture.md`](docs/predictive-action-orchestration/architecture.md).

## Reliability intelligence

WP-2.13 provides a governed reliability-method registry, explicit lifecycle, exposure and
censoring controls, basic reliability and availability metrics, Kaplan–Meier survival,
bounded two-parameter Weibull analysis, composite risk/health methods, immutable execution
fingerprints, tenant-safe APIs, and evidence-ready explanations. See
[`docs/reliability-intelligence/architecture.md`](docs/reliability-intelligence/architecture.md).

Reliability APIs use
`/api/v1/organizations/{organization_id}/reliability`. Reliability scores are not exact
failure probabilities, and safety-critical or maintenance-policy outputs require human review.

## Forecasting intelligence

WP-2.12 provides tenant-safe governed forecasting with a bounded method registry, explicit
forecast readiness, deterministic preparation, rolling-origin and holdout backtesting, safe
error metrics, empirical intervals, deterministic model selection, scenarios, revisions,
actual-versus-forecast monitoring, and OIKB/orchestrator/evidence integration. See
`docs/forecasting-intelligence/architecture.md`.

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

## Progressive Intelligence

WP-2.09 arithmetic-first method selection, explicit engine adapters,
sufficiency and escalation policy, idempotency, and explainability are
documented in
[`docs/progressive-intelligence-orchestrator.md`](docs/progressive-intelligence-orchestrator.md).

## Statistical intelligence

WP-2.11 adds a bounded, explainable statistical method registry, explicit statistical
readiness enforcement, reproducible baselines, anomaly scoring, false-positive
controls, tenant-safe execution APIs, and OIKB/orchestrator integration. See
[`docs/statistical-intelligence/architecture.md`](docs/statistical-intelligence/architecture.md).
An anomaly is a governed deviation from a baseline and is not a causal, fraud,
misconduct, or safety conclusion.

## Operational Intelligence Knowledge Base

WP-2.10 adds the governed OIKB definition registry, immutable semantic versions,
bounded formula contracts, provenance, validation, approvals, lifecycle audit,
tenant-safe specialization resolution, and execution-package export. See
[`docs/oikb/architecture.md`](docs/oikb/architecture.md).

OIKB APIs use the `/api/v1/oikb` prefix. Private operations require
`organization_id`; shared system knowledge requires platform administration.
The migration installs ten active provisional seed definitions and retains an
explicit code-backed compatibility fallback for definitions not yet governed.
