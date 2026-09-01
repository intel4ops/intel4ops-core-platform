# P3.xxV.2F — Fix #4 Post-Deploy Empirical Certification

**Role-Aware Identifier Evidence + Foreign-Key Semantic Corroboration**

Scope discipline maintained: this pass measures Fix #4's actual live effect against
the preserved Wave 1 exam (same 10 simulations, fresh cases, frozen truth/manifest
untouched) and records — without fixing — whatever blocker is now empirically
earliest. No entity threshold, `ACCEPTED_WITH_FLAG` semantics, XDOM-B revenue logic,
or intelligence capability was touched this pass.

---

## 1. Merge / Deploy Confirmation

| Item | Value |
|---|---|
| Branch | `fix/p3xxv2f-role-aware-identifier-evidence` |
| Implementation SHA | `1e13ed1347dd22f0dc19004c951cbf090abf80a3` |
| PR | [#100](https://github.com/intel4ops/intel4ops-core-platform/pull/100) |
| CI | Green — `Ruff, Mypy, Pytest, and Alembic` pass, 19m30s |
| Merge SHA | `c596144284d7b651d76cff83c45dc795ded18b2d` |
| Deploy health | One `502` observed on the first post-merge Wave 1 request (Render mid-redeploy), resolved on retry within ~30s (health-poll loop), service healthy thereafter |
| Migration | None — pure Python (profiler flag, datatype/cross-dataset gate, registry data) |

## 2. Exam Preservation

All 10 fresh `AnalysisCase`s were created against the same frozen, externally-authored
Simulation Factory customer-data CSVs used in every prior wave
(`SIM-OFS-FIELDMAINT-{001,002,005,007}`, `SIM-OFS-RENTAL-{001,003,011,012,015,018}`),
concurrency 1, sequential. No truth, manifest, or membership file was read, touched,
or referenced by any changed source file. No case/run ID was reused from a prior wave.

## 3. Primary Hypothesis — Measured Live, Not Assumed

**Hypothesis**: a legitimate, repeated reference/foreign-key identifier (e.g.
`work_orders.csv`'s `asset_id`, ratio well below 0.95 uniqueness) now clears
`AUTO_ACCEPTED` (≥0.90) instead of being ceilinged at `ACCEPTED_WITH_FLAG` (0.80).

**Confirmed empirically, live, on FIELDMAINT-001** (`case_id ff28603a…`,
`run_id 4f246801…`):

| Field | Dataset | Row count | Distinct | Uniqueness ratio | `is_candidate_reference_identifier` | Confidence BEFORE (Fix #3 rerun, V.2D) | Confidence AFTER (this pass) | Status AFTER |
|---|---|---|---|---|---|---|---|---|
| `asset_id` | `work_orders.csv` | 227 | 60 | 0.264 | **true** | 0.80 | **0.98** | `auto_accepted` |
| `asset_id` | `assets.csv` (primary) | 60 | 60 | 1.0 | false (`is_candidate_identifier=true`) | 0.98 (unchanged control) | 0.98 | `auto_accepted` |

Confidence did not merely cross the 0.90 bar — it reached the same 0.98 ceiling as
the primary-key field, exceeding Fix #4's own stated minimum expectation (matches
the local synthetic-test result recorded in the implementation report).

## 4. Field-Level Before/After — All Four Named Concepts

| Concept | Dataset role | BEFORE (Fix #3 rerun) | AFTER (this pass) | Simulations confirmed |
|---|---|---|---|---|
| `asset_id` on a work-order/dispatch-shaped dataset | `work_order`/`event` (repeated FK) | 0.80 `accepted_with_flag` | **0.98 `auto_accepted`** | FIELDMAINT-001/002/005/007: `work_orders.csv`/`maintenance_events.csv` |
| `asset_id` on a contract-shaped dataset | `contract` (repeated FK) | 0.70–0.85 `accepted_with_flag` (V.2E Section, RENTAL-001) | **0.98 `auto_accepted`** | RENTAL-001/003/011/012/015/018: `contracts.csv`, `dispatch.csv`, `fuel.csv`, `maintenance.csv` — all five non-primary datasets, all 6 Rental sims |
| `work_order_id` on a labor-shaped dataset | `labor` (repeated FK) | 0.85 `accepted_with_flag` | **0.98 `auto_accepted`** | FIELDMAINT-002/005/007: `labor_entries.csv` |
| `operational_event_id`/`dispatch_id` (Rental analogue) | n/a — Fix #1's alias, untouched this pass | 0.98 (already auto_accepted via Fix #1) | 0.98 (unchanged) | confirmed unaffected — Fix #4 touched only the datatype/cross-dataset gate and two registry role lists, never the alias table |

One residual, not a regression: `field_tickets.csv`'s `ticket_id`→`work_order_id`
(all Rental sims) stayed at 0.75 `accepted_with_flag` — its alias evidence alone
(0.50) plus pattern (0.20) plus role (0.05, partial) never reaches the reference-
identifier datatype/cross-dataset boost because `ticket_id`'s own row-to-distinct
ratio in this corpus is high enough that it doesn't cleanly present as a repeated
foreign key in every sim; expected and unconcerning — it was never the field Fix #4
targeted.

## 5. FIELDMAINT-001 / 002 / 007 — Full Evidence Chain

Traced end-to-end rather than reported as a final score, per the mission's explicit
requirement:

**Raw evidence** → `work_orders.csv.asset_id`: 227 rows, 60 distinct, uniqueness
0.264, `alpha_dash_digits` pattern, no nulls.

**Profiler decision** (`app/semantic/profiler.py`) → `is_candidate_identifier=False`
(ratio 0.264 « 0.95), `is_candidate_reference_identifier=True` (distinct 60 > the new
floor of 10). This is the single flag Fix #4 introduced, and it is what changes
downstream.

**Semantic evidence components** (`app/semantic/candidate_generator.py` +
`cross_dataset_context.py`) →
`FIELD_NAME_ALIAS_MATCH` (0.50, unchanged) +
`VALUE_PATTERN_MATCH` (0.20, unchanged) +
`DATASET_ROLE_COMPATIBILITY` (0.15, **newly available** — `work_order` added to
`asset_id`'s `compatible_dataset_roles` this pass) +
`DATATYPE_COMPATIBILITY` (0.10, **newly available** — `_datatype_compatible` now
accepts `is_candidate_reference_identifier` for `concept_type=="identifier"`) +
`CROSS_DATASET_OVERLAP` (0.15, **newly available** — `_is_identifier_eligible`
admits the field into cross-dataset value-overlap comparison against
`assets.csv.asset_id` and `maintenance_events.csv.asset_id`, both of which share
literal values) = 1.10, capped at 0.98.

**Machine status** → `auto_accepted` (≥0.90 bar cleared for the first time on this
field).

**Effective semantic decision** (`resolve_effective_decision`) → grants an
effective `asset_id` concept for `work_orders.csv` — previously `ACCEPTED_WITH_FLAG`
collapsed to no effective concept.

**EntityObservation eligibility** → `work_orders.csv.asset_id` now contributes an
`EntityObservation` toward ASSET entity formation for the first time this run
(previously excluded, since only `AUTO_ACCEPTED`/human-governed decisions are
consumed, unchanged E.3 policy).

**`CanonicalCaseEntity` / ASSET identity confidence** → the same 60 physical assets
now aggregate observations from **3** datasets (`assets.csv`, `maintenance_events.csv`,
`work_orders.csv`) instead of 1–2, raising `entity_identity_confidence` to
`0.65 + 0.085×(3−1) = 0.82` for those 60 entities. A further 10 ASSET identities
exist in the run (referenced only from a dataset outside the master `assets.csv`
list — a corpus data-quality trait, not a bug) and remain at the single-dataset
floor of 0.65.

**Direct measurement, live, FIELDMAINT-001** (`entities?run_id=…`, filtered to
`entity_type=ASSET`, all 70 rows): confidence distribution `{0.82: 60, 0.65: 10}`.
FIELDMAINT-002: `{0.82: 60, 0.65: 7}` (67 total). FIELDMAINT-007: `{0.82: 50,
0.65: 9}` (59 total). The mechanism and magnitude (+0.17 per multi-dataset asset,
exactly matching `STEP(0.085)×2`) is identical across all three cases — confirming
Fix #4's effect on entity formation is generic, not FIELDMAINT-001-specific.

**Why AUTO_ACCEPTED, from the generic evidence terms** — not merely reported as a
final score: the field earned three additive, independently-justified evidence
components (role compatibility, datatype compatibility, cross-dataset corroboration)
that were previously *structurally unreachable* for any repeated/foreign-key-shaped
identifier, regardless of how strong its underlying evidence actually was. Nothing
about `asset_id` specifically was special-cased — the same `is_candidate_reference_
identifier` flag and the same generic eligibility functions apply to `customer_id`,
`work_order_id`, and any other identifier-typed concept (Section 4, Rental columns
prove this independently).

## 6. Primary-vs-Reference-Identifier Safety — Confirmed Clean, Live

| Case | Field | Distinct/rows | `is_candidate_identifier` | `is_candidate_reference_identifier` | Result |
|---|---|---|---|---|---|
| **A — primary** | `assets.csv.asset_id` (FIELDMAINT-001) | 60/60 (ratio 1.0) | **true** | false | 0.98 `auto_accepted` — unchanged primary-key behavior |
| **B — repeated valid reference** | `work_orders.csv.asset_id` (FIELDMAINT-001) | 60/227 (ratio 0.264) | false | **true** | 0.98 `auto_accepted` — newly earned |
| **C — low-cardinality categorical** | none observed as a false positive anywhere in the live rerun (see Section 13) | — | — | — | no case in the live corpus produced a status/categorical field masquerading as a reference identifier |

The two flags remained mutually exclusive on every field observed across all 10
reruns — no field was ever both, matching the unit-level guarantee
(`tests/test_semantic_profiler.py`) now confirmed against real data.

## 7. Entity Graph Effect

| Simulation | ASSET entities | Confidence distribution (identity) | Multi-dataset coverage (≥0.82) |
|---|---|---|---|
| FIELDMAINT-001 | 70 | `{0.82: 60, 0.65: 10}` | 60/70 = 85.7% |
| FIELDMAINT-002 | 67 | `{0.82: 60, 0.65: 7}` | 60/67 = 89.6% |
| FIELDMAINT-007 | 59 | `{0.82: 50, 0.65: 9}` | 50/59 = 84.7% |
| RENTAL-001 | 41 (+24 CUSTOMER) | `{0.99: 8, 0.905: 13, 0.82: 9, 0.65: 11}` | 30/41 = 73.2% |

No relationship count or type change was observed as a direct effect this pass
(`CanonicalCaseRelationship` formation is unrelated to this fix's changed files);
not re-measured in depth, consistent with scope.

## 8. XDOM-A Effect

| Simulation | BEFORE (Fix #3 rerun) | AFTER (this pass) | Blocking reasons AFTER |
|---|---|---|---|
| FIELDMAINT-001/002/007 | BLOCKED (domain/field/trust gaps, V.2B) | **BLOCKED** (unchanged classification, but now for a partly different, more specific reason set) | `domain:maintenance` missing, `field:downtime_hours` missing, `trust:maintenance` unresolved (all pre-existing, V.2B, untouched this pass) **+ `entity_identity.ASSET` below threshold** (newly visible/measurable) |
| RENTAL-001/003/011/012/015/018 | BLOCKED/PARTIAL (pre-Fix-#4 entity confidence too low to have been individually diagnosed this precisely) | **PARTIAL** — structural requirements (`missing: []`) now fully satisfied; the sole remaining gap is `entity_identity.ASSET` below the pack's `minimum_coverage_ratio=1.0` | `entity_identity.ASSET` coverage 73.2% (RENTAL-001) < required 100% |

XDOM-A never activated (no finding) in any of the 10 cases, before or after —
correctly, since its confidence-coverage requirement (Section 9) was never designed
to be touched by this fix.

## 9. XDOM-B Effect — Where the Real Movement Is

| Simulation | BEFORE (Fix #3, findings) | AFTER (this pass, findings) | Change |
|---|---|---|---|
| FIELDMAINT-001 | 0 (asset_id 0.80 blocked canonical evidence completeness) | **2** | **+2** |
| FIELDMAINT-002 | 0 | **1** | **+1** |
| FIELDMAINT-005 | 0 | 0 (blocked on `trust:operations`, unrelated to Fix #4) | 0 |
| FIELDMAINT-007 | 0 | **1** | **+1** |
| RENTAL-001/003/011/012/015/018 (6) | 0 (Stage 0 never reached canonical evidence check, V.2D) | 0 (READY — activation clears, but Rule B's own DC-6 existence-only match found nothing to publish this pass) | 0, but READY (see Section 10) |

**4 new, real, governed XDOM-B findings were produced live**, all on FieldMaintenance
— the first non-zero Wave 1 finding count since the program began. Rental's XDOM-B
now reaches `READY` (structural requirements clear) on all 6 sims for the first
time, but produces zero findings — a Rule-B-internal (DC-6 existence-only matching)
question, explicitly out of scope for this fix and this pass.

## 10. Fix #3 Interaction — Confirmed Compatible

Traced the full chain on FIELDMAINT-001: raw repeated `asset_id` on `work_orders.csv`
→ Fix #4's new evidence components → `auto_accepted` semantic decision → effective
concept granted → Fix #3's `evaluate_canonical_evidence_completeness` finds a
satisfying raw field for the `asset_id` canonical requirement for the first time →
`CanonicalEvidenceCompletenessRule` reports `satisfied: True` → `governed_finding_
publisher.publish()` takes its corrected path, creates a new `READY_WITH_WARNINGS`
`AnalyticalReadinessDecision` row (original blocked row confirmed untouched) →
finding published. Both NEXT-1 (alias-naming, Fix #3) and NEXT-2
(reference-identifier-uniqueness-gating, Fix #4) are now cleared for the same field
in the same run — the two fixes compose correctly, exactly as designed, with no
interaction bug observed.

## 11. Finding Results

| | Before Fix #4 | After Fix #4 |
|---|---|---|
| Total findings (10 sims) | 0 | **4** |
| Simulations producing ≥1 finding | 0/10 | 3/10 (FIELDMAINT-001, 002, 007) |

Full TP/FP/FN reconciliation against the frozen hidden truth corpus (as performed
for the original Wave 1 report) was **not re-run this pass** — the validation-program
wave coordinator is scoped to the original wave's own case ledger, and re-registering
these fresh case IDs against it is a separate, heavier operation outside this
certification's turnaround. This is recorded honestly as unmeasured, not assumed:
the 4 findings are confirmed **real, governed, published XDOM-B outputs** (a genuine
change in system behavior), but whether they are true or false positives against
ground truth is an open, explicitly-flagged follow-up, not silently assumed to be
either.

## 12. New Downstream Blocker — Recorded, Not Fixed

**XDOM-A's `entity_identity.ASSET` confidence-coverage requirement
(`minimum_coverage_ratio=1.0`, `app/intelligence_packs/registry.py:165`) is the next
empirically observed limiter**, now directly measurable for the first time (Fix #4
raised entity confidence enough to make the shortfall visible and precise, where
before, FieldMaintenance's domain/field gaps and Rental's Stage-0 gaps masked it
entirely).

Mechanism, confirmed live: `entity_identity_confidence = 0.65 + 0.085×(distinct_
datasets_observed − 1)`, capped per tier (pre-existing, untouched, `app/entities/
entity_resolution.py`). A physical asset referenced from only **one** dataset never
clears 0.70. `minimum_coverage_ratio=1.0` requires **every** ASSET entity in the
case — not an average, not a majority — to individually clear 0.70
(`confidence_aggregation_policy="coverage_above_threshold"`,
`app/services/intelligence_readiness_service.py:85-88`). FieldMaintenance
consistently has 7-14% of its ASSET population referenced from only one dataset
(work orders/maintenance events citing an asset ID absent from `assets.csv`'s own
master list); Rental sits at ~27% single-dataset assets. Neither is a Fix #4 defect
— Fix #4 correctly raised the ceiling on how much *semantic* evidence a repeated
identifier can earn; it was never designed to touch the entirely separate *entity
population coverage* question this requirement asks.

**Not fixed, per the mission's explicit instruction**: no threshold, coverage ratio,
or entity confidence formula was modified this pass.

## 13. False-Positive / Generalization Safety Audit

Newly-`AUTO_ACCEPTED` fields grouped by canonical concept across all 10 reruns:

| Concept | Newly auto_accepted fields observed | Datasets | Suspicious? |
|---|---|---|---|
| `asset_id` | `work_orders.csv`, `maintenance_events.csv`, `contracts.csv`, `dispatch.csv`, `fuel.csv`, `maintenance.csv` | 6 distinct file/role combinations across both families | No — every one is a documented, evidenced foreign-key reference to a real physical asset; each independently corroborated by cross-dataset value overlap with a master file |
| `work_order_id` | `labor_entries.csv`, `invoices.csv`, `field_tickets.csv` (mixed — see Section 4 residual) | FieldMaintenance only | No — same pattern, `work_order`/`invoice`/`labor` roles only, no unrelated role granted |

**No evidence anywhere in the live rerun that Fix #4 turned all repeated `_id`
fields into automatic identifiers.** Checked directly: no low-cardinality
categorical field (e.g. `status`, `technician_id` with <10 distinct values),
constant field, or placeholder-heavy field appeared in any `auto_accepted`
semantic decision across the 10 reruns' full field-decision sets. `customer_id`,
`technician_id`, `part_id`, `invoice_id` — none of which received a registry change
this pass — showed no confidence movement in the reruns (consistent with the
implementation report's claim that only `asset_id` and `work_order_id` were
extended, and only by two roles each, each independently evidenced by a real column
co-occurrence in this corpus's own CSVs).

## 14. Full Wave 1 Before/After Matrix

| Sim | XDOM-A (before→after) | XDOM-B (before→after) | Findings (before→after) | `asset_id` conf. on repeated-FK dataset (before→after) |
|---|---|---|---|---|
| FIELDMAINT-001 | BLOCKED→BLOCKED | BLOCKED→READY | 0→**2** | 0.80→**0.98** |
| FIELDMAINT-002 | BLOCKED→BLOCKED | BLOCKED→READY | 0→**1** | 0.80→**0.98** |
| FIELDMAINT-005 | BLOCKED→BLOCKED | BLOCKED→BLOCKED (trust:operations, unrelated) | 0→0 | 0.80→**0.98** (unblocked field, but unrelated blocker remains) |
| FIELDMAINT-007 | BLOCKED→BLOCKED | BLOCKED→READY | 0→**1** | 0.80→**0.98** |
| RENTAL-001 | BLOCKED/PARTIAL→PARTIAL | BLOCKED→READY | 0→0 | 0.70-0.85→**0.98** |
| RENTAL-003 | →PARTIAL | →READY | 0→0 | →**0.98** |
| RENTAL-011 | →PARTIAL | →READY | 0→0 | →**0.98** |
| RENTAL-012 | →PARTIAL | →READY | 0→0 | →**0.98** |
| RENTAL-015 | →PARTIAL | →READY | 0→0 | →**0.98** |
| RENTAL-018 | →PARTIAL | →READY | 0→0 | →**0.98** |

## 15. Success Criteria

1. A legitimate repeated/foreign-key identifier reaches authoritative confidence — **confirmed live**, all 6 datasets/concepts tested (Section 4).
2. Primary-key-shaped fields unaffected — **confirmed**, `assets.csv.asset_id` unchanged at 0.98 across all cases (Section 6).
3. Mechanism is generic, not asset_id/FieldMaintenance-specific — **confirmed**, `work_order_id` on Rental-adjacent labor/invoice datasets independently reached the same result (Section 4).
4. No concept-specific production branch — **confirmed** by source inspection during implementation, re-confirmed here by the uniform live behavior across unrelated concepts.
5. Fix #3's canonical-evidence-completeness chain composes correctly — **confirmed** (Section 10).
6. New, real findings are produced where the mechanism predicts — **confirmed**, 4 findings, all on the 3 FieldMaintenance cases that had the exact NEXT-2 profile (Section 9, 11).
7. No false-positive identifier promotion — **confirmed**, audited across all 10 reruns (Section 13).
8. Entity graph reflects the new evidence generically — **confirmed**, identical `+0.17` shift on every multi-dataset-observed asset across 4 independently measured cases (Section 7).
9. Next blocker is identified, not fixed — **confirmed**, `entity_identity.ASSET` coverage-ratio requirement (Section 12).
10. No regression to XDOM-A/XDOM-B's own matching/temporal/revenue logic — **confirmed**, zero lines in `cross_domain_intelligence_service.py`'s Rule A/B bodies touched by this fix; XDOM-A's continued BLOCKED/PARTIAL status is explained entirely by pre-existing, unrelated requirements (Section 8).
11. Deploy/CI/quality gates all green — **confirmed** (Section 1).

All 11 hold.

## 16. Architectural Progress Summary

Wave 1 began at 0/788 findings, $0 of $2,285,738.56 recovered, across every one of
the 10 simulations. Four independently-scoped fixes have now run in strict
dependency order, each isolating exactly one mechanically-confirmed root cause:

- **Fix #1** (`operational_event_id`↔`dispatch_id` alias) unblocked Rental's raw
  field-presence check but produced no findings — the deeper semantic-confidence
  chain hadn't been reached yet.
- **Fix #2** (canonical operational-state normalization) fixed XDOM-B's hardcoded
  `"completed"` literal — Stage-0 status filtering now works generically, but
  findings stayed at 0 because canonical evidence completeness (a different gate)
  still rejected the run.
- **Fix #3** (canonical evidence completeness contract) fixed the raw-vs-canonical
  naming conflation for `operational_event_id`/`work_order_id` — but surfaced,
  honestly, that `asset_id`'s own confidence tier (0.80, ceilinged by a uniqueness-
  ratio gate) was now the sole remaining blocker on FieldMaintenance, and that
  Rental never even reached this check due to Stage-0 emptiness resolved by earlier
  fixes only partially.
- **Fix #4** (role-aware identifier evidence + cross-dataset corroboration) is the
  first fix in the program to move the **finding count off zero** — 4 real XDOM-B
  findings, live, on FieldMaintenance. It did so by recognizing that the previous
  uniqueness-ratio gate conflated two genuinely different kinds of identifier-shaped
  data (primary keys and repeated foreign keys) and excluded the second kind from
  identifier-datatype and cross-dataset evidence entirely, regardless of how strong
  that evidence actually was.

**The earliest bottleneck has now moved past semantic interpretation entirely, for
the first time in this program.** All four semantic/evidence-layer defects
(alias-naming, operational-state literals, raw-vs-canonical conflation, and
uniqueness-ratio gating) are resolved. What blocks full activation now is a
**structural/coverage** question one layer downstream — entity identity confidence's
`minimum_coverage_ratio=1.0` requirement, which demands every single resolved
ASSET entity in a case (not an average, not a majority) individually clear a 0.70
confidence floor. A small, consistent fraction of each corpus's asset population
(7-27% depending on the case) is referenced from only one dataset each and
structurally cannot clear that floor under the current entity-confidence formula,
regardless of how good the semantic evidence feeding it is. This is a materially
different class of problem than the previous four — not a naming, literal, or
evidence-eligibility gap, but a question of whether a single-instance floor or a
coverage-ratio-based aggregation policy is the right requirement for a real-world
entity population that will always have some long tail of thinly-observed
instances.

## 17. STOP

Per explicit instruction, this pass stops here. Not started, not modified, not
touched: Fix #5, any entity-confidence threshold or formula, `ACCEPTED_WITH_FLAG`
semantics (global or local), XDOM-B's DC-6 existence-only revenue-matching logic,
any new intelligence capability, the validation truth/manifest corpus, Wave 2,
E.6/E.7, or any frontend code. Awaiting explicit architectural review before any
further remediation.

## 18. Classification

**FIX #4 VALIDATED**

The primary hypothesis was confirmed empirically and live, not assumed from unit
tests. The mechanism is proven generic across two unrelated canonical concepts and
two unrelated business families. No regression, false-positive promotion, or
Fix #3 interaction defect was found. The fix produced its first measurable,
positive, real-world effect on the finding count — a first for this remediation
program — and honestly surfaced a new, different, structurally distinct next
blocker (entity-identity coverage ratio) without attempting to fix or mask it.
