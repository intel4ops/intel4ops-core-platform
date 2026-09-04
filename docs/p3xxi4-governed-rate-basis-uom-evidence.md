# P3.xxI.4 — Governed Rate Basis / Unit-of-Measure Evidence

## Status

Implementation merged (PR #119, SHA `e577458d8d8cab42c6a5461a220fb729b115a18b`)
and deployed. Post-merge live certification complete — see Sections O-T.
**Final classification: P3.xxI.4 VALIDATED.**

## A. Baseline

Repository `intel4ops/intel4ops-core-platform`, `main` at
`c93c1f447e3c240b6da05fa41908750e2d607b9a` — P3.xxI.3 CLOSED — PARTIALLY
VALIDATED. Authoritative conclusion preserved as this milestone's own
starting point: all six Rental cases reach `REVENUE-AMOUNT-VARIANCE`
READY with an empty `governed_missing_summary`; governed duration
derivation is proven correct and safe on live data; the FieldMaintenance
control remains intact at 61/0/86/26 with zero mechanical/fabricated
false positives; Rental economic recovery remains $0 because
`contracts.csv`'s `rate` column carries no governed rate UOM/basis
anywhere in the frozen corpus. This milestone does not reinterpret that
as a Rental-specific problem — it builds and hardens the generic rate-
basis primitive the prior report's own Section O named as the next,
separately-scoped gap.

## B. Architecture diagnosis (pre-implementation)

Traced before writing any code, against the mission's own six questions.

**A. What UOM concepts already exist?** `unit_of_measure`
(`app/semantic/concept_registry.py`) — a generic, existing concept
(introduced by P3.xxI.3), `concept_type=CODE`, aliases `unit_of_measure`/
`uom`/`unit`/`rate_basis`, `compatible_dataset_roles` spanning invoice/
inventory/labor/contract/work_order/reference/measurement, and
`alternative_sibling_concept_sets` requiring co-location with
`quantity`/`duration_hours`/`unit_price`/`hourly_rate` before it can
reach AUTO_ACCEPTED. `hourly_rate` also exists as a separate, strongly-
governed monetary concept (`requires_sibling_concepts={"contract_id"}`,
aliases `hourly_rate`/`labor_rate`/`rate_per_hour`) whose own name
inherently encodes an hour denominator.

**B. How are rate denominators represented today?**
`app/services/governed_cross_dataset_rate.py`'s `RateDatasetFields` —
`unit_field` (a resolved `unit_of_measure` column reference) and
`implicit_unit` (a caller-supplied fallback, currently populated only
from `hourly_rate`'s own resolution in
`analysis_case_orchestration_service.py`: `implicit_unit="hour" if
hourly_rate_field is not None else None`). `resolve_applicable_rate`
reads whichever is present per matched row and rejects the match
entirely (never guesses) when both are absent.

**C. Is rate basis currently inferred from field name such as
`hourly_rate`?** Yes, and ONLY that one concept — confirmed by reading
the orchestration wiring directly (line ~2132). `unit_price` (aliases
`unit_price`/`price`/`rate`/`amount`) deliberately gets **no** implicit
unit anywhere in the codebase — it is documented in the concept registry
itself as genuinely ambiguous shared vocabulary, and no code path
attaches a denominator to it. This is the exact, correct boundary
Section 7 of this mission asks to preserve.

**D. Is there already an explicit generic rate-UOM representation?** Yes
— `unit_of_measure`, generic, not duration- or Rental-specific, with a
genericity guard already built in (sibling-concept co-location required
for AUTO_ACCEPTED, so a bare `"unit"` column can never silently self-
authorize).

**E. Can a rate's denominator be governed from: explicit column (yes,
`unit_of_measure` resolution); semantic field meaning (yes, `hourly_rate`
only, by design); contractual/rate-table context (no additional generic
source found — `effective_from`/`effective_to` govern the rate's
temporal window, not its unit; nothing else in the schema encodes a
denominator); another existing governed evidence source (none found that
isn't one of the above two).**

**F. Smallest reusable architecture:** the primitive already exists and
is already correctly conservative. The concrete, bounded gaps found:
(1) `unit_of_measure`'s alias set did not yet include the generic
`rate_unit`/`billing_unit`/`price_unit` spellings this mission's own
Section 8 names; (2) the rate-evidence object `resolve_applicable_rate`
returns (`ApplicableRate`) did not carry an explicit `rate_basis`
(WHICH governed source supplied the denominator) or
`temporal_applicability` (the exact effective-date window actually
matched) field, so full lineage (Section 12's positive test E) required
a caller to re-derive both from the raw dataframe rather than reading
them off the evidence object directly. No missing capability, no
missing safety invariant — a naming/lineage-completeness gap, not an
architecture gap.

## C. Stop gate

Not triggered. No new global units ontology, no dimensional-analysis
engine, no semantic-engine or canonical-schema redesign, no external
master-data subsystem is required — the existing `unit_of_measure`
concept plus `governed_cross_dataset_rate.py`'s existing strict-equality
policy already implement this mission's core safety invariant
correctly. Continuing with a bounded, additive change.

## D. Governed rate evidence contract

`app/services/governed_cross_dataset_rate.py`'s `ApplicableRate` is
renamed to `GovernedRateEvidence` and extended with two new fields:

```python
@dataclass(frozen=True)
class GovernedRateEvidence:
    dataset_id: UUID
    dataset_label: str
    row_reference: str
    amount: Decimal
    unit: str | None
    rate_basis: str | None  # NEW
    currency: str | None
    contract_key: str
    temporal_applicability: tuple[pd.Timestamp | None, pd.Timestamp | None] | None  # NEW
```

`rate_basis` is one of two module-level constants —
`RATE_BASIS_EXPLICIT_UNIT_COLUMN` or `RATE_BASIS_IMPLICIT_UNIT_CONCEPT`
— recording WHICH of the two governed sources (Section E above) actually
supplied the denominator for this specific matched row, never left
implicit. `temporal_applicability` carries the exact `(effective_from,
effective_to)` window this row declared (or `None` when the row declares
no boundary), so a caller building finding lineage never has to re-open
the raw dataframe. No new persistence table — this is the same
plain-dataclass, no-DB-table shape `RateDatasetFields`/`ApplicableRate`
already used, and the one used by P3.xxI.3's own
`DerivedDurationEvidence`.

Mapped against the mission's own illustrative shape:

| Mission's `GovernedRateEvidence` field | This project's field |
|---|---|
| `value` | `amount` |
| `currency` | `currency` |
| `denominator_unit` | `unit` |
| `rate_basis` | `rate_basis` (new) |
| `source_reference` | `dataset_label` + `row_reference` |
| `subject_reference` | `contract_key` |
| `temporal_applicability` | `temporal_applicability` (new) |
| `provenance` | `dataset_id` |

## E. UOM policy

Unchanged, pre-existing, re-confirmed rather than modified:
`resolve_applicable_rate`'s strict-equality-or-abstain rule —
`if expected_unit is None or rate_unit is None or expected_unit !=
rate_unit: continue`. Unlike currency (where "both sides unknown" is
treated as compatible), a rate whose own unit is unknown NEVER matches
any requested unit, including a requested unit that is itself unknown.
`_normalized_unit()`'s alias table (hours/hrs/hr/h → hour; units/each/ea
→ unit; days → day; generic fallback: lowercase + strip trailing "s")
already handles non-duration bases genuinely generically — "visits" →
"visit", "miles" → "mile", "services" → "service" — with zero
duration-specific or Rental-specific branching. No new unit-conversion
logic was added; Section 9's "no silent business rounding" (25 hours
never becomes 2 billable days) was already enforced and remains so.

