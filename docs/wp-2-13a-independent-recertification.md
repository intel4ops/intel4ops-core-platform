# WP-2.13A Independent Recertification

## Review identity

- Repository: `C:\Users\hkepe\Documents\Intel4Ops\intel4ops_core_platform_Github`
- Branch: `feature/wp-2-13a-reliability-truth-safety`
- Reviewed HEAD: `4a66a1327ff02e4fefc072df8eead617f7eb165d`
- Implementation baseline: `79428743b945ba3b7756a1cb471af21585190fcb`
- Baseline relationship: baseline is an ancestor of reviewed HEAD
- Alembic head: `20260728_0023`
- PostgreSQL: `17.10`
- Review role: independent assurance reviewer; no implementation code was modified
- Review date: 2026-07-29

## Authoritative evidence

The review used:

- the locally supplied Phase 2A Intelligence Architecture Assurance Review mandate and the
  accepted WP-2.13 findings carried into the authorization;
- ADR-I01 through ADR-I08 as reproduced in
  `docs/phase-2b-bounded-remediation-specification.md`;
- `docs/phase-2b-bounded-remediation-specification.md`;
- `docs/phase-2b-package-execution-prompts.md`;
- `docs/wp-2-13a-reliability-truth-safety-remediation-report.md`;
- the exact baseline-to-HEAD diff and all eleven changed files.

The repository does not contain a separate Phase 2A result document or a separate Architecture
Decision Register file. The approved decisions and accepted reliability findings are,
however, reproduced in the bounded specification, package authorization, prompt pack, and
remediation report. No implementer-reported test result was accepted without an independent
run.

## Decision

**DO NOT CERTIFY**

WP-2.13A correctly closes the unsafe Weibull censoring and discrete-count behaviors, but a
blocking reliability idempotency defect returns a prior execution for a materially different
governed-definition request. This is an explicit `DO NOT CERTIFY` condition in the
recertification mandate.

Merge recommendation: **DO NOT MERGE**

Next-package readiness: **NOT READY**

## Review finding WP213A-IR-001

- Review finding ID: `WP213A-IR-001`
- Severity: **P1 — High**
- Affected Phase 2A finding or ADR: Reliability reproducibility/idempotency finding; ADR-I02
  (exact governed definition ownership and versioned execution); WP-2.13A requirement that
  behaviorally significant lineage and execution context participate in idempotency
- File and symbol: `app/services/reliability_service.py`,
  `ReliabilityExecutionService.execute`, particularly the execution-package and
  reproducibility hashes and replay lookup
- Evidence:
  - Lines 180–190 hash the definition version's content `fingerprint` but omit
    `payload.definition_code`, `definition.id`, and `version.id`.
  - Lines 192–218 use that incomplete package in the organization-scoped reproducibility hash
    and return the matching execution unchanged.
  - `app/models/oikb.py` permits the same content fingerprint on different definitions because
    `uq_oikb_definition_fingerprint` is scoped to `definition_id`.
  - An independent PostgreSQL 17.10 probe created two active, same-tenant reliability
    definitions with different stable codes and IDs but the same allowed version fingerprint.
    The first request produced execution
    `2bfc69a5-10fc-4a78-8e0d-c1b7a1d27fcc`. A second request naming definition
    `c22cb2f9-60a8-47e8-8b16-ccc8eedd47e5` returned that same execution, whose persisted
    definition was instead `1892eddc-c156-4688-a3b6-8bc1407e9ee7`.
  - Probe result: `collision_reproduced=True`.
- Risk: a request for governed definition B can be reported as an exact retry of definition A.
  The returned execution, evidence, and persisted OIKB binding do not identify the definition
  requested by the caller. This breaks exact lineage, deterministic replay truth, and the
  contract that a materially different request cannot reuse an earlier reliability execution.
- Blocking status: **BLOCKING**. It directly satisfies the mandate's `DO NOT CERTIFY` rule:
  “idempotency can return a prior execution for a materially different request.”
- Required remediation:
  - Include immutable governed definition identity in the canonical execution package and
    reproducibility fingerprint. At minimum bind stable definition code, `definition.id`,
    semantic version, and `version.id` in addition to the content fingerprint.
  - Preserve deterministic canonical serialization.
  - Ensure replay lookup cannot return an execution whose persisted definition/version binding
    differs from the current request.
  - Reconcile the remediation report's idempotency claim with the corrected contract.
