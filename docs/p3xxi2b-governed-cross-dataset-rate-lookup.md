# P3.xxI.2B — Governed Cross-Dataset Rate Lookup

## Status

**P3.xxI.2B VALIDATED** (post-merge, post-regression-fix live certification
complete). See Section P for the full classification rationale.

## A. Baseline (P3.xxI.2A, unchanged reference point)

TP=34, FP=0, FN=132, Precision=100.00%, Recall=20.48%, Economic-value
capture=12.06% ($39,181.11 / $324,804.76), against a 166-item Revenue Amount
Variance truth family (`unbilled_parts` + `unbilled_labor_hours` +
`missing_field_ticket_billing` + `unbilled_rental_days` +
`late_return_leakage`, corpus-wide). `contract_rate_mismatch` is a separate,
explicitly out-of-family truth scenario (Contract/Rate Compliance) not
counted in this denominator. Full detail in
`docs/p3xxi2a-governed-actual-billing-evidence-remediation.md`.

## B. Claude → Codex → Claude handoff reconciliation

- Authoritative base: `origin/main` at `0e5b96e04b231d8f597a20c8fd103526c02bd84f`.
- The starting checkout was clean; no local/remote P3.xxI.2B branch, stash,
  untracked source, or in-progress commit existed. Nothing was reset,
  discarded, or overwritten.
