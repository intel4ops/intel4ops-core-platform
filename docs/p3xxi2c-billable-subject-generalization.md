# P3.xxI.2C — Billable Subject Generalization

## Status

Implementation complete on the dedicated branch; local gates pass. Merge,
deployment, and post-merge Rental live certification remain owner-gated.

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

## I. Rental certification (post-merge, pending)

Not yet performed — per the mission's own required sequencing, live
Rental certification runs only after implementation PR review, CI, and
owner-authorized merge/deployment. This section will be completed in a
docs-only follow-up PR with live TP/FP/FN, precision/recall, and
economic-value capture for Rental, FieldMaintenance, and combined,
reported separately (Section 11's own requirement — domain/process
differences never hidden behind one combined number).

**Honest expectation, stated now rather than discovered silently later**:
this milestone generalizes the SUBJECT (which entity type a finding is
about) and proves that mechanism sound end-to-end. It does **not** add
any new QUANTITY-evidence shape. Hand-verification against RENTAL-011's
own hidden truth shows all four of its truth scenarios
(`delayed_invoicing`, `late_return_leakage`, `rental_rate_mismatch`,
`unbilled_rental_days`) compute their expected amount from `rental_days`
— a value derived from a date interval (`dispatch_date`→`return_date`, or
the contract's own `start_date`→`end_date`), which is never a stored
column in any Rental CSV. `field_tickets.csv`'s own stored quantity
(`hours_used`) is a real, resolvable, but economically UNRELATED metric
to these four scenarios. Computing a quantity from a date interval is a
new, separate evidence-derivation capability this milestone deliberately
does not build (Section 1 of the mission: "the goal is NOT add Rental
support"; building it now would also risk crossing into exactly the kind
of new-capability-model territory the architectural stop gate exists to
catch). Live certification is therefore expected to show the subject
mechanism activating correctly and safely on Rental data (readiness
reaching READY or PARTIAL via the CONTRACT alternative, zero fabricated
findings) while producing few or zero genuine new TP against Rental's
specific truth corpus — a capability-model gap distinct from, and not
evidence against, the subject-generalization mechanism itself. This is
reported as a prediction to be verified, not assumed; Section I will
state the actual live numbers plainly, including if this expectation
turns out wrong in either direction.

## J. Generalization evidence

Beyond Rental itself, Section E's Section 3 and Section 5 tests
independently prove the mechanism generalizes through canonical
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

## K. Remaining limitations

- The date-interval-as-quantity gap described in Section I — the
  dominant reason live Rental recall is expected to be low regardless of
  how well the subject mechanism itself performs.
- Rental's own `field_tickets.csv`/`dispatch.csv` domain classification
  depends on `domain_registry.py`'s pre-existing `dispatch_id`/
  `dispatch_date`/`return_date` aliases (already present, added in an
  earlier milestone) — confirmed necessary and sufficient in Section E's
  Section 5 test, but this milestone does not extend or audit that
  separate alias table beyond confirming it already covers Rental's
  literal column names.
- `EVENT`/`CONTRACT` entity resolution is now live wherever `dispatch_id`/
  `contract_id`-aliased columns appear in ANY case corpus-wide (not just
  Rental) — an intended, generic consequence of closing a documented gap,
  not a new capability targeted at Rental specifically, but worth noting
  as a corpus-wide behavior change to watch for in future live
  certifications of unrelated capabilities.

## L. Final classification

**[Deferred — see Section I.]** Per the mission's own required sequencing,
this milestone's final classification is stated only after live Rental
certification runs post-merge. The implementation itself is complete,
tested, and regression-clean; whether the overall milestone reaches
VALIDATED / PARTIALLY VALIDATED / FAILED depends on live evidence not yet
gathered, not on an assumption made here.
