# WP-2.20 Release Certification Architecture Assessment

## Baseline

- Baseline branch: `main`
- Baseline commit: `6e21076f8e78c4b45bd2012e314412f8c1173116`
- Feature branch: `feature/wp-2-20-release-certification`
- Baseline Alembic head: `20260727_0019`
- Working tree at branch creation: clean
- Target runtime: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2,
  SQLite for isolated tests, and disposable PostgreSQL for lifecycle certification
- Main quality status: PR #25 GitHub Actions and the WP-2.19 post-merge SQLite,
  PostgreSQL, Ruff, Mypy, Alembic lifecycle, drift, and offline-SQL gates passed
- Local environment note: the pre-existing `.venv` references a removed Microsoft
  Store Python 3.12 installation and must be recreated before WP-2.20 gates run

## Existing capabilities to reuse

The platform already provides organization-scoped persistence, authorization and
membership checks, application-client controls, commercial entitlements and usage
metering, governed industry-pack versions and assignments, ingestion and lineage,
trust and readiness decisions, OIKB definitions, deterministic and analytical engines,
orchestration, findings and evidence, predictive actions, recovery economics, verified
value and reversal ledgers, API request audit events, and tenant-scoped idempotency.

The four WP-2.19 pack manifests provide the governed pack identity and component
bindings for Job-to-Cash, Manufacturing, Ports, and Mobility. The Job-to-Cash runtime
already exercises the deepest implemented business path. Existing service-layer
orchestration, immutable audit records, portable JSON columns, UUID identifiers,
stable seed helpers, and the SQLite/PostgreSQL migration suites are the implementation
patterns for WP-2.20.

The current GitHub Actions quality gate already provisions disposable PostgreSQL 17
and runs Ruff, Mypy, SQLite tests, PostgreSQL migration tests, Alembic drift detection,
and offline SQL generation. WP-2.20 will extend this workflow with a deterministic
release-certification command rather than create a separate CI system.

## Missing capabilities

There is no governed simulation scenario registry, machine-readable oracle registry,
validation-run ledger, generalized analytical-artifact governance record, drift-policy
registry, release-candidate registry, gate evaluation, waiver record, immutable
certification evidence, certification report generator, or certification CLI.

Existing economic forecast scenarios are business projections and must not be reused
as validation scenarios. Existing pack validation results validate manifests, not
release candidates. Existing OIKB governance remains authoritative for OIKB content;
WP-2.20 adds release-facing artifact governance references without duplicating OIKB
definitions or model implementations.

## Persistence and migration decision

New persistence is required because release certification must be auditable,
reproducible, tied to an exact commit, and immutable after issuance. One additive
Alembic revision after `20260727_0019` is required. It will introduce:

- scenario definitions and immutable version records;
- oracle definitions and immutable version records;
- validation suites and validation runs;
- analytical-artifact governance records and versions;
- drift-monitoring policies;
- release candidates, gate definitions, gate results, waivers, certifications, and
  evidence references.

Tenant-owned execution records will contain `organization_id`. Platform-wide governed
definitions will use an explicit shared scope and will not silently inherit a tenant.
The migration will use UUIDs, portable JSON, named constraints, deterministic stable
seed identifiers, and additive foreign keys. Downgrade will remove only WP-2.20-owned
objects and seeds, preserving all WP-2.19 data.

## Registry integration

- Scenario versions bind to exact `industry_pack_versions` records.
- Scenario required capabilities use the commercial capability and entitlement keys
  already exposed by pack manifests and the commercial catalog.
- Oracle assertions reference scenario versions and stable output/evidence keys.
- Analytical governance references OIKB stable codes and exact definition versions,
  registered model/method identifiers, rule bindings, and pack components; it does not
  copy executable formulas or models.
- Validation records capture exact pack, rule, OIKB, model, configuration, migration,
  database-engine, seed, branch, and commit versions.
- Future proprietary signatures can use the same artifact-governance contract and
  event-window metadata without being implemented in WP-2.20.

## Evidence storage

Certification persistence stores bounded structured results, hashes, stable references,
comparison summaries, and relative artifact paths. It does not store credentials,
unbounded logs, production data, raw customer records, or generated large datasets.
Generated local scenario packages and human/machine reports live under ignored build
directories. Tests use temporary directories. Evidence records are append-only once a
certification is issued and include integrity hashes tied to the tested commit.

## Scenario and oracle design