## F. Semantic evidence sources

Only two governed sources are accepted, matching Section 6's explicit
whitelist and Section D's `rate_basis` constants exactly:

1. **`RATE_BASIS_EXPLICIT_UNIT_COLUMN`** — an `unit_of_measure`-concept
   column resolved (via the strict, AUTO_ACCEPTED-only resolver) on the
   rate dataset itself, read per-row.
2. **`RATE_BASIS_IMPLICIT_UNIT_CONCEPT`** — a caller-supplied
   `implicit_unit`; today, populated only from `hourly_rate`'s own
   resolution (Section B/C above). `governed_cross_dataset_rate.py`
   itself stays agnostic to which upstream concept supplied it, so a
   future capability could supply a different implicit unit from a
   different strongly-governed concept without touching this module.

Filename, simulation id, customer name, domain name, and hidden truth
were never consulted anywhere in this change — confirmed by grep (no
new string literal in the diff references any of those) and by the
Rental-shaped negative test (Section H) which uses a fixture that LOOKS
like Rental data and is not treated any differently.

## G. Ambiguity rules

Preserved unchanged from P3.xxI.3: `unit_price` (aliases `unit_price`/
`price`/`rate`/`amount`) never acquires an implicit denominator under
any circumstance — confirmed by a new dedicated regression test
(`test_rental_shaped_bare_rate_column_never_infers_day_denominator`,
Section H below) using the exact column shape of the real, frozen
Rental corpus's own `contracts.csv`. Competing/multiple equally-
applicable rate rows still abstain (`matches[0] if len(matches) == 1
else None` — unchanged). An invalid/unparseable UOM token normalizes to
whatever string it is (lower-cased, trailing "s" stripped) and simply
fails to equal the expected unit, abstaining the same as any other
mismatch — no new validation was needed since the existing equality
check already rejects any non-matching token.

