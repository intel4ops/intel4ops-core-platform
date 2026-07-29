# Intel4Ops Phase 2B — Bounded Intelligence Remediation Specification

## 1. Authorization status

- Artifact: Phase 2B bounded remediation specification
- Architecture Decision Register: ADR-I01 through ADR-I08 approved
- Specification preparation: authorized
- Implementation authorization: **not granted**
- Production deployment authorization: **not granted**
- Baseline: `main@bed958d2e5ff6b8fc231ad4543cc751391857340`
- Alembic baseline: `20260728_0023`

This document converts the approved Architecture Decision Register and the Phase 2A
intelligence findings into bounded, dependency-ordered implementation work packages. It does
not authorize coding. Each implementation package requires explicit authorization before its
branch is created.

## 2. Approved architecture decisions

| Decision | Approved policy |
|---|---|
| ADR-I01 | Reliability remains opt-in/manual until a safety-review policy and bounded orchestrator adapter are approved for implementation. |
| ADR-I02 | OIKB owns governed immutable analytical definitions; registries execute versioned bounded methods. |
| ADR-I03 | WP-2.06A provides immutable analytical inputs, schemas, mappings, projections, and lineage bindings. |
| ADR-I04 | Unsupported methods fail closed. Any fallback is explicit, versioned, evidenced, and visible. |
| ADR-I05 | Reliability-driven actions and high-impact findings require human approval. Thresholds are governed configuration, not hard-coded assumptions. |
| ADR-I06 | Forecast intervals use one-step-ahead or backtest residuals, a minimum calibration sample, and a recorded method version. |
| ADR-I07 | Economics overlap accounting uses a governed exclusivity/allocation policy with locked, conserved totals. |
| ADR-I08 | Currency governance defines minor units, analytical precision, rounding stages, valuation dates, FX sources, and conservation rules. |

## 3. Remediation principles

1. Correct confirmed false or unsafe analytical behavior before expanding capability.
2. Do not duplicate the governed-input root cause across downstream packages.
3. Complete WP-2.06A before claiming deterministic replay from stored source data.
4. Use additive Alembic migrations for every schema change.
5. Preserve current API behavior unless a package explicitly defines a compatibility change.
6. Preserve historical executions; never rewrite prior outcomes to appear compliant.
7. Treat existing executions without governed bindings as `inline_manual` or `legacy_unbound`.
8. Enforce tenant equality at both service and database layers.
9. Fail closed for unsupported methods, invalid readiness, ambiguous definitions, currency
   conflicts, and incoherent evidence.
10. Require disposable PostgreSQL certification for every migration or concurrency change.
11. Keep routes thin and business rules in services or independently testable engines.
12. Do not combine unrelated maintainability refactors with remediation.

## 4. Consolidated finding ownership

| Finding group | Primary owner | Disposition |
|---|---|---|
| Immutable analytical inputs, canonical evidence, mapping and lineage bindings | WP-2.06A | One foundation remediation; do not patch independently in every engine |
| Forecast timestamp, readiness, intervals, and calendar behavior | WP-2.12A | Immediate bounded numerical correction |
| Reliability censoring claims and input validation | WP-2.13A | Immediate bounded safety correction |
| Intelligence and orchestration idempotency | WP-2.09A | Shared canonical fingerprint contract |
| Database-enforced tenant equality | WP-2.TI | Cross-domain additive integrity migration |
| OIKB segregation, executable registry boundary, exact version binding | WP-2.10A | OIKB governance hardening |
| Finding/evidence immutable governed references | WP-2.08A | Depends on WP-2.06A and WP-2.10A |
| Action source coherence, concurrency, lifecycle immutability | WP-2.14A | Action governance hardening |
| Economics baseline, overlap, idempotency, currency governance | WP-2.15A | Recovery economics hardening |
| Reliability participation in progressive orchestration | WP-2.09R | Deferred until safety and human-review gates pass |
| End-to-end recertification | WP-2.CERT | Final closure gate |

## 5. Recommended execution sequence

```text
Architecture decisions approved
        |
        +--> WP-2.12A Forecasting Integrity
        |
        +--> WP-2.13A Reliability Truth and Safety
        |
        +--> WP-2.09A Idempotency Contract
        |
        v
WP-2.06A Governed Inputs and Canonical Mapping
        |
        v
WP-2.TI Database-Enforced Tenant Integrity
        |
        +--> WP-2.10A OIKB Governance and Version Binding
        |          |
        |          v
        |     WP-2.08A Governed Evidence Binding
        |
        +--> WP-2.14A Action Governance
        |          |
        |          v
        |     WP-2.15A Economics Integrity
        |
        v
WP-2.09R Reliability Orchestration Decision Gate
        |
        v
WP-2.CERT Phase 2 Intelligence Recertification
```

