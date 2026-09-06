# Simulation Gap Ledger

Program-wide, cumulative record of *reusable platform gaps* -- misses from
`docs/simulation-miss-ledger.md` rolled up by shared root cause, so a fix
is scoped once and benefits every simulation/case it applies to, never
built per-case. Each gap is typed as exactly one of:

- **CODE_GAP** -- a defect or missing mechanism in `app/` that a
  code-only fix can close, with no new customer data required.
- **GOVERNANCE_GAP** -- evidence exists and is correctly resolved, but no
  rule or policy layer consumes it for a given purpose yet.
- **SEMANTIC_GAP** -- a canonical concept/relation the platform's concept
  registry does not yet model at all (not just "not wired up" -- genuinely
  absent from the semantic vocabulary).
- **DATA_CONTRACT_LIMITATION** -- the customer's actual source data does
  not contain the evidence needed, and no code change can supply it.

| ID | Gap | Type | Truth items affected | Economic value affected | Sims affected | Architectural leverage | Expected recall improvement | FP risk if built naively | Implementation complexity | Status |
|---|---|---|---:|---:|---:|---|---|---|---|---|
| GAP-001 | Rental: no governed rate basis/UOM/currency on `contracts.csv` | DATA_CONTRACT_LIMITATION | 22 | $416,247.40 | 6 (all Rental) | None (data problem) | 0% without a new customer data contract | N/A | N/A | Documented (P3.xxI.4); no code path exists |
| GAP-002 | FieldMaintenance: no currency field anywhere in the corpus | DATA_CONTRACT_LIMITATION | 26 | $7,372.32 | 4 (all FieldMaintenance) | None (data problem) | 0% without a new customer data contract | N/A | N/A | Documented (P3.xxI.5A-R); derivation mechanism built and safely abstains |
| GAP-003 | Revenue Amount Variance residual FN (historical, not re-derived this pass) | mixed | 16 | (see prior docs) | FieldMaintenance | -- | -- | -- | -- | Carried forward by reference |
| GAP-004 | Maintenance repeat/rework: no governed failure/component/service/rework relation dimension | DATA_CONTRACT_LIMITATION | 76 | $117,524.00 | 2 (FIELDMAINT-002, -007) | High if evidence ever supplied (identity/readiness foundation already fixed) | 0% without new customer data contract | Proven unsafe if bypassed (1,085 non-truth pairs at 3.21% precision) | N/A until evidence exists | Foundation fixed (P3.xxI.5B-R); capability remains correctly dormant |
| **GAP-005** | Revenue Amount Variance is aggregate (work-order-total), not itemized (line-level); misses/undercaptures unbilled parts masked by sufficient labor billing on the same invoice | **DATA_CONTRACT_LIMITATION** (reclassified -- see note) | 3 (2 FN + 1 partial) | $966.47 | >=1 (FIELDMAINT-005; likely recurs anywhere labor and parts share one invoice) | Low -- the mechanism is already correct given the data it has | 0% safely realizable without new evidence | **High** if "fixed" by guessing a labor/parts split within one aggregate invoice total | High to fix safely, effectively unbounded without new evidence | Investigated, not implemented -- see note |