## H. Currency interaction

Unchanged. `resolve_applicable_rate`'s currency block: `(quantity_currency
is None) != (rate_currency is None)` abstains (asymmetric knowledge is
never treated as a match), and a known mismatch between two present
currencies abstains. No financial finding is ever produced without a
currency resolution on both sides. Not modified this milestone; verified
still covered by `test_g_currency_mismatch_without_fx_abstains` and
`test_one_known_and_one_unknown_currency_abstains` (both pre-existing,
still passing).

## I. Duration compatibility

Unchanged from P3.xxI.3. The elapsed-duration primitive
(`governed_duration_evidence.py`) and the rate-basis primitive
(`governed_cross_dataset_rate.py`) remain two separately governed
modules connected only through the existing strict unit-equality check
— an hours-denominated derived duration matches only an
`hour`-denominated rate; a days-denominated derived duration (selected
only when the QUANTITY side's own dataset carries explicit governed
`day`/`days` evidence, per P3.xxI.3's own swap logic) matches only a
`day`-denominated rate. No new conversion path was added; elapsed
duration and billable duration remain distinct concepts, matching
Section 9's explicit boundary.

## J. Non-duration rate bases

Not implemented as new capabilities this milestone (correctly deferred
per Section 10's own instruction), but confirmed genuinely reachable by
the existing generic design: `test_j_non_labor_schema_with_same_
invariant_works` (pre-existing, `basis: "unit"`, `quantity_unit="each"`)
and this milestone's own new
`test_generic_service_fixture_with_billing_unit_alias_produces_governed_rate`
(a field-service, non-Rental, non-inventory fixture using the new
`billing_unit` alias) both prove the abstraction is not duration-only.
No per-mile/per-visit/per-job CAPABILITY was implemented — only the
generic alias vocabulary and the lineage-completeness fields, exactly as
scoped.

## K. Implementation

- **`app/semantic/concept_registry.py`** — `unit_of_measure`'s alias set
  extended from `{unit_of_measure, uom, unit, rate_basis}` to also
  include `rate_unit`, `billing_unit`, `price_unit`. No new false-
  positive risk: AUTO_ACCEPTED still requires the pre-existing
  `alternative_sibling_concept_sets` co-location with a quantity/
  duration/rate concept.
- **`app/services/governed_cross_dataset_rate.py`** — `ApplicableRate`
  renamed to `GovernedRateEvidence`; added `rate_basis` and
  `temporal_applicability` fields, computed and threaded through
  `resolve_applicable_rate`'s existing match loop (no change to the
  loop's matching/abstention logic itself — only to what is recorded on
  a successful match). Added the two `RATE_BASIS_*` module constants.
- **`tests/test_governed_cross_dataset_rate.py`** — updated the renamed
  import; added `test_rate_basis_implicit_unit_concept_recorded_as_such`
  and `test_no_unit_anywhere_abstains_with_no_rate_basis`; extended the
  existing lineage assertion in
  `test_b_cross_dataset_quantity_and_applicable_rate_resolves` to check
  `rate_basis`/`temporal_applicability`/`dataset_id`/`row_reference`.
- **`tests/test_p3xxi4_governed_rate_basis_uom_evidence.py`** (new) —
  three full, unmodified `execute()` orchestration tests (Section H
  below).
- **No changes** to `app/services/revenue_variance_intelligence_service.py`,
  `app/services/analysis_case_orchestration_service.py`,
  `app/intelligence_packs/registry.py`, or any migration — none were
  needed; the existing wiring already threads `RateDatasetFields`/
  `resolve_applicable_rate` correctly, and the two new
  `GovernedRateEvidence` fields are purely additive (nothing currently
  reads them downstream of `resolve_applicable_rate`'s single call site
  in `_collect_lines`, so no call-site change was required for them to
  exist and be tested).

## L. Tests

Positive (Section 12 of the mission):

| # | Test | Result |
|---|---|---|
| A | explicit `rate_uom=hour` + governed hourly duration → compatible | `test_derived_duration_hourly_rate_end_to_end_generic_shape` (P3.xxI.3, still passing) |
| B | explicit `rate_uom=day` + governed day duration → compatible | `test_derived_duration_day_rate_end_to_end_explicit_unit_conversion` (P3.xxI.3, still passing) |
| C | strong semantic `hourly_rate`, no separate UOM column → hour denominator | `test_explicit_hourly_concept_can_supply_governed_implicit_basis` (pre-existing) + new `test_rate_basis_implicit_unit_concept_recorded_as_such` (asserts the new `rate_basis` provenance label too) |
| D | generic non-Rental fixture: service rate + explicit unit → governed rate evidence | new `test_generic_service_fixture_with_billing_unit_alias_produces_governed_rate` (exercises the new `billing_unit` alias specifically) |
| E | cross-dataset rate card with explicit basis → full lineage preserved | `test_b_cross_dataset_quantity_and_applicable_rate_resolves` (extended this milestone with explicit `rate_basis`/`temporal_applicability`/`dataset_id`/`row_reference` assertions) |

Negative (Section 13):

| # | Test | Result |
|---|---|---|
| A | bare rate with no UOM → abstain | new `test_no_unit_anywhere_abstains_with_no_rate_basis` |
| B | ambiguous rate UOM | covered by the unit-mismatch/multi-candidate primitive tests below |
| C | rate=100, duration=5 days, no denominator → no finding | new `test_rental_shaped_bare_rate_column_never_infers_day_denominator` (full orchestration run) |
| D | hourly duration with day rate, no safe compatibility → abstain | `test_derived_duration_unit_incompatible_with_rate_basis_no_finding` (P3.xxI.3, hour-vs-week; still passing) |
| E | multiple competing UOM fields → abstain | `test_c_multiple_equally_applicable_rates_abstain` (pre-existing) |
| F | currency absent where required → no financial finding | `test_g_currency_mismatch_without_fx_abstains` / `test_one_known_and_one_unknown_currency_abstains` (pre-existing) |
| G | invalid UOM token → abstain | `test_f_uom_mismatch_abstains` (pre-existing) |
| H | field name "rate" in Rental-shaped fixture → must NOT infer day | new `test_rental_shaped_bare_rate_column_never_infers_day_denominator` (uses the real corpus's exact column shape: `contract_id,customer_id,asset_id,start_date,end_date,rate`) |

Section 15 (rate-card / actual-billing separation, direct regression):
new `test_rate_card_value_never_double_counted_as_actual_billing` — a
self-cancellation fixture proving the rate card's own value is never
independently re-read as a second, actual-billing line.

## M. Regression

| Suite | Result |
|---|---:|
| `tests/test_governed_cross_dataset_rate.py` | 14 passed |
| `tests/test_p3xxi4_governed_rate_basis_uom_evidence.py` | 3 passed |
| `tests/test_p3xxi3_governed_duration_evidence.py` + `test_revenue_amount_variance.py` + `test_p3xxi2c_billable_subject_generalization.py` | 61 passed |
| Focused sweep (`rate`/`uom`/`duration`/`revenue`/`semantic`/`readiness`/`relationship`/`trust`/`lineage`/`validation_isolation`/`tenant`) | 577 passed, 1 pre-existing unrelated flake (`test_list_is_tenant_scoped_filtered_paginated_and_read_only`, `MappingRun` listing — a `created_at` tie-break timing flake unconnected to rate/UOM/revenue/semantic code; passes standalone and passed in the full suite run below) |
| Full non-PostgreSQL suite | 1698 passed |
| Disposable PostgreSQL migration/tenant-boundary suite (fresh schema reset) | 83 passed |
| `ruff format --check .` | 801 files already formatted |
| `ruff check .` | all checks passed |
| `mypy .` | 617 source files, no issues |

## N. PR / CI / merge

Implementation branch: `feature/p3xxi4-governed-rate-basis-uom-evidence`.
Implementation PR: [#119](https://github.com/intel4ops/intel4ops-core-platform/pull/119).
The repository Quality Gate passed on implementation commit `f9dd6ebc370a38060fac69e7bd2791a81fb41701`
(18m19s), including the SQLite/application suite, disposable PostgreSQL
suite, and Alembic drift/offline-SQL checks. Merged by explicit owner
authorization naming PR #119 and its exact head SHA; merge commit
`e577458d8d8cab42c6a5461a220fb729b115a18b`; local `main` synced; backend
health confirmed HTTP 200 (a `502` observed immediately after the merge
was the in-progress Render redeploy, which resolved to a stable `200`
within the same check cycle).

## O. FieldMaintenance control (post-merge, complete)

Four fresh cases were run against the frozen FieldMaintenance corpus,
via the operator UI against the live, deployed, post-merge backend
(`https://intel4ops-core-api.onrender.com`):