WP-2.12A, WP-2.13A, and WP-2.09A may be implemented independently after explicit package
authorization because they correct confirmed defects without depending on governed mappings.
Broader reproducibility, evidence, action, and economics claims remain blocked until WP-2.06A
and tenant-safe integrity are complete.

## 6. Work package WP-2.12A — Forecasting Integrity Correction

### Purpose

Correct confirmed forecasting behavior that can misalign time series, accept the wrong
readiness level, understate forecast uncertainty, or drift across calendar periods.

### In scope

- Preserve timestamp/value pairing through every filtering and preparation step.
- Require a tenant-owned forecasting-level readiness decision.
- Replace current-observation residuals with one-step-ahead or governed backtest residuals.
- Persist interval method code/version, calibration size, confidence level, and limitations.
- Define minimum calibration size; return structured insufficient-data when unmet.
- Use calendar-aware monthly, quarterly, and annual offsets.
- Reject unsupported forecast methods without implicit substitution.
- Correct forecasting idempotency inputs where bounded to the forecasting service.

### Non-scope

- New forecasting algorithms.
- Automated model search.
- WP-2.06A governed dataset bindings.
- Reliability integration.

### Acceptance tests

- Removing an interior partial/error observation retains the matching timestamp/value pairs.
- A statistical or reliability readiness decision is rejected for forecasting.
- Forecast intervals match approved numerical fixtures using one-step-ahead/backtest errors.
- Insufficient calibration returns a structured non-success outcome.
- Month-end, leap-year, quarterly, annual, and timezone boundary fixtures pass.
- Unsupported methods fail explicitly and produce no successful execution.
- Historical execution fields remain readable.

### Migration

Additive migration only if interval metadata or request fingerprints require new columns.
Existing interval results are labeled with their historical method; they are not recomputed.

### Required gates

Ruff, Mypy, full Pytest, numerical reference fixtures, API/service tests, and disposable
PostgreSQL migration/service tests.

## 7. Work package WP-2.13A — Reliability Truth and Safety Correction

### Purpose

Align reliability claims, validation, evidence, and safety behavior with the methods actually
implemented.

### In scope

- Set Weibull `supports_censoring=false` and reject/route censored Weibull input unless a
  separately validated censor-aware estimator is explicitly approved.
- Ensure Kaplan-Meier censoring behavior remains independently tested.
- Validate failure, repair, event, exposure, and time inputs at the engine boundary.
- Reject fractional counts, booleans, strings, negative counts, invalid times, NaN, and
  infinity.
- Persist method limitations and censoring disposition in evidence.
- Require manual/human review for every reliability-driven action in the initial policy.
- Correct documentation that currently implies progressive-orchestrator participation.

### Non-scope

- Implementing a new censor-aware Weibull estimator.
- Automatic Reliability orchestration.
- Automatic action approval.

### Acceptance tests

- Censored Weibull input fails closed with a structured unsupported-method/assumption result.
- Fractional and nonnumeric counts are rejected without truncation.
- Authoritative uncensored Weibull and Kaplan-Meier fixtures pass.
- Limitations and method version are persisted.
- Reliability-driven action creation cannot bypass human approval.
- Tenant, authorization, and error-envelope tests pass on SQLite and PostgreSQL.

### Migration

No migration is expected unless evidence or review-policy fields are absent. Any new field is
additive and nullable for historical rows.

## 8. Work package WP-2.09A — Canonical Idempotency and Replay Contract

### Purpose

Prevent reuse of an idempotency key with different analytical content and make retry behavior
consistent across direct intelligence, forecasting adapters, and progressive orchestration.

### In scope

- Define a canonical request-fingerprint envelope containing tenant, operation, exact
  definition/method version, readiness binding, input content digest or governed snapshot,
  parameters, time/evaluation context, publication intent, and relevant evidence fingerprint.
- Direct intelligence execution compares the new fingerprint before returning an existing
  request.
- Orchestration includes canonical record content, not only record count.
- Forecast adapter propagates the orchestration idempotency context.
- Same key/same fingerprint returns the original result.
- Same key/different fingerprint returns 409.
- Concurrent identical requests create one aggregate and one evidence/finding set.
- Database uniqueness races map to deterministic replay or conflict.