> **GAP-005 note (investigated during this pass, reclassified from an
> initial `CODE_GAP` hypothesis):** `_AmountLine` already carries
> per-row, not just per-subject, evidence, so the limitation is not a
> missing data structure. It is that `invoices.csv` carries one flat
> `amount` per invoice with no line-item breakdown -- there is no
> customer-visible evidence anywhere in this corpus indicating how much
> of that one amount covers labor vs. which specific part. Detecting the
> 2 fully-missed and 1 partially-valued item precisely would require
> guessing an allocation across an un-itemized total, which is exactly
> the class of unsafe inference this program has consistently rejected
> elsewhere (e.g. never assuming a currency, never inventing a rate
> basis). Correctly reclassified as a data-contract limitation, not a
> safely fixable code gap -- no remediation is proposed for it.
| **GAP-006** | No capability reads `labor_entries.overtime_hours` against any workload-normalcy baseline (`overtime_leakage`) | **SEMANTIC_GAP** | 255 | $8,154.50 | >=1 (FIELDMAINT-005; likely recurs across all FieldMaintenance cases given 255 items in one case alone) | Low-medium -- no governed "expected/normal hours for this job size" concept exists to compare against; the breadth-expansion doc already independently flagged the parent "Labor Productivity" family as `HIGH_DESIGN_RISK` | Unknown/high risk of requiring an invented threshold to realize | **High** if a workload-normalcy baseline is invented rather than governed -- exactly the class of risk this program has repeatedly rejected elsewhere | High -- needs a new governed concept, not just new wiring | Identified, not implemented; recommend deferring per the breadth doc's own existing risk flag |
| **GAP-007** | No capability compares `maintenance_events.scheduled_date` to `completed_date` against an overdue/materially-late threshold (`preventive_maintenance_missed`) | **GOVERNANCE_GAP** | 44 (FIELDMAINT-005) + 7 (FIELDMAINT-002) = 51 across the frozen FieldMaintenance corpus | $160,196.00 (+ FIELDMAINT-002's own PM-missed value, not separately re-derived here) | 2 of 4 FieldMaintenance cases (001, 007 correctly have zero PM-missed truth and zero findings) | **High** -- both `scheduled_date` and `completed_date` were already independently confirmed `auto_accepted`/near-`auto_accepted`; no new customer data was needed | **Realized: 51/51 = 100% recall, 0 FP** across the entire frozen FieldMaintenance corpus (44/44 on FIELDMAINT-005, 7/7 on FIELDMAINT-002, 0/0 correctly on 001/007) | **Realized: 0** -- the rule requires no invented threshold at all (see implementation note) | Medium, as estimated -- plus one additional foundational fix (see note) | **IMPLEMENTED** (`MAINTENANCE-SCHEDULE-COMPLETION-GAP`, PR pending) |

> **GAP-007 implementation note:** built as designed -- an asset-anchored
> capability comparing each maintenance event's own `scheduled_date` to its
> own `completed_date` (never a cross-record comparison, never an
> externally invented overdue-day threshold). Empirical verification
> across the real corpus found that no threshold was even needed: every
> `PM`-type event in the frozen FieldMaintenance corpus is either fully
> completed or has no completion date recorded at all (zero
> partially-late cases), and corrective-maintenance-shaped rows never
> carry a scheduled date to begin with -- so "scheduled but never
> completed" alone reaches 100% recall with zero false positives, with no
> dependency on the `event_type`/"PM" label at all. One additional
> foundational fix was required during implementation and generalizes
> beyond this capability: `scheduled_timestamp` had no path to
> `AUTO_ACCEPTED` in `app/semantic/concept_registry.py` (capped at 0.80,
> `ACCEPTED_WITH_FLAG` -- it had no `compatible_dataset_roles` and no
> sibling-corroboration declaration at all), the same class of gap
> `completed_timestamp` was already fixed for in P3.xxI.3, using the
> already-precedented `alternative_sibling_concept_sets` mechanism, applied
> identically here -- raising it to `AUTO_ACCEPTED` (0.98) wherever a
> sibling `work_order_id` or `contract_id` resolves on the same dataset.
| GAP-008 | `required_field_completeness` Trust rule cannot express cross-dataset "zero matching rows" defects (`missing_records`) | CODE_GAP | 60 (DQ, not economic) | n/a | >=1 (FIELDMAINT-005) | Medium -- a referential/join-completeness check is a generically reusable Trust primitive, not FieldMaintenance-specific | Would newly surface all 60 DQ defects if built | Low -- a completeness signal, not a finding; no economic exposure risk | Medium | Identified, not implemented |

## Ranking (per the mandated criteria: truth items, economic value, sims
affected, architectural leverage, expected recall improvement, FP risk,
implementation complexity)

1. **GAP-007 (preventive_maintenance_missed)** -- ranked highest and
   **implemented**. Largest single economic exposure of any *actionable*
   gap ($160,196 -- GAP-001/002/004 are larger in aggregate but are
   confirmed data-contract dead ends with no code path at all), fully
   governed evidence already in hand, self-referential comparison (no
   invented external policy), `GOVERNANCE_GAP` (the cheapest gap type to
   close -- no new semantic concept required), and the breadth-expansion
   doc's own prior risk assessment did not flag this family as high-risk
   the way it flags Labor Productivity. Realized recall on implementation:
   51/51 (100%), 0 FP.
2. **GAP-006 (overtime_leakage)** -- highest truth-item count (255) but
   lowest per-item value ($32 average) and, critically, requires a
   governed workload-normalcy concept that does not exist yet
   (`SEMANTIC_GAP`) -- exactly the "invent a threshold" risk this program
   has consistently rejected. The breadth-expansion doc independently
   already flagged its parent family `HIGH_DESIGN_RISK`. Ranks second by
   value/count but is **not recommended to build next** given the
   governed-evidence gap.
