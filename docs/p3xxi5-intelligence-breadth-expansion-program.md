# P3.xxI.5 Intelligence Breadth Expansion Program

## P3.xxI.5 INTELLIGENCE BREADTH RECONCILIATION

**Status:** Capability #1 implemented and live-certified; P3.xxI.5A FAILED

**Reconciled baseline:** pre-implementation `origin/main` at
`a9609e36b95df0d85fabf04cc51a6a1673eae0a5`; implementation merged at
`cf25345411bbb11305503e45e0d290a7625ecbba`

**Scope:** architecture, prioritization, frozen Wave 1 evidence reconciliation,
and Capability #1 certification closeout only

## Executive decision

Recommend **Contract/Rate Compliance** as Capability #1.

Do not begin with Revenue/Billing Timeliness. The frozen data can support an observed invoice lag, but it does not currently supply both a governed invoice/billing timestamp concept and a governed allowed-delay policy. Treating an observed lag as a compliance violation would therefore require an invented business threshold and would weaken the platform's abstention and zero-fabrication posture.

Contract/Rate Compliance is the strongest next capability because it:

- compares two governed economic facts without inventing a policy threshold;
- reuses the certified rate, duration, billing, temporal-applicability, linkage, currency, UOM, identity, and lineage primitives;
- already has strong mechanical evidence: the Revenue Amount Variance certification independently reproduced 24 of 26 FieldMaintenance contract-rate truths to the cent;
- has a known, safe Rental boundary: the 22 Rental truths cannot be evaluated while governed rate-basis evidence is absent, and the engine already abstains rather than fabricating a rate;
- generalizes across labor, equipment, rental, and other governed rate schedules without Rental-specific logic.

That recommendation was subsequently implemented as P3.xxI.5A. Its live
certification result is recorded below; no Capability #2 work is authorized
by this closeout.

## Reconciled pre-implementation state

Before P3.xxI.5A, the capability registry contained four packs:

1. `MAINT-001-REPEATED-FAILURE`
2. `XDOM-A-ASSET-FAILURE-LOST-ACTIVITY`
3. `XDOM-B-LOST-ACTIVITY-REVENUE-GAP`
4. `REVENUE-AMOUNT-VARIANCE`

Only Revenue Amount/Billing Variance has a clean, end-to-end graduation against a matching frozen truth family. The other three packs are reusable portfolio assets but should not be counted as fully graduated breadth for the ten-family program: XDOM-A has ambiguous alignment to the frozen downtime truth mechanism, while MAINT-001 and XDOM-B have no clean matching Wave 1 truth items.

### Honest pre-implementation breadth measures

| Measure | Pre-implementation result | Meaning |
|---|---:|---|
| Registered/implemented portfolio breadth | 4/10 = **40.00%** | Four of the ten target areas have a registered pack with at least partial overlap. |
| Graduated family breadth | 1/10 = **10.00%** | One target truth family has completed matching end-to-end certification. |
| Graduated truth-family addressability | 166/788 = **21.07%** | The graduated Revenue Amount family contains 166 of all 788 frozen findings. |
| Addressability among classified truth items | 166/763 = **21.76%** | Excludes the 25 truth items with no `scenario_id`. |
| Observed certified TP coverage | 150/788 = **19.04%** | Uses the demonstrated Revenue Amount true-positive count, not theoretical addressability. |
| Observed authored-value capture | $83,263.29 / $2,285,738.56 = **3.64%** | Directional only; the frozen set lacks fully governed, comparable currency semantics and delayed-invoicing items have no authored value. |

The often-cited 35–40% breadth is defensible only as **registered portfolio breadth**, not as graduated family breadth or observed truth recall.

## Frozen Wave 1 truth distribution

The ten frozen cases contain 788 expected findings with a truth-authored `expected_value` total of $2,285,738.56. Twenty-five findings lack `scenario_id`; they are a truth-authoring gap and cannot be assigned honestly to one of the ten families.