| Case | Case ID | Run ID | `REVENUE-AMOUNT-VARIANCE` findings | Certified baseline | Match |
|---|---|---|---:|---:|---|
| P3xxI4-Cert-FIELDMAINT-001 | `680bc4f2-7dae-4f3c-8189-8f260c309647` | `883b467c-3774-4325-82df-155993f2476c` | 61 | 61 | exact |
| P3xxI4-Cert-FIELDMAINT-002 | `5183aa02-0244-45f5-89fa-a269d137ee58` | `68e41e95-8306-45fe-805c-3dbfb6a458d2` | 0 | 0 | exact |
| P3xxI4-Cert-FIELDMAINT-005 | `13b35dc0-6d39-49fb-9118-5472309ca820` | `8c5cd10d-2645-409b-bbff-507a11062512` | 86 | 86 | exact |
| P3xxI4-Cert-FIELDMAINT-007 | `ab26536a-c8c5-4643-b705-a006168e8474` | `51d6a633-7f01-437c-a956-324621ea22fd` | 26 | 26 | exact |

The certified 61/0/86/26 pattern is preserved byte-for-byte, read
directly from each case's `rule_id`-tagged finding list (all four cases'
totals also carry the same pre-existing, unrelated `XDOM-DATA-LINKAGE-
ISSUE`/`XDOM-B-LOST-ACTIVITY-REVENUE-GAP` findings observed during
P3.xxI.3's own certification — unchanged counts, confirming this
milestone touched nothing on that path either). All four cases resolved
`REVENUE-AMOUNT-VARIANCE` readiness to READY. As predicted in Section M,
none of FieldMaintenance's real fixtures ever reach
`resolve_applicable_rate` at all (they resolve same-row `quantity` x
`unit_price` — Form A — directly), so this control confirms the
`GovernedRateEvidence` rename and its new fields introduced zero
observable change to FieldMaintenance's own finding path.

