# Intel4Ops Enterprise Operational Intelligence Platform

Executable foundation for Connect, Trust, Intelligence, Command, and Recovery.

Phase 3 architecture is approved. WP-3.01 implements the initial governed
Enterprise Operational Knowledge Graph while the certified Phase 2 contracts
remain frozen. See the
[Enterprise Intelligence Network blueprint](docs/phase3/enterprise-intelligence-network-architecture.md)
and [WP-3.01 Knowledge Graph specification](docs/phase3/wp-3.01-knowledge-graph-specification.md),
[architecture approval record](docs/phase3/wp-3.01-architecture-approval-record.md), and
[operations guide](docs/phase3/wp-3.01-operations.md).

WP-2.21 completes the governed operational feature and proprietary signature
platform and closes the Phase 2 structural assessment. See
[Operational Signatures](docs/operational-signatures.md),
[Enterprise Readiness](docs/wp-2.21-enterprise-readiness.md), and the
[Phase 2 Certification](docs/wp-2.21-phase-2-certification.md).

WP-2.18 adds a multi-application request context, Executive Command APIs, and the first
deterministic Job-to-Cash vertical slice. See [API gateway](docs/api-gateway.md),
[Executive Command](docs/executive-command.md), and
[Job-to-Cash vertical slice](docs/job-to-cash-vertical-slice.md).

WP-2.17 adds versioned products and plans, subscriptions, contracts, tenant entitlements,
append-only usage metering, limits, feature flags, and governed industry-pack activation.
See [Commercial platform](docs/commercial-platform.md).

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
The tenant-root record and its ratified WP-2.01 contract are documented in
[Organizations Foundation](docs/wp-2-01-organizations-foundation.md).
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

Resolve the current head from the migration graph rather than copying a revision
into operational instructions:

```bash
python -m alembic heads
```

The repository requires exactly one Alembic head.

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

### Pilot auth bridge (temporary, P3.xxA.2)

`app/auth/pilot_bridge.py` adds an optional, environment-gated bearer-token identity used
only as a **one-time, operator-held bootstrap credential** to unblock a pilot deployment
(e.g. SOTRA) before real platform-admin provisioning ships. It is disabled by default and
**cannot activate when `APP_ENV=production`**, regardless of the `PILOT_AUTH_*` settings.
See that module's docstring for the exact activation rules, and `app/core/config.py` for
the four `PILOT_AUTH_*` / `pilot_*` settings. This bridge is temporary and should be
removed once real platform-admin provisioning is implemented; do not build further
features on top of it.

**`PILOT_AUTH_TOKEN` must never reach the browser.** It is a bootstrap/testing credential
for an operator to call the API directly (curl, Postman, an admin script) — never embed it
in a `VITE_*` variable, Lovable/Navigator frontend source, a compiled JavaScript bundle,
`localStorage`, or any other browser-visible configuration. The Navigator frontend must
never hold or send this token. Normal Operator use of Navigator authenticates through the
frontend's own real identity provider and never touches the pilot bridge at all (see the
recommended flow below).

### Recommended pilot security model (bootstrap once, then normal auth only)

The platform already has a self-service organization/membership path that does **not**
require platform-admin for normal operation — the pilot bridge is only needed for the
one-time bootstrap step, and only if no real authenticated identity is available yet to
perform it:

1. **Bootstrap** (operator only, one time): an authenticated identity — either a real
   Navigator/OIDC user if one is already available, or the pilot bridge token used
   directly against the API (never through the browser) — calls
   `POST /api/v1/me/organizations` (`app/api/access_routes.py`) with the SOTRA Pilot
   payload. This creates the organization **and** atomically grants the caller an active
   `organization_admin` membership on it (`create_organization_with_owner` in
   `app/services/access_context_service.py`). No platform-admin role is required or
   granted by this call.
2. **Provision real users** (by that `organization_admin`, via the API): call
   `POST /api/v1/organizations/{organization_id}/invitations` (`app/api/invitation_routes.py`)
   with `{"email": "<operator's real email>", "role": "analyst"}` (or `"operator"` —
   whichever is the minimum role the pilot needs; both satisfy
   `MAINTENANCE_ANALYSIS_ROLES` and `ORGANIZATION_READ_ROLES`). This returns a one-time
   invitation token, delivered out-of-band (never via the pilot bridge or the browser).
3. **Real user accepts, under their own identity**: the invitee, authenticated as
   themselves through Navigator's normal login, calls `POST /api/v1/invitations/accept`
   with `{"token": "..."}`. `invitation_service.accept` binds the resulting
   `OrganizationMembership` to *their own* OIDC-derived `user_id` — never the pilot
   identity's. From this point on that user's normal Navigator session satisfies
   `require_organization_roles(...)` for `POST /intelligence/maintenance/analyze` and
   `GET /command/findings` with no elevated privilege and no pilot token involved.
4. The pilot bridge is not touched again after step 1. It exists purely to get past the
   "no real identity can self-bootstrap yet" chicken-and-egg problem once.

This is the existing, unmodified membership/invitation contract — no new endpoints or
membership behavior were added for this.

### Frontend organization context

Navigator needs to know which `organization_id` to send on org-scoped calls. Two existing
mechanisms already cover this without a new endpoint:

- `GET /api/v1/me` (`CurrentIdentityRead`) returns the caller's active memberships, each
  with its `organization` (id/name/slug/status) and `role`.
- `GET /api/v1/me/context[?organization_id=...]` (`AccessContextRead`) resolves a specific
  membership's state (`active`, `no_membership`, `multiple_organizations`,
  `suspended_organization`, `revoked_membership`, `pending_invitation`) plus
  `permitted_actions` and `entitlement_summary` — the richer "am I set up correctly here"
  check a frontend would want after login.

For a single-tenant pilot with exactly one organization, an environment-configured
`organization_id` (a non-secret UUID) in Navigator is an acceptable short-term
simplification once step 1 above has run and the id is known — but `GET /api/v1/me` is
the durable, self-describing mechanism and should be preferred as soon as it's practical,
since it needs no redeploy if the organization or a user's membership changes.

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

## Governed industry packs

WP-2.19 adds semantic-versioned, entitlement-controlled manifests for Job-to-Cash,
Manufacturing, Ports and Terminals, and Mobility and Public Transport. Packs extend
the shared Trust, OIKB, findings, economics, recovery, command, and commercial
contracts; they do not create separate vertical platforms. See
[`docs/wp-2.19-industry-pack-architecture.md`](docs/wp-2.19-industry-pack-architecture.md)
and [`docs/industry-packs/README.md`](docs/industry-packs/README.md).

## Release certification

WP-2.20 adds deterministic pack-aware simulations, approved scenario oracles,
analytical-artifact governance, golden validation for all four packs, security and
resilience checks, release gates, time-bounded waivers, and commit-bound JSON/Markdown
certification evidence. See
[`docs/wp-2.20-release-certification-architecture.md`](docs/wp-2.20-release-certification-architecture.md)
and [`docs/release-certification-runbook.md`](docs/release-certification-runbook.md).

WP-2.21 adds the mandatory, non-waivable `OPERATIONAL_SIGNATURES` release gate.
The gate covers deterministic replay, evidence completeness, tenant isolation,
lifecycle governance, and exact version linkage.