| Truth scenario | Count | Authored expected value | Program family |
|---|---:|---:|---|
| `overtime_leakage` | 301 | $9,524.00 | Labor Productivity |
| `unbilled_parts` | 113 | $60,102.76 | Revenue Amount/Billing Variance |
| `repeat_repair` | 76 | $117,524.00 | Maintenance Repeat Visit/Rework |
| `preventive_maintenance_missed` | 51 | $189,058.00 | Process Cycle-Time/Schedule Adherence |
| `excessive_asset_downtime` | 44 | $126,566.63 | Asset Utilization/Lost Activity |
| `unbilled_labor_hours` | 32 | $9,470.00 | Revenue Amount/Billing Variance |
| `contract_rate_mismatch` | 26 | $7,372.32 | Contract/Rate Compliance |
| `late_maintenance` | 26 | $1,087,000.00 | Process Cycle-Time/Schedule Adherence |
| missing `scenario_id` | 25 | $717,611.00 | Unclassified / truth-authoring gap |
| `technician_idle_time` | 23 | $6,181.65 | Labor Productivity |
| `rental_rate_mismatch` | 22 | $416,247.40 | Contract/Rate Compliance |
| `delayed_invoicing` | 21 | not authored | Revenue/Billing Timeliness |
| `late_return_leakage` | 12 | $189,650.00 | Revenue Amount/Billing Variance |
| `fuel_discrepancy` | 7 | $1,459.80 | Material/Inventory Reconciliation |
| `missing_field_ticket_billing` | 7 | $14,182.00 | Revenue Amount/Billing Variance |
| `unbilled_rental_days` | 2 | $51,400.00 | Revenue Amount/Billing Variance |

The dollar column is truth-authored evidence, not a claim that every item has governed scenario-level currency. It is unsuitable for currency-normalized prioritization without an additional governed currency contract.

## Ten-family capability matrix

Status vocabulary is intentionally constrained to the program's required classifications.