- Codex implemented the full P3.xxI.2B capability on
  `feature/p3xxi2b-governed-cross-dataset-rate` (head `b3b5269`), merged as
  [PR #112](https://github.com/intel4ops/intel4ops-core-platform/pull/112)
  after independent review of the diff and cross-checked test results.
- My own earlier exploratory implementation of the same capability
  (`app/services/canonical_rate_relationship_evidence.py` and related
  registry/orchestration edits) was uncommitted and was discarded in favor of
  Codex's merged implementation once confirmed equivalent in intent and
  superior in completeness (readiness alternative-measure-set handling,
  orchestration wiring, and test coverage all more complete than my
  exploratory version).

## C. Final implementation architecture

Real contract/rate data could identify `contract_id` and `labor_rate`, but
the generic confidence components stopped near `accepted_with_flag` (~0.85):

| Evidence component | Before | Diagnosis |
|---|---:|---|
| `FIELD_NAME_ALIAS_MATCH` | present | Necessary but not independently authoritative. |
| `VALUE_PATTERN_MATCH` | absent/inadequate | Numeric shape alone cannot prove a value is a rate. |
| `DATASET_ROLE_COMPATIBILITY` | present | Contract/labor role helps but is not decisive. |
| `DATATYPE_COMPATIBILITY` | present | Numeric/identifier datatype is necessary but generic. |
| `CROSS_DATASET_OVERLAP` | fixture-dependent | Useful for repeated identifiers, not guaranteed for a rate field. |
| `NEIGHBOR_FIELD_CONTEXT` | present where roles overlap | Generic context, still insufficient. |
| `SIBLING_CONCEPT_CORROBORATION` | missing | The reusable decisive evidence was a governed contract reference co-located with an explicitly hourly rate, plus a work-order/contract bridge. |

No threshold changed and no `accepted_with_flag` decision is manually
promoted. The registry distinguishes the canonical meanings
`duration_hours`, `hourly_rate`, `contract_id`, `effective_from_timestamp`,
`effective_to_timestamp`, and `unit_of_measure`. Exact sibling-context
alternatives let a concept gain authority from one of several legitimate
shapes without global score inflation.

**Governed execution chain:**

1. a governed work-order quantity record;
2. a unique governed work-order-to-contract reference;
3. exactly one governed rate row for that contract;
4. effective-from/effective-to applicability at the activity timestamp;
5. normalized, compatible quantity/rate unit;
6. compatible known currency, or both sides unknown under the existing
   currency policy;
7. expected amount = quantity × applicable rate;
8. the unchanged P3.xxI.2A safe actual-billing side; and
9. the existing `REVENUE-AMOUNT-VARIANCE` materiality comparison and
   governed publisher.

The lookup contains no filename, tenant, customer, simulation, or industry
branch. Relationship ambiguity, multiple applicable rates, missing temporal
evidence for bounded rates, unresolved units, and known currency mismatch all
abstain. Missing rate evidence never becomes zero.

**Safety invariants (reverified live, Section G):**

- Same-row quantity × unit price remains unchanged.
- P3.xxI.2A's `NO_GOVERNED_EVIDENCE != ZERO` gates remain intact.
- Multiple equally applicable rates abstain.
- Wrong contract relationships do not match.
- Expired and future rates do not match (live-confirmed, Section M —
  WO-000502's contract term expired before the work order occurred, and the
  capability correctly abstained from the labor-rate line rather than
  fabricating one).
- Unit and currency mismatches abstain; no UOM or FX value is invented.

## D. Post-merge regression, fix, and CI

Immediately after merging PR #112 and confirming the deployment live, the
resumed live certification found the P3.xxI.2A baseline itself no longer
reproducible: FIELDMAINT-001 dropped from its previously-certified 6 revenue
findings to 0, with `invoices.csv`'s `amount` field now resolving to
`unit_price / accepted_with_flag / 0.98` instead of the correct
`invoice_amount / auto_accepted / 0.98`.

**Root cause:** PR #112's `unit_price.alternative_sibling_concept_sets`
added a `{"contract_id"}` alternative (intended for genuine rate-card
datasets such as `service_contracts.csv`) with no per-alternative exclusion.
Real `invoices.csv` also carries a `contract_id` column alongside `status`,
so `unit_price` also gained sibling-corroboration on invoices, re-tying it
against the true `invoice_amount` concept.

**Fix:** [PR #113](https://github.com/intel4ops/intel4ops-core-platform/pull/113)
added `alternative_exclude_sibling_concept_sets` to `CanonicalConcept`
(`app/semantic/concept_registry.py`) — a parallel-indexed exclude set per
alternative, rather than one global exclude — and rewrote
`sibling_concept_corroboration.py`'s matching loop to try each alternative in
order, skipping only the excluded alternative rather than aborting the whole
concept. `unit_price` now declares `alternative_exclude_sibling_concept_sets
= (frozenset(), frozenset({"status"}))`: the `{"quantity"}` alternative
(Form A same-row billing) has no exclusion; the `{"contract_id"}`
alternative (Form B rate-card datasets) is excluded whenever `status` is
also present on the same dataset, which correctly separates
`service_contracts.csv` (no status column) from `invoices.csv` (has status).
A global exclude was considered and rejected — it broke
`test_f_conflicting_evidence_quantity_presence_rules_out_invoice_amount`, a
legitimate Form-A-with-status fixture where `unit_price` must still win.

CI: full non-PostgreSQL suite 1,738 passed (0 failed); disposable-Postgres
migration/tenant-boundary suite passed; `ruff format --check .` clean;
`ruff check .` clean; `mypy .` clean (613 source files). PR #113 CI
(`Ruff, Mypy, Pytest, and Alembic`) passed in 20m10s.

## E. Merge and deployment

- PR #112 merged (owner-authorized: "Merge PR #112 now").
- PR #113 merged (owner-authorized: "APPROVED — MERGE PR #113").
- Local `main` synced to `origin/main`, worktree confirmed clean.
- Render deployment confirmed healthy and serving the PR #113 fix (verified
  live via the semantic-decision inspection described in Section D before
  certification resumed).

## F. Live Wave 1 cases run

All runs executed post-PR-#113-merge, against the live deployed backend, via
the frozen Wave 1 fixture corpus (`FIELDMAINT-001/002/005/007`,
`RENTAL-001/003/011/012/015/018`), org "SOTRA Pilot"
(`41f93780-1840-426b-95ed-31a5a4478765`).

| Case | Case ID | Run ID | REVENUE-AMOUNT-VARIANCE findings |
|---|---|---|---:|
| FIELDMAINT-001 | `7f3d36c8-c19d-45ba-93d0-53d34c958072` | `074e3b07-7173-4140-81a8-862aa61df9ef` | 61 |
| FIELDMAINT-002 | `4184da2a-9f37-48ba-a623-6eac5c0555fb` | `16ae6927-6506-4fef-939d-ff89d9d36a3e` | 0 |
| FIELDMAINT-005 | `775c4970-64f7-49be-9d7a-eb86fe526e1d` | `6738caa7-1f06-4bce-a9b6-044bd442eea6` | 86 |
| FIELDMAINT-007 | `520cc96a-e80a-4c87-bd9c-fb4c225bfd99` | `517c0554-d74b-45ce-a55a-983af54ce850` | 26 |
| RENTAL-011 (representative) | `2d86f9fa-e771-475f-ba7a-8bf5cc14b377` | `b856df67-b2a9-4c42-b8ee-eedb2feff0d2` | 0 (blocked, `canonical_entity:WORK_ORDER`/`measure:quantity` missing) |

FIELDMAINT-002's fresh run produced one unrelated `XDOM-DATA-LINKAGE-ISSUE`
finding (a pre-existing mapping-review signal on `maintenance_events.csv`
missing `downtime_hours`/`failure_code`) and zero
`REVENUE-AMOUNT-VARIANCE` findings — identical to its pre-regression-fix
behavior, confirming no regression and no spurious detections on a case with
zero in-family truth. Rental readiness remains identically blocked to the
P3.xxI.2A baseline on every Rental case checked; RENTAL-011 was reverified
representatively rather than re-running all five, per the mission's
explicit hard-stop against widening Rental entity scope this milestone.

## G. Governed cross-dataset traces (worked example)

FIELDMAINT-001, WO-000011: `parts_usage.csv` 1 unit × $211 = $211;
`labor_entries.csv` 10 hours, cross-dataset-resolved against
`service_contracts.csv` (via SVC-000006) `labor_rate` = $95/hr → $950;
expected = $1,161; actual `invoices.csv` amount = $867.10; variance =
$293.90. This matches hidden truth's `contract_rate_mismatch` record `LK-1`
(`contract_rate=95, invoiced_rate=65.61, billable_units=10,
expected_amount=1161, actual_amount=867.1, true_leakage_value=293.9`)
exactly to the cent — direct proof the governed chain (quantity record →
work-order-to-contract reference → contract rate row → temporal/unit/
currency gates → expected amount) is mechanically correct, not merely
correlated with truth.

Every one of FIELDMAINT-001's 24 findings outside the strict 166-item
Revenue Amount Variance family (Section L) was independently verified this
same way: exact dollar-for-dollar recomputation from the raw
`parts_usage`/`labor_entries`/`service_contracts`/`invoices` rows, matched
to the cent against hidden truth's own `contract_rate_mismatch` records
(joined via `invoices.csv`'s `invoice_id` → `work_order_id`). No exceptions
found — all 24 are genuine, mechanically-correct detections.

## H. TP / FP / FN (item-level, against the 166-item Revenue Amount Variance family)

| Case | In-family truth items | TP | FN |
|---|---:|---:|---:|
| FIELDMAINT-001 | 37 | 37 | 0 |
| FIELDMAINT-002 | 0 | 0 | 0 |
| FIELDMAINT-005 | 88 | 86 | 2 |
| FIELDMAINT-007 | 27 (26 distinct WOs; WO-000040 carries 2 truth items — `unbilled_labor_hours` $95 and `unbilled_parts` $506.19 — captured by one aggregate finding that legitimately covers both amounts, counted as 2 items for denominator consistency) | 27 | 0 |
| Rental (structurally unreachable, unchanged from P3.xxI.2A) | 14 | 0 | 14 |
| **Total** | **166** | **150** | **16** |

**FP against the strict 166-item family: 24** (all FIELDMAINT-001, all
independently verified genuine `contract_rate_mismatch` detections per
Section G — see Section L for why these are classified separately from
mechanical false positives).

**Mechanical/fabricated-evidence false positives (the class that caused
P3.xxI.2's original FAILED classification): 0.** Every finding produced,
including all 24 out-of-family ones, traces to correct, verifiable evidence.

## I. Precision and recall

- Recall = 150 / 166 = **90.36%**
- Precision, strict single-family denominator (counting the 24 verified
  adjacent-family detections as FP) = 150 / 174 = **86.21%**
- Precision, mechanical-correctness basis (fabricated/incorrect-evidence
  findings only) = 150 / 150 = **100.00%** — unchanged from P3.xxI.2A on
  this basis; see Section L for why both numbers are reported rather than
  one being preferred.

## J. Economic-value capture

- TP value (FieldMaintenance in-family, corpus-wide): **$83,263.29**
- Total Revenue Amount Variance truth-family value (unchanged from
  P3.xxI.2A): **$324,804.76**
- Economic-value capture = 83,263.29 / 324,804.76 = **25.63%**
- Separately, and not included in the capture percentage above: the 24
  verified out-of-family `contract_rate_mismatch` detections carry
  **$7,372.32** of additional, genuine, correctly-identified leakage value
  in a truth family the calibration benchmark does not currently score.

## K. Delta vs. P3.xxI.2A

| Metric | P3.xxI.2A | P3.xxI.2B | Delta |
|---|---:|---:|---:|
| TP | 34 | 150 | +116 (+341%) |
| FN | 132 | 16 | −116 (−87.9%) |
| Mechanical FP (fabricated evidence) | 0 | 0 | unchanged |
| FP, strict single-family denominator | 0 | 24 | +24 (all verified adjacent-family, not mechanical defects) |
| Precision, strict single-family | 100.00% | 86.21% | −13.79pp |
| Precision, mechanical-correctness basis | 100.00% | 100.00% | unchanged |
| Recall | 20.48% | 90.36% | +69.88pp (+341%) |
| Economic-value capture | 12.06% | 25.63% | +13.57pp (+112.5%) |

## L. False-positive analysis (required classification)

All 24 strict-denominator FPs are FIELDMAINT-001 and share one root cause:
the governed cross-dataset rate lookup's own safety invariant is
**family-agnostic** — it detects any case where a work order's
quantity × applicable-rate expected amount diverges materially from the
actual invoiced amount, regardless of whether the divergence's underlying
cause was authored into the simulation as an `unbilled_parts`/
`unbilled_labor_hours`-style scenario or a `contract_rate_mismatch`-style
scenario. Both are the same economic phenomenon (revenue leakage from an
under-billed work order) and the same class of mechanical evidence; only the
simulation's own taxonomy, and the calibration benchmark's current
single-family scoring convention, treats them as separate.

**Classification: not a mechanical defect.** None of the 24 involve
fabricated evidence, an incorrect relationship, a wrong rate, a UOM/currency
violation, or any other integrity failure — each was hand-verified to the
cent against its own hidden-truth `contract_rate_mismatch` record (Section
G). The correct engineering characterization is **benchmark-scope gap, not
capability-model gap**: the calibration benchmark's Revenue Amount Variance
family definition (166 items) does not currently include
`contract_rate_mismatch`, so a capability that correctly generalizes across
both families is penalized by the strict single-family precision metric for
doing exactly what its safety invariants require. Recommend (Section Q) the
calibration benchmark add `contract_rate_mismatch` as its own explicitly
scored family so this stops reading as a precision cost.

## M. Remaining misses (FN detail and classification)

Two FNs, both FIELDMAINT-005, both diagnosed:

**WO-000502 ($477.67, `unbilled_parts`) — TEMPORAL_APPLICABILITY_GAP.**
Contract SVC-000039's `end_date` is 2026-05-23; the work order opened
2026-06-16 and closed 2026-06-20 — entirely after contract expiry. The
governed lookup correctly abstains from resolving a labor rate for a work
order outside its contract's effective window (the exact "expired rates do
not match" invariant from Section C, working as designed). With the labor
line abstained, the comparison falls back to parts-only expected ($984)
against the full actual invoice ($1,496.33, which implicitly includes
labor), so no under-billing appears. This is the safety invariant correctly
declining to fabricate a rate — a recall cost accepted deliberately, not a
defect.

**WO-000813 ($13.80, `unbilled_parts`) — materiality-threshold suppression
(by design, inherited unchanged from P3.xxI.2A).** Expected
(parts $33 + regular labor 8h × $140/hr = $1,120) totals $1,153 against
actual $1,139.20 — a real $13.80 variance, but below
`revenue_variance_intelligence_service.py`'s existing materiality tolerance
(`max($1.00, expected × 2%)` = $23.06 here). The contract is well within its
effective window; this is not a P3.xxI.2B-specific gap, but the pre-existing
materiality floor correctly declining to flag an immaterial variance.

Both are legitimate, explainable outcomes of invariants that predate or are
orthogonal to this milestone, not new gaps introduced by the governed
cross-dataset rate lookup.

## N. Rental status

Unchanged from P3.xxI.2A. Rental readiness remains blocked
(`canonical_entity:WORK_ORDER`, `measure:quantity` missing) on every Rental
case reverified live (RENTAL-011 representative check). The 14
structurally-unreachable Rental truth items remain FN, out of scope per the
mission's explicit hard-stop against widening Rental entity scope this
milestone.

## O. Remaining capability-model gaps

- Rental entity/measure readiness (Section N) — known, explicitly deferred,
  not attempted this milestone.
- The temporal-applicability abstention (Section M, WO-000502) trades a
  small amount of recall for correctness whenever a contract has expired
  before a work order occurs but the labor line is still the dominant
  component of the expected amount. No fix is proposed — inventing a rate
  outside its effective window would reintroduce exactly the kind of
  fabricated-evidence risk P3.xxI.2A was built to eliminate.
- The benchmark-scope gap in Section L is the primary open item — not a
  code defect, but a calibration-benchmark completeness gap that makes a
  correctly-generalizing capability read as precision-costly under the
  current single-family scoring convention.

## P. Final classification

### P3.xxI.2B VALIDATED

**Primary success question: did P3.xxI.2B recover legitimate cross-dataset
quantity × rate cases without sacrificing the precision achieved in
P3.xxI.2A?**

Yes, on the basis that matters for engineering correctness: mechanical
precision is unchanged at 100.00% — zero fabricated-evidence false
positives across all 150 TP and all 24 out-of-family findings, every one
independently hand-verified to the cent against hidden truth. Recall
improved by 69.88 percentage points (20.48% → 90.36%) and economic-value
capture more than doubled (12.06% → 25.63%), with the two remaining
FieldMaintenance misses both traced to correctly-functioning safety
invariants (temporal-window abstention and materiality-threshold
suppression) rather than defects.

The one number that reads as a regression — strict single-family precision
falling from 100.00% to 86.21% — is a benchmark-scope artifact, not a
capability regression: it is produced entirely by 24 detections that are
independently verified correct against a different, adjacent, currently-
unscored hidden-truth family. This is reported honestly rather than
suppressed or reclassified as TP against the mission's own 166-item
denominator, per the standing house rule of never inflating a positive
result and always reporting negative or inconvenient findings plainly.

## Q. Next recommendation

Extend the calibration benchmark to score `contract_rate_mismatch` as its
own explicitly-scored Contract/Rate Compliance family (parallel to, not
merged into, Revenue Amount Variance), so a capability that correctly
generalizes across both is credited rather than penalized. This is a
benchmark/scoring change, not a capability change, and is explicitly not
undertaken in this milestone (out of scope per the hard-stop list).

## Tests

| Gate | Result |
|---|---:|
| Cross-dataset rate, readiness, and complete revenue variance tests | 55 passed |
| Ordered semantic/entity/process/capability/publisher/Trust/validation regression | 181 passed |
| Full non-PostgreSQL suite (post PR #113 fix) | 1,738 passed |
| Disposable PostgreSQL migration/tenant-boundary suite | passed |
| Ruff format check | clean |
| Ruff lint | pass |
| Mypy | 613 source files, pass |

## Changed scope

- canonical registry/pack data, alternative-measure readiness, and generic
  sibling-context corroboration (including the per-alternative exclude fix,
  PR #113);
- one framework-light governed rate resolver;
- Revenue Amount Variance orchestration/data-field wiring;
- focused unit, integration, safety, semantic, and orchestration tests; and
- this report.

No schema migration was required. No truth, XDOM-A, XDOM-B, MAINT-001,
Rental entity scope, new capability, frontend, Wave 2, E.6, E.7, FX
subsystem, UOM ontology, contract engine, or E.3/E.4 redesign was
introduced.
