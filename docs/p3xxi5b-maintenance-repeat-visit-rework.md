# P3.xxI.5B Maintenance Repeat Visit / Rework

## Implementation status

**Phase:** post-merge live certification complete

**Capability:** `MAINTENANCE-REPEAT-VISIT` (`MAINT-REPEAT`, version 1.0)

**Baseline:** authoritative `main` at
`cd3839bf2fcf83f03cb134fcf138b7cd670529ca`

**Implementation branch:** `feature/p3xxi5b-maintenance-repeat-visit`

This capability is additive and independent. `MAINT-001` remains unchanged.
It continues to identify repeated categorical failures; P3.xxI.5B instead
identifies a mechanically related prior/subsequent intervention pair and
reports its observed recurrence interval.

## Frozen certification denominator

The hidden-truth family was reconciled and frozen before implementation
findings were inspected:

| Frozen case | Truth scenario | Count | Truth-authored value |
|---|---|---:|---:|
| `FIELDMAINT-002` | `repeat_repair` | 38 | included below |
| `FIELDMAINT-007` | `repeat_repair` | 38 | included below |
| `FIELDMAINT-001` | `repeat_repair` | 0 | $0.00 |
| `FIELDMAINT-005` | `repeat_repair` | 0 | $0.00 |
| **Total** | **Maintenance Repeat Visit / Rework** | **76** | **$117,524.00** |

The denominator is examiner-side only and was not used to choose production
pairing logic. It will remain 76 for post-merge certification.

## P3.xxI.5B pre-implementation architecture diagnosis

### Existing evidence and control-plane support

The existing architecture already provides the minimum reusable primitives:

- canonical `ASSET` identity and governed identity confidence;
- `work_order_id`, mapped through the existing operational-event identifier
  bridge, as intervention identity;
- `completed_timestamp`, with `event_timestamp` as an explicit governed
  alternative;
- the existing maintenance-domain `activity_category` vocabulary and aliases
  (`event_type`, `activity_type`, `service_type`, `maintenance_type`, and
  `work_type`);
- maintenance Trust assessments, readiness decisions, stable finding identity,
  evidence items, calculation lineage, and tenant-scoped publication.

The architecture does not provide a governed repeat/rework policy window in
the frozen corpus. No global maintenance ontology, E.3/E.4 redesign, graph
engine, customer-specific taxonomy, or truth-derived pairing rule is needed
for the bounded observed-recurrence capability.

### Diagnosis answers

**A. Prior intervention evidence.** A non-null governed intervention identifier,
subject identifier, activity category, and timestamp on an eligible maintenance
record identify the prior intervention.

**B. Subsequent intervention evidence.** A distinct governed intervention
identifier with the same evidence contract and a strictly later governed
timestamp identifies the subsequent intervention.

**C. Comparison subject.** The comparison is scoped to canonical `ASSET`.
Each intervention/work-order identity remains separate in the finding.

**D. Relationship evidence.** The two interventions must share the same
canonical asset and the same normalized, governed activity category. Exact
category equality is deliberately narrower than free-text similarity. Merely
having another maintenance event on the asset is insufficient.

**E. Governed window.** None was found. The capability does not encode 7-, 30-,
90-day, or any other repeat threshold.

**F. Safe output without a window.** Yes. It can report an observed, mechanically
related recurrence and its elapsed interval while explicitly declining to
assert a policy violation or confirmed rework.

**G. Smallest generic contract.** Eligible canonical asset + distinct governed
intervention identities + exact governed activity-category equality + strict
timestamp ordering = observed related repeat-intervention candidate.

The stop gate did not trigger because the contract is satisfied with small,
additive registry, semantic-bridge, orchestration, and service changes.

## Mechanical contract

For every eligible maintenance record, the implementation requires:

1. a canonical asset key that clears the capability's 0.70 identity-confidence
   floor;
2. a governed intervention/work-order identifier;
3. a governed `completed_timestamp`, or governed `event_timestamp` alternative;
4. a governed activity category;
5. a resolved maintenance Trust assessment; and
6. complete canonical evidence for the exact fields used by the candidate.

