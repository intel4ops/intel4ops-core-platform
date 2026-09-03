# P3.xxI.2C — Billable Subject Generalization

## Status

**P3.xxI.2C VALIDATED** (post-merge, live certification complete). See
Section L for the full classification rationale.

Merged: PR #115, merge SHA `22fc897da08826642d970091f852eefcb67d18be`.
Local main synced and confirmed at that SHA; backend deployment confirmed
live via the first post-merge production run (Section F).

## A. Baseline

Repository `intel4ops/intel4ops-core-platform`, `main` at
`2f760da06a748e3580c16bdf8ba90a08b3feffe0` — P3.xxI.2B CLOSED — VALIDATED.
Certified Revenue Amount / Billing Variance baseline preserved as the
control population this milestone must not regress: TP=150, FN=16,
recall=90.36%, economic-value capture=25.63%, mechanical/fabricated-evidence
FP=0. The 24 FIELDMAINT-001 findings independently verified as genuine
`contract_rate_mismatch` leakage outside the strict denominator are
preserved as-is and not touched by this milestone.

## B. Architecture diagnosis (pre-implementation)

**Why Rental currently fails readiness.** Two independent, compounding
gaps, neither a redesign:

1. `contract_id` — an already fully governed, high-confidence `IDENTIFIER`
   concept — had `compatible_entity_types=frozenset()`. `entity_type_
   inference.infer_entity_type()` only ever infers a type when
   `compatible_entity_types` has exactly one value, so no `CONTRACT`
   entity was ever produced from it, even though the concept itself
   resolved perfectly.
2. `dispatch.csv`'s `dispatch_id` — the row carrying the actual billable
   rental-period grain — had no registered concept at all.

`required_canonical_entities=frozenset({WORK_ORDER})` on the
`REVENUE-AMOUNT-VARIANCE` pack then trivially failed: no `WORK_ORDER`
entity exists anywhere in Rental data, because Rental has no
`work_order_id`-shaped column at all.

**Which canonical entity already represents the economic unit being
billed.** `CONTRACT` (`contracts.csv`: `contract_id, customer_id,
asset_id, start_date, end_date, rate`). Verified live against the frozen
RENTAL-011 fixture: `contract_id` ↔ `dispatch_id` ↔ `invoice_id` is a
clean 1:1:1 mapping (67 contracts, 67 dispatches, 65 invoices — 2
contracts genuinely unbilled). Billing (`invoices.csv.amount`) is keyed
directly by `contract_id`; quantity-adjacent evidence
(`field_tickets.csv.hours_used`) is keyed by `dispatch_id`, one hop from
`contract_id` via `dispatch.csv`. `CONTRACT` was already a declared
`EntityType` value — `entity_type.py`'s own comment flagged it as
"defined here but has no backing CanonicalConcept registered yet"; this
milestone closes exactly that documented gap, not a new one.

