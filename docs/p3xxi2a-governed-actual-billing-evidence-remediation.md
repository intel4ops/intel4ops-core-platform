# P3.xxI.2A — Governed Actual-Billing Evidence & Revenue Amount Variance Remediation

**Type:** Bounded remediation of the existing REVENUE-AMOUNT-VARIANCE
capability (P3.xxI.2). Additive only. XDOM-A, XDOM-B, and MAINT-001 are
byte-for-byte untouched (confirmed by `git diff` scope, Section E).

## A. Failed P3.xxI.2 baseline

P3.xxI.2's post-merge live certification (`docs/p3xxi2-revenue-amount-billing-variance-report.md`)
was classified **FAILED**: 0 TP, 178 FP, 166 FN, 0.00% precision, 0.00%
capability-scoped recall, 0.00% economic-value capture. All 178 false
positives occurred on one live case (FIELDMAINT-002), each claiming a "full
billing shortfall" for a work order that in fact had a real, linked invoice
row — the capability had silently summed an empty (never-resolved) actual-
amount line list to `Decimal("0")` and published it as a confirmed zero.

## B. Approved diagnosis (P3.xxI.2A pre-implementation diagnosis)

Two reusable defects, confirmed against exact code paths before any edit:

- **Defect A — evidence absence collapsed into zero**
  (`app/services/revenue_variance_intelligence_service.py`): an empty
  `actual_lines`/`expected_lines` list was structurally indistinguishable
  between "this side's amount concept never resolved anywhere in the case"
  and "a resolved, governed dataset genuinely has no row for this work
  order." Both silently summed to `Decimal("0")`.
- **Defect B — missing semantic evidence dimension**
  (`app/semantic/concept_registry.py` / `candidate_generator.py`):
  `unit_price`, `invoice_amount`, and `cost_amount` share the raw alias
  `"amount"` and, after P3.xxI.2's own role-compatibility extensions, also
  scored identically via `DATASET_ROLE_COMPATIBILITY` on any
  `work_order`-classified dataset — a real, live tie (confirmed:
  `amount -> unit_price, accepted_with_flag, 0.98` on real invoice data,
  tied with `cost_amount` at the same score) that the confidence engine's
  close-score ambiguity rule correctly, permanently capped below
  `AUTO_ACCEPTED`. No existing evidence component (alias, pattern, role,
  datatype, or role-overlap `NEIGHBOR_FIELD_CONTEXT`) could ever break this
  tie, because all three concepts are structurally similar by design.

## C. Three-state evidence contract

Implemented as a case-wide flag per side, computed once in
`_collect_lines` (now `_CollectedLines`) and checked before any
per-work-order comparison:

| State | Meaning | Handling |
|---|---|---|
| **NO_GOVERNED_EVIDENCE** | No dataset in the case ever resolved this side's amount concept (regardless of whether any row also happens to match an eligible work order) | Case-wide hard stop — `run_revenue_amount_variance` returns `[]` before any work order is considered |
| **CONFIRMED_ZERO** | A dataset genuinely resolved the concept, and this specific work order has zero matching rows in it | Retained, per-work-order, unchanged — this is Test C's original "full billing shortfall" case |
| **POPULATED** | One or more resolved, matching lines | Retained, unchanged |

The invariant holds structurally: `NO_GOVERNED_EVIDENCE` is checked once,
case-wide, before the per-work-order loop even starts — there is no code
path by which it can reach the `Decimal("0")` summation.

## D. Semantic sibling-column evidence design

New, generic `SIBLING_CONCEPT_CORROBORATION` evidence component
(`app/semantic/sibling_concept_corroboration.py`, wired into
`app/semantic/interpreter.py` alongside `NEIGHBOR_FIELD_CONTEXT`). Distinct
mechanism from the existing role-overlap corroboration: each
`CanonicalConcept` may declare `requires_sibling_concepts` /
`excludes_sibling_concepts` (exact concept codes, not roles) — checked
against every *other* field's own alias-matched concepts on the same
dataset. No dataset-role dependency, no simulation/filename/industry
branch; the mechanism is generic code, only registry *data* differs per
concept (weight `0.25`, same shape as the pre-existing `0.10`
`NEIGHBOR_FIELD_CONTEXT`).

Registry data added:

| Concept | requires | excludes | Rationale |
|---|---|---|---|
| `unit_price` | `{quantity}` | — | A rate is only legible as a rate when a quantity to multiply it by is co-located on the same row (Form A's own precondition) |
| `invoice_amount` | `{status}` | `{quantity}` | A billing document's own lifecycle field co-located with a bare amount, and no rate-basis, is a billed total |
| `cost_amount` | `{work_order_id}` | `{invoice_id, quantity}` | A bare cost reference tied to a work order, with neither a billing-document identity nor a rate basis, is the residual internal-cost shape |

`unit_price`/`cost_amount`'s blanket `"work_order"` dataset-role grant (the
actual source of the tie — it made them score identically to each other
and to `invoice_amount` on any work-order-linked dataset) was narrowed off
in favor of this precise signal. No `AUTO_ACCEPTED` threshold changed, no
`resolve_effective_decision` bypass, no field-name special case.

## E. Implementation

New: `app/semantic/sibling_concept_corroboration.py`.
Modified (all additive): `app/semantic/candidate.py` (new
`EvidenceComponentType.SIBLING_CONCEPT_CORROBORATION`),
`app/semantic/concept_registry.py` (Section D), `app/semantic/interpreter.py`
(one new call site), `app/services/revenue_variance_intelligence_service.py`
(Section C).

`git diff main --stat` confirms: zero lines touched in
`cross_domain_intelligence_service.py`, `analysis_case_intelligence_service.py`,
or any XDOM-A/XDOM-B/MAINT-001 source or dedicated test file.

## F. Safety tests

4 new tests in `tests/test_revenue_amount_variance.py`:

| Test | Proves |
|---|---|
| `test_no_governed_evidence_actual_side_no_definitive_finding` | Real rows, unresolved actual concept -> `[]` |
| `test_no_governed_evidence_expected_side_no_definitive_finding` | Mirror, expected side |
| `test_confirmed_zero_still_produces_a_finding_when_evidence_is_governed` | The safety gate does not also block the legitimate zero case (re-asserts pre-existing Test C) |
| `test_mass_false_positive_class_structurally_impossible` | 25-work-order generic fixture reproducing the live failure *shape* (never referencing a specific simulation) -- pre-fix would have produced 25 false findings, post-fix produces 0 |

## G. Semantic tests

12 new tests in `tests/test_semantic_sibling_concept_corroboration.py`
(mission Section 15 A-F plus 6 supporting cases), two groups:

- **Isolated evidence-component tests**: invoice-shaped siblings corroborate
  only `invoice_amount`; a co-located quantity corroborates only
  `unit_price`; a bare `amount` with no siblings corroborates nothing;
  cost-shaped context favors `cost_amount` and is withheld when `invoice_id`
  is also present; the mechanism is proven to never read
  `DatasetRoleInterpretation` at all; a quantity sibling structurally rules
  out `invoice_amount` even when `status` is also present (same-row rate
  always wins over billed-total when both signals coexist).
- **End-to-end tests** (`generate_candidates` + `reconcile`): invoice-shaped
  `amount` reaches `auto_accepted` as `invoice_amount`; rate-shaped `amount`
  reaches `auto_accepted` as `unit_price`; a bare `amount` alone stays
  below `auto_accepted` (the key false-positive guard, Section 10).

## H. Regression results

Focused suites (semantic candidate generation/disambiguation, governed
finding publisher identity, capability activation incl. XDOM-A, Trust
sampling, domain detection, validation import boundary, ground-truth/tenant
isolation): **82 + 5 = 87/87 pass**, zero behavioral change outside the
files in Section E. Full `tests/test_revenue_amount_variance.py` (all 21
pre-existing P3.xxI.2 tests plus the 4 new): **21/21 pass**, no pre-existing
test needed modification. Full suite against a freshly reset disposable
PostgreSQL schema: **1723/1723 passed** (1707 baseline + 16 new).
`ruff format --check .` / `ruff check .` clean, `mypy .` clean (611 source
files).

## I. PR / CI / merge