- Required retest:
  - same request/same definition returns exactly one execution;
  - different definition code or definition ID with identical content fingerprint produces a
    distinct execution or an explicit deterministic conflict, never a replay;
  - different definition version ID, Trust/readiness binding, dataset reference/fingerprint,
    lineage reference, orchestration context, asset scope/type, observation window, exposure
    unit/basis, censoring policy, inputs, method/version, and engine version do not replay;
  - concurrent identical PostgreSQL requests create one result without integrity leakage;
  - focused, default, full PostgreSQL, migration lifecycle, drift, offline SQL, diff, and secret
    gates all pass after remediation.

## Verified remediated before the blocking stop

- Weibull registry metadata declares `supports_censoring=false`.
- `WEIBULL_TWO_PARAMETER` rejects any censored observation before fitting and returns the
  deterministic “does not support censored observations” error.
- No censored observation is filtered while a successful Weibull fit is returned.
- Uncensored Weibull fixtures produced deterministic, positive, finite shape, scale, B10, and
  B50 values, with B10 below B50.
- Insufficient and constant Weibull populations fail safely.
- Failure and repair counts are validated before conversion. Fractional, boolean, string,
  negative, NaN, and infinity representations are rejected at the applicable schema or engine
  boundary; valid integers remain operational.
- The public `/evaluate` observation boundary is typed, finite, length-bounded, and
  `extra="forbid"`. Persisted execution observations are typed, finite, and bounded by field and
  collection constraints.
- Downtime greater than exposure is rejected.
- Unsupported method/version pairs fail closed.
- Reliability execution requires a tenant-scoped completed Trust assessment and a tenant-scoped
  `reliability` readiness decision in `ready` or `ready_with_warnings`.
- Blocked readiness, wrong readiness level, cross-tenant Trust/readiness, unauthenticated access,
  and unauthorized organization access are rejected by focused tests and service inspection.
- Definition and execution reads are tenant-scoped and return non-enumerating not-found errors.
- Identical retries with the same incomplete fingerprint return the existing execution, and a
  changed source-lineage reference produces a distinct execution.
- Successful reliability results continue to require human review and do not automatically
  create operational actions.
- The code-backed progressive engine registry contains arithmetic, deterministic rule,
  statistical, and forecasting adapters only; no Reliability adapter was added.
- No migration, WP-2.06A governed-input implementation, WP-2.TI implementation, commercial
  threshold, new reliability model, or censor-aware estimator was introduced.
- Censoring, method-registry, and orchestrator-boundary documentation agrees with the corrected
  Weibull runtime behavior.

## Reopened findings

- Reliability idempotency and exact governed-definition replay integrity:
  `WP213A-IR-001`.

## Blocking findings

- `WP213A-IR-001` — materially different governed-definition requests can reuse a prior
  reliability execution.

## Non-blocking conditions

- None. The one observed third-party `StarletteDeprecationWarning` does not affect the decision.

## Independent validation evidence

| Gate | Result | Evidence |
|---|---|---|
| Ruff format | PASS | `361 files already formatted` |
| Ruff check | PASS | `All checks passed!` |
| Mypy | PASS | `mypy app`: no issues in 147 source files |
| Focused reliability tests | PASS | 29 passed; one third-party deprecation warning |
| Independent numerical probes | PASS | deterministic finite uncensored fit; positive parameters; B10 < B50; censored, insufficient, and constant cases rejected |
| Full default tests | PASS | 328 passed, 13 PostgreSQL-only skipped, one warning |
| PostgreSQL tests | PASS | 13 passed on PostgreSQL 17.10; one warning |
| Authorization tests | PASS | unauthenticated and unauthorized organization API cases passed within the 29 focused tests |
| Tenant-isolation tests | PASS | tenant-scoped Trust/readiness/execution cases passed within focused tests; PostgreSQL tenant behavior passed |
| Idempotency tests | **FAIL — BLOCKING** | identical retry and changed-lineage regressions passed, but independent same-content/different-definition PostgreSQL probe reproduced prior-execution reuse |
| Alembic upgrade | PASS | upgraded/confirmed `20260728_0023` |
| Alembic downgrade | PASS | `20260728_0023 -> 20260728_0022` |
| Alembic re-upgrade | PASS | `20260728_0022 -> 20260728_0023` |
| Alembic drift | PASS | `No new upgrade operations detected.` |
| Offline PostgreSQL SQL | PASS | PostgreSQL dialect; 7,096 lines / 914,036 characters; initial schema and head revision present |
| Git diff | PASS | exact baseline-to-HEAD `git diff --check` produced no errors |
| Secret scan | NOT RUN | validation stopped immediately after the blocking defect was established |

