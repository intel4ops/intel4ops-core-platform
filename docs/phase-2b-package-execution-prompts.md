# Intel4Ops Phase 2B — Package-Specific Execution Prompts

## Authorization boundary

These prompts are approved for preparation and review only.

**No package is authorized for implementation.**

Before using any prompt below, the owner must issue a separate instruction that:

1. names exactly one package;
2. states that implementation/coding may begin;
3. approves the package scope and prerequisites;
4. resolves any owner decisions identified by that package.

An approval to edit, review, publish, or merge these prompt documents is not implementation
authorization.

All prompts inherit:

- `AGENTS.md`;
- `docs/phase-2b-bounded-remediation-specification.md`;
- ADR-I01 through ADR-I08;
- the immutable baseline and all subsequently merged remediation work;
- the prohibition on production, Mobility, customer, shared, or demonstration databases.

## Common execution contract

Append this contract to every authorized package:

> Read `AGENTS.md`, the bounded remediation specification, relevant architecture documents,
> migrations, models, services, routes, engines, and tests before editing. Confirm the
> authorized package and prerequisites. Stop if authorization is absent or dependencies are
> unmet. Create the specified feature branch from updated `main`. Modify only the bounded
> package scope. Keep routes thin, preserve tenant filtering, use Alembic for schema changes,
> preserve historical rows honestly, and add positive, negative, tenant, authorization,
> idempotency, numerical, API, and PostgreSQL tests proportional to the change. Never connect
> to production, Mobility, customer, shared, or demonstration databases. Before commit, run
> Ruff format/check, Mypy, full Pytest, migration lifecycle, drift check, and offline SQL where
> applicable. Review the exact diff, scan for secrets/artifacts, and report changes, tests,
> compatibility, risks, and rollback. Do not push or open a PR unless separately instructed.

---

## Prompt 1 — WP-2.12A Forecasting Integrity Correction

### Required authorization

The owner must say: **Authorize implementation of WP-2.12A.**

### Branch

`feature/wp-2-12a-forecasting-integrity`

### Execution prompt

Implement only WP-2.12A.

Correct the confirmed forecasting integrity defects:

1. Preserve timestamp/value pairing through partial/error filtering.
2. Require a tenant-owned readiness decision whose analytical level is forecasting.
3. Replace current-observation residual calibration with one-step-ahead or governed backtest
   residuals.
4. Persist interval method/version, confidence, calibration size, and limitations.
5. Return structured insufficient-data when calibration is inadequate.
6. Replace fixed 30/91/365-day calendar grains with calendar-aware periods.
7. Fail closed for unsupported methods; do not silently substitute.
8. Correct forecasting idempotency inputs only where local to the forecasting service.

Do not add new forecast algorithms, automated model search, governed-input persistence, or
Reliability integration.

Preserve historical forecast outputs. If output semantics change, introduce a new method
version; do not relabel historical executions.

Required regression tests:

- interior partial/error removal and paired timestamps;
- cross-level readiness rejection;
- authoritative interval fixtures;
- insufficient calibration;
- month-end, leap-year, quarterly, annual, and timezone boundaries;
- unsupported-method failure;
- exact retry versus conflicting idempotency key;
- disposable PostgreSQL service and migration behavior.

Stop after local validation and a focused commit unless push/PR authority is separately given.

---

## Prompt 2 — WP-2.13A Reliability Truth and Safety

### Required authorization

The owner must say: **Authorize implementation of WP-2.13A.**

### Branch

`feature/wp-2-13a-reliability-truth-safety`

### Execution prompt

Implement only WP-2.13A.

Align reliability claims and validation with actual implemented methods:

1. Mark current Weibull as not supporting censoring.
2. Reject censored Weibull inputs with a structured unsupported outcome.
3. Do not implement a new censor-aware estimator in this package.
4. Validate integral nonnegative failure/repair counts and valid event/exposure/time inputs at
   the engine boundary.