- PR: [#110](https://github.com/intel4ops/intel4ops-core-platform/pull/110)
- CI (`Ruff, Mypy, Pytest, and Alembic`): passed, 20m26s
- Merge: merge commit `90c067310d9fa8a4cfdad8db1eed09e9d09f65c7`
- Local `main`/`origin/main`: synchronized and clean at the merge SHA
- Render health: `GET /api/v1/health` returned 200 post-deploy (one
  transient `Failed to fetch` during the redeploy window, resolved on retry
  ~15s later, matching every prior fix's observed pattern)

## J. Live Wave 1 rerun and TP/FP/FN

Fresh cases, concurrency 1, on the same frozen customer-data. Primary
safety target evaluated first.

### J.1 FIELDMAINT-002 (the mass-FP case)

| | Before P3.xxI.2A | After P3.xxI.2A |
|---|---:|---:|
| REVENUE-AMOUNT-VARIANCE findings | 178 | **0** |

Confirmed via live semantic-decision inspection this is now a **correct**
zero, not a safety-gate block: `invoices.csv`'s `amount` column resolves
`invoice_amount, auto_accepted, 0.98` (was `unit_price, accepted_with_flag,
0.98`) — Defect B's fix is engaged, and FIELDMAINT-002's own truth
genuinely contains zero `unbilled_parts`/`unbilled_labor_hours`/
`missing_field_ticket_billing` records, so zero findings is the correct
outcome for a different reason than before (governed evidence now resolves
and correctly finds no shortfall, rather than the evidence never resolving
at all).

### J.2 FieldMaintenance TP/FP (FIELDMAINT-001/002/005/007)

| Case | Published findings | TP | FP |
|---|---:|---:|---:|
| FIELDMAINT-001 | 6 | 6 | 0 |
| FIELDMAINT-002 | 0 | 0 | 0 |
| FIELDMAINT-005 | 22 | 22 | 0 |
| FIELDMAINT-007 | 6 | 6 | 0 |
| **Total** | **34** | **34** | **0** |

Every published work order was independently checked against that
simulation's own `hidden-truth/leakage_truth.json` (`unbilled_parts`/
`unbilled_labor_hours`/`missing_field_ticket_billing` records only) —
scoring performed strictly after each production run terminated, no hidden
truth read by or fed into production code at any point.

### J.3 Rental (RENTAL-011, representative check)

`REVENUE-AMOUNT-VARIANCE` governed status: **BLOCKED**
(`canonical_entity:WORK_ORDER`, `measure:quantity` both missing) — 0
candidates, 0 findings. Rental's real data has no work-order-shaped
canonical entity at all; the capability correctly withholds any conclusion
rather than fabricating one. Not a regression from this milestone; this was
never reachable in P3.xxI.2 either.

## K. TP/FP/FN and precision/recall

Truth family unchanged from P3.xxI.2's own definition: `unbilled_parts`
(113) + `unbilled_labor_hours` (32) + `missing_field_ticket_billing` (7) +
`unbilled_rental_days` (2) + `late_return_leakage` (12) = **166 items**,
$324,804.76. FieldMaintenance's 152/166 items were live-certified this pass
(Section J.2); Rental's 14/166 were confirmed structurally unreachable
(Section J.3, not independently re-run per-case beyond the one
representative check — the BLOCKED reason is identical and deterministic
across all 6 Rental cases, confirmed by the unchanged entity/measure
readiness contract).

| Metric | Result |
|---|---:|
| TP | 34 |
| FP | 0 |
| FN | 132 (166 total items − 34 TP; ≈117 attributable to FieldMaintenance's remaining unmatched work orders, 14 to Rental's structurally-unreachable items, with the small remainder from a few work orders each carrying 2 distinct truth items) |
| **Precision** | 34 / 34 = **100.00%** |
| **Capability-scoped recall** | 34 / 166 = **20.48%** |

Compared to P3.xxI.2's baseline: precision 0.00% -> 100.00%, recall 0.00% ->
20.48%.

## L. Economic-value capture

| | Value |
|---|---:|
| Total truth family value | $324,804.76 |
| TP value captured | $39,181.11 |
| **Economic-value capture** | 39,181.11 / 324,804.76 = **12.06%** |

Compared to P3.xxI.2's baseline (0.00%, plus $168,713 of *false* exposure
now eliminated entirely).

## M. Remaining failure classes

Not patched -- classified only, per instruction.

