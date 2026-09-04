# P3.xxI.3 — Governed Canonical Duration / Interval Evidence

## Status

Implementation merged (PR #117, SHA `98013e10fb1e21d58881b8907453c9291a7ed406`)
and deployed. Post-merge live certification complete — see Sections L-Q.
**Final classification: P3.xxI.3 PARTIALLY VALIDATED.**

### Certification recovery note

The first live-certification attempt on this milestone hit two apparent
blockers left over from a deploy restart: five `AnalysisCaseRun` rows stuck
`RUNNING`, and terminal Rental runs landing on `review_required` due to
`DOMAIN_REVIEW_REQUIRED` on `payments.csv`/`field_tickets.csv`/`maintenance.csv`.
Diagnosis (no code change) found both harmless to certification:

- The stuck runs reconciled cleanly to the existing `INTERRUPTED` terminal
  state via the pre-existing lease/heartbeat lazy-reconciliation path
  (`mark_stale_if_needed`, triggered by polling `GET .../runs/{id}/status`)
  — an existing, designed recovery mechanism, not a defect. One real but
  non-blocking gap was found and is recorded in Section O: the parent
  `AnalysisCase.status` is never updated when a run reconciles this way, so
  it can show a stale `"running"` label after its run is already terminal.
- `DOMAIN_REVIEW_REQUIRED` (`app/services/domain_detection_service.py`,
  a stateless, case-local, deterministic function of column headers) does
  **not** gate pipeline execution — `any_review_required` is read only once,
  at the very end of `execute()`, purely to choose the cosmetic final
  status label. Every stage (semantic interpretation, entity resolution,
  relationship discovery, readiness, `REVENUE-AMOUNT-VARIANCE`) already ran
  to completion before that flag is read. Confirmed empirically: terminal
  `review_required` Rental runs showed `governed_status: READY` and fully
  resolved entities, and a `review_required` FieldMaintenance control
  produced 63 real findings under the identical label.

Fresh certification cases were created per Section 1 of the recovery
mission rather than reusing these partially-executed ones (Section L).

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
Implementation PR: [#117](https://github.com/intel4ops/intel4ops-core-platform/pull/117).
The repository Quality Gate passed on implementation commit `007eddc`
([run 33819620029](https://github.com/intel4ops/intel4ops-core-platform/actions/runs/33819620029))
in 20m36s, including the SQLite/application suite, disposable PostgreSQL
suite, Alembic drift/offline-SQL checks, and release-certification artifact.
The PR will not be merged without explicit owner authorization, per standing
house rule.

## L. Live Rental certification (post-merge, complete)

Six fresh, single-mode-avoided (orchestrated) cases were created against
the frozen Rental customer-data corpus (`assets.csv`, `contracts.csv`,
`customers.csv`, `dispatch.csv`, `field_tickets.csv`, `fuel.csv`,
`invoices.csv`, `maintenance.csv`, `payments.csv` per case) — the same
files used for the P3.xxI.2C certification, none of the partially-executed
cases from the recovery diagnosis were reused:

| Case | Case ID | Run ID | `REVENUE-AMOUNT-VARIANCE` readiness | Entities (CONTRACT/EVENT/ASSET/CUSTOMER) | Findings |
|---|---|---|---|---|---|
| P3xxI3-Cert-RENTAL-001 | `b3d92fcd-b6d3-4bb5-b509-8c5efd74ce82` | `e5b504f9-16dd-4b35-8f57-4bca66a0715e` | READY, `governed_missing_summary: []` | 55/55/41/24 | 0 |
| P3xxI3-Cert-RENTAL-003 | `26a01e92-ac73-4cf5-a423-e6fcfce7c45b` | `07062dbf-9eb0-48a6-863e-9c408afda8dd` | READY, `[]` | 29/29/40/12 | 0 |
| P3xxI3-Cert-RENTAL-011 | `eaf51ec0-6222-41d1-a6a1-80a20a532976` | `ee7684b6-c61e-4323-a493-17703538f264` | READY, `[]` | 67/67/45/30 | 0 |
| P3xxI3-Cert-RENTAL-012 | `6fb5fb3d-3091-49f6-a265-7fcc303fa7ad` | `6637cd7d-fc3e-40a6-bca9-9254153cb302` | READY, `[]` | 76/76/45/30 | 0 |
| P3xxI3-Cert-RENTAL-015 | `5b46a8e1-0830-4e5c-a919-2d54a2d657ea` | `01ce34cc-db06-417b-8b9b-8e19ce7845ba` | READY, `[]` | 150/150/351/60 | 0 |
| P3xxI3-Cert-RENTAL-018 | `14ec0983-c25d-4af7-b7c6-7fe70d59d5d4` | `280c7f5b-6e26-4a8c-8921-8174484f161d` | READY, `[]` | 89/89/50/40 | 0 |

**Primary question A — is `REVENUE-AMOUNT-VARIANCE` READY?** Yes, all six
cases, `governed_missing_summary` empty on every one. `measure:quantity`
has ceased to be the blocker P3.xxI.2C identified — CONTRACT/EVENT entity
resolution (from P3.xxI.2C) and the new governed-duration measure path
(this milestone) compose correctly.

**Primary question B — is governed duration evidence actually created and
consumed?** Yes, proven with a full per-row trace, not inferred from
readiness alone. A local, read-only instrumented rerun of the real
RENTAL-001 corpus (`app/services/analysis_case_orchestration_service.py`'s
unmodified `execute()`, run against the identical frozen files, with the
service's own `_collect_lines`/`resolve_applicable_rate` functions wrapped
purely to log their arguments and return values — no behavior changed)
shows:

| contract_id | `dispatch_date` | `return_date` | derived duration (hours) |
|---|---|---|---:|
| CNT-000001 | 2026-02-23 | 2026-03-16 | 504.0 (= 21 days × 24, exact) |
| CNT-000002 | 2026-08-10 | 2026-09-04 | 600.0 (= 25 days × 24, exact) |
| CNT-000003 | 2026-04-19 | 2026-05-05 | 384.0 (= 16 days × 24, exact) |
| CNT-000004 | 2026-08-01 | 2026-08-17 | 384.0 (= 16 days × 24, exact) |
| CNT-000005 | 2026-04-03 | 2026-05-05 | 768.0 (= 32 days × 24, exact) |

Every value is the exact, unrounded elapsed interval (Section E's "23
hours ≠ 1 day" invariant holds — nothing here silently became a day
count). `dispatch.csv`'s `DatasetConceptFields.quantity_field` resolves
to the derived-duration column
(`__p3xxi3_derived_duration_hours__event_timestamp__completed_timestamp`),
`contract_id_field='contract_id'`, and `event_timestamp_field` resolves
to `dispatch_date` — the derived quantity, its subject linkage, and its
temporal-applicability anchor all thread correctly into
`resolve_applicable_rate(rate_datasets, contract_key='CNT-000001',
event_at=2026-02-23T00:00:00Z, unit='hour', currency=None)` for every one
of the 55 contracts. **This is direct proof the primitive works live on
real production-shaped data and that its output reaches the amount
calculation** — the question is not whether duration evidence exists, but
what happens next.

**Primary question C — if READY but 0 findings, where exactly does
candidate generation stop?** At the rate-unit safety check, on every
single subject, for an identical reason across all six cases:
`resolve_applicable_rate` returns `None` every time because
`contracts.csv`'s `rate` column carries **no governed unit-of-measure
anywhere** — `unit_field=None`, `implicit_unit=None` on the resolved
`RateDatasetFields`. `governed_cross_dataset_rate.py`'s pre-existing,
unmodified-by-this-milestone unit policy is strict-equality-or-abstain
(`if expected_unit is None or rate_unit is None or expected_unit !=
rate_unit: continue`) — unlike currency, "both sides unknown" is
deliberately never treated as compatible for units. With `rate_unit`
always `None` here, the gate abstains on every contract, regardless of
what unit the duration side requests. This was independently confirmed
structural, not an accident of one case: `contracts.csv`'s header —
`contract_id,customer_id,asset_id,start_date,end_date,rate` — is
byte-identical across all six frozen Rental cases (`RENTAL-001/003/011/
012/015/018`); none of the six declares a `unit`/`day`/`days` column
anywhere in the corpus, so the day-unit swap this milestone added
(Section G) never has a governed signal to trigger on, and the fallback
hour-denominated request can never match the rate's permanently-unknown
unit.

**Full traced path** (Section 4's required trace, RENTAL-001/CNT-000001):
CONTRACT subject `CNT-000001` → interval endpoints `dispatch_date`=
2026-02-23, `return_date`=2026-03-16 (both `event_timestamp`/
`completed_timestamp`, AUTO_ACCEPTED) → derived duration 504.0 hours
(exact) → quantity field wired to the derived column, requested unit
`hour` (no day-swap trigger available) → applicable rate lookup against
`contracts.csv`'s `rate=1850` for `CNT-000001` → **abstains**: rate's own
unit is ungoverned, strict policy refuses to guess it → no expected-amount
line produced → `actual` side (from `invoices.csv`/`payments.csv`) never
gets compared against anything → no `_AmountLine` on either side for this
subject → no finding. This is the same outcome, for the same reason, on
every one of the 55+ contracts across all six cases — a systemic,
corpus-wide gap in the RATE data's own governed evidence, not a per-case
anomaly and not a defect in the duration primitive.

This is precisely the outcome this report's pre-merge Section L predicted
before any live evidence was gathered.

## M. FieldMaintenance control

Four fresh cases were run against the frozen FieldMaintenance corpus
(`assets.csv`, `customers.csv`, `field_tickets.csv`, `invoices.csv`,
`labor_entries.csv`, `maintenance_events.csv`, `parts_usage.csv`,
`payments.csv`, `service_contracts.csv`, `sites.csv`, `technicians.csv`,
`work_orders.csv`) and their `REVENUE-AMOUNT-VARIANCE`-specific finding
counts read directly from each case's finding list (`rule_id` field),
not the case's raw total finding count (which also includes unrelated
cross-domain rules, see below):

| Case | Case ID | Run ID | `REVENUE-AMOUNT-VARIANCE` findings | P3.xxI.2B certified baseline | Match |
|---|---|---|---:|---:|---|
| P3xxI3-Cert-FIELDMAINT-001 | `cfdcee5e-6304-44d0-b23c-f8c79262a950` | `903ccdf3-1e6b-42e0-856d-4d9c3408888e` | 61 | 61 | exact |
| P3xxI3-Cert-FIELDMAINT-002 | `a5728fc4-ffe0-4b88-9e17-d2ee90f61178` | `dd6a2453-547d-45cc-9d32-08ba84ff5560` | 0 | 0 | exact |
| P3xxI3-Cert-FIELDMAINT-005 | `49b76d10-b65b-4182-b66f-ae699fedb712` | `99738054-bb94-4191-bc2b-cc46a125bcf5` | 86 | 86 | exact |
| P3xxI3-Cert-FIELDMAINT-007 | `a1246e06-ed50-4a3b-b4c4-d48d0c873ee5` | `72d429f3-b9c6-4ed3-bc3b-a83dc417fe83` | 26 | 26 | exact |

The certified 61/0/86/26 pattern is preserved byte-for-byte. Each case's
total finding count (as read from the case's full finding list, all
rules combined) is 1-2 higher than these numbers — traced per-`rule_id`
and confirmed to come entirely from `XDOM-DATA-LINKAGE-ISSUE` (all four
cases) and, on FIELDMAINT-001 only, one additional
`XDOM-B-LOST-ACTIVITY-REVENUE-GAP` finding. Both are unrelated
cross-domain rules outside `REVENUE-AMOUNT-VARIANCE`'s scope and outside
this milestone's change surface — not a regression, and not something
this milestone touched. This matches the local regression evidence from
Section I: `is_rate_card_shaped` only suppresses a fallback that was
never reachable for FieldMaintenance's own fixtures, and the derived-
duration path only engages as a last resort when a direct `quantity`/
`duration_hours` column is absent — FieldMaintenance always has one, so
the new P3.xxI.3 code paths are structurally never exercised for these
four cases at all.

## N. TP / FP / FN, precision, recall, economic-value capture

**FieldMaintenance** — `REVENUE-AMOUNT-VARIANCE` finding counts and
subjects are identical to the P3.xxI.2B certified run (Section M); the
new duration-evidence code paths are confirmed never exercised for this
corpus (same reasoning as Section M). On that basis the certified
P3.xxI.2B scoring stands unchanged: **TP=150, FN=16, Recall=90.36%,
mechanical/fabricated FP=0**. This is carried forward from identical
finding-set identity plus a proven non-engagement of this milestone's
new code, not an independently re-run scoring pass against hidden truth
in this session — stated explicitly rather than implied, per this
program's standing rule against unearned positive claims.

**Rental** — zero findings on all six cases (Section L) against the
established 14-item truth slice (`unbilled_rental_days` +
`late_return_leakage`, $241,050 total value, P3.xxI.2C's own examiner-
side denominator, unchanged here):

| Metric | Value |
|---|---|
| TP | 0 |
| FP | 0 (no fabricated or mechanical false positives — the pipeline abstained everywhere, exactly as Section 4's safety invariant requires) |
| FN | 14 (all) |
| Precision | N/A (no positive predictions) |
| Recall | 0% |
| Economic-value capture | $0 of $241,050 |

**Combined** (informational only, FieldMaintenance + Rental): TP=150,
FP=0, FN=30, recall = 150/180 = 83.3%.

## O. Remaining gaps

- **UOM_GAP on Rental's rate data (Section L, confirmed, not
  hypothetical).** `contracts.csv`'s `rate` column carries no governed
  unit anywhere in the frozen corpus. Recovering Rental's $241,050 of
  known truth value requires either (a) the source data itself declaring
  a governed unit on the rate, or (b) a deliberate, explicit, reusable
  business-rule decision that a rental contract's bare `rate` concept
  defaults to "per day" absent contrary evidence — the latter is an
  explicit business-rule/UOM-inference decision squarely inside this
  mission's own Section 12 boundary ("do NOT implement ... unless already
  governed and reusable") and is correctly left for a future, explicitly
  scoped milestone rather than invented here.
- **`AnalysisCase.status` staleness after lazy stale-run reconciliation**
  (found during recovery diagnosis, Section "Certification recovery
  note"): `mark_stale_if_needed` updates `AnalysisCaseRun.status` but
  never the parent `AnalysisCase.status`, so a case whose only run
  reconciles via this path can show a stale `"running"` label
  indefinitely. Does not affect any read API (all are `run_id`-scoped)
  and does not block certification; recorded as a non-blocking platform
  note per this session's explicit instruction, not fixed here.
- **`review_required` status/messaging implies gating it doesn't do**
  (same recovery note): `findings_availability()`'s message text ("Findings
  not produced because ... review is required") can read as causal even
  when review-required and finding-count are unrelated for that run, as
  demonstrated directly in this certification. A future UI/messaging
  clarification is a reasonable follow-up; not a P3.xxI.3 blocker.
- Cross-dataset subject-linked duration (`resolve_cross_dataset_duration`)
  is implemented and unit-tested (Section H) but not wired into the live
  `REVENUE-AMOUNT-VARIANCE` orchestration path — Rental's own
  `dispatch.csv` carries both endpoints on one row, so same-row
  derivation is sufficient for the certification target; wiring the
  cross-dataset path into a live capability is deferred to whichever
  future capability actually needs it.
- `DECLARED_INTERVAL_PAIRS` covers two pairs (event→completed,
  scheduled→completed). A future capability needing a different
  generic pairing (e.g. a dedicated "response received"/"response
  resolved" concept pair) would add a declaration here, not a
  capability-specific branch.

## P. Final classification

**P3.xxI.3 PARTIALLY VALIDATED.**

The generic duration primitive itself is proven live, correct, and safe:
it computes the exact, unrounded elapsed interval on real production-
shaped data (Section L's per-row trace), correctly threads that value
through governed subject linkage and temporal applicability into the
existing rate-resolution path, eliminates the exact `measure:quantity`
blocker P3.xxI.2C identified (readiness went from BLOCKED to READY with
an empty missing-summary on all six Rental cases), and introduces zero
regression on the FieldMaintenance control (Section M, byte-for-byte
match) and zero fabricated or mechanical false positives anywhere
(Section N). Every one of Section 4's safety invariants held under live
production data: no case fabricated a duration, and every case that
could not safely produce one abstained rather than guessed.

It is not VALIDATED outright because a separate, reusable, correctly-
diagnosed downstream gap (Section O's UOM_GAP on Rental's rate data —
pre-existing infrastructure this milestone did not create and correctly
did not bypass) prevents any material economic-value recovery for
Rental in this pass: 0 of $241,050 known truth value, TP=0/FN=14. Per
this mission's own Section 8 definitions, that combination — the
primitive works live, but a reusable downstream model gap prevents
material recovery — is PARTIALLY VALIDATED, not VALIDATED, and the zero
Rental recall is not itself grounds for FAILED given it stems entirely
from an explainable, upstream-data gap outside this milestone's
boundary rather than any defect in the duration evidence contract,
temporal semantics, or safety invariants this milestone owns.

## Q. Next recommendation

Do not implement a UOM-inference business rule as part of any
in-progress work. If Rental's $241,050 of known value is to be pursued,
the next owner-directed milestone should explicitly scope one of: (a)
extending the frozen Rental corpus (or a future real customer's data) to
carry a governed unit on its rate data, or (b) a deliberate, reusable,
explicitly-governed business decision for how a bare rental `rate`
concept's unit should be inferred when absent — stated as its own
milestone with its own safety invariants, not folded into a duration-
evidence primitive that has now done its job correctly. No other
capability work should start until the owner reviews this report, per
the mission's hard stop.
