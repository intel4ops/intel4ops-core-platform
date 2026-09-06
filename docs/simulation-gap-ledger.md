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