Records are grouped by `(asset, normalized activity category)`. Interventions
are deduplicated by `(asset, intervention identity)`, sorted by governed
timestamp and deterministic identity, and paired only with the nearest
subsequent related intervention.

For a chain `A -> B -> C`, the output is `A -> B` and `B -> C`. It never emits
the transitive `A -> C` pair. This avoids combinatorial expansion and preserves
the most local mechanical recurrence relation.

## Temporal policy

The rule contains no time-window threshold. A positive interval is a measured
fact:

`elapsed_hours = subsequent_timestamp - prior_timestamp`

Every finding states that it is an observed related-intervention interval and
that no repeat/rework policy window was supplied. Severity is informational;
the finding does not claim a policy breach, defective repair, or avoidable
cost. Tied timestamps across distinct intervention identities cause abstention
because the sequence is ambiguous.

## Relationship evidence

Relationship evidence is exact and governed:

- same canonical asset; and
- exact equality after case-insensitive normalization of the governed activity
  category.

No free-text embedding, fuzzy similarity, filename branch, simulation ID,
hidden-truth label, failure-specific synonym table, or customer-specific
taxonomy is used. Different categories on the same asset do not pair.

## Readiness

The capability registry requires:

- maintenance domain evidence;
- canonical asset, operational-event/intervention ID, and activity category;
- canonical `ASSET` identity at or above 0.70;
- `completed_timestamp` or `event_timestamp` evidence;
- resolved maintenance Trust; and
- subject, intervention, category, and timestamp evidence requirements.

Currency and UOM are intentionally agnostic because the capability neither
aggregates money nor compares physical quantities. A generic end-to-end fixture
proves READY is reached through real multi-dataset asset corroboration rather
than a lowered confidence threshold.

## Finding identity and lineage

Stable finding identity includes:

- canonical asset subject;
- prior intervention identity;
- subsequent intervention identity; and
- normalized activity-category condition.

Each published finding preserves the primary and contributing dataset IDs,
maintenance Trust assessment, prior and subsequent record references,
timestamps, activity category, exact interval calculation, and a
`policy_violation_asserted: false` trace. Distinct repeat pairs therefore remain
distinct findings and cannot collapse into one case-wide identity.

Economic status remains governed-pending. No exposure is estimated because the
implementation has no governed pair-attributable rework cost.

## Safe abstention and duplicate handling

The implementation abstains when:

- the asset does not clear governed identity eligibility;
- intervention identity, timestamp, or activity category is missing;
- canonical evidence completeness fails;
- one intervention identity has conflicting category or timestamp
  representations;
- distinct interventions tie on timestamp within a related group; or
- no exact activity-category relationship exists.

Identical representations of one intervention across rows or datasets collapse
to one deterministic intervention. Source row order does not affect pairing.
Missing evidence is never interpreted as rework, and repeated maintenance alone
is never enough to publish.

## Implementation inventory

- `app/services/maintenance_repeat_visit_service.py` — deterministic evidence
  extraction, duplicate/conflict handling, adjacent pairing, interval
  calculation, and governed publication.
- `app/semantic/concept_registry.py` — reusable `activity_category` semantic
  concept using the established maintenance-category aliases.
- `app/intelligence_packs/registry.py` — governed capability/readiness contract.
- `app/registries/rule_registry.py` — independent versioned rule definition.
- `app/services/analysis_case_orchestration_service.py` — additive governed
  execution after readiness; existing `MAINT-001` execution is unchanged.
- `tests/test_maintenance_repeat_visit.py` — positive, negative,
  generalization, determinism, deduplication, and lineage coverage.
- `tests/test_capability_shadow_stage.py` — governed registry inventory updated
  for the additive capability.

No migration, truth, XDOM-A, XDOM-B, MAINT-001, frontend, E.6, or E.7 file is
changed.

## Tests and regression gates

| Gate | Result |
|---|---:|
| New capability focused suite | **13 passed** |
| MAINT-001/entity/relationship/temporal/duration/readiness/identity/lineage/Trust/validation/tenant/Revenue regression selection | **120 passed** |
| Full non-PostgreSQL suite | **1,744 passed** |
| Fresh disposable PostgreSQL suite | **82 passed** |
| Ruff format check | **passed** |
| Ruff lint | **passed** |
| Mypy | **passed; 621 source files** |