Scenarios are code-backed deterministic generators selected through a registry.
Published metadata is persisted as immutable versions. A seed plus scenario version
produces a canonical manifest and artifacts with stable ordering and hashes. Industry
profiles provide pack-specific records and intentional defects while sharing generation,
manifest, export, and comparison infrastructure.

Every scenario version has an approved oracle containing typed assertions: exact,
tolerance, range, required/forbidden finding, evidence, calculation trace, confidence,
exposure, value state, action, audit, usage, API, failure category, and duration.
Certification compares actual normalized output to the oracle; realistic-looking output
is never sufficient.

## Release gates and waivers

Gate evaluation is deterministic and fail closed. A mandatory unrun, blocked, or failed
gate prevents certification. Security, tenant isolation, migration integrity, secret
scanning, authorization, evidence integrity, and verified-value separation are
non-waivable. Only explicitly waivable warning-level gates may receive a time-bounded,
approved waiver with owner, justification, compensating control, evidence, and expiry.
Expired or improperly approved waivers are rejected.

Certification states are derived from gate results:

- `certified` when every mandatory gate passes;
- `conditionally_certified` when all mandatory gates pass and only approved,
  unexpired waivable failures remain;
- `rejected` for any non-waivable failure;
- `blocked` when required evidence or execution is absent.

No endpoint or CLI flag can override a non-waivable failure.

## Reproducible local and CI execution

The certification CLI accepts an explicit commit, environment, database engine, suite,
and output directory. It refuses a dirty tree for release certification, records the
Alembic head, normalizes timestamps out of comparison payloads, and returns a non-zero
exit code for blocked or rejected candidates. Local and CI paths call the same services
and registries. PostgreSQL validation requires `TEST_POSTGRES_URL` and
`CONFIRM_DISPOSABLE_POSTGRES=1`; there is no production or shared-database fallback.

## Controlled implementation sequence

### WP-2.20A — Simulation and oracle foundation

1. Add typed scenario, manifest, event-window, artifact, and oracle contracts.
2. Add deterministic registries, generators, exporters, and comparator.
3. Register the required 36 scenarios across the four packs.
4. Implement deep Oilfield Services and servo-degradation event sequences.
5. Prove deterministic replay, defect injection, schema validation, and tenant isolation.

### WP-2.20B — Validation, governance, security, and resilience

1. Add persistence models, migration, lifecycle services, and immutable audit behavior.
2. Add analytical-artifact lifecycle and drift-policy validation.
3. Add golden pack validators using existing platform services.
4. Add security, tenant-isolation, authorization, entitlement, idempotency, retry,
   observability, and failure-injection checks.

### WP-2.20C — Release certification and CI integration

1. Add release-candidate, gates, results, waiver, evidence, and certification services.
2. Add thin admin APIs and the local certification CLI.
3. Produce JSON and Markdown reports tied to the exact commit.
4. Extend GitHub Actions with certification and artifact upload.
5. Complete SQLite and disposable PostgreSQL lifecycle validation and documentation.

## Key risks and mitigations

- **Scope size:** deliver and test A, B, and C independently with shared contracts.
- **False confidence from synthetic data:** require approved oracles, forbidden outcomes,
  boundary cases, false-positive/negative challenges, and explicit limitations.
- **Registry duplication:** store references to OIKB, model, pack, and commercial
  registries rather than parallel executable definitions.
- **Tenant leakage:** require `organization_id` on tenant executions and evidence,
  filter every service query, and include negative cross-tenant tests.
- **Non-determinism:** canonical ordering, decimal-safe serialization, seeded local RNGs,
  stable UUID generation, and content hashes.
- **Value double counting:** assert expected, realized, verified, adjustment, and reversal
  states independently and reconcile them through the immutable recovery ledger.
- **Unsafe database targeting:** explicit disposable PostgreSQL URL and confirmation,
  database-name safety checks, and no credential logging.
- **Large artifacts in Git:** generate into ignored output directories and commit only
  compact manifests, definitions, documentation, and test fixtures.
- **Over-broad security claims:** certification is an engineering release gate, not SOC 2,
  ISO certification, penetration testing, or proof of production infrastructure.

## Assessment decision

WP-2.20 should proceed with one additive migration and a shared validation domain that
coordinates existing services and registries. It must not become a second analytics
platform, a second industry-pack system, or a deployment system. The implementation is
ready to begin with WP-2.20A after the isolated Python environment is restored.