3. **GAP-005 (Revenue Amount Variance itemization)** -- on investigation,
   reclassified from an initial code-gap hypothesis to a data-contract
   limitation: `invoices.csv` has no line-item breakdown, so closing the
   remaining 3 items would require guessing a labor/parts allocation
   within one aggregate invoice total -- unsafe inference this program
   consistently rejects elsewhere. Not a fixable gap without new
   (itemized-invoice) customer data.
4. **GAP-008 (DQ referential completeness)** -- real and reusable, but
   scores no economic value and is a Trust-layer primitive, not an
   Intelligence capability; lower urgency than the three above.
5. **GAP-001/002/003/004** -- unchanged from prior certifications;
   confirmed data-contract dead ends (or, for GAP-004, foundation already
   fixed and correctly dormant). No code path exists for any of them
   without new customer data.

## Selection and outcome (evidence-driven, not roadmap continuation)

**Selected and implemented: GAP-007 -- "Maintenance Schedule Completion
Gap"** (`MAINTENANCE-SCHEDULE-COMPLETION-GAP`, rule version `1.0`),
comparing each maintenance event's own `scheduled_timestamp` against its
own `completed_timestamp`. Owner-authorized after the ranking above was
presented; built as a genuine new capability (dataset-resolution module,
orchestration wiring, intelligence pack and rule registry entries, tests,
live verification), matching the scale of every prior capability this
program has built.

**Result exceeded the pre-implementation estimate.** No overdue-day
threshold was needed at all -- empirical verification found every
`PM`-type event in the frozen corpus is either fully completed or has no
completion date whatsoever (zero ambiguous "materially late" cases), so
"scheduled with no completion timestamp" alone is a complete, zero-
invented-parameter detector. Live-verified across the full frozen
FieldMaintenance corpus: **51/51 TP, 0 FP** (44/44 on FIELDMAINT-005, 7/7
on FIELDMAINT-002, 0/0 correctly on FIELDMAINT-001/007). Revenue Amount
Variance (61/0/86/26), `MAINTENANCE-REPEAT-VISIT`, and
`CONTRACT-RATE-COMPLIANCE` all remained unchanged on every case. Full
non-Postgres suite (1,761 tests) and disposable-Postgres suite pass; one
pre-existing test (`test_capability_shadow_stage.py`) required its
hard-coded governed-rule-code set updated to include the new rule, the
same maintenance every prior new capability in this program has required.

See the parent report (`docs/p3xxi6-fieldmaint005-full-graduation.md`) for
the full certification and implementation section.

## Learning Batch 1 (5 new simulations, 2026-09-06)

Selected from the Simulation Factory inventory (9 FieldMaintenance + 23
Rental sealed, validation-ready packages; `SIM-CLI-FM-TEST-1` excluded as
a development/test artifact by naming convention). FIELDMAINT-001/002/005/007
and RENTAL-001/003/011/012/015/018 were excluded as already-seen (frozen
Wave 1). FIELDMAINT-008 (5,518 truth items, 5.6MB/14,077 work orders) was
excluded from this first batch specifically for processing-time reasons --
flagged as a good candidate for a future scale-focused batch, not skipped
for lack of diversity value.

Selected for diversity across vertical, scale, scenario-family coverage,
and manifest/schema vintage: **FIELDMAINT-003** (richest single-case
FieldMaintenance scenario coverage, 9/9 families), **FIELDMAINT-006**
(largest scenario-diverse mid-scale case, introduces
`missing_field_ticket_billing`/`technician_idle_time`), **FIELDMAINT-009**
(introduces `unauthorized_discount`, entirely novel), **RENTAL-013**
(richest single-case Rental scenario coverage, 9/9 families, unseen), and
**RENTAL-004** (an older manifest-schema Rental package -- `category`
instead of `scenario_id`, contract/dispatch-keyed instead of work-order-keyed
-- a genuinely different data-structure vintage). All 5 hash-validated
clean against their sealed `manifest/customer_data_manifest.json`.

### Batch import/execution (Phase F)

