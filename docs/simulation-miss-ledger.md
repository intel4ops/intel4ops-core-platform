# Simulation Miss Ledger

Program-wide, cumulative record of every material false negative (FN)
observed during a full or partial simulation graduation, classified at
the finest grain that is actually distinct, and deterministically grouped
where the underlying cause is identical across many truth items. Read
alongside `docs/simulation-gap-ledger.md`, which rolls related misses up
into reusable, ranked platform gaps.

**2026-09-06 post-merge note:** the `preventive_maintenance_missed` row
below was re-measured (not assumed) against deployed `main` at
`72d5816b682ba1b0a9dd8684d6f15999108ef2f8` via a fresh production case
(`0521ccda-2bc7-407c-9ab9-c9c24db16db3`) and confirmed resolved exactly as
recorded. See `docs/p3xxi6-fieldmaint005-full-graduation.md` Section 7 for
the full post-merge verification.

Columns: **Sim** (simulation the miss was observed on) · **Truth ref**
(scenario/finding id(s)) · **Items** · **Value** · **Classification**
(`SOURCE_HAS_EXPLICIT_SEMANTIC_EVIDENCE` /
`SOURCE_HAS_DERIVABLE_STRUCTURED_EVIDENCE` / `SOURCE_ONLY_HAS_FREE_TEXT` /
`SOURCE_HAS_INSUFFICIENT_EVIDENCE` / `IDENTITY_OR_TEMPORAL_BLOCKER` /
`GOVERNANCE_ACCEPTANCE_BLOCKER` / `CAPABILITY_MODEL_GAP` /
`DATA_CONTRACT_GAP` / `OTHER`) · **Cause** · **Linked gap**.

## SIM-OFS-FIELDMAINT-005 (P3.xxI.6 full graduation, 2026-09-06)

| Truth ref | Items | Value | Classification | Cause | Linked gap |
|---|---:|---:|---|---|---|
| `unbilled_parts`: `WO-000502`, `WO-000813` | 2 | $491.47 | `DATA_CONTRACT_GAP` | Aggregate invoice total exceeds the parts-only "expected" baseline (labor billing masks the specific unbilled part); `invoices.csv` carries no line-item breakdown to attribute the aggregate amount between labor and specific parts, so a precise fix would require guessing an allocation -- investigated and reclassified from an initial code-gap hypothesis. | `GAP-005` |
| `unbilled_parts`: `WO-000045` (partial) | 1 (partial) | $475.00 under-captured of $1,202.56 | `DATA_CONTRACT_GAP` | Same aggregate-vs-itemized mechanism as above, in a milder form -- a real shortfall is found but its magnitude does not match the simulator's own per-component model, for the same itemized-invoice-data-absence reason. | `GAP-005` |
| `overtime_leakage` (all) | 255 | $8,154.50 | `CAPABILITY_MODEL_GAP` | No registered capability reads `labor_entries.overtime_hours` against any workload-normalcy baseline; `technicians.csv` carries no `overtime_rate`-shaped field in this corpus. Building a safe baseline without inventing a threshold is unsolved. | `GAP-006` |
| `preventive_maintenance_missed` (all, FIELDMAINT-005) -- **RESOLVED** | 44 -> 0 | $160,196.00 -> $0 remaining FN | `CAPABILITY_MODEL_GAP` -> **CLOSED** | Was: no registered capability compared `scheduled_timestamp` to `completed_timestamp`. Fixed by the new `MAINTENANCE-SCHEDULE-COMPLETION-GAP` capability (GAP-007), retested: 44/44 TP, 0 FP on FIELDMAINT-005; 7/7 TP, 0 FP on FIELDMAINT-002; 0/0 correctly on FIELDMAINT-001/007. | `GAP-007` (closed) |
| DQ `missing_records` (all) | 60 defects | n/a (DQ, not economic) | `CAPABILITY_MODEL_GAP` | Existing `required_field_completeness` Trust rule is a same-row, per-field null check; structurally cannot express "zero matching rows in a different dataset" (the actual shape of this defect). | `GAP-008` |

## Learning Batch 1 (5 new simulations, 2026-09-06)

Full detail, per-sim scoring, and root-cause analysis in
`docs/simulation-gap-ledger.md`'s "Learning Batch 1" section. Summarized
here at truth-family grain (not one row per truth item, per this ledger's
own deterministic-grouping convention).

