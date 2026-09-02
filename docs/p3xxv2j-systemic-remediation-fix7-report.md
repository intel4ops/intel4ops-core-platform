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

The required post-deploy rerun of the ten frozen production simulations was not
performed because no authenticated production session or API credential was
available. Therefore production publication attempts, dedupe decisions, subject
identities, and persisted finding counts remain unmeasured for this deployment.
No unrelated recall improvement is claimed.

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

**FIX #7 PARTIALLY VALIDATED**

The implementation, controlled fixture, local regression suite, Linux CI, merge,
and public deployment health are validated. Full validation is withheld solely
because the same fixture and frozen Wave 1 corpus were not rerun against an
authenticated production deployment and the health endpoint cannot attest its
commit SHA.

## N. Remaining blockers

- Production authentication is required for post-deploy controlled and Wave 1
  behavioral certification.
- FieldMaintenance XDOM-A remains blocked by the untouched domain-classification
  issue.
- Rental's current downtime/dispatch windows remain legitimate non-overlaps under
  the unchanged XDOM-A model.
- XDOM-B capability/coverage limitations remain unchanged.

## O. Architectural convergence assessment

The remediation program is crossing toward **intelligence model / capability
coverage defects dominant**, but has not completed that transition. Rental's
generic semantic, entity, readiness, temporal, and now finding-identity plumbing
has been corrected without changing model logic; its remaining zero XDOM-A result
is an actual window-model/data outcome. The broad Wave 1 taxonomy still exceeds
registered capability coverage. However, FieldMaintenance retains one known
foundational domain-classification defect, so foundational generalization defects
are no longer uniformly dominant but are not fully eliminated.

No Fix #8, FieldMaintenance remediation, XDOM-B remediation, capability expansion,
Wave 2, E.6, E.7, or frontend work was started.