| # | Intelligence family | Truth count | Current status | Reusable primitives | Missing primitives / governing evidence | Complexity | Commercial value | Breadth leverage | FP risk | Customer-data dependence | Overlap | Certification feasibility | Recommendation |
|---:|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Revenue Amount/Billing Variance | 166 | **GRADUATED** | Invoice linkage; governed duration/rate; amount, currency, UOM; readiness; stable identity; lineage | Rental governed rate-basis evidence remains absent | Medium | High | High | Low under current abstention rules | High for Rental rate basis | Can surface rate-driven amount differences | High; completed | Preserve baseline; use as control and shared arithmetic layer |
| 2 | Revenue/Billing Timeliness | 21 | **FOUNDATIONAL_GAP_REQUIRED** | Event/completed timestamps; invoice entity; temporal linkage; lineage | Dedicated governed invoice/billing timestamp and governed allowed-delay policy | Medium | High | Medium | High if a delay threshold is invented | High | May share invoice/subject linkage with amount and existence | Low today | Add semantic and policy-evidence contracts before build |
| 3 | Maintenance Repeat Visit/Rework | 76 | **FOUNDATIONAL_GAP_REQUIRED** | Asset/work-order identity; event timestamps; relationship graph; repeat detection patterns | Governed proximity window and evidence distinguishing rework from legitimate subsequent work | Medium-high | High | High | Medium-high | Related to MAINT-001, but not the same truth mechanism | Low today | Define policy evidence and intervention equivalence before build |
| 4 | Contract/Rate Compliance | 48 | **PARTIALLY_IMPLEMENTED** | Registered pack; explicit actual-rate semantics; applicable-rate resolver; temporal windows; duration; quantity; currency/UOM; subject-aware identity; lineage | Live Wave 1 has no explicit actual-rate field; implementation omitted governed attributable amount/quantity derivation; Rental also lacks rate basis/UOM and currency | Medium | High | High | Low with strict abstention | High | Overlaps economically with amount variance but explains a distinct rate breach | Live certification completed at 0 TP / 48 FN | Do not graduate; owner review required |
| 5 | Labor Productivity | 324 | **HIGH_DESIGN_RISK** | Person/work-order identity; duration; quantity; timestamps; relationship graph | Governed productive/nonproductive time, shift/capacity, overtime entitlement, work attribution | High | High | Very high | High | High | May share labor amounts with Revenue Amount | Medium-low | Defer until labor evidence model is governed |
| 6 | Process Cycle-Time/Schedule Adherence | 77 | **FOUNDATIONAL_GAP_REQUIRED** | Scheduled/completed timestamps; asset/work-order linkage; duration arithmetic | Governed schedule tolerance, expected occurrence semantics, cancellation/deferral evidence | Medium-high | High | High | High | High | Shares temporal concepts with Timeliness and Repeat Visit | Low today | Establish a reusable policy/tolerance contract first |
| 7 | Material/Inventory Reconciliation | 7 | **DEFER** | Part identity; quantity; UOM; work-order relationships | Governed movement types, independent book/physical quantities, location/custody, conversion rules | High | Medium | Low | High | High | Limited overlap with unbilled parts; different control objective | Low | Defer; low breadth return before material ledger evidence exists |
| 8 | Asset Utilization/Lost Activity | 44 | **PARTIALLY_IMPLEMENTED** | XDOM-A; asset/event linkage; governed duration; XDOM-B downstream value bridge | Frozen truth mechanism and expected utilization/downtime policy are not cleanly aligned | Medium-high | High | Medium | Medium-high | High | Strong XDOM-A/XDOM-B overlap | Low against current truth | Preserve; reconcile truth mechanism before claiming graduation |
| 9 | Repeated Maintenance Category/Failure | 0 | **PARTIALLY_IMPLEMENTED** | MAINT-001 repeated-failure pack; asset/work-order/event identity | No clean matching frozen truth items for certification | Low incremental | Medium | None in Wave 1 | Unknown | Medium | Related to, but not equivalent to, Repeat Visit/Rework | None in Wave 1 | Preserve; do not count as graduated family breadth |
| 10 | Revenue Existence/Missing Billing | 0 | **PARTIALLY_IMPLEMENTED** | XDOM-B; cross-domain linkage; revenue-gap lineage | No clean matching frozen truth items for isolated certification | Low incremental | High | None in Wave 1 | Unknown | High | May overlap with missing-field-ticket billing truth assigned to amount variance | None in Wave 1 | Preserve; do not count as graduated family breadth |

## Priority model

Each new-build candidate is scored from 1 to 5 on:

- **A — Commercial value**
- **B — Uncovered truth volume**
- **C — Cross-industry generality**
- **D — Reuse of certified architecture**
- **E — Delivery safety** (higher means lower implementation risk)
- **F — Precision safety** (higher means lower fabricated-FP risk)
- **G — Customer-data availability**
- **H — Frozen-certification feasibility**

Weighted score out of 60:

`2A + B + 1.5C + 1.5D + 1.5E + 2F + 1.5G + H`

Safety and precision receive more weight than raw truth volume. Registered packs that need truth realignment are excluded from the build ranking even where their architectural reuse is high.

| Rank | Candidate | A | B | C | D | E | F | G | H | Score / 60 | Gating interpretation |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | Contract/Rate Compliance | 5 | 2 | 5 | 5 | 4 | 5 | 4 | 5 | **54.0** | Ready to build with strict attributable-scope rules |
| 2 | Maintenance Repeat Visit/Rework | 4 | 3 | 5 | 4 | 2 | 2 | 4 | 2 | **39.5** | Blocked on governed proximity/rework policy evidence |
| 2 | Process Cycle-Time/Schedule Adherence | 4 | 3 | 5 | 4 | 2 | 2 | 4 | 2 | **39.5** | Blocked on governed schedule/tolerance evidence |
| 4 | Revenue/Billing Timeliness | 4 | 2 | 5 | 4 | 2 | 2 | 3 | 2 | **37.0** | Blocked on billing timestamp semantics and allowed-delay policy |
| 5 | Labor Productivity | 5 | 5 | 4 | 2 | 1 | 1 | 3 | 2 | **34.0** | High volume but unsafe without governed labor/capacity semantics |
| 6 | Material/Inventory Reconciliation | 3 | 1 | 4 | 2 | 1 | 2 | 2 | 2 | **26.5** | Low Wave 1 leverage and foundational ledger gaps |