The first PostgreSQL attempt ran against a contaminated persistent disposable
database and produced 11 migration-replay/stale-row failures alongside 71
passes. The target was verified as local `127.0.0.1/intel4ops_test`, reset, and
the complete fresh run passed 82/82. No production database was accessed.

The full non-PostgreSQL run initially reported two failures: the governed-rule
inventory correctly observed the new rule, and the sandbox denied creation of
the disposable SQLite migration file. The inventory assertion was updated and
both exact tests passed on isolated rerun, producing the reconciled 1,744/1,744
result.

`MAINT-001` application code and rule definition were not modified. Its focused
regression tests pass.

## Implementation PR / CI state

Implementation PR: **#125**

CI status: **PASSED — Quality Gate**

Merge status: **merged at `f9d1d9455c8a7ff3624c2533a4adf1aae5a6c055`**

## Post-merge live certification

### Merge, deployment, and production-run ledger

PR #125 merged through the repository's normal merge method at
`f9d1d9455c8a7ff3624c2533a4adf1aae5a6c055`. Local `main` was synchronized to
that exact `origin/main` revision with a clean worktree. The Render deployment
record for the same SHA reached `success` at `2026-09-05T20:55:48Z`, and the
Core health endpoint returned HTTP 200 with `status: ok`. The post-merge main
Quality Gate subsequently completed successfully.

Production execution preceded examiner-side truth access. All four applicable
frozen FieldMaintenance cases reached terminal `review_required` state; this is
an orchestrator review outcome, not a failed run.

| Frozen case | Case ID | Terminal run used | Live readiness reported by Navigator | `MAINTENANCE-REPEAT-VISIT` findings | Total findings | Revenue Amount control |
|---|---|---|---|---:|---:|---:|
| `FIELDMAINT-001` | `e326e61b-f11b-4713-9048-6fccc7297a38` | `99c2f022-fb79-4bfb-ac2d-61a1acbcf310` | not reported | 0 | 63 | 61 |
| `FIELDMAINT-002` | `1fc05ddd-47d5-4f59-888e-6e968a577942` | `8c4d74bd-9dcd-4d37-a224-bc58510a345d` | not reported | 0 | 1 | 0 |
| `FIELDMAINT-005` | `8a7f562f-ea71-42f6-9405-09e2d8f25eda` | `5accaf18-49b3-4633-a884-c24711f15572` | not reported | 0 | 87 | 86 |
| `FIELDMAINT-007` | `fbc51228-9a76-4454-8569-a93b5ec03438` | `a473e728-e60e-463a-b05d-29c121a72cb5` | not reported | 0 | 27 | 26 |

The live readiness view returned “The backend has not reported intelligence
readiness for this case” for the certification runs. This absence is material:
there is no persisted live READY evidence on which to claim activation.

### Production-path diagnosis

The merged production code was replayed locally against the exact frozen
customer files, without loading or consulting hidden truth. That controlled
trace isolates two connected defects:

1. The generic readiness index marks `MAINTENANCE-REPEAT-VISIT` **READY** on
   each FieldMaintenance shape because it sees maintenance, canonical asset,
   `operational_event_id`, `activity_category`, timestamp, and domain-level
   Trust evidence.
2. Execution applies a stricter dataset-local evidence contract.
   `maintenance_events.csv.work_order_id` is only `accepted_with_flag` at 0.85
   because both event and work-order identifiers are present. The authoritative
   concept resolver therefore correctly refuses it as intervention identity.
   Consequently no maintenance dataset is admitted for pairing.

The representative exact trace for `FIELDMAINT-002` was:

- governed readiness: `READY`, no missing-summary items;
- eligible canonical assets: 60 of 67 (0.70 capability threshold);
- `asset_id`: `auto_accepted`, 0.98;
- `event_type -> activity_category`: `auto_accepted`, 0.95;
- `completed_date -> completed_timestamp`: `auto_accepted`, 0.98;
- `work_order_id -> work_order_id`: `accepted_with_flag`, 0.85;
- candidate datasets: 0;
- adjacent pairs: 0;
- published findings: 0.