### Non-scope

- Retrofitting governed stored input before WP-2.06A.
- Action or economics idempotency, which remain in their domain packages.

### Compatibility

Historical rows without request fingerprints remain readable. A legacy replay must not be
silently treated as a verified exact retry unless its fingerprint can be reconstructed.

### Acceptance tests

- Same key and same count with different record values returns 409.
- Direct intelligence key reuse with changed records/parameters returns 409.
- Changed readiness, lineage, method, finding candidate, or publication intent returns 409.
- Concurrent PostgreSQL requests create exactly one execution.
- Retry does not duplicate findings, evidence, stages, usage events, or lineage.

## 9. Work package WP-2.06A — Governed Analytical Input and Canonical Mapping

### Purpose

Bind Trust and downstream intelligence to immutable, reproducible, tenant-isolated source
selections, canonical schemas, mapping versions, projections, and processing lineage.

### Entry gate

The WP-2.06A execution specification must be revised to resolve every independent architecture
review change request, then receive focused approval. That approval does not imply
implementation authorization.

### Required increments

1. Immutable governed-input snapshots.
2. Persistent canonical and source schema definitions and versions.
3. Governed mapping definitions and immutable mapping versions.
4. Governed projections with immutable readable output generation and digest.
5. Trust binding to one coherent input/schema/mapping/projection/ProcessingRun tuple.
6. Backward-compatible `inline_manual` and `legacy_unbound` treatment.

### Mandatory architecture corrections

- Use `selection_mode` for snapshots and reserve `input_mode` for Trust compatibility.
- Define raw-object cardinality and database mode/cardinality checks.
- Define canonical digest serialization completely.
- Use concrete composite tenant-safe key templates.
- Make projection bindings one coherent database-enforced tuple.
- Persist legal-hold application/release evidence.
- Define retention precedence for retained assessments.
- Preserve the v1 inline shape for at least 180 days after governed-input general availability;
  removal requires telemetry, customer notice, and separate API-version approval.
- Define meter units, aggregation, emission, deduplication, and failure behavior.

### Exit gate

No downstream capability may claim exact replay from governed data until WP-2.06A has passed
independent PostgreSQL recertification.

## 10. Work package WP-2.TI — Database-Enforced Tenant Integrity

### Purpose

Make cross-tenant edges impossible at the database layer across the intelligence flow.

### In scope

- Add `(organization_id, id)` unique keys to tenant-owned parents.
- Replace or supplement single-column foreign keys with composite organization/ID foreign keys.
- Cover intelligence executions/evidence, orchestration requests/stages/decisions, findings,
  lineage, actions/dependencies/resources/evidence/outcomes, opportunities, scenarios,
  assumptions, calculations, overlap groups, prioritizations, and approved baselines.
- Validate historical rows before enabling constraints.
- Add organization-first indexes matching service access paths.

### Rollout

1. Inventory and prove no mismatched historical rows.
2. Add parent unique keys and supporting indexes.
3. Add composite constraints using a bounded PostgreSQL lock strategy.
4. Validate constraints.
5. Retain service-layer tenant filters.

### Rollback

Downgrade removes only the new constraints and indexes. It must not rewrite or delete domain
data. A mismatch discovered during rollout stops deployment and produces a redacted audit
report.

### Acceptance tests

Direct SQL cross-tenant inserts fail for every managed edge. API responses remain
non-enumerating. Migration lock duration and representative-volume performance are recorded.

## 11. Work package WP-2.10A — OIKB Governance and Version Binding

### Purpose

Make OIKB the authoritative owner of governed analytical definitions while keeping execution
registries bounded and deterministic.

### In scope

- Define the contract between OIKB method definitions and executable registry versions.
- Add exact immutable OIKB-definition-version references to governed executions.
- Verify stored definition fingerprint matches the referenced version.
- Enforce author/validator/approver/activator segregation for production/reference-grade
  definitions.
- Provide a governed, audited emergency exception without silent self-approval.
- Define predicate-match versus business-breach semantics.
- Reject deprecated, ambiguous, or unsupported definitions for new executions.

### Compatibility

Legacy code-backed executions retain code/version/fingerprint and are explicitly classified.
No synthetic foreign key is assigned without verifiable identity.

### Acceptance tests

- Author cannot approve their production/reference-grade definition.
- Exact version cannot be substituted after execution.
- Registry behavior changes require a new method version.
- `BETWEEN` and other rule operators have unambiguous business fixtures.
- Shared and private definitions remain tenant/scope isolated.