| Sim | Truth ref | Items | Value | Classification | Cause | Linked gap |
|---|---|---:|---:|---|---|---|
| FIELDMAINT-003, -006 | `repeat_repair` | 524 | $865,862.00 | `DATA_CONTRACT_GAP` | Same root cause as the original 76-item finding, now measured at much larger scale -- no governed relation dimension beyond a coarse activity category. | `GAP-004` |
| FIELDMAINT-003, -006, -009 | `technician_idle_time` | 404 | $97,888.50 | `SEMANTIC_GAP` | No governed workload-normalcy baseline exists to compare logged hours against; same root cause as `overtime_leakage`. | `GAP-006` |
| FIELDMAINT-003, -009 | `delayed_work_order_completion` | 155 | $1,001,250.00 | `GOVERNANCE_GAP` | No governed "allowed completion time" policy exists; evidence (timestamps) may be present but no threshold is defined, and none should be invented from truth. | `GAP-009` |
| FIELDMAINT-009 | `unauthorized_discount` | 90 | $28,780.46 | `SEMANTIC_GAP` | No governed discount-authorization concept exists; single-simulation occurrence so far. | `GAP-010` |
| RENTAL-013 (9 families), RENTAL-004 (3 categories) | Rental-specific leakage (`excessive_asset_downtime`, `late_maintenance`, `late_return_leakage`, `unbilled_rental_days`, `duplicate_credit_or_adjustment`, `fuel_discrepancy`, `missing_field_tickets`, `delayed_invoicing`, `rental_rate_mismatch`, `UNDER_BILLING`, `UNBILLED_SERVICE`, `DUPLICATE_PAYMENT`) | 113 | $3,157,225.27 | `CAPABILITY_MODEL_GAP` (majority) / `DATA_CONTRACT_GAP` (`rental_rate_mismatch` slice) | **Superseded by the 2026-09-06 GAP-011 discovery pass** (see `docs/simulation-gap-ledger.md`'s "GAP-011 Rental Capability Discovery" section): the "structurally inapplicable" characterization here was overstated -- code-level inspection of `app/domain_registry.py` found `dispatch.csv` and `invoices.csv` already reach existing generic concepts (`operational_event_id`, `transaction_amount`, `event_date`) via alias, so several families are evidence-sufficient today, not wholesale foreign to the platform's vocabulary. GAP-011 is decomposed into 4 distinct sub-families (DATA_CONTRACT_GAP, SEMANTIC_GAP, GOVERNANCE_GAP, and two genuinely new CAPABILITY_MODEL_GAP candidates) in that section. | `GAP-011` (extends `GAP-001`; decomposed 2026-09-06) |
| FIELDMAINT-003, -006, -009 (partial) | `unbilled_parts` residual | 5 | $796.56 | `DATA_CONTRACT_GAP` | Same aggregate-vs-itemized-invoice limitation already identified on FIELDMAINT-005. | `GAP-005` |

**Resolved this batch (not misses):** `preventive_maintenance_missed`
(171/171 across FIELDMAINT-003/006/009, `GAP-007`, zero new code) and, as
an unplanned positive transfer of the pre-existing `REVENUE-AMOUNT-VARIANCE`
capability, `unbilled_labor_hours` (179/180), `missing_field_ticket_billing`
(142/142), and `contract_rate_mismatch` (31/31, FIELDMAINT-003 only).

## Prior sessions (carried forward for continuity, not re-verified in this pass)

| Sim(s) | Truth ref | Items | Value | Classification | Cause | Linked gap |
|---|---|---:|---:|---|---|---|
| FIELDMAINT-002, -007 | `repeat_repair` (all 76) | 76 | $117,524.00 | `DATA_CONTRACT_GAP` | No governed failure/component/service/rework relation field exists in this corpus beyond a coarse two-value activity category; identity/readiness were fixed by P3.xxI.5B-R, this blocker was not and is not fixable in code alone. | `GAP-004` (see `docs/p3xxi5b-r-semantic-relation-reconciliation.md`) |
| FieldMaintenance (24 reachable), FieldMaintenance (2 unreachable, `LK-14`/`LK-49`-class) | `contract_rate_mismatch` | 24 + 2 | $7,022.26 + $350.06 | `DATA_CONTRACT_GAP` | No currency field exists anywhere in the FieldMaintenance corpus; the derived-rate mechanism computes correctly and safely withholds publication (see P3.xxI.5A-R). | `GAP-002` |
| Rental (all 6 cases) | `contract_rate_mismatch`/`rental_rate_mismatch` | 22 | $416,247.40 | `DATA_CONTRACT_GAP` | `contracts.csv` declares a bare `rate` with no rate-basis, UOM, or currency (P3.xxI.4). | `GAP-001` |
| FieldMaintenance (16 items, historical Revenue Amount baseline) | revenue-amount family | 16 | (see `docs/p3xxi2c...`/certification docs) | mixed | Pre-P3.xxI.6 FN detail not re-derived in this pass; carried forward by reference only. | `GAP-003` |

Rows above the "Prior sessions" divider are freshly re-verified in this
pass (2026-09-06, against `main` at `cc7d8a7`). Rows below it restate
prior, already-documented certification results by reference for
ledger continuity and are not re-scored here -- see each linked
certification document for their own primary evidence.
