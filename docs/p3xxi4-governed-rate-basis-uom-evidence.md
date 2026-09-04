# P3.xxI.4 — Governed Rate Basis / Unit-of-Measure Evidence

## Status

Implementation complete on the dedicated branch; local gates pass. Merge,
deployment, and post-merge Rental live certification remain owner-gated.

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
PR not yet opened at report-drafting time — opened immediately after this
report is committed (see commit history for the PR number). Will not be
merged without explicit owner authorization, per standing house rule.

## O. FieldMaintenance control (post-merge, pending)

Not yet re-run live in this pass (deferred to the post-merge
certification alongside Rental, per established two-phase precedent from
P3.xxI.3). Local regression (Section M) gives strong evidence the
mechanism cannot regress FieldMaintenance: none of this milestone's
changes touch `revenue_variance_intelligence_service.py`'s amount-line
construction, the orchestration wiring, or any code path that actually
executes for FieldMaintenance's own fixtures (which always resolve a
direct `quantity`/`unit_price` pair on the same row — Form A — and never
reach `resolve_applicable_rate` at all). The `GovernedRateEvidence`
rename and its two new fields are additive and only observable by a
caller of `resolve_applicable_rate`, which FieldMaintenance's own
finding path does not invoke.

## P. Rental certification (post-merge, pending)

Not yet performed — per the mission's own required sequencing (Section
18), live Rental certification runs only after implementation PR review,
CI, and owner-authorized merge/deployment. This section will be
completed in a docs-only follow-up PR, using the same fresh-case
methodology established for P3.xxI.3.

**Primary question restated**: can Intel4Ops now establish a governed
rate basis from the frozen Rental customer data without guessing? Based
directly on this milestone's own architecture diagnosis (Section B) and
the new regression test using Rental's real column shape (Section H):
**no** — `contracts.csv` across all six frozen Rental cases carries no
`unit_of_measure`/`uom`/`unit`/`rate_basis`/`rate_unit`/`billing_unit`/
`price_unit` column, and its `rate` column resolves as `unit_price` (not
`hourly_rate`), which by design never acquires an implicit denominator.
This milestone's own regression test, built from that exact column
shape, predicts zero findings will persist on live Rental data — not
because the new capability failed, but because the honest answer, given
the real data, is that no governed rate-basis evidence exists to find.
This prediction is stated now, before live evidence is gathered, exactly
as the analogous P3.xxI.3 UOM-gap prediction was and was subsequently
confirmed.

## Q. TP / FP / FN, precision, recall, economic-value capture (post-merge, pending)

Deferred to the post-merge live certification (Section P) — reporting
these without live evidence would be exactly the kind of unearned
positive claim this program's standing house rules forbid.

## R. Remaining gaps

- **Predicted DATA_CONTRACT_GAP on Rental (Section P)** — genuinely open
  until live certification runs, though this milestone's own diagnosis
  and regression test both point the same direction as the prediction.
- Contractual/rate-table context beyond an explicit UOM column or the
  `hourly_rate` concept name (Section B, question E) has no other
  generic governed source in the current architecture. A future
  milestone could introduce one (e.g. a governed default-basis-per-
  contract-type declaration) only as its own explicitly scoped,
  reusable capability — never inferred here.
- Non-duration rate-basis capabilities (per-mile, per-visit, per-job)
  remain unimplemented by design (Section J) — the alias vocabulary and
  lineage fields are generic and ready for them, but no capability
  consumes them yet.

## S. Final classification

**[Deferred pending post-merge live certification — see Section P.]**
The implementation itself is complete, tested, and regression-clean; the
existing rate-basis architecture was found already correct and
conservative, and this milestone's additions (three new generic aliases,
explicit `rate_basis`/`temporal_applicability` lineage fields, and eight
new/extended regression tests directly encoding this milestone's own
required positive/negative cases) close the concrete gaps the
architecture diagnosis found without requiring any new capability,
persistence table, or unit-inference logic. Whether the overall
milestone reaches VALIDATED / PARTIALLY VALIDATED / FAILED is stated
only after live Rental certification runs post-merge, per the mission's
own required sequencing.

## T. Next recommendation

Deferred to the post-merge report. If live certification confirms the
predicted DATA_CONTRACT_GAP (Section P), the next owner-directed
milestone — not started here — should explicitly scope how Rental's own
rate data should acquire governed UOM evidence (either upstream data
contract enforcement, or an explicit, reusable, owner-approved default-
basis-inference rule), matching P3.xxI.3's own Section Q recommendation
verbatim.