## 12. Work package WP-2.08A — Governed Evidence Binding

### Dependencies

WP-2.06A and WP-2.10A.

### Purpose

Make finding, calculation, rule, and aggregate evidence traceable to exact governed inputs and
definitions.

### In scope

- Bind canonical evidence to governed projection, record locator, and digest.
- Bind aggregate evidence to a bounded derivation manifest.
- Bind finding evidence to exact execution, OIKB definition version, readiness decision,
  input snapshot, mapping, projection, and ProcessingRun.
- Preserve bounded sampling and payload limits.
- Define the legacy finding path as non-governed and prevent it from satisfying governed
  publication requirements.

### Acceptance tests

- Nonexistent, cross-tenant, or cross-projection evidence is rejected.
- Published evidence is immutable.
- Retry creates one finding/evidence bundle.
- Failed, blocked, unsupported, and insufficient executions cannot create publishable findings.
- Historical evidence remains resolvable after definition supersession and payload expiration.

## 13. Work package WP-2.14A — Action Governance and Concurrency

### Purpose

Ensure each action has one coherent source, stable evidence, conflict-safe idempotency, and an
immutable governed lifecycle.

### In scope

- Use a discriminated exactly-one source contract.
- Bind source type, source ID, execution/version fingerprint, finding/reliability evidence, and
  governed lineage coherently.
- Fingerprint action creation, assignment, and transition commands.
- Return 409 on key reuse with different content.
- Use row locking, version columns, or compare-and-swap for lifecycle transitions.
- Enforce a per-state mutation matrix for plans, dependencies, resources, evidence, assignment,
  expected outcomes, completion, and verification.
- Freeze approval and verification inputs; later corrections are append-only revisions.
- Detect dependency cycles beyond immediate reverse edges.
- Keep completion distinct from evidence-backed verification.

### Acceptance tests

- Multiple or mismatched source IDs are rejected.
- Cross-tenant sources/evidence fail at service and database layers.
- Concurrent transitions produce one valid state history.
- Terminal actions reject mutable planning/resource/evidence changes.
- Verification requires authorized actor and governed evidence.
- Reliability-driven actions require human approval.

## 14. Work package WP-2.15A — Recovery Economics Integrity

### Purpose

Make approved financial conclusions reproducible, conserved, currency-governed, and safe under
concurrency.

### In scope

- Bind each calculation to ordered immutable assumption IDs, versions, fingerprints, scenario
  version, engine version, rounding policy, currency, and valuation date.
- Approve exactly the calculation/assumption set that produced the baseline.
- Persist an immutable approved-baseline fingerprint.
- Define one overlap policy with group exclusivity/allocation semantics.
- Enforce allocation conservation and prevent nondeterministic multi-group overwrite.
- Lock or serialize overlap, version, prioritization, and approval operations.
- Fingerprint every consequential idempotent command and return 409 on conflicting reuse.
- Define `ever_approved` or baseline-aware immutability.
- Make amendments append-only.
- Implement approved currency minor-unit, analytical precision, rounding-stage, FX source/date,
  and conservation contracts.
- Preserve estimated, expected, approved, realized, and verified value as distinct states.

### Owner decisions required before implementation

- Currency minor-unit table and update authority.
- Whether cross-currency portfolios are prohibited or require an approved FX conversion layer.
- Approved FX source hierarchy and valuation-date behavior.
- Overlap model: exclusive membership, conserved fractional allocation, or governed hierarchy.

Until those details are approved, default behavior is:

- no cross-currency aggregation;
- no implicit FX conversion;
- one overlap group per opportunity;
- allocation totals must equal exactly one for included group members.

### Acceptance tests

- Approved calculations replay exactly after later assumption revisions.
- Multi-group/nested overlap cannot silently overwrite allocation.
- Allocation totals conserve value under parallel requests and rounding.
- Same idempotency key with changed economics inputs returns 409.
- JPY, USD, and three-decimal currency fixtures follow the approved policy.
- Zero cost, negative benefit, extreme value, and division-by-zero cases are explicit.
- Historical approved baselines remain immutable after status changes.

## 15. Work package WP-2.09R — Reliability Orchestration Gate

### Purpose

Decide whether and how Reliability participates in progressive orchestration after reliability
truth, governed inputs, evidence binding, and human-review controls are certified.

### Initial approved safety policy

- Reliability remains opt-in/manual.
- No reliability result automatically creates, approves, assigns, executes, or verifies an
  action.
