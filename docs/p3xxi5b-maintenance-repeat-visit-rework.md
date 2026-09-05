# P3.xxI.5B Maintenance Repeat Visit / Rework

## Implementation status

**Phase:** implementation quality gate; post-merge live certification not yet authorized

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

CI status: **running**

Merge status: **owner-gated; do not merge**

## Post-merge live certification placeholder

Post-merge certification has not started and is not authorized by this PR.
After an explicit owner-authorized merge and confirmed deployment, production
runs must complete before the Validation Plane examines the frozen truth.

The certification report will preserve the 76-item denominator and record:

- READY cases and safe abstentions;
- TP, FP, FN, precision, recall, and mechanically supported economic capture;
- duplicate suppression and exact adjacent pairing;
- pairing failure, false-positive, and false-negative classifications;
- mechanical/fabricated false positives; and
- exact truth coverage without changing production pairing rules.

Graduation targets remain precision at least 95%, zero mechanical/fabricated
false positives, and recall at least 80% (preferably 90% when governed evidence
supports it). Safety thresholds will not be weakened to reach recall.

P3.xxI.5B stops at the implementation PR owner gate.