The same source shape is present in all four applicable cases. Across 2,087
maintenance-event rows, production therefore abstained before pair formation.
The primary failure is a **CAPABILITY_MODEL_GAP**: readiness and execution do
not evaluate the same governed, dataset-local intervention-identity evidence.
The underlying evidence condition is a **SEMANTIC_EVIDENCE_GAP**; lowering the
global semantic threshold is not a safe remedy.

### Pairing safety and false-positive risk

After all production runs were terminal, examiner-side analysis applied the
implementation's exact pairing helper to the frozen source rows solely to
measure the latent model risk. It did not alter production results or truth.

| Case | Exact-category adjacent pairs if the identity gate were bypassed | Matches frozen `repeat_repair` truth | Non-truth pairs | Truth misses |
|---|---:|---:|---:|---:|
| `FIELDMAINT-001` | 114 | 0 | 114 | 0 |
| `FIELDMAINT-002` | 136 | 16 | 120 | 22 |
| `FIELDMAINT-005` | 765 | 0 | 765 | 0 |
| `FIELDMAINT-007` | 106 | 20 | 86 | 18 |
| **Total** | **1,121** | **36** | **1,085** | **40** |

This proves that accepting the flagged work-order concept would be unsafe.
Exact activity-category equality plus adjacency does not distinguish a genuine
repeat repair from ordinary recurring maintenance. It would also miss 40 truth
pairs whose governed `event_type` differs between the prior and subsequent
interventions (for example `CM -> PM` or `PM -> CM`). The corpus supplies no
governed repeat/rework marker, component/service equivalence, or policy window
that safely closes that distinction. Repeated maintenance alone is not rework.

No duplicate `(asset, work_order, completed timestamp, activity category)`
representations exist in the four frozen source files. Production duplicate
suppression count is therefore 0; pairing never began. Ordering, lineage, and
finding-identity checks are not applicable because no candidate or finding was
created. No policy violation or economic exposure was fabricated.

### Validation Plane scoring

Only after production was terminal did the examiner compare the persisted
finding ledger with the pre-frozen 76-item family: 38 items in
`FIELDMAINT-002` and 38 in `FIELDMAINT-007`, with $117,524.00 of
truth-authored value.

| Metric | Result |
|---|---:|
| TP | **0** |
| FP | **0** |
| FN | **76** |
| Precision | **N/A** (no positive predictions) |
| Recall | **0 / 76 = 0.00%** |
| Truth-authored economic-value capture | **$0.00 / $117,524.00 = 0.00%** |
| Mechanical/fabricated FP | **0** |
| READY cases (live reported) | **0 of 4** |
| Case-level safe abstentions | **4 of 4** |
| Duplicate suppressions | **0** |
| Findings overlapping `MAINT-001` | **0** |

The dollar result is examiner-side, directional truth coverage. The capability
correctly emitted no governed economic exposure because no pair-attributable
rework cost was established.

All 76 false negatives are classified **CAPABILITY_MODEL_GAP**, with the
immediate production blocker `SEMANTIC_EVIDENCE_GAP` on authoritative
intervention identity. Even if that immediate gate were removed, the
1,085-pair false-positive exposure demonstrates a second capability-model gap:
the current relationship contract is not specific enough to identify rework.

### Regression controls

- Revenue Amount / Billing Variance remained exactly **61 / 0 / 86 / 26**.
- `MAINT-001` code and rule identity were unchanged. It produced no finding on
  these four frozen cases, matching the existing FieldMaintenance behavior;
  the new capability overlap count is 0.
- Total persisted findings remained **63 / 1 / 87 / 27**, comprising the
  preserved Revenue Amount results and the pre-existing cross-domain/linkage
  findings only.
- Mechanical/fabricated false positives remained 0.

No truth, XDOM-A, XDOM-B, MAINT-001, semantic threshold, or application code
was changed during certification.

## Final classification

P3.xxI.5B FAILED