Automated where the platform's own upload API/browser flow allowed;
customer-data-only exposure and hidden-truth-after-terminal discipline
maintained throughout. No development gap was hit in the case-creation/
upload/run pipeline itself. One process note: FIELDMAINT-006 and
FIELDMAINT-009's live production runs (Render) ran unusually long (>15
minutes, vs. 3-5 minutes for a comparably-sized case earlier the same
session) and had not reached terminal status at the time of this report --
likely contention from five near-simultaneous large uploads against a
single free/shared backend instance, not a code defect. Their reported
scores below are from a debug-instrumented execution of the byte-identical
merged `main` code against the same real files (the same cross-verification
method used throughout this program, always previously confirmed to match
live output exactly) -- flagged as pending final live terminal confirmation,
not fabricated.

| Sim | Case ID | Run ID | Terminal (live) |
|---|---|---|---|
| FIELDMAINT-003 | `a956483d-102b-4b92-8219-67d3d3624525` | `d53f51a4-783b-46ff-9cfc-d5bb61628ab0` | Yes -- `review_required` |
| FIELDMAINT-006 | `2106800e-9843-40b8-8501-1111f830799b` | `e5be2199-bd19-41ac-a470-86218769ed67` | Pending (debug-harness-verified) |
| FIELDMAINT-009 | `9b1e0337-4c33-4a5e-9569-c88854df46e6` | `3198178c-f499-4c43-9563-f7c5280c6aa4` | Pending (debug-harness-verified) |
| RENTAL-013 | `869718e0-cb79-4840-bbce-4d72440052cb` | `f041e47d-ef89-4547-96f6-60fd8257e3ea` | Yes -- `review_required` |
| RENTAL-004 | `ac31bafd-c502-4fc4-8e25-499c441ca362` | `3c8591fe-365d-4749-bdce-f77858696363` | Yes -- `review_required` |

### Per-simulation graduation results

| Sim | Truth items | Total value | TP | FP | FN | Precision | Recall | Economic capture |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FIELDMAINT-003 | 267 | $363,975.63 | 99 | 0 | 168 | 100.00% | 37.08% | 27.98% |
| FIELDMAINT-006 | 985 | $1,419,229.04 | 310 | 0 | 675 | 100.00% | 31.47% | 42.80% |
| FIELDMAINT-009 | 674 | $1,274,063.93 | 295 | 0 | 379 | 100.00% | 43.77% | 27.62% |
| RENTAL-013 | 80 | $2,225,523.27 | 0 | 0 | 80 | N/A | 0.00% | 0.00% |
| RENTAL-004 | 33 | $931,702.00 | 0 | 0 | 33 | N/A | 0.00% | 0.00% |
| **Batch total** | **2,039** | **$6,214,493.87** | **704** | **0** | **1,335** | **100.00%** | **34.53%** | **17.08%** |

Mechanical/fabricated FP = **0** across all five, verified by cross-
referencing every published finding's work order/invoice against every
truth item's `affected_records` (not just the scenario it happened to
match) -- every finding traces to a real, truth-tagged leakage.
DQ capture was not independently re-derived for this batch (would require
reading five more `data_quality_truth.json` files); expected consistent
with FIELDMAINT-005's 0/60, since no DQ-specific capability exists
(`GAP-008`, unchanged).

### Per-family results