The score does not override a foundational gate. Repeat Visit, Schedule Adherence, and Timeliness remain non-buildable as compliance capabilities until the required policy evidence is governed, even if their relative scores are attractive.

## Reusable governed primitives

### Canonical entities and identifiers

- `ASSET` / `asset_id`
- `WORK_ORDER` / `work_order_id`
- `CONTRACT` / `contract_id`
- `EVENT` / `dispatch_id` and event identity
- `INVOICE` / `invoice_id`
- `PERSON` / `technician_id`
- `PART` / `part_id`

### Temporal and quantitative evidence

- `event_timestamp`, `scheduled_timestamp`, `completed_timestamp`
- `effective_from` and `effective_to` applicability windows
- governed same-row and subject-linked duration evidence
- `quantity`, `duration_hours`, `unit_price`, `hourly_rate`
- `invoice_amount`, `cost_amount`, `currency_code`, and UOM
- governed cross-dataset rate resolution with temporal applicability and safe abstention

### Control-plane and finding infrastructure

- E.3 entity/relationship graph
- capability registry and readiness evaluator
- stable finding identity
- evidence and decision lineage
- materiality and currency safeguards
- finding publication
- examiner-side hidden-truth separation

These primitives make comparisons possible. They do not supply missing customer policies such as “invoice within N days,” “repeat within N days,” or “schedule deviation above N hours.” Those must remain governed evidence, not code constants inferred from hidden truth.

## Prior certification evidence carried forward

### Revenue Amount/Billing Variance

- TP = 150, FN = 16, recall = 90.36%.
- Mechanical/fabricated FP = 0.
- FieldMaintenance control counts = 61 / 0 / 86 / 26.
- Strict family precision = 150 / 174 = 86.21% because 24 findings belonged to Contract/Rate Compliance rather than the amount-variance truth family.
- All 24 out-of-family findings were independently verified against frozen contract-rate truths to the cent; they represent 24 of 26 FieldMaintenance `contract_rate_mismatch` items and $7,372.32 in truth-authored value.
- Amount-family authored value = $324,804.76; captured value = $83,263.29, or 25.63%.

### Governed Rental rate evidence

- All six Rental cases reached Revenue Amount Variance READY.
- Governed duration evidence remained correct.
- 466 Rental `CONTRACT` entities were evaluated.
- Zero had governed rate-basis evidence.
- All 466 correctly abstained, with zero fabricated/mechanical false positives.
- The remaining boundary is `MISSING_GOVERNED_RATE_BASIS_EVIDENCE / DATA_CONTRACT_GAP`, not a duration or capability-model defect.

## Capability #1 architecture contract: Contract/Rate Compliance

### Business question

Was an attributable billed unit rate different from the governed rate applicable to the same subject, service interval, UOM, currency, and billing scope?

### Required evidence

1. A governed subject (`WORK_ORDER`, `CONTRACT`, or another general canonical subject).
2. An exact link from that subject to the applicable contract/rate row.
3. A governed transaction or service timestamp within the rate's effective window.
4. A governed applicable rate, rate basis, UOM, and currency.
5. An exact link to billed-amount evidence.
6. Governed billable quantity or duration with a compatible UOM.
7. An attributable scope proving the billed amount and billable quantity describe the same charge.

### Evaluation

Derive an actual applied rate only when:

`actual_applied_rate = attributable_billed_amount / governed_billable_quantity`