**Whether a generic abstraction is already latent in E.3/E.4.** Yes,
unexercised. E.3's `relationship_discovery.py` already generically
discovers a relationship whenever two entity-typed columns co-occur on
the same dataset row. The corpus-wide P3.xxE.3/E.4 baseline showed zero
relationships everywhere because no dataset ever had two such columns
simultaneously resolve — not because the mechanism doesn't work.
Registering `contract_id`→`CONTRACT` and a new `dispatch_id` concept→
`EVENT` (already forward-declared, unbacked, in `entity_type.py`) means
`dispatch.csv` produces real `CanonicalCaseRelationship` rows for the
first time — for free, via existing machinery. The rate side needed zero
changes: `unit_price`'s alias set already includes bare `"rate"` and its
`{"contract_id"}` sibling alternative (exclude-by-status-fixed in PR
#113) already matches `contracts.csv`'s `rate` column exactly, the same
shape as `service_contracts.csv.labor_rate`. `effective_from_timestamp`/
`effective_to_timestamp` already alias `start_date`/`end_date`;
`event_timestamp` already aliases `dispatch_date`.

**Whether the capability can accept multiple governed subject entity
types without redesigning the canonical architecture.** Yes.
`IntelligencePackDefinition` already had this exact shape for measures
(`alternative_canonical_measure_sets`); adding a parallel
`alternative_canonical_entity_sets` is the same declarative pattern, not
a new one.

**Stable finding identity.** The actually-resolved subject type and key,
never a hardcoded literal — `entities_json`/`StableFindingIdentityReference`
are now parameterized by the real subject type (`"work_order"` or
`"contract"`), preserving Fix #7's entity-aware identity: a Rental
finding's stable key is genuinely distinct from a FieldMaintenance
finding's, never collapsed into one case-wide key.

**Smallest reusable generalization.** Register `contract_id.compatible_
entity_types={"CONTRACT"}`; register a new identifier concept `dispatch_id`
(generic aliases, `compatible_entity_types={"EVENT"}`); add `"hours_used"`
to `duration_hours`'s aliases; add `alternative_canonical_entity_sets` to
the registry; genericize `DatasetConceptFields`/`run_revenue_amount_
variance` from WORK_ORDER-literal to subject-type-parameterized; when the
quantity dataset's own row doesn't carry the subject id directly, consume
a small new governed one-hop identifier bridge, reusing the exact
same-row co-occurrence philosophy `_collect_lines`'s own pre-existing
work-order/contract bridge already uses, generalized from hardcoded field
names to parameters.

**Stop-gate check.** None of this required a new `EntityType` value, new
global ontology, new relationship-discovery mechanism, or any
`if domain/simulation/filename == ...` branch — declarative concept/
registry additions plus generalizing existing WORK_ORDER-literal code
into parameters, the same shape P3.xxI.2A and P3.xxI.2B already used. No
architectural expansion required.

## C. Subject abstraction (implementation)

### Concept registry (`app/semantic/concept_registry.py`)

- `contract_id` gains `compatible_entity_types=frozenset({"CONTRACT"})`.
- New concept `dispatch_id` (aliases: `dispatch_id`, `assignment_id`,
  `service_event_id`, `rental_event_id`; `compatible_entity_types=
  frozenset({"EVENT"})`; `alternative_sibling_concept_sets=
  (frozenset({"contract_id"}),)` — a billable event/assignment
  co-located with a contract reference is real, generic corroborating
  evidence, the same shape `unit_price`'s own `{contract_id}` alternative
  already uses).
- `duration_hours` gains `"hours_used"` as a generic alias.
- New `CanonicalConceptRegistry.identifier_concept_codes_for_entity_type()`
  — the reverse of `infer_entity_type`: every active `IDENTIFIER` concept
  whose `compatible_entity_types` is exactly `{entity_type}`, so an
  intelligence rule can ask "which column(s) carry THIS entity type's own
  identity" generically.

### Readiness (`app/intelligence_packs/registry.py`,
`app/services/intelligence_readiness_service.py`)

- `IntelligencePackDefinition` gains `alternative_canonical_entity_sets:
  tuple[frozenset[str], ...] = ()`, the entity-side counterpart to the
  already-established `alternative_canonical_measure_sets`.
  `REVENUE-AMOUNT-VARIANCE` declares
  `(frozenset({WORK_ORDER}), frozenset({CONTRACT}))`, WORK_ORDER first
  (unchanged priority for the certified population).
- `evaluate_readiness()` is satisfied by any ONE alternative entity set
  being fully present. The confidence-threshold check was corrected to
  evaluate the SPECIFIC entity type that actually satisfied readiness
  (`satisfied_canonical_entities`), never blindly `required_canonical_
  entities` — a naive port of the measure-set pattern would have silently
  checked confidence against WORK_ORDER even when CONTRACT is what
  satisfied readiness. Covered by
  `test_readiness_confidence_check_applies_to_the_satisfying_type_not_the_primary`.

### Revenue variance service
(`app/services/revenue_variance_intelligence_service.py`)