| Scenario | Sims encountered | TP / total | Notes |
|---|---:|---:|---|
| `preventive_maintenance_missed` | 3 (003, 006, 009) | 171 / 171 (100%) | GAP-007, already remediated -- perfect transfer, zero new code |
| `unbilled_parts` | 2 (003, 006, 009 -- 3) | 181 / 186 (97.3%) | Pre-existing Revenue Amount Variance mechanism; same small aggregate-vs-itemized gap as FIELDMAINT-005 (GAP-005, data-contract-limited) |
| `unbilled_labor_hours` | 2 (003, 009) | 179 / 180 (99.4%) | **Unplanned positive transfer** -- Revenue Amount Variance was never built "for" this scenario name, catches it anyway via the same aggregate consumption-vs-billed mechanism |
| `missing_field_ticket_billing` | 2 (003, 006) | 142 / 142 (100%) | Same unplanned positive transfer |
| `contract_rate_mismatch` | 1 (003) | 31 / 31 (100%) | Same unplanned positive transfer (via Revenue Amount Variance, not the dedicated, currency-blocked Contract/Rate Compliance) |
| `repeat_repair` | 2 (003, 006) | 0 / 524 | `GAP-004`, confirmed at much larger scale ($865,862 in this batch alone vs. $117,524 originally measured) -- still data-contract-limited, unchanged conclusion |
| `technician_idle_time` | 3 (003, 006, 009) | 0 / 404 | **New gap** -- see `GAP-006` extension below |
| `overtime_leakage` | 0 in this batch (present in 005 only among sims examined this closely) | -- | Rolls into the same `GAP-006` family as `technician_idle_time` (shared root cause) |
| `delayed_work_order_completion` | 2 (003, 009) | 0 / 155 | **New gap, `GAP-009`** |
| `unauthorized_discount` | 1 (009) | 0 / 90 | **New gap, `GAP-010`** -- single occurrence so far, monitor for recurrence |
| All 9 Rental scenario families | 2 (013, 004's 3 categories) | 0 / 113 | **`GAP-011`**, Rental-vertical capability gap, extends `GAP-001` |

### New and updated gaps

| ID | Gap | Type | Sims affected (cumulative) | Economic value affected (cumulative) | Status |
|---|---|---|---:|---:|---|
| GAP-004 (updated) | `repeat_repair` -- no governed relation dimension | DATA_CONTRACT_LIMITATION | 4 (002, 003, 006, 007) | $983,386 (was $117,524) | Unchanged conclusion at much larger measured scale |
| GAP-006 (updated) | `overtime_leakage` + `technician_idle_time` (WORKFORCE_PRODUCTIVITY, no governed workload-normalcy baseline) | SEMANTIC_GAP | 4 (003, 005, 006, 009) | ~$106,043 (was $8,154.50) | Unchanged conclusion; still requires a governed concept before safe to build |
| **GAP-009** | `delayed_work_order_completion` -- no governed allowed-completion-time policy | GOVERNANCE_GAP (policy not yet defined) | 2 (003, 009) | $1,001,250 | New. Same risk class as the breadth-expansion doc's already-deferred "Revenue/Billing Timeliness" family (`FOUNDATIONAL_GAP_REQUIRED`) -- needs a governed allowed-delay policy defined before any detection logic, or risks inventing one |
| **GAP-010** | `unauthorized_discount` -- no governed discount-authorization concept | SEMANTIC_GAP | 1 (009) | $28,780.46 | New, single occurrence; insufficient evidence yet to justify investment |
| **GAP-011** | Rental vertical: 9 distinct leakage families (`excessive_asset_downtime`, `late_maintenance`, `late_return_leakage`, `unbilled_rental_days`, `duplicate_credit_or_adjustment`, `fuel_discrepancy`, `missing_field_tickets`, `delayed_invoicing`, plus the already-known `rental_rate_mismatch`/`UNDER_BILLING`/`UNBILLED_SERVICE`/`DUPLICATE_PAYMENT`) have zero dedicated capability coverage; every current capability is FieldMaintenance-shaped (`work_order_id`-keyed) and structurally does not apply to Rental's `contract_id`/`dispatch_id`-keyed schema | CAPABILITY_MODEL_GAP (majority) + DATA_CONTRACT_LIMITATION (the `rental_rate_mismatch` slice specifically, via the already-known currency/rate-basis gap) | 8 (all Rental sims examined across this program: 001, 003, 004, 011, 012, 013, 015, 018) | ~$3.58M (this batch's $3.16M + Wave 1's $416,247.40) | New/quantified. By far the single largest economic opportunity measured in this program; also the largest *architectural* undertaking -- effectively a second capability portfolio, not an extension of the first |

### Ranking (Phase H criteria: sims affected, economic value, truth-item volume, generalizability, N+1 transfer benefit, FP risk, implementation complexity)

1. **GAP-011 (Rental vertical)** -- largest by every volume/value measure (8 sims, ~$3.58M), but the least architecturally ready: no Rental-specific capability has ever been built, and most of its 9 sub-families have not yet been individually investigated for data-contract feasibility the way FieldMaintenance's gaps have been. High generalizability *within* Rental (a fix benefits all 23+ Rental sims), unknown FP risk (unstudied), high implementation complexity (new capability portfolio, not a single rule).
2. **GAP-004 (`repeat_repair`)** -- large, now-confirmed-larger value ($983,386, 4 sims), but a **closed, unavoidable data-contract limitation** -- not reusable engineering effort available today.
3. **GAP-009 (`delayed_work_order_completion`)** -- large value ($1,001,250, 2 sims), high generalizability if a governed delay policy is ever defined, but explicitly not safe to build without that policy first (same class already flagged `FOUNDATIONAL_GAP_REQUIRED` for the adjacent Billing Timeliness family).
4. **GAP-006 (workforce productivity)** -- moderate value (~$106,043, 4 sims), same "don't invent a threshold" blocker, independently already flagged `HIGH_DESIGN_RISK`.
5. **GAP-010 (`unauthorized_discount`)** -- smallest value, single occurrence; not enough evidence to prioritize yet.

**Not automatically selecting `overtime_leakage`/`technician_idle_time` despite FIELDMAINT-005's 255-item count**, per explicit instruction -- its cross-batch economic value (~$106,043) ranks below both `GAP-011` and `GAP-009`, and all three of the top candidates share the same disqualifying property today: **none are safely buildable without new evidence that does not yet exist** (new customer data for GAP-004, a new governed policy definition for GAP-009, a new capability portfolio requiring its own discovery phase for GAP-011). This is a materially different situation from GAP-007, which was safely buildable immediately because its evidence was already fully governed.

### Learning Transfer Rate (Phase I)

**Strict LTR** (previously-remediated gap types correctly handled without
new code / previously-remediated gap types encountered): `GAP-007`
(`preventive_maintenance_missed`) was encountered in 3 of 5 batch sims
and handled correctly in all 3 with zero new code. **LTR = 3/3 = 100%.**

**Unplanned positive transfer** (not part of the formal LTR metric, but a
notable bonus finding): the pre-existing `REVENUE-AMOUNT-VARIANCE`
capability -- never built "for" `unbilled_labor_hours`,
`missing_field_ticket_billing`, or `contract_rate_mismatch` specifically --
correctly and safely caught all three at 97-100% recall with zero new
code and zero fabricated FP, purely because its aggregate consumption-
vs-billed mechanism generalizes beyond its original design intent.

| Metric | Value |
|---|---:|
| New gap types this batch | 3 (`technician_idle_time`* extends GAP-006; `delayed_work_order_completion` = GAP-009; `unauthorized_discount` = GAP-010) |
| Repeat gap types this batch | 3 (`repeat_repair` = GAP-004; `overtime_leakage`/workforce-productivity family = GAP-006; Rental currency/rate gap = part of GAP-011/GAP-001) |
| Regression count | 0 -- no code changed during this batch; it is read-only graduation |
| Simulation graduation rate | 0/5 reach a graduated (near-full-recall) state; partial coverage ranges 0-43.77% |
| Aggregate recall | 34.53% (704/2,039) |
| Aggregate precision | 100.00% (0 FP) |
| Aggregate economic capture | 17.08% ($1,061,187.58 / $6,214,493.87) |

\* counted once under GAP-006 rather than as a fully separate new gap,
since it shares GAP-006's exact root cause (no governed workload-normalcy
concept), not a new blocker.

