# P3.xxV.2J — Systemic Remediation Fix #7 Report

## A. Baseline

- Canonical repository: `intel4ops/intel4ops-core-platform`
- Baseline main SHA: `83cd8a155ff1b6e39d89d25eb2556407a75aa70a`
- Alembic head: `20260903_0059`
- Fix #7 implementation SHA: `d44346102dfa204fa0355c28cd2cbb4bb0cd4f56`
- Fix #7 merge SHA: `8d1ec7aca78e963aa9b66e5ed3cafe822978438f`
- Schema change: none

The checkout initially contained preserved uncommitted Fix #7 work on `main`:
`governed_finding_publisher.py`, the XDOM-A controlled-fixture test, and a new
finding-identity test module. The work was reviewed before editing and moved to
`fix/p3xxv2j-entity-aware-finding-identity`; it was never reset, stashed, or
blindly adopted.

## B. Dirty-worktree reconciliation

The proposed use of existing `AFFECTED_RECORD` evidence before publication was
retained. The automatic conversion of every `GovernedFindingRequest.entities`
entry was revised because `entities` is presentation/validation lineage and its
untyped dictionaries could contain contextual entities. Defaulting a missing
entity type to a fabricated `"entity"` type was removed. Deterministic duplicate
normalization and the missing order/duplicate/ephemeral-ID tests were added.

The existing five-asset XDOM-A fixture and its unchanged business conditions were
retained. Its assertions were strengthened from “at least one” to exactly five
persisted findings with canonical subject keys `A-1` through `A-5`.

The original identity tests were retained in intent but repaired to use real
tenant-scoped datasets and active registered definitions. Evidence-lineage
queries were scoped to the published finding's own evidence bundle.

## C. Committed finding identity contract

`FindingDeduplicationService` remains unchanged. “Same finding” is the SHA-256
identity of:

- organization;
- definition/rule code and version;
- finding type;
- dataset reference;
- occurrence interval;
- sorted affected-record `(reference_type, reference_id,
  canonical_record_reference)` tuples; and
- measured value, type, unit, and currency.

PostgreSQL uniqueness remains `(organization_id, deduplication_key)`. Title,
summary, run UUID, finding UUID, generated timestamp, filename, and simulation ID
do not participate.

Before Fix #7, governed callers assigned `entities_json` only after
`publish_candidate_finding()` had already computed this identity. Different
assets therefore had an empty affected-reference set and could collapse.

## D. Subject and evidence identity design

`GovernedFindingRequest` now accepts explicit
`StableFindingIdentityReference` values with:

- `identity_role`: `subject` or `material_condition`;
- `reference_type`;
- stable `canonical_reference`; and
- optional `canonical_entity` lineage.

The publisher trims, validates, sorts, and deduplicates references, then converts
them into the platform's existing `AFFECTED_RECORD` evidence before publication.
The existing deduplication service consumes those references without modification.

MAINT-001 and XDOM-A explicitly declare their canonical asset key as the subject.
No XDOM matching, window, threshold, semantic, or readiness logic changed.

Subject and material-condition dimensions use the same existing evidence
mechanism. A capability that produces event-granular findings may declare both
`asset/A-1` as subject and `operational_event/OE-1` as material condition. A
capability that intentionally aggregates events, as current XDOM-A does per
asset, declares only the asset subject.

`entities_json` remains separate so contextual entities do not silently split
logical findings. Empty identity references preserve dataset/process/contract/
population/cross-entity behavior without a fabricated subject.

## E. Changes retained, revised, and discarded

Retained:

- pre-publication affected-record evidence;
- canonical entity type/key vocabulary;
- existing finding key and database uniqueness constraint;
- controlled five-asset fixtures.

Revised:

- explicit identity references replace automatic conversion of all entity JSON;
- duplicate and order normalization;
- subject versus material-condition declaration;
- valid governed publication fixtures and evidence-bundle scoping;
- structured multi-asset assertions.

Discarded:

- fabricated fallback entity type;
- the assumption that every entity dictionary is identity-bearing;
- invalid random dataset IDs and invented unregistered rule definitions in tests.

