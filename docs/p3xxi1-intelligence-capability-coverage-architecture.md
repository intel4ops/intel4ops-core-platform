# P3.xxI.1 — Intelligence Capability Coverage Architecture

**Type:** Analysis / architecture only. No application code, XDOM-A, XDOM-B,
MAINT-001, truth, simulations, or frontend were changed to produce this
document.

## 1. Post-Fix-#8 baseline

- `main` at merge commit `ca9f983ada6e7fe07e111a88123c113979757e45` (PR #106,
  Fix #8 certification; code itself landed in PR #105, merge
  `910b55a846246167e158c7c0e9ca8e9c9a40709b`).
- DC-3 (FIELDMAINT-005 `trust:operations` never established) and DC-4
  (FieldMaintenance operational data never classified `domain:maintenance`)
  are both closed, confirmed live across all 10 frozen Wave 1 simulations.
- The systemic-foundation "Fix #N" sequence (Fix #1 through Fix #8) is
  considered complete. No new foundational-generalization defect was found
  during this review beyond the one item in Section 9 below, which this
  document classifies rather than fixes.
- Remaining open item carried forward from Fix #8: FieldMaintenance's XDOM-A
  is blocked only by `field:downtime_hours` — an out-of-scope
  capability/evidence-contract gap, analyzed in Section 9.

## 2. Full-truth vs. capability-scoped recall (unchanged by Fix #8)

The frozen Wave 1 truth denominator is **788 expected findings**,
$2,285,738.56 (`p3xxv1b` Section J; FieldMaintenance 629 / $413,414.73,
Rental 159 / $1,872,323.83). Truth was not touched by Fix #8 or by this
review.

| Bucket | Count | Share |
|---|---:|---:|
| PARTIALLY_IMPLEMENTED (a registered capability's declared phenomenon at least partially overlaps) | 263 | 33.4% |
| OUT_OF_SCOPE_NOT_IMPLEMENTED (no registered capability at all) | 456 | 57.9% |
| AMBIGUOUS (schema doesn't resolve whether a contract applies, or truth carries no `scenario_id`) | 69 (44 + 25) | 8.8% |
| Check | 788 | 100% |

Four governed, published FieldMaintenance findings remain in the live ledger
(FIELDMAINT-001: 2, -002: 1, -007: 1; all Rental and FIELDMAINT-005: 0), all
via XDOM-B's `XDOM-DATA-LINKAGE-ISSUE` no-shared-match-key path, not the
primary existence-match path. These were never independently re-matched
against hidden truth (`p3xxv2f` Section 11's flagged, still-open follow-up).
Honest upper bounds, not measured recall:

- **Capability-scoped recall: ≤ 4/263 = 1.5%.**
- **Full-truth recall: ≤ 4/788 = 0.5%.**

**Zero items in the wave are cleanly `IN_SCOPE_IMPLEMENTED`** once judged
against the registered rules' actual mechanics rather than scenario-name
similarity (`p3xxv2b` Section K) — this is the central fact this document
works from.

## 3. Wave 1 truth taxonomy (scenario-level, from `p3xxv2b` Sections J/L, re-verified against current code)

**FieldMaintenance (629 findings, 4 sims):**

| scenario_id | count | mapped capability | coverage status | mechanism mismatch |
|---|---:|---|---|---|
| `unbilled_parts` | 113 | XDOM-B | PARTIALLY_IMPLEMENTED | amount-variance on an *existing linked* invoice (LK-3 trace: invoice exists, amount short) — XDOM-B only checks existence |
| `unbilled_labor_hours` | 32 | XDOM-B | PARTIALLY_IMPLEMENTED | same amount-variance structural family |
| `missing_field_ticket_billing` | 7 | XDOM-B | PARTIALLY_IMPLEMENTED | same |
| `repeat_repair` | 76 | MAINT-001 | PARTIALLY_IMPLEMENTED | temporal-proximity, 2-occurrence pattern on `opened_date`/`closed_date` (LK-2 trace) — MAINT-001 is a categorical `(asset_id, failure_code)` grouping requiring ≥3 occurrences and `downtime_hours`/`repair_cost` columns absent from this data |
| `overtime_leakage` | 301 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | labor-cost/overtime-authorization; no registered capability addresses labor cost |
| `preventive_maintenance_missed` | 51 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | scheduled-vs-actual maintenance adherence |
| `contract_rate_mismatch` | 26 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | contracted-vs-actual rate comparison |
| `technician_idle_time` | 23 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | labor utilization |

**Rental (159 findings, 6 sims):**

| scenario_id | count | mapped capability | coverage status | mechanism mismatch |
|---|---:|---|---|---|
| `excessive_asset_downtime` | 44 | XDOM-A (tentative) | AMBIGUOUS | whether the injection is generated as a window-overlap event or a simple duration threshold could not be determined from the truth schema alone |
| `delayed_invoicing` | 21 | XDOM-B | PARTIALLY_IMPLEMENTED | timing/lateness; XDOM-B has no temporal-lateness logic |
| `late_return_leakage` | 12 | XDOM-B | PARTIALLY_IMPLEMENTED | LK-1 trace: base-contract revenue record exists, only the overage portion is unbilled — an existence check reads this as "matched" |
| `unbilled_rental_days` | 2 | XDOM-B | PARTIALLY_IMPLEMENTED | same amount-based reasoning |
| `late_maintenance` | 26 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | schedule adherence |
| `rental_rate_mismatch` | 22 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | rate comparison |
| `fuel_discrepancy` | 7 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | fuel cost/volume reconciliation |
| (no `scenario_id`) | 25 | — | AMBIGUOUS | truth-authoring gap, external (DC-8) |

No per-scenario dollar breakdown exists in the corpus as authored (`p3xxv1b`
Section N/J) — only family-level totals (FieldMaintenance $413,414.73, Rental
$1,872,323.83). Any per-scenario dollar figure would be fabricated; none is
given here.

## 4. Existing capability contracts (read directly from current code)

### XDOM-A — `run_asset_failure_to_lost_activity` (`app/services/cross_domain_intelligence_service.py:65-172`)

- **Business question:** did a maintenance-recorded asset downtime window
  overlap a scheduled/actual operational event for the same asset — i.e., did
  a failure cause a loss of planned activity?
- **Required canonical evidence:** literal raw/canonical column
  `downtime_hours` on the maintenance-domain dataset (via `domain_registry`
  alias, not a semantic concept); governed canonical temporal evidence on
  both maintenance and operations datasets (`canonical_temporal_evidence.py`,
  Fix #6); an ASSET-typed canonical entity clearing
  `minimum_entity_identity_confidence=0.70` (E.3, Fix #5).
- **Candidate construction:** per eligible asset key, all maintenance events
  and all operational events for that asset.
- **Matching logic:** for each maintenance event with a resolved downtime
  duration, compute `window = [event_time, event_time + downtime_hours]`;
  collect operational events whose resolved timestamp falls inside that
  window.
- **Calculation logic:** none — a pure boolean overlap, no economic value.
- **Finding condition:** at least one operational event falls inside at
  least one asset's downtime window.
- **Entity scope:** per-asset (subject = `asset`).
- **Time scope:** the maintenance event's own downtime duration only — no
  cross-event aggregation, no trend.
- **Value/recovery semantics:** none. `limitations` explicitly states "no
  economic value estimated."
- **Known blind spot:** requires a literal, pre-computed duration value; does
  not derive duration from a start/end timestamp pair even when both exist
  (Section 9).
- **Truth mechanisms it legitimately covers:** none confirmed in Wave 1 — the
  closest candidate, `excessive_asset_downtime`, is AMBIGUOUS (Section 3),
  and FieldMaintenance's own live data has no `downtime_hours` field at all.
- **Truth mechanisms it does not cover:** any revenue, billing, labor, rate,
  or schedule-adherence phenomenon.

### XDOM-B — `run_lost_activity_to_revenue_gap` (`app/services/cross_domain_intelligence_service.py:175-285`)

- **Business question:** did a completed operational event ever get billed
  at all?
- **Required canonical evidence:** `operational_event_status` on the
  operations dataset, mapped through the shared canonical-state vocabulary
  (`app/process/state_normalization.py`) to `COMPLETED`/`CLOSED`; a
  `revenue`-domain dataset.
- **Candidate construction:** operational events whose canonical status is
  `COMPLETED` or `CLOSED`.
- **Matching logic:** exact `operational_event_id` set-membership against
  the revenue dataset; fallback `(route_id, event_date)` tuple membership.
  If neither key exists on both sides at all, publishes a distinct,
  low-severity `XDOM-DATA-LINKAGE-ISSUE` finding instead of a leakage claim.
- **Calculation logic:** **binary presence only** — a vectorized anti-join.
  Never compares amounts, never checks whether a matched revenue row's
  amount is complete, has no timing/lateness concept.
- **Finding condition:** at least one completed event has no matching
  revenue row.
- **Entity scope:** dataset-level, not entity-scoped (`identity_references`
  deliberately empty since Fix #7 — "XDOM-B is intentionally non-entity
  scoped").
- **Time scope:** none beyond the fallback key's same-date requirement.
- **Value/recovery semantics:** none. `limitations` states "no amount
  estimated."
- **Known blind spot:** cannot express "billed, but for less than expected"
  (amount), "billed, but late" (timing), or "billed the base but not the
  overage" (partial/incremental quantity) — all three are structurally
  different from "never billed."
- **Truth mechanisms it legitimately covers:** none confirmed in Wave 1 —
  every PARTIALLY_IMPLEMENTED item mapped to it fails on the amount/timing
  dimension, not the existence dimension (Section 3).
- **Truth mechanisms it does not cover:** `unbilled_parts`,
  `unbilled_labor_hours`, `missing_field_ticket_billing`,
  `delayed_invoicing`, `late_return_leakage`, `unbilled_rental_days`.

### MAINT-001 — `run_maintenance_pack` (`app/services/analysis_case_intelligence_service.py:18-80`)

- **Business question:** has the same asset failed repeatedly with the same
  categorized failure type?
- **Required canonical evidence:** literal raw/canonical columns `asset_id`,
  `failure_code`, `downtime_hours`, `repair_cost` (registry
  `required_canonical_fields`), none semantic-concept-backed for
  `failure_code`/`downtime_hours`/`repair_cost`.
- **Candidate construction:** group the maintenance-domain canonical frame
  by `(asset_id, failure_code)`.
- **Matching logic:** exact categorical equality on `failure_code` — two
  failures on the same asset with *different* failure codes never group
  together, however close in time.
- **Calculation logic:** group size ≥ 3; `downtime` = sum of the group's
  `downtime_hours`; severity HIGH if downtime ≥ 24h else MEDIUM. No dollar
  exposure carried into the governed pipeline (legacy USD/hour discarded by
  design).
- **Finding condition:** group size ≥ 3.
- **Entity scope:** per-asset (subject = `asset`, Fix #7).
- **Time scope:** none — no recency window, no proximity requirement; three
  same-coded failures spread across years would still qualify.
- **Value/recovery semantics:** none carried forward (governed_pending,
  explicit limitation).
- **Known blind spot:** requires an explicit categorical failure-code field
  most maintenance exports do not carry, and a ≥3 bar that misses the far
  more common 2-occurrence "repeat visit" pattern.
- **Truth mechanisms it legitimately covers:** none confirmed in Wave 1 —
  `repeat_repair` fails on both dimensions (LK-2 trace: 2-occurrence, no
  `failure_code`/`downtime_hours`/`repair_cost` columns at all in this data).
- **Truth mechanisms it does not cover:** temporal-proximity repeat visits,
  excessive maintenance cost, excessive downtime as its own outlier signal,
  parts/labor overconsumption.

## 5. Implemented / partial / unsupported / ambiguous counts

| Status | Count | Notes |
|---|---:|---|
| IN_SCOPE_IMPLEMENTED (a registered rule's actual mechanical contract is satisfied by the truth mechanism) | **0** | confirmed by direct trace, not assumed (`p3xxv2b` Section K) |
| PARTIALLY_IMPLEMENTED | 263 | Section 3 |
| OUT_OF_SCOPE_NOT_IMPLEMENTED | 456 | Section 3 |
| AMBIGUOUS | 69 | 44 schema-ambiguous + 25 truth-authoring gap |

## 6. Capability-family architecture (reusable, not simulation-named)

Grouping the Wave 1 taxonomy (Section 3) by the underlying *business
invariant and evidence shape* — not by scenario name — yields eight
candidate families. Each is defined generically; none references
FieldMaintenance/Rental/OFS by name.

| Family | Business invariant | Minimum canonical evidence | Optional evidence | Entity scope | Time relationship | Economic measurement | Wave 1 items (by mechanism, not raw scenario count) |
|---|---|---|---|---|---|---|---|
| **REVENUE LEAKAGE — Existence** (XDOM-B, existing) | A completed unit of work has no linked billing record at all | operational event + status concept, revenue dataset, a shared identifier | route/date fallback key | dataset-level | none | none (existence only) | 0 confirmed (Stage-0/contract mismatch on all reachable candidates) |
| **REVENUE LEAKAGE — Amount Variance** (new) | A linked billing record exists but its billed quantity/amount is less than the observed/expected quantity/amount | a linked (work-order/event, invoice) pair; an observed quantity or cost concept (`quantity`, `cost_amount`) on the work side; a billed quantity or `invoice_amount` on the revenue side | unit price for a computed expected amount | per work-order/event | none | quantity or $ variance | `unbilled_parts`(113) + `unbilled_labor_hours`(32) + `missing_field_ticket_billing`(7) + `unbilled_rental_days`(2) + `late_return_leakage`(12) = **166** |
| **REVENUE LEAKAGE — Timeliness** (new) | A linked billing record exists but was issued materially later than the triggering event | a linked (event, invoice) pair; `event_timestamp`/`completed_timestamp`; `invoice_id`'s own issue date | a configurable lateness threshold | per work-order/event | event→invoice date delta | days-late, optionally $ carrying cost | `delayed_invoicing`(21) = **21** |
| **ASSET UTILIZATION / LOST ACTIVITY** (XDOM-A, existing) | A recorded asset-downtime interval overlapped planned/actual operational activity | asset identity; a duration/interval concept (missing today, Section 9); operational event timestamps | — | per asset | interval overlap | none today | `excessive_asset_downtime`(44, AMBIGUOUS) |
| **MAINTENANCE / RELIABILITY — Repeated Category Failure** (MAINT-001, existing) | The same asset fails ≥3 times under the same categorized failure code | `asset_id`, `failure_code`, `downtime_hours`/`repair_cost` | — | per asset | none | downtime hours | 0 confirmed reachable in Wave 1 (columns absent) |
| **MAINTENANCE / RELIABILITY — Repeat Visit / Rework** (new) | The same asset required a second service visit shortly after a prior one closed, regardless of failure category | `asset_id`, two service-event timestamps (open/close or equivalent) per asset | failure/category label if present | per asset | short temporal proximity between two events | none required, cost optional | `repeat_repair`(76) = **76** |
| **LABOR PRODUCTIVITY** (new, unsupported today) | Labor hours logged against work exceed an authorized/expected baseline, or logged labor time has no corresponding productive work | technician/labor time entries; a work-order/event linkage; an authorized-hours or standard-time reference | overtime flag | per technician or per work-order | shift/period | hours, optionally $ | `overtime_leakage`(301) + `technician_idle_time`(23) = **324** |
| **CONTRACT / RATE COMPLIANCE** (new, unsupported today) | A billed or contracted rate differs from the rate actually applied/observed | a contract/rate-schedule reference; the transaction's applied rate | — | per contract | none required | rate variance, $ | `contract_rate_mismatch`(26) + `rental_rate_mismatch`(22) = **48** |
| **PROCESS CYCLE-TIME / SCHEDULE ADHERENCE** (new, unsupported today) | A scheduled activity (preventive maintenance, a scheduled service) did not occur within its expected window | a schedule/plan reference; actual-occurrence evidence | — | per asset or per contract | scheduled-vs-actual delta | none required | `preventive_maintenance_missed`(51) + `late_maintenance`(26) = **77** |
| **MATERIAL / INVENTORY RECONCILIATION** (new, unsupported today, small) | A resource consumption record (fuel, parts) disagrees with an independent reference reading | a consumption record; an independent reading/reference | — | per asset | none required | quantity, $ | `fuel_discrepancy`(7) = **7** |

Two families (Amount Variance, Repeat Visit/Rework) are additive siblings to
already-registered rules, not replacements — this mirrors the Fix #5/#6
precedent of extending an existing rule's evidence contract rather than
rewriting it.

## 7. Economic coverage analysis

Only family-level totals exist in the corpus as authored (Section 3);
scenario-level dollar splits are not obtainable without a Simulation Factory
truth-schema change (`p3xxv1b` Section N — no `currency` field either).
Directionally: Rental's family total ($1,872,323.83) is dominated by
`excessive_asset_downtime`(44 items) and the REVENUE LEAKAGE — Amount
Variance items (`late_return_leakage` + `unbilled_rental_days`, 14 items);
FieldMaintenance's ($413,414.73) is spread across `overtime_leakage`(301,
largest count) and the Amount Variance items (152 items). Without a
per-record value, ranking families by confirmed dollar coverage would be
fabricated — Section 10's roadmap ranks by truth-item count and mechanism
reuse instead, and flags $ coverage as unmeasured.

## 8. Cross-industry applicability

Every family in Section 6 is defined against reusable process archetypes,
never an OFS-specific concept:

| Family | Archetype |
|---|---|
| Revenue Leakage (Existence / Amount / Timeliness) | Job-to-Cash, Contract-to-Billing |
| Asset Utilization / Lost Activity | Asset-to-Availability |
| Maintenance / Reliability (both variants) | Maintenance-to-Reliability |
| Labor Productivity | Labor-to-Productivity |
| Contract / Rate Compliance | Contract-to-Billing |
| Process Cycle-Time / Schedule Adherence | Dispatch-to-Execution, Maintenance-to-Reliability |
| Material / Inventory Reconciliation | Inventory-to-Job |

None requires a FieldMaintenance- or Rental-specific branch; industry packs
(`app/knowledge_graph`'s existing pack precedent) may later configure
thresholds or vocabulary, never the underlying contract.

## 9. XDOM-A `downtime_hours` — classification

Traced against the current canonical-concept registry
(`app/semantic/concept_registry.py`): 14 concepts are registered
(`asset_id`, `work_order_id`, `customer_id`, `invoice_id`, `technician_id`,
`part_id`, `event_timestamp`, `scheduled_timestamp`, `completed_timestamp`,
`quantity`, `unit_price`, `invoice_amount`, `cost_amount`, `currency_code`,
`status`). **None represents a duration or interval concept.**
`downtime_hours` is resolved only through the older, separate
`domain_registry.py` raw-alias table (used for domain classification and
Trust) and is read directly by literal column name inside
`run_asset_failure_to_lost_activity` (`event.get("downtime_hours")`) — the
same class of dependency `event_date` had before Fix #6 introduced
`canonical_temporal_evidence.py`. FieldMaintenance's real
`maintenance_events.csv` has no duration column at all, only a
`scheduled_date`/`completed_date` pair a duration could legitimately be
*derived* from — a derivation the current code never performs.

**Classification: FOUNDATIONAL_GENERALIZATION_GAP**, with a small necessary
downstream rule-contract change — the same two-part shape as Fix #6 (a new
canonical-evidence-resolution module plus a small XDOM-A signature change to
consume its output instead of a raw column). It is not purely an
`INTELLIGENCE_MODEL_CONTRACT_GAP`: XDOM-A's own overlap arithmetic is
already correct once given a resolved duration value; the gap is that no
canonical "duration/interval" concept and resolver exist yet, upstream of
any rule. Not implemented in this pass — analysis only.

## 10. Prioritized capability roadmap

Ranked by Wave 1 truth coverage, reusable-evidence availability
(already-registered canonical concepts vs. new concept work required),
cross-industry applicability, false-positive risk, dependency ordering, and
implementation complexity. Economic value is directional only (Section 7),
so it is not used as a primary ranking input.

| Rank | Capability | Wave 1 items | Reuses | New evidence needed | False-positive risk | Complexity |
|---|---|---:|---|---|---|---|
| 1 | Revenue Amount / Billing Variance | 166 | XDOM-B's existing linkage/matching logic and already-registered `quantity`/`cost_amount`/`invoice_amount`/`unit_price` concepts | none new | low (variance threshold, additive to an already-matched pair) | low-moderate |
| 2 | Revenue Billing Timeliness | 21 | the same matched (event, invoice) pairs Rank 1 produces | none new | low (date-delta threshold) | low |
| 3 | Maintenance Repeat Visit / Rework | 76 | MAINT-001's existing per-asset grouping infrastructure | none new (uses existing timestamp concepts) | moderate (temporal-proximity threshold needs calibration) | low-moderate |
| 4 | Duration/Interval canonical evidence (foundational) + XDOM-A consumption | 44 (AMBIGUOUS today; would also make MAINT-001's own `downtime_hours` requirement derivable) | Fix #6's `canonical_temporal_evidence.py` pattern | new: a duration/interval canonical concept and resolver | low (derivation-only, mirrors Fix #6) | low-moderate, foundational |
| 5 | Labor Productivity | 324 | none existing | new: labor-time and authorized-baseline concepts | moderate-high (baseline definition is business-context-dependent) | high — largest new family |
| 6 | Contract / Rate Compliance | 48 | none existing | new: a contracted-rate reference concept | moderate (rate-schedule modeling varies by industry) | moderate |
| 7 | Process Cycle-Time / Schedule Adherence | 77 | partial overlap with Rank 4's duration work | new: a schedule/plan reference concept | moderate | moderate |
| 8 | Material / Inventory Reconciliation | 7 | none existing | new: an independent-reading reference concept | low | low, but small Wave 1 payoff |

## 11. Recommended first implementation milestone

**Revenue Amount / Billing Variance** — a new capability, additive sibling to
XDOM-B within the REVENUE LEAKAGE family (never modifying XDOM-B itself).

- **High truth coverage:** 166/788 (21%) of the entire wave, and 166/263
  (63%) of the already-partially-reachable scope — the single largest
  reusable mechanism in the corpus.
- **High commercial relevance:** underbilling/amount-variance on already-
  linked billing records is a canonical Job-to-Cash leakage pattern, the
  category this platform is positioned around.
- **Reusable canonical evidence:** `quantity`, `unit_price`, `invoice_amount`,
  and `cost_amount` are already-registered canonical concepts (Section 9);
  the linkage mechanism (operational_event_id/work_order_id matching) is
  XDOM-B's own, already built and governed.
- **Low simulation specificity:** "an existing linked billing record's
  amount/quantity is less than what the work actually consumed or
  performed" has no FieldMaintenance- or Rental-specific concept in it.
- **Clear validation criteria:** a computed expected amount/quantity
  (from `quantity` × `unit_price`, or an observed usage count) compared
  against the linked record's billed amount/quantity, flagged when the
  variance exceeds a governed tolerance.

**Success criteria for this milestone (once approved and implemented):**
positive-path tests proving detection on a linked-record amount-shortfall
fixture; negative-path tests proving a fully and correctly billed linked
record produces no finding; no change to XDOM-B's own contract or findings;
full quality-gate discipline (focused → regression → full pytest → ruff →
mypy); a live Wave 1 rerun showing no regression on the existing 4 published
findings and honest, unforced reporting of whatever recall change (if any)
results — a flat or near-flat live recall on this specific frozen corpus
would not by itself invalidate the capability, since Wave 1's linked-record
population for this mechanism was not independently confirmed to be
non-empty in this review.

## 12. Explicit exclusions (this milestone)

No application code was modified. XDOM-A, XDOM-B, and MAINT-001 remain
byte-identical to their post-Fix-#8 state. No capability was added. Truth,
simulations, the capability registry, and the frontend were not touched. No
Wave 2, E.6, or E.7 work was started. The recommended capability in Section
11 is not implemented — implementation requires explicit project-owner
approval of this architecture first.