The first default-suite attempt had 327 passes and one setup error because the sandbox denied
pytest access to its user-profile temp directory. No application test failed. The complete suite
was rerun without exclusion using a verified workspace-local disposable base temp directory and
passed 328 tests.

The first PostgreSQL invocation was rejected before test setup because the unique database name
did not contain the repository's required safety marker. It was replaced with a name containing
`validation`; all 13 PostgreSQL tests then passed.

The dedicated database
`intel4ops_wp213a_recert_validation_agent2_20260729` was removed after the blocking probe, and
catalog verification returned zero matching databases. No credentials were printed.

## Scope integrity

- Reliability orchestrator integration added: **NO**
- WP-2.06A work added: **NO**
- WP-2.TI work added: **NO**
- Commercial thresholds invented: **NO**
- Unvalidated censor-aware estimator added: **NO**
- New reliability models outside the approved package: **NO**
- Unrelated refactoring or feature development: **NO**

## Documentation assessment

The remediation report accurately describes supported/unsupported censoring, strict discrete
counts, reliability readiness, human review, PostgreSQL execution, remaining WP-2.06A and
WP-2.TI dependencies, and exclusion from automatic progressive orchestration.

Its idempotency section is incomplete as an assurance claim: although the listed context fields
are included, immutable governed-definition identity is not. After remediation, the report must
state and evidence the exact definition/version binding used by replay.

## Final disposition

- Decision: **DO NOT CERTIFY**
- Merge recommendation: **DO NOT MERGE**
- Next-package readiness: **NOT READY**
- Required action: remediate `WP213A-IR-001` and repeat the complete independent
  recertification from a clean exact reviewed commit.

## Post-review implementation note

The original `DO NOT CERTIFY` decision above is unchanged. A later bounded remediation added
governed definition/version identity to reliability execution fingerprinting and added
sequential and concurrent regression coverage. These implementation notes are not independent
certification evidence. Complete independent recertification must review the new commit range
before the decision may change.

=========================================
Final Independent Recertification
After WP213A-IR-001 Remediation
=========================================

## Review identity

- Repository: `C:\Users\hkepe\Documents\Intel4Ops\intel4ops_core_platform_Github`
- Branch: `feature/wp-2-13a-reliability-truth-safety`
- Reviewed HEAD: `e80ac50b5b54aa8983e387445ddae62eeebc21a9`
- Reviewed baseline: `79428743b945ba3b7756a1cb471af21585190fcb`
- Baseline relationship: baseline confirmed an ancestor of reviewed HEAD; reviewed HEAD confirmed
  the tip of `feature/wp-2-13a-reliability-truth-safety`
- Alembic head: `20260728_0023` (single head, confirmed)
- PostgreSQL: `17.10`
- Review role: independent assurance reviewer; no implementation code, tests, migrations, or
  schemas were modified during this review
- Review date: 2026-07-30

Excluded from this recertification, per mandate: `fix/phase-2a-wave1-p0-corrections`, commit
`98c93e8`, commit `a4a4716`, `fix/phase-2a-wave2-hardening`. Both excluded commits were confirmed
absent from the baseline-to-HEAD ancestry (`git merge-base --is-ancestor` returned false for
both).

## Scope of remediation reviewed

Baseline-to-HEAD diff: 12 files changed (`app/engines/reliability_engine.py`,
`app/schemas/reliability.py`, `app/services/reliability_service.py`, three
`docs/reliability-intelligence/*.md` files, this document, the remediation report, and four test
files). No file under `app/models/`, `migrations/`, `app/services/orchestration_service.py`, or
`app/services/action_service.py` was touched.

## WP213A-IR-001 closure verification

- **Original defect status:** preserved above as historical evidence; not re-executed against
  the withdrawn vulnerable code path, which no longer exists at reviewed HEAD.