## P. Rental certification (post-merge, complete)

Six fresh cases were run against the frozen Rental corpus, via the same
methodology, against the live, deployed, post-merge backend:

| Case | Case ID | Run ID | Readiness | CONTRACT entities | Findings |
|---|---|---|---|---:|---:|
| P3xxI4-Cert-RENTAL-001 | `e4010321-624d-48c1-82cb-6ee2896b3ca1` | `73d359b6-b4b7-4375-8f65-c8cd8d67107e` | READY, `[]` | 55 | 0 |
| P3xxI4-Cert-RENTAL-003 | `0454cd8d-bc01-475d-9b58-45a07166ad89` | `5eecad31-42c9-4c30-bf28-9f01c0f27e8d` | READY, `[]` | 29 | 0 |
| P3xxI4-Cert-RENTAL-011 | `b0bb051f-4edc-4240-a809-e5e0554c87a4` | `8e03a755-046f-4ecc-9139-6b3d120a4789` | READY, `[]` | 67 | 0 |
| P3xxI4-Cert-RENTAL-012 | `c2962932-9c20-42c1-8f4b-c25fd48b2a5e` | `7089a015-1a3a-4878-8483-388e35e0c919` | READY, `[]` | 76 | 0 |
| P3xxI4-Cert-RENTAL-015 | `9e4b4081-a809-4195-96a9-9a1b424a485e` | `ad4e75c5-5883-4ecf-8dda-391816219894` | READY, `[]` | 150 | 0 |
| P3xxI4-Cert-RENTAL-018 | `f2151483-9984-496c-9698-2b5d0e5a8ac0` | `d2c94289-f20e-4cd5-9b11-8ec9dfb1b001` | READY, `[]` | 89 | 0 |