5. Reject booleans, strings, fractional counts, invalid times, NaN, and infinity.
6. Persist method version, limitations, and censoring disposition in evidence.
7. Preserve and strengthen Kaplan-Meier censoring fixtures.
8. Require human approval for every reliability-driven action.
9. Correct documentation that implies automatic progressive-orchestrator integration.

Do not add the Reliability orchestrator adapter or automatic action approval.

Required tests:

- censored Weibull fails closed;
- fractional and malformed counts are rejected without truncation;
- authoritative uncensored Weibull and Kaplan-Meier fixtures;
- persisted method limitations;
- tenant, authorization, error-envelope, and PostgreSQL service tests;
- reliability-driven action cannot bypass human approval.

---

## Prompt 3 — WP-2.09A Canonical Idempotency and Replay

### Required authorization

The owner must say: **Authorize implementation of WP-2.09A.**

### Branch

`feature/wp-2-09a-canonical-idempotency`

### Execution prompt

Implement only WP-2.09A.

Create a shared canonical request-fingerprint contract for direct intelligence, progressive
orchestration, and the forecasting adapter. The fingerprint must include tenant, operation,
definition/method version, readiness, canonical record-content digest or governed snapshot,
parameters, time context, lineage/evidence context, and finding-publication intent.

Required behavior:

- same organization/key/fingerprint returns the original aggregate;
- same organization/key with different fingerprint returns HTTP 409;
- same key in a different organization remains independent;
- concurrent identical requests create one execution and one child/evidence/finding set;
- unique races map to replay or conflict, never an unhandled integrity error;
- legacy rows without reconstructable fingerprints remain readable but are not asserted to be
  exact retries.

Do not implement governed input persistence, action idempotency, or economics idempotency.

Required tests:

- same count/different records conflicts;
- changed parameters, method, readiness, lineage, finding candidate, or publication intent
  conflicts;
- direct intelligence validates before replay;
- concurrent PostgreSQL requests create exactly one aggregate;
- retries do not duplicate stages, evidence, findings, usage, or lineage.

---

## Prompt 4 — WP-2.06A Governed Analytical Input and Canonical Mapping

### Required authorization

This prompt may not be used until:

1. the WP-2.06A execution specification is revised against its independent review;
2. the revised specification receives focused architecture approval; and
3. the owner says: **Authorize implementation of WP-2.06A.**

### Branch

`feature/wp-2-06a-governed-analytical-input`

### Execution prompt

Implement WP-2.06A only in the approved incremental migration sequence:

1. immutable governed-input snapshots;
2. canonical and source schema definitions/versions;
3. governed mapping definitions/versions;
4. governed projections with immutable readable output generation and digest;
5. coherent Trust binding to snapshot, schemas, mapping, projection, ProcessingRun, and digest;
6. backward-compatible `inline_manual`/`legacy_unbound` handling.

Use `selection_mode` for snapshot selection. Define raw-object cardinality, canonical digest
serialization, mode/cardinality checks, composite tenant-safe keys, retention precedence,
legal-hold audit evidence, meter semantics, and v1 compatibility exactly as approved in the
revised specification.

Do not synthesize provenance for historical rows. Do not claim exact replay until disposable
PostgreSQL recertification passes.

Implement one migration increment at a time with isolated tests and review. Stop at any
increment whose prerequisite approval is incomplete.

---

## Prompt 5 — WP-2.TI Database-Enforced Tenant Integrity

### Required authorization

The owner must say: **Authorize implementation of WP-2.TI.**

WP-2.06A must be merged and certified first unless the approved package specification narrows
WP-2.TI to preexisting tables only.

### Branch

`feature/wp-2-ti-database-tenant-integrity`

### Execution prompt

Implement additive database-enforced tenant equality across the approved intelligence-domain
edges.

For every tenant-owned parent:

- add or reuse unique `(organization_id, id)`;
- add supporting indexes;
- create composite foreign keys from tenant-owned children;
- preserve service-layer tenant filters.

Cover the explicitly approved tables for intelligence, orchestration, findings, lineage,
actions, economics, and governed-input domains.

Before constraints:

- inspect historical rows;
- fail with a redacted report if any ownership mismatch exists;
- do not rewrite mismatched data automatically.