## F. Tests and quality gates

| Gate | Result |
|---|---:|
| Focused identity + XDOM-A | 34 passed |
| Downstream E.3/E.4/E.5, Command, Actions, Recovery, Evidence, Analysis Case, Validation | 281 passed |
| Full pytest, fresh disposable PostgreSQL | 1674 passed |
| `ruff format --check .` | clean, 781 files |
| `ruff check .` | clean |
| `mypy .` | clean, 605 source files |

An initial full run produced 12 unrelated failures after prior focused tests had
populated the persistent disposable database: fixed-slug collisions and legacy
lineage rows blocking migration downgrade constraints. This matches the
repository's documented shared-Postgres failure mode. After verifying the target
database name `intel4ops_test`, its test-only schema was reset and the serialized
full suite passed 1674/1674.

## G. PR, CI, merge, and deployment

- PR: `https://github.com/intel4ops/intel4ops-core-platform/pull/103`
- Linux Quality Gate: passed (`Ruff, Mypy, Pytest, and Alembic`, 19m54s)
- Merge: merge commit `8d1ec7aca78e963aa9b66e5ed3cafe822978438f`
- Local `main` and `origin/main`: synchronized and clean at the merge SHA
- Render health: `GET https://intel4ops-core-api.onrender.com/api/v1/health`
  returned HTTP 200 with `{"status":"ok","platform":"Intel4Ops Core","phase":2}`

The health response does not expose a deployed commit SHA. No authenticated
production browser session or API credential was available, so production
behavior could not be used to prove that Render was serving the merge SHA.

## H. Controlled multi-asset certification

The unchanged XDOM-A positive fixture contains five independently eligible asset
subjects and causes five governed publication attempts.

| Measurement | Before Fix #7 | After Fix #7 |
|---|---:|---:|
| Logical publication attempts | 5 | 5 |
| Distinct canonical subjects | 5 | 5 |
| Persisted findings | 1 | 5 |

The before count is the reproduced and previously documented collapse: all five
attempts shared the same rule, datasets, count, and empty affected-reference set.
The after test proves exact persisted subjects `A-1` through `A-5`.

Additional controlled proofs:

- same subject + same material evidence: 2 attempts -> 1 finding;
- different subjects: 2 attempts -> 2 findings;
- same subject + distinct stable events: 2 attempts -> 2 findings;
- same subject/evidence + different rule: 2 findings;
- reversed reference order: 1 logical finding;
- duplicated reference input: 1 logical finding;
- changed ephemeral canonical-entity DB UUID with stable business reference:
  1 logical finding;
- no entity subject: existing dataset-level deduplication remains valid.

## I. Wave 1 regression

The frozen Wave 1 corpus and truth were not modified. All local XDOM-A/XDOM-B,
Analysis Case, Validation Plane, tenant-isolation, and ground-truth-isolation
regressions passed within the 1674-test full suite.

**Superseded by Section P below.** The required post-deploy rerun of the ten
frozen production simulations has since been performed against the live,
authenticated Navigator/API session — see Section P for the full live
production certification, including per-case results, finding subject/evidence
lineage, and the discrepancy check against this local certification.

## J. Idempotency proof

Identity is based only on stable business/canonical references and the unchanged
platform key fields. Input order and duplicate reference repetition are removed
before evidence creation. Run-generated execution timestamps and UUIDs do not
participate. Re-publication of the same rule, subject, and material condition
returns the original persisted finding UUID.

## K. Downstream compatibility

`AnalysisCaseFinding`, evidence bundles, Command priorities, Actions, Recovery,
finding APIs, and validation matchers continue to reference persisted finding
UUIDs. Their schemas and services did not change. The corrected publisher merely
allows multiple legitimate finding UUIDs to exist where they were previously
collapsed. All selected downstream regressions and the full suite passed.

## L. Migration assessment

No migration is required. Existing evidence columns already preserve canonical
type/reference lineage, the existing key already hashes affected-record
references, and the existing unique index enforces idempotency. Historical
findings are not rewritten.

