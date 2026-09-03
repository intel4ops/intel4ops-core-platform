# P3.xxI.3 — Governed Canonical Duration / Interval Evidence

## Status

Implementation complete on the dedicated branch; local gates pass. Merge,
deployment, and post-merge Rental live certification remain owner-gated.

## A. Baseline

Repository `intel4ops/intel4ops-core-platform`, `main` at
`6a1f0f1bd59b96b2edce100dccfbd7c11093d4c0` — P3.xxI.2C CLOSED — VALIDATED.
Authoritative conclusion preserved as this milestone's own starting point:
Rental's subject/entity scope is fixed (CONTRACT/EVENT entities resolve
correctly, E.3 relationships activate, FieldMaintenance baseline intact,
zero mechanical/fabricated FP); all six Rental cases were BLOCKED on
exactly one remaining gate, `measure:quantity`, classified as
`FOUNDATIONAL_CANONICAL_DURATION_EVIDENCE_GAP`. This milestone does not
reinterpret that as a Rental-specific problem — it builds the generic
primitive the classification named.

## B. Architecture diagnosis (pre-implementation)

**What timestamp concepts already exist.** Six, in
`app/semantic/concept_registry.py`: `event_timestamp` ("when an event/
activity occurred," already aliases `dispatch_date`/`maintenance_date`),
`scheduled_timestamp` (`scheduled_date`/`planned_date`/`due_date`),
`completed_timestamp` (`completed_date`/`completed_at`/`closed_date`/
`finished_at`), and the pair `effective_from_timestamp`/
`effective_to_timestamp` (`start_date`/`end_date`, but
`requires_sibling_concepts={contract_id}` — this pair means specifically
"a rate-card row's own applicability window," consumed exclusively by
`governed_cross_dataset_rate.py`).

**Which existing pair represents a generic interval.** None as-is —
`effective_from/to` is semantically and mechanically committed to
rate-window validity; reusing it for "elapsed duration of an activity"
would conflate two different concepts and risk destabilizing the
existing rate machinery. The correct generic pair is `event_timestamp`
(start) → `completed_timestamp` (end), with a second declared
alternative `scheduled_timestamp` → `completed_timestamp` (literally
"cycle time," one of the mission's own listed examples). Both concepts
already existed; the only addition was `"return_date"` on
`completed_timestamp`'s alias set — a generic "an activity came to an
end" spelling, not Rental-specific.

**Is duration already partially represented.** No. `duration_hours` is a
`QUANTITY` concept read directly from one stored column — never derived
from two timestamps. `governed_cross_dataset_rate.py`'s `_timestamp()`
helper only does point-in-time window comparison, never elapsed-time
arithmetic. Confirmed clean gap.

**Should duration be a concept, a derived observation, or another type
— and where should it live.** A derived, ephemeral evidence object,
computed by a new framework-light service module
(`app/services/governed_duration_evidence.py`), mirroring
`governed_cross_dataset_rate.py`'s own shape exactly — a plain dataclass
result, no DB table, no new semantic-concept type. Invoked from a small,
capability-agnostic orchestration helper, not embedded inside
`REVENUE-AMOUNT-VARIANCE`'s own code, so any future capability can reuse
it unchanged. The derived value is materialized as a new column on a
copied dataframe, reusing the exact bridge-column pattern P3.xxI.2C
already proved — `_collect_lines`/`resolve_applicable_rate` needed
**zero changes**; a derived duration is just another `quantity_field` to
them.

**Provenance.** A `DerivedDurationEvidence` dataclass (start/end concept
+ field + raw value, elapsed value + unit, row reference) threaded into
the existing `_AmountLine.basis`/evidence-description mechanism — visible
in every finding's `supporting_evidence`, no new persistence.

**Unit representation.** Exact `timedelta` arithmetic, exposed as two
separately-computed, unrounded columns (hours and days); the orchestration
layer selects whichever matches the resolved rate's own governed unit —
mirrors `governed_cross_dataset_rate.py`'s `_normalized_unit()` policy
exactly (units compared by equality, never coerced).

**Smallest reusable implementation.** One new service module, one small
orchestration helper, one alias addition, two `alternative_sibling_
concept_sets` additions (below), one new `alternative_canonical_measure_
sets` pair of entries. No new concept types, no new DB schema, no new
global ontology.

**Stop-gate check.** Fits entirely within the existing declarative-registry
+ framework-light-service + orchestration-wiring pattern already used
three times (P3.xxI.2A/2B/2C). No architectural expansion required.

## C. Duration evidence contract

`app/services/governed_duration_evidence.py`:

- `DurationEndpointPair(start_concept, end_concept)` — a declared,
  generic pair. `DECLARED_INTERVAL_PAIRS = (("event_timestamp",
  "completed_timestamp"), ("scheduled_timestamp", "completed_timestamp"))`,
  tried in declared order.
- `DerivedDurationEvidence(start_concept, end_concept, start_field,
  end_field, start_value, end_value, elapsed_hours, elapsed_days,
  row_reference)` — provenance-complete by construction.
- `resolve_row_duration(row, start_field, end_field, start_concept,
  end_concept, row_reference)` — same-row derivation. Returns `None`
  (abstain) on any missing, unparseable, or inverted endpoint. Never a
  fabricated zero.
- `resolve_cross_dataset_duration(start_by_subject, end_by_subject,
  start_concept, end_concept)` — subject-keyed cross-dataset variant
  (Section 13E). A subject present in only one map is silently absent
  from the result, never a fabricated entry (Section 14I).

## D. Temporal semantics

- **Governed authority only.** Callers pass endpoint field names already
  resolved through the strict, `AUTO_ACCEPTED`-only
  `_resolve_canonical_concept_field` path — an ambiguous or
  `REVIEW_REQUIRED`/`ACCEPTED_WITH_FLAG` endpoint never reaches the
  derivation at all (Section 9's "do not bypass
  `resolve_effective_decision`"). Verified directly:
  `test_ambiguous_endpoint_never_reaches_derivation_no_duration`,
  `test_one_governed_one_ambiguous_endpoint_no_duration`.
- **Missing/inverted/unparseable → abstain, never zero.** `_parse_timestamp`
  returns `None` on anything `pd.to_datetime` can't resolve;
  `_elapsed()` returns `None` on `end < start` or a `TypeError` from
  comparing incompatible timestamps (e.g. one offset-aware, one naive —
  pandas itself refuses this comparison, which is exactly the correct
  abstain signal, never papered over).
- **Timezone safety.** Offsets are preserved via `pd.to_datetime`'s own
  parsing; naive timestamps stay naive. No invented conversion anywhere.
  Verified: `test_timezone_aware_timestamps_correct_elapsed_time`,
  `test_mismatched_tz_awareness_abstains_not_crashes`.
- **Date-only intervals.** A bare date parses to that date's own
  midnight — pandas' own pre-existing, deterministic behavior, not a new
  rule this module introduces. Verified:
  `test_date_only_interval_deterministic_midnight_semantics`.
- **Competing interval pairs.** When more than one declared pair
  resolves on the same dataset and disagrees materially (>0.01h) on any
  shared row, the derivation abstains entirely rather than silently
  preferring one. When they agree (or don't overlap), declaration order
  is the governed resolution — the same convention `alternative_
  canonical_measure_sets`/`alternative_sibling_concept_sets` already use
  elsewhere. Verified: `test_competing_interval_pairs_that_disagree_
  abstain`, `test_competing_interval_pairs_that_agree_use_first_declared`.

## E. Unit policy

No rounding, ever: `elapsed_hours`/`elapsed_days` are both computed
directly from `timedelta.total_seconds()` as exact `Decimal` division (÷
3600, ÷ 86400) — 23 hours stays 23 hours, 25 hours stays 25 hours, never
coerced to a day boundary (Section 6's own explicit prohibition, verified
directly: `test_no_rounding_23_hours_stays_23_hours_not_1_day`,
`test_no_rounding_25_hours_stays_25_hours_not_1_day`).

**Which unit reaches the rate match** is a policy decision at the
orchestration layer, never inside the primitive itself:

1. If the QUANTITY dataset carries its own explicit, governed
   `unit_of_measure` value saying "day"/"days", days is used directly.
2. Otherwise the quantity defaults to hours, but the choice is
   **provisional** — recorded as a pending swap candidate — until the
   full per-subject-type pass's `rate_dataset_fields` is known (a
   dataset processed early in the loop cannot yet see a rate discovered
   later in the same pass).
3. After the loop, if ANY applicable rate's own governed `unit_of_
   measure` value says "day"/"days", every pending candidate is swapped
   from the hours column to the days column.
4. If neither signal fires, hours stays the exposed quantity, and a
   day-denominated rate correctly, honestly fails to match
   (`resolve_applicable_rate`'s own strict equality check) — the honest
   UOM_GAP outcome, never a fabricated match. Verified end-to-end:
   `test_derived_duration_unit_incompatible_with_rate_basis_no_finding`
   (a "week"-denominated rate against an hours-denominated duration
   correctly produces zero findings).

No business rounding, minimum billable day, round-up, grace period, or
billing calendar is implemented anywhere — Section 12's boundary is
respected exactly as stated.

## F. Lineage

Every derived expected-amount line's `basis` reads
`"quantity_x_cross_dataset_rate"` exactly as before (unchanged from
P3.xxI.2B) — the derivation is transparent to the existing evidence
mechanism by design (Section E's own point: zero changes needed to
`revenue_variance_intelligence_service.py`). The governed concept pair
actually used (`event_timestamp->completed_timestamp` or
`scheduled_timestamp->completed_timestamp`) feeds
`canonical_evidence_completeness`'s `required_concepts` set — but only
when the specific pair the derivation actually used, never an unrelated
resolved timestamp this dataset happens to also carry (mirrors
P3.xxI.2C's own "only the concept actually used, never one that merely
resolved" completeness discipline).

## G. Implementation

### Concept registry (`app/semantic/concept_registry.py`)

- `completed_timestamp` gains `"return_date"` as a generic alias, and
  `alternative_sibling_concept_sets=(frozenset({"work_order_id"}),
  frozenset({"contract_id"}))` — the identical sibling-corroboration
  mechanism `event_timestamp` already declared. Without this,
  `completed_timestamp` had **no path to `AUTO_ACCEPTED` at all**
  (capped by alias+role+datatype evidence alone, just under the 0.90
  bar) — discovered empirically via the first end-to-end test attempt,
  not predicted in the diagnosis. This would have silently blocked
  every governed interval this milestone's primitive depends on, not
  just Rental's.
- `unit_of_measure` gains `compatible_dataset_roles` (previously empty,
  meaning it never received the `DATASET_ROLE_COMPATIBILITY` evidence
  component at all) and `alternative_sibling_concept_sets` against
  `quantity`/`duration_hours`/`unit_price`/`hourly_rate` — a bare "unit"
  column is genuinely ambiguous without this; without it, an explicit
  governed unit value could never reach `AUTO_ACCEPTED` on a rate
  dataset either, silently forcing every match onto the both-unknown
  fallback rather than the unit it was actually governed to declare.
  Also discovered empirically, not predicted.

### `app/services/governed_duration_evidence.py` (new)

The primitive itself — see Section C.

### `app/services/case_capability_index_service.py`

A small, explicit allowlist (`_DURATION_ENDPOINT_CONCEPTS =
frozenset({"event_timestamp", "scheduled_timestamp",
"completed_timestamp"})`) lets these three TIMESTAMP-typed concepts
register in `canonical_measures` for readiness purposes, without
broadening `_MEASURE_CONCEPT_TYPES` to every TIMESTAMP concept (which
would let unrelated single timestamps, e.g. `effective_from_timestamp`
alone, register as bare "measures" with no such meaning).

### `app/intelligence_packs/registry.py`

`REVENUE-AMOUNT-VARIANCE` gains two more `alternative_canonical_measure_
sets` entries: `{event_timestamp, completed_timestamp, unit_price}` and
`{event_timestamp, completed_timestamp, hourly_rate}` — readiness is
satisfied by a governed interval pair plus a compatible rate exactly the
same way a stored quantity column already satisfies it.

### `app/services/analysis_case_orchestration_service.py`

- `_resolve_derived_duration_field(cd, df, semantic_outcome)` — the new
  helper. Tries `DECLARED_INTERVAL_PAIRS` in order, computes per-row
  duration via `resolve_row_duration`, detects and abstains on
  materially-disagreeing competing pairs, materializes the winning
  pair's hours/days columns on a copied dataframe (never mutates the
  shared `canonical_frames` dataframe other stages still read).
- Wired into the `REVENUE-AMOUNT-VARIANCE` per-dataset loop as a **last
  resort**, only after a direct `quantity`/`duration_hours` column is
  confirmed absent — a derived value never overrides a more directly
  governed one.
- The hours→days swap decision (Section E) is deferred via a small
  `pending_derived_duration_day_swap` list, resolved once after the full
  per-subject-type pass's `rate_dataset_fields` is known.
- **A pre-existing, previously-latent bug fixed as a prerequisite**: a
  rate-card-shaped dataset (contract reference + explicit rate, e.g.
  Rental's own `contracts.csv` shape) was ALSO eligible for
  `revenue_variance_intelligence_service.py`'s "no quantity/invoice/cost
  present → read unit_price as a flat billed amount" fallback — meaning
  its own governed RATE value was being independently re-read as an
  unrelated ACTUAL billed total, silently self-cancelling the variance
  (expected == actual by construction, zero findings, no error). This
  existed since P3.xxI.2A/2B/2C but was never triggered live because
  readiness always blocked before executing far enough to reach it —
  P3.xxI.3's own duration primitive is what finally let execution reach
  this path for the first time, surfacing it via the very first
  end-to-end test attempt. Fixed with a new `DatasetConceptFields.
  is_rate_card_shaped: bool` flag, set once by the orchestration layer
  (which already computes this exact classification) and consulted by
  `_collect_lines` to suppress ONLY the flat-amount fallback for that
  specific dataset — a real `invoice_amount`/`cost_amount` on the same
  rate-card-shaped dataset is unaffected. Would have corrupted every
  Rental case's expected-vs-actual comparison in the post-merge
  certification had it shipped unfixed.

## H. Tests

New file `tests/test_p3xxi3_governed_duration_evidence.py` (24 tests, all
passing):

| Section | Coverage |
|---|---|
| A. Primitive positive | same-row (13A), alternate aliases (13B), date-only (13C), timezone-aware (13D), no-rounding both directions (Section 6), cross-dataset subject-linked (13E) |
| B. Primitive negative | missing start (14A), missing end (14B), end<start (14C), unparseable (14F), null value, mismatched tz-awareness, missing subject linkage (14I) |
| C. Full orchestration, positive | derived duration + hourly rate end-to-end on a synthetic, non-Rental, non-FieldMaintenance "service response interval" shape (13F, Section 15's generalization requirement); derived duration + daily rate with explicit unit conversion (13G) |
| D. Orchestration helper, direct-call | ambiguous endpoint never reaches derivation (14D/E, both single- and mixed-tier), governed pair produces correct columns, competing pairs disagree→abstain and agree→first-declared-wins (14H) |
| C (cont.) | unit incompatible with rate basis → no finding (14G) |

`tests/test_revenue_amount_variance.py` (23/23) and
`tests/test_p3xxi2c_billable_subject_generalization.py` (16/16) —
unchanged, zero regression from this milestone's changes (including the
`is_rate_card_shaped` fix, which only suppresses a fallback that was
never legitimately reachable for any FieldMaintenance fixture in the
first place).

## I. Regression

Focused: `test_p3xxi3_governed_duration_evidence.py` (24/24),
`test_revenue_amount_variance.py` (23/23),
`test_p3xxi2c_billable_subject_generalization.py` (16/16) — 63/63 total.
Broader keyword sweep (`temporal`, `canonical_evidence`, `duration`,
`revenue`, `relationship`, `process`, `readiness`, `lineage`, `trust`,
`validation`, `tenant`, `semantic`, `entity`, `capability`): 902/902 pass
(3 pre-existing, unrelated Postgres state-leak failures from repeated
runs against the same disposable database — `duplicate key value
violates unique constraint`, a test-ordering artifact confirmed
independent of this milestone's changes by reproducing it identically
against unmodified `main` in the prior two milestones; a fresh schema
reset produces a clean result, recorded in Section J below).

## J. Full-suite / quality-gate results

| Gate | Result |
|---|---:|
| `tests/test_p3xxi3_governed_duration_evidence.py` | 24 passed |
| `tests/test_revenue_amount_variance.py` (FieldMaintenance regression control) | 23 passed |
| `tests/test_p3xxi2c_billable_subject_generalization.py` (Rental subject-generalization control) | 16 passed |
| Broader keyword sweep | 902 passed |
| Full non-PostgreSQL suite | 1694 passed, 82 deselected |
| Disposable PostgreSQL migration/tenant-boundary suite (fresh schema reset; exact Quality Gate selector) | 82 passed, 1 non-PostgreSQL test deselected |
| `ruff format --check .` | 800 files already formatted |
| `ruff check .` | all checks passed |
| `mypy .` | 616 source files, no issues |

## K. PR / CI / merge

Implementation branch: `feature/p3xxi3-governed-duration-evidence`.
Implementation PR is not yet open. It will not be merged without explicit
owner authorization, per standing house rule.

## L. Live Rental certification (post-merge, pending)

Not yet performed — per the mission's own required sequencing, live
Rental certification runs only after implementation PR review, CI, and
owner-authorized merge/deployment. This section will be completed in a
docs-only follow-up PR.

**Primary question restated**: does `measure:quantity` cease to be the
blocker because governed duration evidence is now available? Given the
readiness-gate change is purely additive (two new `alternative_
canonical_measure_sets` entries) and Rental's real `dispatch.csv`
already carries `dispatch_id`/`contract_id`/`asset_id`/`dispatch_date`/
`return_date` on one row — the same shape proven live in this
milestone's own synthetic E2E tests (`occurred_at`/`completed_at`
co-located with a contract reference) — readiness is expected to clear
this specific gate. Whether EXECUTION then produces genuine TP against
Rental's own truth corpus is a separate question this report does not
assume the answer to.

**Honest expectation carried forward from P3.xxI.2C, now testable
directly**: Rental's own hidden truth (`unbilled_rental_days`,
`late_return_leakage`) computes its expected amount from `rental_days` —
elapsed time between `dispatch_date` and `return_date`, exactly what
this milestone's primitive derives. Whether the RATE side (`contracts.csv`,
`contract_id,customer_id,asset_id,start_date,end_date,rate` — no
explicit unit/UOM column anywhere) can supply the governed "day" signal
Section E's swap logic requires is a genuinely open, previously-flagged
question (P3.xxI.2C's own report named this exact UOM_GAP risk). If no
governed day signal exists in Rental's real data, this milestone
predicts execution will still correctly abstain (hours-denominated
duration against an implicitly-day-priced rate, no fabricated match) —
a UOM_GAP outcome, not a duration-evidence failure, and precisely the
kind of "architecturally different outcome" Section 18's own taxonomy
exists to classify. This is stated now, before live evidence is
gathered, exactly as the analogous prediction was in P3.xxI.2C.

## M. FieldMaintenance control

Not yet re-run live in this pass (deferred to the post-merge
certification alongside Rental, per established two-phase precedent).
Local regression (Section I) confirms the mechanism cannot regress
FieldMaintenance: `is_rate_card_shaped` only suppresses a fallback that
was never reachable for FieldMaintenance's own fixtures, and the derived-
duration path is only ever attempted as the last resort after a direct
`quantity`/`duration_hours` column is confirmed absent — FieldMaintenance
always has one.

## N. TP / FP / FN, precision, recall, economic-value capture

Deferred to the post-merge live certification (Section L) — reporting
these without live evidence would be exactly the kind of unearned
positive claim this program's standing house rules forbid.

## O. Remaining gaps

- The UOM_GAP risk named in Section L — genuinely open until live
  certification runs.
- Cross-dataset subject-linked duration (`resolve_cross_dataset_duration`)
  is implemented and unit-tested (Section H) but not wired into the live
  `REVENUE-AMOUNT-VARIANCE` orchestration path — Rental's own
  `dispatch.csv` carries both endpoints on one row, so same-row
  derivation is sufficient for the certification target; wiring the
  cross-dataset path into a live capability is deferred to whichever
  future capability actually needs it (Section 13E's own "if supported
  by existing architecture" framing, satisfied at the primitive level).
- `DECLARED_INTERVAL_PAIRS` covers two pairs (event→completed,
  scheduled→completed). A future capability needing a different
  generic pairing (e.g. a dedicated "response received"/"response
  resolved" concept pair) would add a declaration here, not a
  capability-specific branch.

## P. Final classification

**[Deferred — see Section L.]** Per the mission's own required
sequencing, this milestone's final classification is stated only after
live Rental certification runs post-merge. The implementation itself is
complete, tested, and regression-clean; whether the overall milestone
reaches VALIDATED / PARTIALLY VALIDATED / FAILED depends on live
evidence not yet gathered.

## Q. Next recommendation

Deferred to the post-merge report, once live Rental evidence
(specifically: does a governed day-unit signal exist anywhere in
Rental's real rate data) is known.