- Every reliability-driven action requires human approval.
- Until governed high-impact thresholds are approved, all reliability findings are treated as
  high impact for automation purposes.

### Adapter requirements if later authorized

- Exact reliability readiness and governed input binding.
- Deterministic method selection with no fallback.
- Structured unsupported/insufficient/blocked/failure translation.
- Exact execution and evidence propagation.
- No automatic finding publication above configured impact thresholds.
- No automatic action approval.
- Entitlement and tenant applicability rechecked at worker execution time.

## 16. Work package WP-2.CERT — Intelligence Recertification

### Entry requirements

- All accepted P1 findings closed.
- Accepted P2 certification blockers closed or explicitly waived by governance.
- WP-2.06A independently certified.
- Approved ADR policies implemented and documented.

### Required certification suites

- Tenant isolation at API, service, and direct-SQL layers.
- Role, entitlement, publication, approval, and verification authority.
- Canonical idempotency and PostgreSQL concurrency.
- Numerical golden fixtures for arithmetic, statistics, forecasting, reliability, and
  economics.
- Unsupported, insufficient, blocked, failed, partial, and warning semantics.
- Exact definition/method/input/evidence replay.
- Finding-to-action-to-economics continuity.
- Migration empty-to-head, per-revision downgrade/re-upgrade, drift, offline SQL, constraint
  inspection, and seed ownership.
- Representative-volume query plans and migration lock-duration evidence.
- Secret scan and generated-artifact review.

### Certification decision

Certification uses a separate independent reviewer. Passing engineering tests alone does not
constitute certification.

## 17. Cross-package backward compatibility

- Existing API v1 request/response shapes remain supported unless a separately approved package
  says otherwise.
- Existing analytical rows remain readable.
- New provenance and fingerprint columns are nullable for historical rows.
- Historical rows are labeled honestly as `inline_manual`, `legacy_unbound`, or equivalent.
- No migration invents governed provenance for historical rows.
- Existing findings/actions/economics records are not recomputed automatically.
- Corrected algorithms use new method versions where output semantics change.
- Historical method versions remain identifiable and non-default for new execution.

## 18. Rollout and rollback

Each implementation package must:

1. deploy additive schema changes with writes disabled;
2. validate historical data and constraints;
3. deploy compatible read paths;
4. enable internal/demo tenants;
5. execute shadow or golden comparisons;
6. enable selected tenants through explicit entitlement;
7. monitor conflicts, unsupported outcomes, latency, and evidence continuity;
8. retain a kill switch for new writes/executions.

Rollback disables new writes first. Schema downgrade occurs only after verifying that no new
rows depend on the removed contract. Destructive rewrites are prohibited.

## 19. PostgreSQL certification strategy

Every package with migrations, database constraints, concurrency, lifecycle, or idempotency
changes requires:

- an explicit disposable `TEST_POSTGRES_URL`;
- `CONFIRM_DISPOSABLE_POSTGRES=1`;
- a recognized disposable database name;
- proof that the target differs from runtime/production/customer databases;
- empty-to-head upgrade;
- package-boundary downgrade and re-upgrade;
- direct schema and constraint inspection;
- `alembic check`;
- offline PostgreSQL SQL generation;
- PostgreSQL-specific behavioral and concurrency tests;
- independent cleanup verification.

No production, Mobility, shared demonstration, or customer database may be used.

## 20. Package authorization template

Before coding any package, the owner must approve:

- package identifier and purpose;
- in-scope and non-scope boundaries;
- accepted findings and ADRs;
- migration expectation;
- backward-compatibility behavior;
- exact acceptance tests;
- PostgreSQL certification requirement;
- branch name;
- whether independent review is mandatory;
- rollout and rollback authority.

Authorization of one package does not authorize another.

## 21. Specification approval decisions

The owner must decide:

1. Approve or revise the package decomposition.
2. Approve parallel correction of WP-2.12A, WP-2.13A, and WP-2.09A.
3. Approve WP-2.06A as the required reproducibility foundation, subject to its focused
   specification re-review.
4. Approve a dedicated cross-domain tenant-integrity migration package.
5. Approve the initial Reliability policy that treats every reliability-driven action as
   human-review-required.
6. Approve the default economics policy of no implicit FX conversion and conserved,
   single-group overlap until detailed owner policy is supplied.
7. Approve independent recertification as the final Phase 2 closure gate.

Approval of this specification authorizes preparation of package-specific execution prompts.
It does not authorize implementation unless the approval explicitly names the package and
states that coding may begin.