- **Remediation inspected:** `ReliabilityExecutionService._execution_package_fingerprint` now
  binds `definition.stable_code`, `definition.id`, `version.semantic_version`, `version.id`, and
  `version.fingerprint`, in addition to method, failure-definition, exposure basis, and
  censoring policy. `_verified_replay` rejects any persisted-execution match whose
  `oikb_definition_id`, `oikb_definition_version_id`, or `execution_package_fingerprint` does not
  match the current request, or whose definition/version identity fields are empty, raising
  `IDEMPOTENCY_CONFLICT` (HTTP 409) instead of returning a mismatched execution. A concurrent
  `IntegrityError` on the pre-existing `uq_reliability_reproducibility` constraint
  (`organization_id`, `reproducibility_fingerprint`) is caught, the session is rolled back, the
  existing row is re-queried, and the same identity verification is applied before replay.
- **Exact identity verification — independent reproduction:** a standalone probe script (not
  part of the implementer's test suite) was run against a freshly created, disposable
  PostgreSQL 17.10 database and exercised directly against the application's own services. All
  16 independent assertions passed:
  - two same-tenant definitions with identical content (version) fingerprint but different
    definition IDs and stable codes produced two distinct, correctly bound executions — no
    cross-definition replay;
  - two versions of one definition, requested with otherwise identical execution content but
    different version identities, produced two distinct, correctly bound executions — no
    cross-version replay; the database's own `uq_oikb_definition_fingerprint` constraint was
    confirmed to structurally forbid two versions of the *same* definition from sharing a
    content fingerprint, meaning the only reachable fingerprint-collision path is
    cross-definition, which was independently proven not to replay;
  - an identical request retried against the same definition/version returned exactly one
    execution;
  - two different, same-content-fingerprint tenants (cross-tenant equivalent requests) produced
    two distinct, organization-scoped executions, with cross-tenant read-by-ID returning a
    non-enumerating not-found error;
  - a forced persisted-fingerprint collision between two different definitions raised
    `IDEMPOTENCY_CONFLICT` / HTTP 409 deterministically, never a replay.
- **Conflict behavior:** confirmed at both the service layer (independent probe) and the API
  layer (`tests/test_reliability_api.py::test_reliability_api_returns_conflict_for_mismatched_persisted_identity`,
  independently rerun) — HTTP 409, body `{"code": "IDEMPOTENCY_CONFLICT"}`.
- **Concurrency validation:** `tests/test_postgres_migrations.py::test_concurrent_reliability_definition_identity_idempotency`
  was independently rerun against a freshly created disposable PostgreSQL 17.10 database (not
  reused from any prior session). Two concurrent identical requests resolved to exactly one
  execution. A forced same-fingerprint collision across two different definitions, submitted
  concurrently, produced exactly one success and one deterministic `IDEMPOTENCY_CONFLICT` —
  never a replay to the losing request. Two concurrent distinct-definition requests produced two
  separate, correctly bound executions.
- **Partial-record prevention:** independently confirmed exactly one `ReliabilityExecution`, one
  `ReliabilityModelResult`, one `ReliabilityExecutionStep`, and a positive `ReliabilityMetric`
  count for the identical-replay case; exactly one `ReliabilityExecution` row for the forced
  same-fingerprint collision despite two concurrent attempts; exactly two rows for the
  concurrent-distinct case. No duplicate or partial records were observed under any concurrency
  scenario.
- **Tenant isolation:** independently confirmed at both the service layer (cross-tenant probe
  above) and within the disposable PostgreSQL suite; the replay-lookup query remains scoped by
  `organization_id`, and the reproducibility fingerprint itself also binds the organization,
  giving two independent layers of cross-tenant protection.

**WP213A-IR-001 is CLOSED.** The defect described in the original finding — a materially
different governed-definition request silently reusing a prior execution — was independently
reproduced as historical fact against the pre-remediation code and independently shown, through
fresh reproduction against the current code and a fresh disposable database, not to occur at
reviewed HEAD.

## Complete WP-2.13A reverification

All items listed under "Verified remediated before the blocking stop" above were independently
reconfirmed at reviewed HEAD, with no regression:

- Weibull registry metadata `supports_censoring=false`; censored observations rejected before
  fitting with a deterministic error; no censored observation is silently filtered.
- Uncensored Weibull fixtures remain deterministic, positive, finite, with B10 < B50.
- Insufficient/constant populations fail safely; fractional, boolean, string, negative, NaN, and
  infinite counts are rejected at the schema/engine boundary.
- Downtime greater than exposure is rejected at both schema and engine layers.
- Unsupported method/version pairs fail closed.
- Reliability execution requires a tenant-scoped completed Trust assessment and a tenant-scoped
  `reliability` readiness decision in `ready` or `ready_with_warnings`; blocked readiness, wrong
  readiness level, cross-tenant Trust/readiness, unauthenticated access, and unauthorized
  organization access are all rejected.
- Definition and execution reads remain tenant-scoped with non-enumerating not-found errors.
- Successful reliability results continue to require human review and do not automatically
  create operational actions.
- No Reliability adapter exists in the Progressive Intelligence Orchestrator; `orchestration_service.py`
  contains no reliability reference (independently confirmed by direct search).
- No migration, model change, WP-2.06A governed-input implementation, WP-2.TI implementation,
  commercial threshold, new reliability model, or censor-aware estimator was introduced.
- Censoring, method-registry, and orchestrator-integration documentation, and the remediation
  report's WP213A-IR-001 section, accurately describe the corrected behavior; documented test
  counts match the counts independently observed in this recertification.

## Independent validation evidence

| Gate | Result | Evidence |
|---|---|---|
| Ruff format | PASS | `362 files already formatted` |
| Ruff check | PASS | `All checks passed!` |
| Mypy | PASS | `mypy app`: no issues found in 147 source files |
| Focused reliability tests | PASS | 34 passed |
| Full default tests (SQLite) | PASS | 333 passed |
| PostgreSQL tests | PASS | 14 passed on PostgreSQL 17.10, freshly created disposable database |
| Concurrency tests | PASS | identical, forced-collision, and distinct-definition concurrent cases all correct; zero partial/duplicate records |
| Authorization tests | PASS | 401/403 cases within the focused suite |
| Tenant-isolation tests | PASS | focused suite plus independent cross-tenant probe |
| Idempotency tests | PASS | retry, cross-definition, cross-version, cross-tenant, and forced-collision cases all resolve correctly |
| API conflict tests | PASS | HTTP 409 `IDEMPOTENCY_CONFLICT` confirmed at the API layer |
| Alembic upgrade | PASS | to `20260728_0023` |
| Alembic downgrade | PASS | `20260728_0023 -> 20260728_0022` |
| Alembic re-upgrade | PASS | `20260728_0022 -> 20260728_0023` |
| Alembic drift | PASS | autogenerate produced an empty upgrade/downgrade body — no drift |
| Offline PostgreSQL SQL | PASS | PostgreSQL dialect; 7,071 lines / 913,648 characters; initial schema through head revision present |
| Git diff | PASS | exact baseline-to-HEAD `git diff --check` produced no errors |
| Secret scan | PASS | pattern scan of the full baseline-to-HEAD diff found no credentials, keys, or tokens |
| Cleanup verification | PASS | both disposable databases created for this review were dropped and catalog verification returned zero matching databases; no credentials were printed |

Two disposable PostgreSQL databases were created for this recertification, both freshly named
with a `validation` safety marker and today's timestamp, distinct from any database used in the
prior review or any other session. Both were dropped after use and their absence was verified
against `pg_database`.

## Scope integrity (reconfirmed)

- Reliability orchestrator integration added: **NO**
- WP-2.06A work added: **NO**
- WP-2.TI work added: **NO**
- Commercial thresholds invented: **NO**
- Unvalidated censor-aware estimator added: **NO**
- New reliability models outside the approved package: **NO**
- Unrelated refactoring or feature development: **NO**
- P0 commit `98c93e8` included in review: **NO**
- P1 commit `a4a4716` included in review: **NO**

## Reopened findings

- None.

## New findings

- None.

## Blocking findings

- None.

## Non-blocking conditions

- One third-party `StarletteDeprecationWarning` (httpx/starlette `TestClient`), pre-existing and
  outside scope — does not affect the decision.

---

## FINAL DECISION

**CERTIFY**

Merge recommendation:

**APPROVE**