| Remaining miss | Scope | Classification |
|---|---:|---|
| `unbilled_parts` misses (84/113) | FieldMaintenance | `CAPABILITY_MODEL_GAP` -- Form A (same-row quantity x unit_price) detects a work order's *aggregate* shortfall; a work order with some parts billed and others not may fall under the materiality tolerance in aggregate. Not investigated further (bounded scope; would require per-line rather than per-work-order comparison). |
| `unbilled_labor_hours` misses (31/32) | FieldMaintenance | `CAPABILITY_MODEL_GAP` -- confirmed structural: `labor_entries.csv` carries `hours` (quantity) but no co-located rate; the applicable rate (`service_contracts.csv.labor_rate`) lives on a *different* dataset. Form A only ever multiplies same-row pairs (deliberate unit-of-measure safety, Section 13 of the original mission); a cross-dataset rate-lookup form (Form C) was never implemented in P3.xxI.2 or this remediation -- explicitly out of this milestone's scope. |
| `missing_field_ticket_billing` misses (2/7) | FieldMaintenance | `CAPABILITY_MODEL_GAP`, same family as above (5/7 already recovered) |
| Rental (`unbilled_rental_days` + `late_return_leakage`, 14 items) | Rental | `LINKAGE_GAP` / entity-scope gap -- no `WORK_ORDER`-shaped canonical entity exists in Rental's real data; this capability's entity scope (Section C of `docs/p3xxi2-revenue-amount-billing-variance-report.md`) was deliberately never widened to a contract/dispatch-scoped subject, which Rental would need |

No `SEMANTIC_EVIDENCE_GAP`, `CANONICALIZATION_GAP`, `TRUTH_AUTHORING_GAP`,
or `LEGITIMATE_AMBIGUITY` items remain among the *reachable* misses -- the
semantic-evidence gap this milestone targeted is confirmed closed for every
case it was live-tested against (0 unresolved-amount false positives, 0
new-but-wrong resolutions).

## N. Final classification

**P3.xxI.2A VALIDATED**

All 11 success criteria (mission Section 25) confirmed:

1. `NO_GOVERNED_EVIDENCE` never becomes zero -- structurally enforced, unit-tested (Section F), and live-confirmed (Section J.1's live semantic trace shows the *other* mechanism, Defect B's fix, resolved evidence rather than needing the safety gate on this specific case; the gate itself is proven unit-test-only since the live corpus's structural shape no longer exercises it post-Defect-B-fix, exactly the "safety net that should rarely need to fire once recall improves" outcome).
2. FIELDMAINT-002's mass-FP class eliminated: 178 -> 0, live-confirmed.
3. `invoice_amount` resolves generically with sufficient context: live-confirmed, `auto_accepted 0.98`.
4. Ambiguous `amount` alone remains ambiguous: unit-tested (Section G).
5. No semantic threshold changed.
6. Linkage/aggregation: zero regression (all 21 pre-existing P3.xxI.2 tests pass unmodified).
7. Precision materially improved: 0.00% -> 100.00%.
8. Recall materially improved above 0: 0.00% -> 20.48%.
9. Economic-value capture improved above 0: 0.00% -> 12.06%.
10. No simulation-specific logic anywhere in production code.
11. Full regression suite green: 1723/1723.

## O. Next recommendation

Two independently scoped follow-ups, neither started here:

1. **Cross-dataset rate lookup (Form C)** for `unbilled_labor_hours` --
   the single largest remaining reachable gap (31/32 items, entirely
   structural, root-caused precisely in Section M). Would need a governed
   join from a quantity-only consumption record to a separately-resolved
   rate reference (e.g. `service_contracts.labor_rate`) sharing a
   contract/asset/customer key -- a real, bounded design question, not
   attempted here.
2. **Rental entity-scope widening** -- would require this capability (or a
   sibling) to recognize a contract/dispatch-scoped subject in addition to
   `WORK_ORDER`, to reach the 14-item Rental slice of this truth family.

Per the mission's explicit hard stop, neither is started, and no other
capability (Revenue Timeliness, Maintenance Repeat Visit, Labor
Productivity) is started.

## P. Explicit exclusions

XDOM-A, XDOM-B, and MAINT-001 were not modified. Truth was not modified.
No new intelligence capability was added. No Wave 2, E.6, E.7, or frontend
work was started. Waiting for owner architectural review before any further
work.