Required PostgreSQL certification:

- direct cross-tenant SQL insert failures for every managed edge;
- empty-to-head, boundary downgrade, and re-upgrade;
- lock-duration and representative-volume measurements;
- query-plan inspection;
- SQLite compatibility where supported;
- downgrade removes constraints/indexes only and never deletes domain data.

---

## Prompt 6 — WP-2.10A OIKB Governance and Version Binding

### Required authorization

The owner must say: **Authorize implementation of WP-2.10A.**

### Branch

`feature/wp-2-10a-oikb-governance`

### Execution prompt

Implement only WP-2.10A.

1. Make OIKB the authoritative owner of governed immutable analytical definitions.
2. Keep executable registries as bounded, versioned method implementations.
3. Add exact immutable OIKB-definition-version references to governed executions.
4. Verify the stored definition fingerprint matches the referenced version.
5. Enforce author/validator/approver/activator segregation for production/reference-grade
   definitions.
6. Implement only an explicitly approved, fully audited emergency exception.
7. Clarify predicate-match versus business-breach semantics.
8. Reject ambiguous, deprecated, or unsupported definitions for new executions.

Legacy code-backed executions remain readable and explicitly classified. Do not assign
synthetic OIKB foreign keys without verifiable identity.

Required tests:

- self-approval rejection;
- exact version substitution rejection;
- registry change requires a new method version;
- unambiguous rule fixtures, including `BETWEEN`;
- shared/private scope isolation;
- concurrent publication/version allocation on PostgreSQL.

---

## Prompt 7 — WP-2.08A Governed Evidence Binding

### Required authorization

WP-2.06A and WP-2.10A must be merged and certified. The owner must then say:
**Authorize implementation of WP-2.08A.**

### Branch

`feature/wp-2-08a-governed-evidence`

### Execution prompt

Implement only WP-2.08A.

- Bind canonical evidence to a governed projection, immutable record locator, and digest.
- Bind aggregate evidence to a bounded derivation manifest.
- Bind finding evidence to exact execution, OIKB version, readiness decision, input snapshot,
  mapping, projection, and ProcessingRun.
- Preserve bounded evidence sampling.
- Define legacy findings as non-governed and prevent them from satisfying governed publication
  requirements.
- Preserve historical findings and evidence without invented provenance.

Required tests:

- cross-tenant, nonexistent, and cross-projection evidence rejection;
- published evidence immutability;
- retry creates one finding/evidence bundle;
- failed, blocked, unsupported, or insufficient executions cannot publish findings;
- historical evidence resolution after supersession and payload expiration;
- direct PostgreSQL tenant-safe foreign-key tests.

---

## Prompt 8 — WP-2.14A Action Governance and Concurrency

### Required authorization

The owner must say: **Authorize implementation of WP-2.14A.**

WP-2.TI and the approved evidence prerequisites must be complete.

### Branch

`feature/wp-2-14a-action-governance`

### Execution prompt

Implement only WP-2.14A.

1. Replace ambiguous source combinations with a discriminated exactly-one source contract.
2. Persist a coherent source execution/version/evidence/lineage fingerprint.
3. Fingerprint creation, assignment, and lifecycle commands.
4. Return 409 for conflicting idempotency reuse.
5. Serialize lifecycle changes with a row lock, version/CAS contract, or another approved
   PostgreSQL-safe mechanism.
6. Enforce a per-state mutation matrix.
7. Freeze approval and verification inputs; later corrections are append-only revisions.
8. Detect arbitrary dependency cycles.
9. Preserve completion versus evidence-backed verification.
10. Require human approval for reliability-driven actions.

Required tests:

- mismatched/multiple/cross-tenant sources rejected;
- conflicting idempotency key rejected;
- concurrent transitions create one valid history;
- terminal-state mutation rejected;
- arbitrary dependency cycles rejected;
- verification authority and evidence enforced;
- PostgreSQL concurrency and constraint tests.

---

## Prompt 9 — WP-2.15A Recovery Economics Integrity

### Required authorization

Before implementation, owners must approve:

- currency minor-unit table and update authority;
- FX source hierarchy and valuation-date policy, or confirmation that conversion remains
  prohibited;
- overlap model.

Then the owner must say: **Authorize implementation of WP-2.15A.**

### Branch

`feature/wp-2-15a-recovery-economics-integrity`

### Execution prompt

Implement only WP-2.15A using the approved financial policies.

- Bind calculations to exact scenario, ordered assumptions, fingerprints, engine version,
  rounding policy, currency, and valuation date.
- Approve the exact calculation/assumption set that produced the baseline.
- Persist immutable approved-baseline fingerprints.
- Enforce the approved conserved overlap policy.
- Prevent multi-group overwrite and double counting.
- Serialize overlap, version, prioritization, and approval operations.
- Fingerprint all consequential idempotent commands.
- Introduce baseline-aware/ever-approved immutability and append-only amendments.
- Apply approved minor-unit, analytical precision, rounding-stage, FX, and conservation rules.
- Keep estimated, expected, approved, realized, and verified value distinct.

Until detailed policy is approved, do not implement implicit FX conversion or multi-group
overlap.

Required tests:

- exact replay after later assumption revisions;
- deterministic/conserved overlap under concurrency and rounding;
- conflicting idempotency keys return 409;
- approved baselines remain immutable after later status changes;
- zero-cost, negative-benefit, extreme-value, and division-by-zero cases;
- approved currency fixtures;
- PostgreSQL concurrency and migration lifecycle.

---

## Prompt 10 — WP-2.09R Reliability Orchestration Gate

### Required authorization

WP-2.13A, WP-2.06A, WP-2.08A, and WP-2.14A must be certified. The human-review threshold
catalog must be approved. The owner must then say:
**Authorize implementation of WP-2.09R.**

### Branch

`feature/wp-2-09r-reliability-orchestration`

### Execution prompt

Implement a bounded Reliability adapter only if the entry gates are satisfied.

- Bind exact reliability readiness, governed input, method, execution, and evidence.
- Fail closed; no implicit fallback.
- Translate unsupported, insufficient, blocked, warning, failure, and partial states exactly.
- Recheck tenant, entitlement, and applicable industry pack at worker execution.
- Do not automatically approve, assign, execute, or verify actions.
- Require human review for all configured high-impact findings and all reliability-driven
  actions.
- Preserve deterministic orchestration order and replay.

If any safety policy is missing, do not implement the adapter; update documentation to retain
the manual boundary.

---

## Prompt 11 — WP-2.CERT Intelligence Recertification

### Required authorization

The owner must say: **Authorize WP-2.CERT independent recertification.**

All accepted P1 findings and certification-blocking P2 findings must be merged first.

### Branch

No implementation branch unless certification documentation corrections are separately
authorized. The review itself is read-only.

### Execution prompt

Conduct an independent Phase 2 intelligence recertification.

Do not modify code. Verify:

- tenant isolation at API, service, and direct-SQL layers;
- role, entitlement, publication, approval, and verification authority;
- exact replay from governed input through finding, action, and economics;
- canonical idempotency and PostgreSQL concurrency;
- numerical golden fixtures;
- explicit unsupported/insufficient/blocked/failed/partial/warning behavior;
- OIKB version integrity;
- evidence continuity;
- migration lifecycle, drift, offline SQL, constraints, and seed ownership;
- representative-volume performance and migration locks;
- secrets and generated artifacts.

Issue one result:

- `CERTIFIED`;
- `CERTIFIED WITH EXPLICIT LIMITATIONS`;
- `NOT CERTIFIED`.

Do not remediate findings during recertification.

## Prompt-use register

When a package is authorized, record:

| Field | Required value |
|---|---|
| Package | Exact package identifier |
| Authorization statement | Exact owner instruction |
| Approved commit | Specification/prompt commit |
| Prerequisites | Evidence that dependencies are merged/certified |
| Owner decisions | Exact approved policies |
| Branch | Approved feature branch |
| Implementation agent | Named agent/task |
| Start time | UTC |
| Completion decision | Separate from implementation authorization |