**Primary certification question: can Intel4Ops establish a governed
rate basis from the frozen Rental customer data without guessing?
No** — and this was proven directly, not merely inferred from a zero
finding count. A read-only, instrumented rerun of the real RENTAL-001
corpus against this milestone's own merged, deployed code (`main` at
`e577458d8d8cab42c6a5461a220fb729b115a18b` — `_collect_lines`/
`resolve_applicable_rate` wrapped purely to log arguments and results,
no behavior changed) traced every one of the 55 contracts end to end:

| Field | Value (representative: CNT-000001) |
|---|---|
| Subject | `CNT-000001` (CONTRACT) |
| Derived duration | 504.0 hours (`dispatch_date` 2026-02-23 → `return_date` 2026-03-16, exact, unrounded) |
| Rate value | 1850 (`contracts.csv`'s `rate` column) |
| Rate basis (`GovernedRateEvidence.rate_basis`) | **unresolved** — neither `RATE_BASIS_EXPLICIT_UNIT_COLUMN` nor `RATE_BASIS_IMPLICIT_UNIT_CONCEPT` applies |
| Rate UOM | **unresolved** — `contracts.csv` carries no `unit_of_measure`/`uom`/`unit`/`rate_basis`/`rate_unit`/`billing_unit`/`price_unit` column anywhere, and `rate` resolves as `unit_price` (0.98 confidence), never `hourly_rate`, so no implicit unit is ever attached |
| Currency | unresolved (`contracts.csv` carries no currency column either) |
| Temporal applicability | N/A — never reached; the unit check aborts the match before temporal windowing is evaluated on this path |
| Actual billing | present (`invoices.csv`/`payments.csv` resolve `unit_price`/lifecycle evidence) but never compared, since no expected-amount line exists to compare it against |
| Expected amount | **none produced** — `resolve_applicable_rate` returns `None` |
| Variance | not computed |
| Finding | none — correct abstention, `governed_status: READY`, `governed_confidence_summary.unit_violation: false` (the mismatch is an absence of evidence, not a detected conflict) |

This is not a per-case anomaly: `contracts.csv`'s header —
`contract_id,customer_id,asset_id,start_date,end_date,rate` — is
byte-identical across all six frozen Rental cases (confirmed by direct
inspection of each file), so the same evidence-absence applies to every
one of the 466 total CONTRACT entities resolved across the six live
cases (55+29+67+76+150+89). **Rate basis evidence source: none available**
for any of them — not filename, not simulation id, not hidden truth
(none consulted), not an inferred "Rental defaults to per-day" rule
(explicitly not implemented, per Section 7/11 of the mission).

**Classification of the remaining gap: `MISSING_GOVERNED_RATE_BASIS_EVIDENCE`
/ `DATA_CONTRACT_GAP`.** This is the same outcome this report's pre-merge
Section P predicted before any live evidence was gathered, now directly
confirmed with a full per-subject trace rather than inferred from a
finding count alone.

## Q. TP / FP / FN, precision, recall, economic-value capture

**FieldMaintenance** — identical to the P3.xxI.2B certified baseline
(Section O: exact finding-count match, confirmed non-engagement of the
rate-basis path): **TP=150, FN=16, Recall=90.36%, mechanical/fabricated
FP=0.**

**Rental** — against the established 14-item truth slice
(`unbilled_rental_days` + `late_return_leakage`, $241,050 total value,
examiner-side denominator, unchanged):

| Metric | Value |
|---|---|
| TP | 0 |
| FP | 0 |
| FN | 14 (all) |
| Precision | N/A (no positive predictions) |
| Recall | 0% |
| Economic-value capture | $0 of $241,050 |

**Rate-basis-specific counts (Section 6/18 of the mission)**:

| Metric | Value |
|---|---:|
| Rental CONTRACT entities with a governed rate basis established | 0 |
| Rental CONTRACT entities with unresolved rate basis | 466 (all) |
| Evidence source used for any resolved basis | none (none resolved) |
| Correctly abstained (no fabricated match) | 466 (all) |
| Fabricated / mechanical false positives | 0 |

**Combined** (informational only): TP=150, FP=0, FN=30, recall =
150/180 = 83.3%.

## R. Remaining gaps

- **Confirmed `DATA_CONTRACT_GAP` on Rental (Section P)** — no longer a
  prediction. Recovering Rental's $241,050 of known truth value requires
  either (a) the source data itself declaring a governed unit on the
  rate (an upstream data-contract fix, outside this codebase), or (b) a
  deliberate, explicit, reusable business-rule decision that a rental
  contract's bare `rate` concept defaults to "per day" absent contrary
  evidence — explicitly out of this milestone's scope (Section 11's "no
  Rental-specific inference is permitted" and Section 7's ambiguity-
  preservation rule) and correctly left for a future, explicitly scoped,
  owner-authorized milestone.