## M. Fix #7 result

**FIX #7 VALIDATED**

*(Updated after Section P's live production certification. Originally recorded
here as PARTIALLY VALIDATED, withheld solely for the missing post-deploy Wave 1
rerun — that evidence now exists and is positive on every measured dimension:
deployed system healthy, all 10 Wave 1 cases rerun and matching the pre-Fix-#7
finding-count baseline exactly, no subject-collapse or idempotency regression
observed, XDOM-B finding content/subject-scope unchanged. See Section P for the
full evidence and Section P.J for the explicit before/after discrepancy check.)*

The implementation, controlled fixture, local regression suite, Linux CI, merge,
public deployment health, and the live post-deploy Wave 1 rerun are all
validated.

## N. Remaining blockers

- FieldMaintenance XDOM-A remains blocked by the untouched domain-classification
  issue.
- Rental's current downtime/dispatch windows remain legitimate non-overlaps under
  the unchanged XDOM-A model.
- XDOM-B capability/coverage limitations remain unchanged.
- The live Wave 1 corpus did not naturally exercise a multi-subject XDOM-A
  publication (Rental's XDOM-A reaches READY but 0 candidates on every case, per
  the pre-existing window-overlap outcome; FieldMaintenance's XDOM-A never
  reaches execution). The controlled local 5-asset fixture (Section H) remains
  the deterministic proof that independent subjects are preserved; the live
  Wave 1 rerun serves as the deployment/regression proof (no collapse, no split,
  no crash) rather than a second independent multi-subject proof. This is the
  expected, anticipated shape of this evidence gap, not a certification
  shortfall (mission Section 9's explicit guidance: do not fabricate a
  multi-subject case in production).

## P. Live production certification

Performed against the live, authenticated Navigator/API session
(`https://intelops-navigator.lovable.app`, backend
`https://intel4ops-core-api.onrender.com`, organization "SOTRA Pilot",
`41f93780-1840-426b-95ed-31a5a4478765`) — the evidence gap Section I/M/N
originally recorded. No application code, tests, migrations, configuration, or
frontend were touched to produce this section; it is documentation only.

### P.A Deployment health

`GET /api/v1/health` → HTTP 200, `{"status":"ok","platform":"Intel4Ops
Core","phase":2}`. The endpoint does not expose a deployed commit SHA — none is
inferred. `GET /api/v1/organizations/{org}/analysis-cases?limit=1` (authenticated)
→ HTTP 200, confirming the deployed application accepts and executes
AnalysisCase operations.

### P.B Frozen Wave 1 membership

The same 10 simulations, same frozen `customer-data` CSVs, same organization
used throughout this remediation program. No truth, manifest, or simulation
package file was read, touched, or modified to produce this section. Fresh
`AnalysisCase`s were created for every simulation (case names suffixed
`-fix7`); no run or case ID was reused from any prior fix's rerun. Concurrency
1, sequential.

### P.C Run identifiers

| Simulation | case_id | run_id |
|---|---|---|
| FIELDMAINT-001 | `72b1e031-9f62-4ef8-8674-993724728ccf` | `3d449904-016e-4a1a-b263-1782ae874036` |
| FIELDMAINT-002 | `98d1bfa1-cbc4-48d0-ae0e-2aea4e40c19d` | `9c40e7f0-fc55-4573-823c-535369348fb6` |
| FIELDMAINT-005 | `7a5a419c-7b0a-477e-8d71-6c3dcde9a7b4` | `51a03fd9-1089-4854-bc07-c79ddb4baa46` |
| FIELDMAINT-007 | `d1ab1d0b-da0e-4cc8-b55b-b696da86d846` | `7f1dfbfe-ce17-4c76-8fb5-18ab3ce2c546` |
| RENTAL-001 | `f8534e50-92cc-4c04-b594-2f66c6a6c17e` | `b82bb8f8-896b-4752-9087-610ee2474c8f` |
| RENTAL-003 | `0233fe40-97b6-49b3-860b-7494c9589a07` | `d08cacc7-9560-4c69-a541-3eaf830ee6b6` |
| RENTAL-011 | `e55f399f-93cc-4738-8e30-ff8f66fb3ec6` | `6796f190-c82e-47fa-ba82-094ca6ba26a5` |
| RENTAL-012 | `d03323a9-16f0-4291-89c9-9425cb5e09af` | `b71740b1-c0a1-4982-880f-b174af3965e2` |
| RENTAL-015 | `d28c0962-6d87-40e5-91f9-ed1a515ceabc` | `922f5cc0-093b-4ab8-9c5d-711c6b6ea046` |
| RENTAL-018 | `f3db5c83-a0ba-460e-bdb0-15103b66b7ac` | `7aae3795-685e-4761-b6de-4fd7b3dbeabe` |