`DatasetConceptFields.work_order_id_field` → `subject_id_field`;
`wo_key`/`eligible_work_order_keys` → `subject_key`/`eligible_subject_
keys` throughout. `run_revenue_amount_variance()` gains a
`subject_entity_type: str = "work_order"` parameter, carried verbatim
into every finding's title, `entities_json`, and
`StableFindingIdentityReference`. One mechanical gap closed in
`_collect_lines`'s cross-dataset-rate branch: `contract_key` now falls
back to `subject_key` itself when no separate `contract_id_field`/bridge
mapping exists — always correct when the case's chosen subject IS the
contract (the subject key already equals the value `rate_datasets` are
keyed by), harmless otherwise (a work-order-shaped subject key simply
never matches a real `contract_id` row, so `resolve_applicable_rate`
still correctly returns `None`).

### Orchestration (`app/services/analysis_case_orchestration_service.py`)

Two new private helpers:

- `_resolve_identifier_bridge_map(case_datasets, raw_dfs, semantic_outcome,
  bridge_concept, subject_concept)` — a governed, generic one-hop
  identifier bridge. For ANY dataset where both concepts co-occur on the
  same row (e.g. `dispatch.csv`'s `dispatch_id`+`contract_id`), builds
  `bridge_value -> subject_value`. Ambiguity-safe by construction: a
  bridge value observed against more than one distinct subject value
  anywhere in the case is dropped, the exact "1:1 survives, ambiguous
  drops" rule the pre-existing work-order/contract bridge already used,
  generalized to an arbitrary concept pair. No dataset name, domain, or
  simulation identity is read.
- `_resolve_subject_field_for_dataset(...)` — resolves the column on one
  dataset carrying the chosen subject's identity: directly when a
  subject concept resolves there, or via the bridge above through any
  OTHER resolved identifier concept on the same dataset when it doesn't.
  `allow_bridge=False` disables the fallback for a dataset the caller
  already determined is rate-card-shaped (contract reference + explicit
  rate) — bridging such a dataset would wrongly attach a transient
  subject identity to a governed reference/lookup row, risking its rate
  value being misread downstream as a flat billed amount.

The `REVENUE-AMOUNT-VARIANCE` orchestration block now iterates candidate
subject types in the pack's declared order (WORK_ORDER, then CONTRACT).
A dataset that resolves a subject field (direct or bridged) at one tier
is **claimed** and never reconsidered by a later, coarser tier in the
same run — this is what prevents one work order's own evidence from ALSO
being reprocessed at the CONTRACT grain now that `contract_id` carries an
entity type too (FieldMaintenance's own `invoices.csv`/
`service_contracts.csv` already carry both `work_order_id` and
`contract_id`; without the claim rule they would double-publish the same
leak under two subject identities — this is the mechanism that keeps the
certified FieldMaintenance baseline exactly unchanged, verified in
Section E). Rate-card-shaped datasets are exempt from claiming (a rate
lookup source is usable by every subject-type pass, never "consumed" by
one). Each subject type with ≥1 eligible governed entity and ≥1 unclaimed
dataset able to attribute evidence to it runs as its own, independently-
published call to `run_revenue_amount_variance`.

Two secondary fixes surfaced only once the bridge was exercised through
the real semantic/domain pipeline, both now covered by tests:

- **Rename-layer bug**: `domain_registry.py`'s own, unrelated alias table
  may already have renamed a raw column (e.g. `dispatch_id` →
  `operational_event_id`) inside `canonical_frames` before the bridge
  looks it up — the bridge-field lookup now applies `canonicalize_field()`
  to the semantic decision's raw `source_field`, exactly mirroring
  `_resolve_canonical_concept_field`'s own established translation, which
  the initial bridge implementation omitted.
- **Completeness over-strictness**: `required_concepts` (feeding
  `canonical_evidence_completeness`, the P3.xxV.2D correction path) now
  only includes the subject-bridge concept when it independently clears
  the same strict AUTO_ACCEPTED-only bar every other required concept
  there already does. A bridged dataset's own per-row bridge-concept
  decision may legitimately sit at a weaker tier (locating the join
  column is a structural lookup, not itself an authoritative assertion —
  the real authority is the bridge map, built strictly elsewhere); such a
  dataset's completeness is judged on its OTHER governed evidence only,
  never inflated by a concept that did not actually clear the bar on that
  specific dataset.

## D. Readiness changes summary

`REVENUE-AMOUNT-VARIANCE` readiness now accepts WORK_ORDER OR CONTRACT as
the governed billable subject, gated identically (same confidence floor,
same measure-set alternatives, same currency/unit policy) regardless of
which one satisfies it. No other pack's readiness changed.

## E. Tests

New file `tests/test_p3xxi2c_billable_subject_generalization.py` (16
tests, all passing):

| Section | Coverage |
|---|---|
| 1. Concept registry | `identifier_concept_codes_for_entity_type` for CONTRACT/EVENT/WORK_ORDER/unregistered types |
| 2. Readiness | alternative-set satisfaction, confidence-check-on-satisfying-type regression guard, primary-set-unchanged regression, BLOCKED-when-neither-present |
| 3. Service layer | `run_revenue_amount_variance` with `subject_entity_type="contract"` via the `agreement_id` alias (never the literal string `"contract_id"`) — proves the mechanism is concept-driven, not label-driven |
| 4. Orchestration bridge | `_resolve_identifier_bridge_map` (builds + drops ambiguous), `_resolve_subject_field_for_dataset` (direct preferred, bridges when absent, bridge disabled for rate-card-shaped, returns None with no path) — a third, synthetic concept-pair shape, neither FieldMaintenance's nor Rental's literal spellings |
| 5. Full orchestration | one real, unmodified `execute()` run, Rental-shaped columns (`dispatch_id`/`agreement_id`/`rate_card_id`/`hours_used`), zero `work_order_id`-aliased column anywhere in the case — 6/6 CONTRACT-subject findings, each correctly exposure=200, each correctly subject-tagged `"contract"` |

`tests/test_revenue_amount_variance.py` — updated only for the
`work_order_id_field`→`subject_id_field` rename (mechanical, no behavior
change); all 23 tests still pass, including
`test_orchestration_cross_dataset_hourly_rate_end_to_end` (6/6 WORK_ORDER
findings, unchanged) and `test_generalization_different_schema_same_
invariant` — these are the certified FieldMaintenance regression control.

## F. FieldMaintenance regression

`tests/test_revenue_amount_variance.py`: 23/23 pass, unchanged from
pre-P3.xxI.2C. In particular
`test_orchestration_cross_dataset_hourly_rate_end_to_end` still produces
exactly 6 findings (not 12) — direct proof the new CONTRACT-subject pass
does not double-publish FieldMaintenance's own WORK_ORDER findings once
`contract_id` also carries an entity type, via the claim-exclusivity
mechanism described in Section C.

## G. Regression

Focused suites: `tests/test_p3xxi2c_billable_subject_generalization.py`
(16/16), `tests/test_revenue_amount_variance.py` (23/23). Broader sweep
(`entity`, `relationship`, `capability`, `readiness`, `semantic`,
`intelligence_pack`, `concept_registry`, `governed_cross_dataset_rate`,
`capability_architecture`, `process`, `trust`, `validation`, `tenant`
keyword matches): 816/816 pass. Full non-PostgreSQL suite and disposable
PostgreSQL migration/tenant-boundary suite: see Section H below. `ruff
format --check .`, `ruff check .`, `mypy .`: all clean on every changed
file.

## H. Full-suite / quality-gate results

| Gate | Result |
|---|---:|
| `tests/test_p3xxi2c_billable_subject_generalization.py` | 16 passed |
| `tests/test_revenue_amount_variance.py` (FieldMaintenance regression control) | 23 passed |
| Broader keyword sweep (entity/relationship/capability/readiness/semantic/intelligence_pack/concept_registry/governed_cross_dataset_rate/capability_architecture/process/trust/validation/tenant) | 816 passed |
| Full non-PostgreSQL suite | 1,671 passed |
| Disposable PostgreSQL migration/tenant-boundary suite (fresh schema reset) | 83 passed |
| `ruff format --check .` | 797 files already formatted |
| `ruff check .` | all checks passed |
| `mypy .` | 614 source files, no issues |

(An initial pass of the disposable-PostgreSQL suite showed 3 failures
purely from accumulated state across repeated runs against the same
database — `duplicate key value violates unique constraint`, a
test-ordering artifact, not a regression. A fresh `DROP SCHEMA public
CASCADE; CREATE SCHEMA public;` reset before the run above produced the
clean 83/83 result recorded here.)

## I. Live cases run (post-merge)

All runs executed against the live deployed backend (merge SHA
`22fc897`, confirmed live via the first production run below), org
"SOTRA Pilot" (`41f93780-1840-426b-95ed-31a5a4478765`).

**FieldMaintenance control** (regression check against the P3.xxI.2B
certified baseline):

| Case | Case ID | Run ID | REVENUE-AMOUNT-VARIANCE findings | Subject type(s) |
|---|---|---|---:|---|
| FIELDMAINT-001 | `64ee8eb9-00bf-43d3-a0a5-ac7a4c255946` | `98e94bbc-9434-442a-ba38-4a3bac3db8b3` | 61 | 100% `work_order` |
| FIELDMAINT-002 | `2478d851-e4d6-4870-b62b-ab417e192995` | `59eb4543-c108-4fa9-9640-a66bcc5ace54` | 0 | — |
| FIELDMAINT-005 | `4eab09b6-1314-4703-b223-581276f136b9` | `abb80d9c-110e-48a9-8f3c-ca4aebc2b55a` | 86 | 100% `work_order` |
| FIELDMAINT-007 | `b9a6fb15-ed9e-4819-b4af-ef7f4725d59e` | `71955993-4a46-4982-93d4-44ac8e6c9857` | 26 | 100% `work_order` |

Every count matches the P3.xxI.2B certified baseline exactly (61/0/86/26),
and every finding is tagged `work_order` — zero contamination from the
newly-reachable CONTRACT pass. This confirms Section F's pytest-level
regression proof live, on the deployed backend, not just locally.

**Rental** (the milestone's validation case):

| Case | Case ID | Run ID | Governed status | Missing | CONTRACT entities | EVENT entities |
|---|---|---|---|---|---:|---:|
| RENTAL-001 | `d681c279-5722-48e9-9cd4-a6c18d2273eb` | `42581510-99a6-4cf9-bdf7-334eb6a47b6d` | BLOCKED | `measure:quantity` | 55 | 55 |
| RENTAL-003 | `bdeceb7b-2647-4bd5-a93d-e779d4d3783d` | `cdf9e16d-0dee-409c-b66f-61896b126d7c` | BLOCKED | `measure:quantity` | 29 | 29 |
| RENTAL-011 | `f03ae8d3-aef8-4d66-b6aa-c4dbbceee48b` | `cbdebb48-cc85-471b-9589-d02c0b98cd5a` | BLOCKED | `measure:quantity` | 67 | 67 |
| RENTAL-012 | `ad408bdb-2b7f-4c18-8c25-c641192797c7` | `e4bec248-572f-4c3d-b563-a1c2951e8397` | BLOCKED | `measure:quantity` | 76 | 76 |
| RENTAL-015 | `164e5600-e3a9-4f99-8d26-855dd09a69e5` | `62d26b47-e169-40a6-a02a-75fc396a8979` | BLOCKED | `measure:quantity` | 150 | 150 |
| RENTAL-018 | `51f791bc-1923-4ee4-9a02-a0bf138703a3` | `ba139e42-8cd3-4efc-9fb7-629926f0e2b2` | BLOCKED | `measure:quantity` | 89 | 89 |

All six terminal, all identical pattern, zero exceptions: `governed_
missing_summary` reads **exactly `["measure:quantity"]`** — the entity
side is never listed as missing. CONTRACT and EVENT entity counts are
always exactly equal to each other on every case (matching the real
1:1 contract↔dispatch structure confirmed pre-implementation), and match
the raw contract/dispatch row counts in each fixture exactly (e.g.
RENTAL-011: 67 contracts, 67 dispatches in the raw CSVs → 67 CONTRACT +
67 EVENT entities resolved). RENTAL-011 also shows E.3 relationship
discovery activating for the first time on this corpus: 334
`CanonicalCaseRelationship` rows (201 `BELONGS_TO`, 66 `ASSOCIATED_WITH`,
67 `REFERENCES`) — confirmed live, matching the pre-implementation
diagnosis exactly (Section B: "no dataset ever had two entity-typed
columns resolve simultaneously" — now several do).

## J. Answers to the certification's primary questions

**A. Does Rental now become reachable through governed CONTRACT/EVENT
entities rather than failing because WORK_ORDER is absent?**

Yes, unambiguously. Pre-P3.xxI.2C, every Rental case was BLOCKED with
`missing_canonical_entities` including `WORK_ORDER` (no valid subject at
all). Post-merge, `missing_canonical_entities` is empty on every one of
the six cases — the entity/subject gate is fully satisfied via the
CONTRACT alternative, with EVENT entities and real E.3 relationships
resolving alongside it. The remaining `BLOCKED` status comes entirely
from a different, later gate (`measure:quantity`), never from the entity
side.

**B. Does the existing P3.xxI.2B FieldMaintenance baseline remain
intact?**

Yes. Section I's FieldMaintenance control table shows all four cases
producing exactly the certified baseline counts (61/0/86/26), every
finding correctly tagged `work_order`, zero double-publication under the
newly-reachable CONTRACT pass — confirmed live, on the deployed backend.

**C. If Rental remains unable to detect its truth cases, is the
remaining blocker the already-anticipated derived duration/rental_days
evidence gap rather than subject/entity scope?**

Yes, precisely confirmed, with one refinement over the pre-implementation
prediction. The single missing item, on every case, is literally
`measure:quantity` — not any entity, relationship, or subject-scope
signal. Tracing why: `field_tickets.csv`'s `hours_used` resolves to the
`duration_hours` concept (not the literal `quantity` concept), and
`contracts.csv`'s `rate` resolves to `unit_price` (via its `contract_id`
sibling alternative — not `hourly_rate`, whose alias set is `hourly_
rate`/`labor_rate`/`rate_per_hour`, none of which match `rate`). Real
Rental data's governed measure shape is therefore `{duration_hours,
unit_price}` — a real, resolvable, cross-dataset-rate-capable pairing at
the SERVICE layer (`_collect_lines` already accepts `duration_hours` as
a `quantity_field` stand-in and already treats `unit_price` as a valid
rate source) — but the READINESS gate's declared
`alternative_canonical_measure_sets` only lists `{quantity, unit_price}`
and `{duration_hours, hourly_rate}`, neither of which matches this exact
combination. This is classified as
**FOUNDATIONAL_CANONICAL_DURATION_EVIDENCE_GAP**, not
CAPABILITY_MODEL_GAP: the dominant, decisive reason genuine truth-corpus
recovery remains at zero is not this narrow readiness-declaration gap
(which is mechanical and could in principle be closed by adding a third
alternative set) but that Rental's own hidden truth (`unbilled_rental_
days`, `late_return_leakage`) computes its expected amount from
`rental_days` — a value derived from a date interval
(`dispatch_date`→`return_date`), which exists nowhere as governed
canonical duration evidence, stored or derived. `hours_used` is a real,
governed, but economically UNRELATED metric to these two truth
scenarios; even a hypothetical fix to the narrower readiness-declaration
gap would not recover genuine truth-corpus TP, since the quantity it
would admit (dispatch hours) is not what the truth's own expected-amount
calculation uses. Neither gap is patched in this milestone, per the
mission's explicit instruction; both are reported precisely rather than
either silently worked around or conflated with a subject-generalization
failure.

## K. Metrics

**FieldMaintenance** (own denominator: 152 in-family truth items —
37+0+88+27 across FIELDMAINT-001/002/005/007):

| Metric | Value |
|---|---:|
| TP | 150 |
| FN | 2 (both FIELDMAINT-005, diagnosed in the P3.xxI.2B report as temporal-applicability abstention and materiality-threshold suppression — both correctly-functioning safety invariants, unchanged by this milestone) |
| Mechanical/fabricated FP | 0 |
| FP, strict single-family denominator (FIELDMAINT-001's 24 verified-genuine `contract_rate_mismatch` findings, out-of-family) | 24 |
| Precision, strict single-family | 150/174 = 86.21% |
| Precision, mechanical-correctness basis | 150/150 = 100.00% |
| Recall | 150/152 = 98.68% |
| Economic-value capture | $83,263.29 / ~$83,754.76 FieldMaintenance-own truth value ≈ 99.4% (unchanged from P3.xxI.2B) |

**Rental** (own denominator: 14 in-family truth items — `unbilled_
rental_days` + `late_return_leakage` across RENTAL-001/003/011/012/015/018;
verified directly against each sim's own `hidden-truth/leakage_truth.json`
this session: RENTAL-011 contributes 5, RENTAL-015 contributes 9, the
other four contribute 0 — RENTAL-001/003 carry no `scenario_id`-labeled
truth at all, RENTAL-012/018 carry only maintenance/fuel/timeliness
scenarios outside this family):

| Metric | Value |
|---|---:|
| TP | 0 |
| FN | 14 |
| FP (any kind) | 0 |
| Precision | N/A (0 findings produced; not 0% — no denominator) |
| Recall | 0/14 = 0.00% |
| Economic-value capture | $0 / $241,050.00 = 0.00% |

**Combined** (166 in-family truth items total, matching the P3.xxI.2A/2B
denominator exactly):

| Metric | Value | Delta vs. P3.xxI.2B |
|---|---:|---:|
| TP | 150 | unchanged |
| FN | 16 | unchanged |
| Mechanical/fabricated FP | 0 | unchanged |
| FP, strict single-family | 24 | unchanged |
| Precision, strict single-family | 150/174 = 86.21% | unchanged |
| Recall | 150/166 = 90.36% | unchanged |
| Economic-value capture | $83,263.29 / $324,804.76 = 25.63% | unchanged |

The combined numbers are, deliberately, unchanged — Rental's TP was 0
before this milestone and remains 0 now, for an entirely different and
now precisely understood reason (Section J.C). Reporting FieldMaintenance
and Rental separately (this section) rather than only the unchanged
combined number is what actually shows this milestone's real effect,
per the mission's own instruction not to hide domain/process differences
behind one combined figure.

**Additional required reporting:**

- **Rental readiness improvement**: `missing_canonical_entities` went
  from including `WORK_ORDER` (BLOCKED, no subject at all) to empty on
  every one of six cases (BLOCKED only on `measure:quantity`) — a
  structural improvement not visible in the recall number above.
- **Subject/entity generalization result**: CONTRACT and EVENT entities
  resolve correctly and consistently on 100% of live Rental cases (6/6),
  entity counts matching the raw data exactly on every case.
- **E.3 relationship activation**: live-confirmed on RENTAL-011 (334
  relationships: 201 BELONGS_TO, 66 ASSOCIATED_WITH, 67 REFERENCES) —
  the first live corpus-wide activation of this mechanism, exactly as
  predicted pre-implementation (Section B).
- **Stable finding identity behavior**: live-confirmed on the
  FieldMaintenance control (173 findings across three cases, 100%
  correctly tagged `work_order`) and pre-merge via
  `test_p3xxi2c_billable_subject_generalization.py` Section 5 (6/6
  correctly tagged `contract`, real orchestration run). Rental itself
  produced no findings to inspect live (Section J.C), so subject-identity
  behavior for a live CONTRACT-subject finding is proven via the merged
  test suite's own real orchestration run, not via the Rental cases in
  this certification pass specifically.

## L. Generalization evidence

Beyond Rental itself, the merged test suite's Section 3 and Section 5
tests independently prove the mechanism generalizes through canonical
semantics rather than recognizing either FieldMaintenance's or Rental's
own literal column names:

- Section 3 resolves a CONTRACT subject via the `agreement_id` alias
  (never `"contract_id"` literally).
- Section 4's bridge unit tests use a synthetic `svc_event`/`rate_card`
  column-name pair, distinct from both Rental's `dispatch_id`/
  `contract_id` and FieldMaintenance's `work_order_id`/`contract_id`.
- Section 5 is a full, real orchestration run using Rental's own
  `dispatch_id`/`dispatch_date` spellings (needed so domain
  classification — a separate, pre-existing subsystem this milestone
  does not touch — succeeds) but different file names, different
  grouping, and `agreement_id`/`rate_card_id`/`labor_rate` in place of
  literal `contract_id`/`hourly_rate`, still producing 6/6 correct
  findings purely through concept resolution.

Live Rental certification (Section I) adds a further, larger-scale proof
of the same point: real Rental data, using its own literal column names,
resolves CONTRACT/EVENT entities and E.3 relationships correctly across
six independent cases with zero exceptions.

## M. Remaining limitations

- **FOUNDATIONAL_CANONICAL_DURATION_EVIDENCE_GAP** (Section J.C, the
  dominant blocker): no governed canonical duration evidence exists for
  a date-interval-derived quantity (`rental_days`), which is what
  Rental's own truth corpus actually uses as its expected-amount basis.
  Not patched in this milestone, per explicit instruction.
- **Narrower readiness-declaration gap** (Section J.C, secondary):
  `alternative_canonical_measure_sets` does not yet declare a
  `{duration_hours, unit_price}` combination, even though the service
  layer already mechanically supports it. Not patched in this milestone
  either — and patching it alone would not recover genuine Rental TP
  (Section J.C explains why), so it is reported as a precise, separate
  observation rather than conflated with the dominant gap above or
  treated as something worth fixing reflexively.
- `EVENT`/`CONTRACT` entity resolution is now live wherever `dispatch_id`/
  `contract_id`-aliased columns appear in ANY case corpus-wide (not just
  Rental) — an intended, generic consequence of closing a documented gap,
  not a new capability targeted at Rental specifically, but worth noting
  as a corpus-wide behavior change to watch for in future live
  certifications of unrelated capabilities.

## N. Final classification

### P3.xxI.2C VALIDATED

The mission's own three primary questions (Section J) all resolve
cleanly and consistently, with zero exceptions across six independent
live Rental cases:

- Rental is now reachable through governed CONTRACT/EVENT entities —
  confirmed structurally (entity/relationship resolution) on every case.
- The certified FieldMaintenance baseline is fully intact — confirmed
  live, not just in pytest, with zero double-publication under the newly
  reachable CONTRACT pass.
- Rental's continued zero recall traces to a precisely diagnosed,
  correctly out-of-scope evidence gap (derived duration), never to
  subject/entity scope — confirmed identically on all six cases, not
  merely plausible on one.

Per the mission's own explicit guidance: "If the billable-subject
architecture works but Rental remains blocked only by the independent
duration/rental_days evidence gap, that can still support VALIDATED or
PARTIALLY VALIDATED depending on the live evidence." The live evidence
here is unusually clean — a single, identical, correctly-classified
blocker on every case, no ambiguity, no partial or inconsistent behavior,
zero mechanical/fabricated false positives anywhere, and the certified
control population (FieldMaintenance) provably unaffected. This supports
the stronger of the two allowed outcomes: VALIDATED, not PARTIALLY
VALIDATED, because nothing about the subject-generalization mechanism
itself was found lacking, ambiguous, or inconsistent — only a distinct,
separately-scoped, already-anticipated capability gap remains, exactly
as the mission's own pre-authorized interpretation describes.

## O. Next recommendation

Two independent, separately-scoped follow-up items, neither undertaken
in this milestone:

1. **FOUNDATIONAL_CANONICAL_DURATION_EVIDENCE_GAP**: a governed
   capability to derive a canonical duration/quantity concept from a
   date interval (e.g. `dispatch_date`→`return_date`), with the same
   abstain-on-ambiguity discipline this codebase already applies
   everywhere else (missing/malformed dates abstain, never a fabricated
   duration). This is the actual prerequisite for Rental's own truth
   corpus (`unbilled_rental_days`, `late_return_leakage`) to become
   detectable at all.
2. Optionally, and independently, declare a third
   `alternative_canonical_measure_sets` entry
   (`frozenset({"duration_hours", "unit_price"})`) on
   `REVENUE-AMOUNT-VARIANCE`, since the service layer already supports
   this combination mechanically. Recommended only together with, or
   after, item 1 — declared alone it would let the capability reach
   READY on Rental data using `hours_used` as the quantity basis, which
   Section J.C already establishes is not what Rental's own truth
   corpus's expected-amount calculation actually uses, so it would risk
   producing plausible-looking but ECONOMICALLY INCORRECT findings
   rather than genuine recall improvement.