Then compare that rate with the single governed applicable rate for the same scope. A mismatch may become a finding only after currency precision or an explicit governed tolerance is applied. The capability must not introduce an arbitrary rate threshold.

### Mandatory abstention rules

- Missing billing evidence is not billed amount zero.
- Missing, zero, ambiguous, or non-attributable quantity prevents division and causes abstention.
- Ambiguous subject, invoice, contract, or rate linkage causes abstention.
- Multiple equally applicable rates cause abstention.
- Incompatible or missing rate basis/UOM causes abstention.
- Missing or incompatible currency causes abstention.
- No foreign-exchange conversion occurs without governed FX evidence.
- A total invoice amount cannot be treated as a line's attributable amount without exact scope evidence.

### Identity and lineage

Finding identity should include the governed subject, invoice or billing record, applicable rate reference, and comparison scope. Lineage must expose:

- raw subject, billing, contract, and rate records;
- all relationship and canonicalization decisions;
- rate effective-window selection;
- rate basis, UOM, currency, and timestamps;
- billed-amount and quantity attribution;
- actual-rate arithmetic, expected-rate comparison, and materiality decision;
- every abstention reason when the evidence contract is incomplete.

### Generalization and overlap controls

Certification fixtures should cover labor, equipment/rental, and material unit-rate shapes without source- or simulation-specific branches. A rate mismatch may also cause a Revenue Amount Variance finding, but the two capabilities answer different questions. Portfolio aggregation must prevent double-counting the same economic impact while preserving both explanations and their lineage.

## Breadth gain projection

### Capability #1 alone

If all 48 rate-compliance truths were addressable, graduating Capability #1 would produce:

- graduated family breadth: 2/10 = **20.00%**;
- theoretical truth-family addressability: (166 + 48) / 788 = **27.16%**.

The current evidence-supported ceiling is lower because the 22 Rental rate-mismatch truths lack governed rate-basis evidence:

- currently supportable amount-plus-rate items: (166 + 26) / 788 = **24.37%**.

The difference must be reported as customer-data dependence, not recovered with Rental-specific billing logic.

### Three-capability planning horizon

If Contract/Rate Compliance, Maintenance Repeat Visit/Rework, and Revenue/Billing Timeliness eventually graduate:

- registered portfolio breadth could rise from 4/10 to 7/10 = **70.00%**;
- graduated family breadth could rise from 1/10 to 4/10 = **40.00%**;
- theoretical truth-family addressability would be (166 + 48 + 76 + 21) / 788 = **39.47%**.

That sequence does **not** reach 60% truth-weighted breadth. Labor Productivity contains 324 items and is ultimately necessary to exceed 60%, but its current evidence model is high risk. It should not be accelerated merely to improve the percentage.

After Capability #3, the program must stop for owner review before any fourth build, exactly as the milestone gate requires.

## Architecture risks and required mitigations

| Risk | Consequence | Required mitigation |
|---|---|---|
| Capability-family double counting | Inflated economic value and conflicting narratives | Preserve distinct finding types and add impact-deduplication semantics at portfolio aggregation. |
| Inferred policy thresholds | Hidden-truth leakage and systematic FP | Require governed policy/tolerance evidence; otherwise compute an observation or abstain. |
| Invoice-header attribution | Total invoice amount divided by unrelated quantity | Require exact charge scope or governed allocation evidence. |
| Missing-versus-zero collapse | Fabricated revenue or compliance findings | Maintain explicit missingness; zero is a finding input only when positively governed. |
| Temporal misapplication | Wrong contract rate selected | Require service/transaction timestamp and a single effective rate window. |
| UOM or rate-basis mismatch | Mechanically plausible but false variance | Normalize only through governed conversions; otherwise abstain. |
| Currency mixing | Invalid value and materiality comparison | Compare like currency only; no implicit FX. |
| Source-specific shortcuts | Non-reusable capability and simulation overfit | Implement against canonical entities/evidence contracts and certify multiple domain shapes. |
| Truth-authoring ambiguity | Misleading breadth claims | Keep the 25 unclassified items outside family-level recall until truth is repaired under separate authorization. |