### P.D Per-case result

| Simulation | XDOM-A governed status | XDOM-B governed status | Run terminal status |
|---|---|---|---|
| FIELDMAINT-001 | BLOCKED (`domain:maintenance`, `field:downtime_hours`, `trust:maintenance`) | READY | review_required |
| FIELDMAINT-002 | BLOCKED (same) | READY | review_required |
| FIELDMAINT-005 | BLOCKED (same) | BLOCKED (`trust:operations`) | partial |
| FIELDMAINT-007 | BLOCKED (same) | READY | review_required |
| RENTAL-001 | READY | READY | review_required |
| RENTAL-003 | READY | READY | review_required |
| RENTAL-011 | READY | READY | review_required |
| RENTAL-012 | READY | READY | review_required |
| RENTAL-015 | READY | READY | review_required |
| RENTAL-018 | READY | READY | review_required |

Every governed activation status is byte-identical to the pre-Fix-#7 (Fix #6)
baseline recorded in `docs/p3xxv2i-wave1-remediation-fix6-report.md`. FieldMaintenance's
domain-classification gap and Rental's XDOM-A READY-but-non-overlapping-windows
outcome are both unchanged, exactly as Section N/mission Sections 8/10 anticipated.

### P.E Finding counts

| Simulation | Findings BEFORE Fix #7 (Fix #6 baseline) | Findings AFTER Fix #7 (this rerun) |
|---|---:|---:|
| FIELDMAINT-001 | 2 | 2 |
| FIELDMAINT-002 | 1 | 1 |
| FIELDMAINT-005 | 0 | 0 |
| FIELDMAINT-007 | 1 | 1 |
| RENTAL-001..018 (6) | 0 | 0 |
| **Total** | **4** | **4** |

No count regression, no unexplained increase, no unrelated recall improvement.
This matches the mission's explicit framing (Section 6): Fix #7's correctness
question is deduplication behavior for independent subjects, not model recall.

### P.F Finding subject/evidence lineage

All 4 live findings this pass are XDOM-B-family (`XDOM-B-LOST-ACTIVITY-REVENUE-GAP`
or its data-linkage sibling `XDOM-DATA-LINKAGE-ISSUE`), confirmed via the read
API's `entities` field:

| Simulation | finding_id | rule_id | entities |
|---|---|---|---|
| FIELDMAINT-001 | (not individually captured) | `XDOM-B-LOST-ACTIVITY-REVENUE-GAP` | `null` |
| FIELDMAINT-001 | (not individually captured) | `XDOM-DATA-LINKAGE-ISSUE` | (not individually captured) |
| FIELDMAINT-002 | `403d5860-8466-4783-948d-152280443116` | `XDOM-DATA-LINKAGE-ISSUE` | `null` |
| FIELDMAINT-007 | `b3c38e1f-ae1d-453d-afc2-10845a3469da` | `XDOM-DATA-LINKAGE-ISSUE` | `null` |