### Recommended next 1-3 remediations, expected improvement, and estimated cost

None of the three top-ranked gaps are recommended for immediate
implementation -- each requires a distinct, separately-scoped
*discovery/evidence* phase before any code is safe to write. Ranked by
readiness-to-invest-in-discovery:

1. **GAP-011 (Rental vertical) -- recommend starting a scoped discovery
   pass first**, not a build: inventory Rental's actual customer-data
   schema per sub-family (contracts/dispatch/fuel/maintenance.csv) the
   same way this program did for FieldMaintenance's own concepts, to
   determine which of the 9 sub-families are safely addressable and
   which are data-contract dead ends, before committing to any capability
   design. Expected improvement: unknown until discovery completes, but
   the value at stake (~$3.58M measured) is large enough to justify the
   discovery cost. Estimated cost: comparable to one full capability's
   worth of reconciliation research (similar in scope to this program's
   original P3.xxI.4/P3.xxI.5A reconciliation passes) before any
   implementation estimate can be trusted.
2. **GAP-009 (`delayed_work_order_completion`) -- recommend a governed
   policy-definition exercise**, not a build: define what "allowed
   completion time" or "expected job-to-cash timing" governed evidence
   would look like without inventing it from truth (the same discipline
   already applied to the adjacent Billing Timeliness family). Expected
   improvement: up to $1,001,250 across the 2 sims already measured (more
   once other sims are graduated), if and only if a safe, generic policy
   contract can be defined. Estimated cost: policy-design effort, likely
   smaller than a full capability build, but blocking.
3. **GAP-006 (workforce productivity) -- lowest priority of the three**:
   same policy-definition need as GAP-009 but for workload-normalcy
   baselines, smaller measured value (~$106,043). Recommend deferring
   until GAP-011/GAP-009 discovery work is further along, per the
   breadth-expansion doc's own existing `HIGH_DESIGN_RISK` flag.

No code changes are proposed by this report. Per the stop gate, work
stops here pending owner authorization.