## Implementation recommendation for owner review

Authorize Capability #1 only if the owner accepts the following bounded plan:

1. Build a general Contract/Rate Compliance pack over governed canonical evidence.
2. Reuse the existing applicable-rate and duration primitives; do not fork Rental-specific logic.
3. Add only the minimum canonical comparison/attribution behavior required by the architecture contract.
4. Preserve all current amount-variance controls as regression cases.
5. Certify FieldMaintenance against the 26 rate truths and Rental against both its 22 authored truths and its known safe-abstention boundary.
6. Report FieldMaintenance and Rental separately, including readiness, TP/FP/FN, precision, recall, value capture, and abstention reasons.
7. Do not alter frozen truth, XDOM-A, XDOM-B, MAINT-001, or semantic thresholds to improve results.
8. Stop after certification and await owner direction before Capability #2.

Revenue/Billing Timeliness should be reconsidered only after the platform has a dedicated governed billing timestamp and a governed allowed-delay policy. Maintenance Repeat Visit/Rework similarly requires a governed proximity/rework policy. Observed elapsed time is a reusable primitive; it is not by itself evidence of a violation.

## Phase 1 closeout

**Recommended Capability #1:** Contract/Rate Compliance

**Implementation status:** MERGED; LIVE CERTIFICATION FAILED

**Owner gate:** REQUIRED

P3.xxI.5 Phase 1 stops here. No application code, truth, semantic threshold, existing capability, frontend, Wave 2, E.6, or E.7 change is included or authorized.

## Capability #1 post-merge scorecard

P3.xxI.5A merged through PR #121 at
`cf25345411bbb11305503e45e0d290a7625ecbba`. Production health returned
HTTP 200. Ten fresh runs reused the exact certified orchestrated Wave 1
cases; Revenue Amount remained 61/0/86/26 with zero mechanical regression.

The Contract/Rate family denominator remained frozen at 48 items before
scoring: 26 FieldMaintenance `contract_rate_mismatch` items worth $7,372.32
and 22 Rental `rental_rate_mismatch` items worth $416,247.40. Every live
case was structurally blocked on `measure:actual_applied_rate`, so no
candidate and no dedicated finding was produced.

| Measure | Before P3.xxI.5A | After P3.xxI.5A | Delta |
|---|---:|---:|---:|
| Registered portfolio breadth | 4/10 = **40.00%** | 5/10 = **50.00%** | +10.00 pp |
| Graduated-family breadth | 1/10 = **10.00%** | 1/10 = **10.00%** | none |
| Graduated truth-family addressability | 166/788 = **21.07%** | 166/788 = **21.07%** | none |
| Certified TP coverage | 150/788 = **19.04%** | 150/788 = **19.04%** | none |
| Observed authored-value capture | $83,263.29 / $2,285,738.56 = **3.64%** | $83,263.29 / $2,285,738.56 = **3.64%** | none |

Capability #1 itself scored TP=0, FP=0, FN=48, recall=0%, precision N/A,
economic-value capture $0/$423,619.72, and mechanical/fabricated FP=0.
Registered breadth increased because the pack exists, but graduated and
observed coverage did not increase because it did not activate on Wave 1.

The dominant FieldMaintenance failure is `CAPABILITY_MODEL_GAP`: the
architecture program called for an exact attributable billed-scope path,
while the implementation accepts only an explicit actual-rate concept and
does not derive an applied rate from governed invoice amount and billable
scope. The Rental failure remains `SEMANTIC_EVIDENCE_GAP` /
`DATA_CONTRACT_GAP`: no explicit actual rate, rate basis/UOM, or currency is
present. Full evidence, per-case run IDs, and regression reconciliation are
in `docs/p3xxi5a-contract-rate-compliance.md`.

**P3.xxI.5A FAILED**

Capability #2 must not start without a new owner authorization.