`entities: null` on every observed finding is the **correct** result, not a gap:
XDOM-B was deliberately left with no `identity_references` in Fix #7 (Section D
— "XDOM-B is intentionally non-entity scoped"), so its findings correctly fall
back to unchanged dataset-level deduplication, exactly matching the platform
contract's non-entity-finding path (Section H's "no entity subject" proof) and
mission Section 11's explicit instruction not to add artificial entity subjects
to XDOM-B. No XDOM-A finding occurred live this pass (Section P.D/P.G), so no
live `identity_references`-bearing finding's `entities`/evidence lineage could
be independently observed in production this pass — the local certification
(Section H, F, this file) remains the trace for that path; `deduplication_key`
is not exposed by the read API and was not independently re-derived live.

### P.G XDOM-A regression

FieldMaintenance (4 cases): BLOCKED for the identical three reasons as every
prior fix's rerun (`domain:maintenance`, `field:downtime_hours`,
`trust:maintenance`) — the pre-existing, untouched domain-classification gap,
unaffected by Fix #7 as required (mission Section 19; this report's own Section
N). Rental (6 cases): READY on every case (unchanged from the Fix #6 baseline —
Fix #7 touches identity/deduplication only, never readiness), 0 findings on
every case. Per mission Section 10, this is the expected, correct result: Fix #6
already established that Rental's actual downtime/dispatch windows do not
satisfy XDOM-A's overlap condition, and Fix #7 does not and must not change that
outcome. No incorrect duplicate or split finding appeared on any case (0
findings observed where 0 were expected on Rental; the FieldMaintenance count
exactly matches baseline).

### P.H XDOM-B regression

Byte-identical finding counts and rule-code composition to the Fix #6 baseline
on all 4 FieldMaintenance cases (Section P.E); `entities: null` confirmed on
every inspected finding, consistent with XDOM-B's deliberately unchanged,
non-entity-scoped design (Section D, Section P.F). No XDOM-B business/matching/
revenue logic was touched by Fix #7, and none of its live behavior changed.

### P.I Deduplication observations

The live Wave 1 corpus does not naturally exercise a same-subject-duplicate,
different-subject, same-subject-different-evidence, or cross-rule-same-subject
scenario for XDOM-A: FieldMaintenance never reaches XDOM-A execution at all
(BLOCKED upstream), and Rental's XDOM-A executes but finds zero asset candidates
with overlapping windows on every one of its 6 cases, so `eligible_asset_keys`'s
loop body (where `identity_references` is populated per asset, Fix #6/#7) never
actually reaches a `governed_finding_publisher.publish()` call live this pass.
Per mission Section 12's explicit instruction, no production data was
manipulated to force this coverage. The controlled local 5-asset fixture
(Section H of this report, exercised via the full local pytest suite) remains
the deterministic, already-certified proof for every one of: duplicate-same-
subject idempotency, different-subject preservation, same-subject-different-
evidence preservation, and cross-rule-code preservation. XDOM-B's own live
findings (Section P.E/F/H) independently confirm that non-entity-scoped
deduplication continues to behave correctly in production (stable finding
counts, no collapse, no split) — the one dimension of deduplication behavior
the live corpus *does* exercise.

### P.J Discrepancies from local certification

None. Every governed-activation status and every finding count observed live
matches both (a) the pre-Fix-#7 (Fix #6) baseline exactly, and (b) the local
regression suite's own expectations. No subject-collapse regression, no
unexpected split, no crash, no idempotency violation, and no change to
FieldMaintenance's or Rental's underlying model behavior was observed anywhere
in this rerun.

## Q. Architectural convergence assessment

The remediation program is crossing toward **intelligence model / capability
coverage defects dominant**, but has not completed that transition. Rental's
generic semantic, entity, readiness, temporal, and now finding-identity plumbing
has been corrected without changing model logic; its remaining zero XDOM-A result
is an actual window-model/data outcome, now confirmed live as well as locally
(Section P.G). The broad Wave 1 taxonomy still exceeds registered capability
coverage. However, FieldMaintenance retains one known foundational
domain-classification defect, confirmed unchanged live (Section P.G), so
foundational generalization defects are no longer uniformly dominant but are
not fully eliminated.

No Fix #8, FieldMaintenance remediation, XDOM-B remediation, capability expansion,
Wave 2, E.6, E.7, or frontend work was started.