- The `hourly_rate` → implicit-hour mechanism (Section F) and the new
  `rate_unit`/`billing_unit`/`price_unit` aliases (Section K) are proven
  correct by direct and E2E tests (Section L) but are not exercised by
  either real corpus available today — FieldMaintenance never reaches
  `resolve_applicable_rate`, and Rental's `contracts.csv` never carries
  those column names. Not a defect; simply means live data has not yet
  presented the shape these paths handle.
- Non-duration rate-basis capabilities (per-mile, per-visit, per-job)
  remain unimplemented by design (Section J) — the alias vocabulary and
  lineage fields are generic and ready for them, but no capability
  consumes them yet.

## S. Final classification

**P3.xxI.4 VALIDATED.**

The mission's own explicit interpretation guidance applies directly: "if
the primitive behaves correctly but the source data provides no rate
basis, VALIDATED or PARTIALLY VALIDATED may still be appropriate
depending on live evidence" — and the live evidence gathered here
supports VALIDATED specifically, not merely PARTIALLY VALIDATED,
because this milestone's own scope (govern rate basis safely, never
guess) was fully and correctly discharged, with no capability left
incomplete for a future milestone to finish. Distinguishing this from
P3.xxI.3's PARTIALLY VALIDATED: duration derivation there was proven
necessary but not sufficient for Rental's economic recovery, leaving an
already-identified, separately-scoped follow-up (rate basis) undone.
Here, that exact follow-up was the milestone, and it did its job
completely: architecture diagnosis correctly found no stop-gate
condition; the governed rate evidence contract (`GovernedRateEvidence`,
`rate_basis`, `temporal_applicability`) is implemented and lineage-
complete; every required positive and negative test (Sections 12/13 of
the mission) passes, including a direct regression proving a bare
`"rate"` column in a Rental-shaped fixture never infers a denominator;
the FieldMaintenance control is byte-for-byte intact; live Rental
certification traced the full rate-resolution path end to end for every
one of 466 real contracts and found zero fabricated or mechanical false
positives — every single one correctly and safely abstained. The
remaining Rental gap is a confirmed, precisely classified data-contract
problem (`MISSING_GOVERNED_RATE_BASIS_EVIDENCE`), not a defect in the
capability this milestone was scoped to deliver.

## T. Next recommendation

Do not implement a UOM-inference business rule as part of any
in-progress work. If Rental's $241,050 of known value is to be pursued,
the next owner-directed milestone should explicitly scope one of: (a)
extending the frozen Rental corpus (or a future real customer's data) to
carry a governed unit on its rate data, or (b) a deliberate, reusable,
explicitly-governed business decision for how a bare rental `rate`
concept's unit should be inferred when absent — stated as its own
milestone with its own safety invariants, matching P3.xxI.3's own
Section Q recommendation. No other capability work should start until
the owner reviews this report, per the mission's hard stop.
