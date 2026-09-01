# P3.xxV.2G — Entity Population Coverage + Model Eligibility Diagnosis

Diagnosis only. No threshold, coverage ratio, entity-confidence formula, semantic
interpretation, capability declaration, XDOM-A, XDOM-B, or truth file was changed
this pass. All findings below trace to specific files/lines or to live data pulled
from the same post-Fix-#4 Wave 1 reruns used in the P3.xxV.2F certification.

---

## A. Current Entity Readiness Contract (exact, not inferred)

Traced the live call path: `CaseCapabilityIndex` (pure data,
`app/intelligence_packs/case_capability_index.py`) is built once per run by
`case_capability_index_service.py` (the one DB-touching file), then evaluated by
`intelligence_readiness_service.evaluate_readiness()` against a pack's
`IntelligencePackDefinition` (`app/intelligence_packs/registry.py`).

For `entity_identity.{TYPE}` specifically:

1. **Population source**: `_canonical_entity_signals()` (`case_capability_index_service.py:59-73`)
   runs one query: `SELECT entity_type, entity_identity_confidence FROM canonical_case_entities
   WHERE organization_id=? AND run_id=?` — **every** row for that `run_id`, grouped
   by `entity_type` into a `ConfidenceDistribution(values=tuple(...))`. No filter by
   dataset, by candidate participation, or by anything else.
2. **Threshold check**: `evaluate_readiness()` (`intelligence_readiness_service.py:157-168`)
   calls `_meets_confidence(distribution, pack.minimum_entity_identity_confidence,
   pack.confidence_aggregation_policy, pack.minimum_coverage_ratio)` for each
   `entity_type` in `pack.required_canonical_entities`.
3. **`_meets_confidence`** (`intelligence_readiness_service.py:67-88`): under the
   default (and XDOM-A's explicit) policy `"coverage_above_threshold"`, returns
   `distribution.coverage_above(minimum) >= minimum_coverage_ratio`.
4. **`coverage_above`** (`confidence_distribution.py:48-54`): `count(v >= threshold) /
   len(values)` — a straight fraction of the **entire** distribution.
5. **Result**: for XDOM-A (`minimum_entity_identity_confidence=0.70`,
   `minimum_coverage_ratio=1.0`), the pack is only exempt from `entity_identity.ASSET`
   appearing in `below_confidence_threshold` if **100% of every `CanonicalCaseEntity`
   row of type ASSET in the entire run** individually has `entity_identity_confidence
   >= 0.70`.

**Exact current contract for XDOM-A**: entity type requirement = `{ASSET}`
(`required_canonical_entities`); minimum identity confidence = `0.70`; minimum
population coverage = `1.0` (100%); coverage = simple fraction of the full
case-run ASSET population at/above 0.70; denominator = every `CanonicalCaseEntity`
row of `entity_type="ASSET"` for `(organization_id, run_id)`, unfiltered.
**XDOM-B declares no `required_canonical_entities` at all** — it has never been
subject to this gate, on any Wave 1 case, before or after Fix #4 (confirmed by
direct inspection of its registration, `registry.py:178-210` — no
`required_canonical_entities` field is set, so `evaluate_readiness()`'s loop at
line 158 iterates an empty set for it).

## B. Why `minimum_coverage_ratio = 1.0` Exists

Traced via `git log --all` and the field's own code comments (repository evidence,
not inferred):

- **Introduced in a single commit**: `6b628ee P3.xxE.5 Phase 1: intelligence
  activation readiness (SHADOW mode)` — the field has never been touched again in
  any subsequent commit (`git log` on `registry.py` shows only two later commits,
  neither touching this field).
- **The dataclass default is `1.0`** (`registry.py:81`), and XDOM-A's own
  registration **repeats the default explicitly** (`registry.py:165`) rather than
  overriding it to something rule-specific. `minimum_entity_identity_confidence`,
  by contrast, IS a deliberately-set non-default value (`0.70` vs. the class
  default of `0.0`) — proving the confidence *threshold* was reasoned about for
  this rule, while the coverage *ratio* was left at whatever E.5 shipped with.
- **The actual rationale, from the code comment itself**
  (`registry.py:74-79`, and mirrored in `confidence_distribution.py:5-13`):
  *"one high-confidence outlier can never carry a low-confidence population to
  READY"* / *"one perfect observation must never make a population-level
  capability READY when the rest of the population is low-confidence."*

**Classification against the mission's five options**: this is **(D) — the
safest initial E.5 default** — dressed in language that reads like (C) ("full
population coverage for statistical validity") but applied uniformly to every
pack regardless of whether that pack is actually a population-statistical model.
No comment, test, or design doc anywhere in the repository distinguishes "the
model needs the whole population to be trustworthy" (C) from "the model needs
each candidate entity it will actually touch to be trustworthy" (A) — the
mechanism only implements a blunt version of the concern behind (C)'s wording,
applied by default to every pack including ones (XDOM-A) whose actual execution
logic never reads the population this gate measures (Section G).

## C. Population Denominator Mechanics

Confirmed by direct read of `_canonical_entity_signals()`: the denominator is
**every `CanonicalCaseEntity` row of that `entity_type` for the run** — full
case-global population. Not: entities relevant to a capability, not: entities
participating in candidate records, not: entities within a specific dataset. A
single SQL `SELECT ... GROUP BY entity_type` query, no join to any
finding/candidate/dataset-role table. This directly answers Section 3's list: it
is **"all ASSET entities in the AnalysisCase['s run]"** and nothing narrower.

## D. Wave 1 ASSET Population Distribution (live, post-Fix-#4)

Live-measured this pass, from the same 10 fresh reruns used for the Fix #4
certification. Confidence values in this system are discrete (tier-quantized by
`entity_resolution.py`'s formula, not continuous), so percentiles collapse onto
the observed value set — reported as the full discrete distribution instead of
interpolated percentiles, which is more exact and not a substitute:

| Simulation | ASSET count | Confidence distribution (value: count) | min | median | max | ≥0.70 | <0.70 | Coverage ratio |
|---|---|---|---|---|---|---|---|---|
| FIELDMAINT-001 | 70 | `{0.82: 60, 0.65: 10}` | 0.65 | 0.82 | 0.82 | 60 | 10 | 0.857 |
| FIELDMAINT-002 | 67 | `{0.82: 60, 0.65: 7}` | 0.65 | 0.82 | 0.82 | 60 | 7 | 0.896 |
| FIELDMAINT-005 | 350 | `{0.82: 350}` | 0.82 | 0.82 | 0.82 | 350 | 0 | **1.000** |
| FIELDMAINT-007 | 59 | `{0.82: 50, 0.65: 9}` | 0.65 | 0.82 | 0.82 | 50 | 9 | 0.847 |
| RENTAL-001 | 41 | `{0.99: 8, 0.905: 13, 0.82: 9, 0.65: 11}` | 0.65 | 0.905 | 0.99 | 30 | 11 | 0.732 |
| RENTAL-003 | 40 | `{0.99: 6, 0.905: 9, 0.82: 5, 0.65: 20}` | 0.65 | 0.735* | 0.99 | 20 | 20 | 0.500 |
| RENTAL-011 | 45 | `{0.99: 13, 0.905: 14, 0.82: 7, 0.65: 11}` | 0.65 | 0.905 | 0.99 | 34 | 11 | 0.756 |
| RENTAL-012 | 45 | `{0.99: 16, 0.905: 12, 0.82: 6, 0.65: 11}` | 0.65 | 0.905 | 0.99 | 34 | 11 | 0.756 |
| RENTAL-015 | 351 | `{0.99: 21, 0.905: 60, 0.82: 35, 0.65: 235}` | 0.65 | 0.65 | 0.99 | 116 | 235 | **0.330** |
| RENTAL-018 | 50 | `{0.99: 15, 0.905: 19, 0.82: 8, 0.65: 8}` | 0.65 | 0.905 | 0.99 | 42 | 8 | 0.840 |

*RENTAL-003's median falls between two discrete values (interpolated,
`(0.65+0.82)/2`) since the population splits almost evenly.

**Coverage ranges from 33.0% to 100.0% across the 10 sims** — this is not a narrow
edge case. Only FIELDMAINT-005 (a single-dataset-free master population) clears
the 1.0 bar. RENTAL-015's 351-entity population is 67% single-dataset, the most
extreme case observed.

Per-entity `single-dataset` vs `multi-dataset` split is exactly the `<0.70`
vs `>=0.70` split above, since the identity-confidence formula
(`0.65 + 0.085×(datasets−1)`, unmodified, `app/entities/entity_resolution.py`)
places every single-dataset entity at exactly `0.65` and every multi-dataset
entity at `0.735` or higher — confirmed directly: no simulation in this rerun
produced any confidence value in the `(0.65, 0.735)` gap, consistent with the
formula's own step size.

`candidate-participating asset count` (i.e., assets the legacy
`EntityResolutionService.resolve()` mechanism marks `MATCHED` and that
`run_asset_failure_to_lost_activity` would actually iterate over) **could not be
measured directly this pass** — no API route exposes `AnalysisCaseEntityLink` rows
(confirmed by inspecting `app/main.py`'s router registrations; no
`entity-links`-shaped endpoint exists). Section F reconstructs this
mathematically instead, from the mechanism's own defined behavior.

## E. Low-Confidence Asset Analysis

Every observed sub-0.70 ASSET entity is at exactly `0.65` — the formula's
single-dataset floor (`TIER_BASE(0.65) + STEP(0.085)×(distinct_datasets−1)` with
`distinct_datasets=1`). Traced what a single-dataset ASSET entity actually is,
from the entity formation mechanism (`app/entities/entity_resolution.py`,
unmodified, read-only this pass): it is a raw `asset_id` value that received
`EntityObservation`s from only one `AnalysisCaseDataset` in the run — i.e., an
asset identifier that appears in exactly one CSV among the case's full set.

For FIELDMAINT-001 specifically: `assets.csv` (the master file) has exactly 60
distinct `asset_id` values (confirmed live, `profiler.field_profiles`,
`distinct_count=60`, Section 3 of the Fix #4 report). The run's total ASSET
population is 70 — **10 more than the master file's own row count**. Those 10 can
only be `asset_id` values appearing in `maintenance_events.csv` or
`work_orders.csv` that are **absent from `assets.csv`'s own 60-row list** — i.e.,
a maintenance event or work order referencing a physical asset that was never
independently registered in the asset master file in this simulation's dataset
(a retired/decommissioned asset, a data-entry variant, an asset acquired outside
the tracked registry, or simply an incomplete master list — a normal real-world
data-quality trait, not a defect in this system).

- **Semantic authority**: unaffected — these are the *same* `asset_id` field on
  the *same* now-`AUTO_ACCEPTED` (post-Fix-#4) columns; the semantic layer has no
  opinion on cross-dataset referential completeness, only on whether a column
  means `asset_id`.
- **Identifier values**: valid, well-formed (`alpha_dash_digits` pattern,
  confirmed via the profiler — no null/placeholder values feed entity formation).
- **Isolated records?**: yes, by definition — one dataset only.
- **Incomplete evidence?**: yes — this is exactly what "incomplete evidence" means
  in this system; it is not a data-quality *error*, it is the honestly-reported
  absence of cross-dataset corroboration for that specific instance.
- **False/spurious?**: no evidence of this. The identifier values are real,
  well-formed, and match the field's expected value pattern — nothing distinguishes
  them from any other asset reference except that they happen not to also appear
  in the master file.
- **Candidate participation**: per Section F below, these single-dataset entities
  are the exact population the legacy `matched_assets` mechanism (independently)
  already excludes from XDOM-A's own candidate loop — they were never going to be
  evaluated by the rule regardless of this readiness gate's outcome.

RENTAL-015's far larger 67% single-dataset share (235/351) is the same mechanism
at greater scale — a rental fleet corpus where a majority of asset references
across `contracts.csv`/`dispatch.csv`/`fuel.csv`/`maintenance.csv` cite asset IDs
outside `assets.csv`'s own master list. Not independently re-verified row-by-row
this pass (out of the diagnosis's time budget), but mechanically identical to the
FIELDMAINT-001 case just traced, and consistent with the same formula/denominator.

## F. Case-Global vs. Candidate-Local — the Central Finding

Read `run_asset_failure_to_lost_activity` (`cross_domain_intelligence_service.py:64-146`)
directly, not inferred:

```python
for asset_id in sorted(matched_asset_keys):
    asset_events = maint[maint["asset_id"].astype(str) == asset_id]
    asset_ops = ops[ops["asset_id"].astype(str) == asset_id] ...
```

The rule **only ever iterates `matched_asset_keys`** — a parameter, not the full
dataset. Traced its caller (`analysis_case_orchestration_service.py:1359-1363`):

```python
matched_assets = {
    link.canonical_key
    for link in links
    if link.entity_type == "asset" and link.status == EntityLinkStatus.MATCHED.value
}
```

`links` comes from `entity_resolution_service.resolve(entity_inputs)` — and
**this is a completely separate, legacy mechanism from E.3's `CanonicalCaseEntity`
system**, confirmed by reading `EntityResolutionService.resolve()` in full
(`app/services/entity_resolution_service.py`): for each canonical dataframe, it
collects `dropna().unique()` raw values of `asset_id` per dataset, and marks a
value `MATCHED` if it appears in `>= 2` distinct datasets — **exact string
equality on the canonical-frame column, with zero dependency on
`SemanticInterpretationDecision`, `resolve_effective_decision`, or
`entity_identity_confidence`**. It does not import or reference
`app.entities.*` or `app.models.entities_canonical` anywhere.

**This is the single most important finding of this diagnosis**: XDOM-A's actual
candidate population (`matched_asset_keys`) and the readiness gate's population
(`CanonicalCaseEntity` rows filtered by `entity_identity_confidence`) are **two
independent systems that happen to both be called "asset identity," built at
different times, measuring different things, joined nowhere in the codebase**.
The readiness gate does not gate the population the rule reads — it gates a
different, E.3-native population that the rule's own execution path never
touches. `cross_domain_intelligence_service.py` contains zero references to
`CanonicalCaseEntity` or `entity_identity_confidence` (confirmed by direct grep,
zero matches).

**Does model correctness require knowing the identity quality of every ASSET in
the case, or only the entity/entities associated with each candidate?** — From
the actual code: **neither, precisely** — the rule's own candidate-formation
mechanism (`matched_asset_keys`) already implements its own, independent,
per-candidate safety filter (exact-match-across-≥2-datasets), and that filter
already excludes exactly the single-dataset-only population this gate is
penalizing the whole run for. The worked example in the mission (does asset
A-999 at 0.65 block evaluation of independent asset A-100 at 0.94?) has a
directly evidenced answer: **A-999 was never going to be evaluated by the rule
in the first place** (a single-dataset asset never earns legacy `MATCHED`
status, since `MATCHED` itself requires cross-dataset appearance — the same
underlying signal, computed twice, by two unconnected mechanisms, one of which
is used for execution and the other for gating). Yet today, A-999's mere
presence in the case-global `CanonicalCaseEntity` population is sufficient to
keep the *entire pack* (including A-100's fully-legitimate candidate) at
BLOCKED/PARTIAL.

## G. False-Positive Risk Assessment

| Risk | Applies to XDOM-A? | Applies to XDOM-B? | Notes |
|---|---|---|---|
| Entity collision (two different physical assets sharing one resolved identity) | Not applicable to the *gate itself* — `matched_assets`' exact-string-match mechanism has its own, independent collision exposure, unrelated to `entity_identity_confidence` | N/A — XDOM-B declares no entity requirement at all | Moving to candidate-local readiness would not introduce this risk; it already exists (or doesn't) independent of the gate |
| Mismatched asset across datasets | Same as above — governed by `EntityResolutionService`'s own exact-match logic, not by this readiness gate | N/A | |
| Cross-entity revenue attribution | XDOM-A publishes per-asset findings keyed by the matched `asset_id` string itself (`entities=[{"entity_type": "asset", "canonical_key": asset_id}]`) — no aggregation across entities | N/A — XDOM-B never sums a monetary amount across records (`currency_behavior="currency_agnostic"`, confirmed in its own registration comment) | Neither rule performs a population-level statistical aggregation where a low-confidence entity could silently distort a shared number |
| Duplicate identities | Governed by `EntityResolutionService`/E.3 entity-deduplication, unrelated to the readiness gate | N/A | |
| Partial entity populations | This is precisely what case-global coverage is trying to guard against — but XDOM-A never reads the case-global population, only its own independently-filtered `matched_assets` set (Section F) | N/A | The risk is real in the abstract, but the current gate protects a population the rule doesn't consume, while leaving unprotected whatever risk *does* exist in `matched_assets` itself (already independently mitigated by its own ≥2-dataset rule) |
| Biased aggregate model calculations | **Applies directly to future population/statistical models** (e.g. a fleet-utilization rate, an average-time-to-failure calculation) — a model that legitimately divides by or averages over the full asset population *would* be distorted by a large low-confidence tail | **Would apply to any future revenue-aggregation model**, not to XDOM-B's current existence-only match | This is the one risk class where population-level coverage semantics remain genuinely necessary |

**Conclusion**: every false-positive risk that a case-global coverage requirement
could meaningfully defend against is either (a) already independently mitigated by
a different mechanism (`EntityResolutionService`'s own matching logic) for
XDOM-A/XDOM-B specifically, or (b) a real risk only for a *different class* of
model — one that performs a genuine population-level statistical aggregation,
which neither current rule does.

## H. XDOM-A Requirements — What It Actually Needs

Per-candidate: an `asset_id` value that (a) legacy-resolves to `MATCHED` (≥2
dataset cross-reference), (b) has a `downtime_hours` maintenance event, and (c)
has an overlapping-window operational event. **The rule's own logic already
enforces per-candidate corroboration** — it is architecturally a **PER_ENTITY /
PER_CANDIDATE** model, not a population-coverage model, judged directly from its
implementation (Section F), not assumed.

## I. XDOM-B Requirements — What It Actually Needs

XDOM-B declares **no `required_canonical_entities`** at all (`registry.py:178-210`)
and its own rule body (`run_lost_activity_to_revenue_gap`) contains zero references
to `CanonicalCaseEntity`/entity confidence (confirmed by the same grep as Section F).
Its matching is existence-only, keyed by `operational_event_id` or
`(route_id, event_date)` (the pre-existing, untouched DC-6 mechanism). **XDOM-B is
already, today, a de facto PER-RECORD model with zero entity-coverage gating** —
it never had this problem, which is exactly why it reached READY on every Rental
case this Wave-1 rerun while XDOM-A did not.

## J. Model Classification

| Model | Actual behavior observed | Semantic classification |
|---|---|---|
| XDOM-A | Iterates a pre-filtered, per-candidate `matched_asset_keys` set; publishes one finding per qualifying asset independently | **PER_ENTITY / CANDIDATE_LOCAL** |
| XDOM-B | Existence-only record match, no entity-identity dependency at all | **PER_RECORD** (entity-coverage concept does not apply) |
| MAINT-001 | Not wired to canonical evidence completeness or entity-coverage gating this program (per Fix #3 report, Section E — deliberately deferred); not re-examined this pass | Unknown — out of scope |
| A hypothetical fleet-utilization / average-time-to-failure model | Would need to divide by or average over the *entire* observed asset population to be statistically meaningful | **POPULATION_COVERAGE** (or **FULL_POPULATION**, if the business requirement is "every registered asset must be accounted for," a stricter bar than statistical validity alone) |

## K. Diagnostic Candidate-Local Readiness Comparison (analysis only, not published)

Direct candidate-local (`matched_assets`) counts could not be pulled from a live
endpoint (Section D). Reasoned instead from the two mechanisms' shared underlying
signal: `EntityResolutionService.resolve()`'s `MATCHED` status requires an
`asset_id` value to appear (as a raw string) in `>= 2` distinct canonical
dataframes — the same "cross-dataset appearance count" the E.3 confidence formula
uses (`distinct_datasets` in `0.65 + 0.085×(distinct_datasets−1)`). A
single-dataset (`distinct_datasets=1`) E.3 entity therefore corresponds to a
legacy-`UNRESOLVED` (never `MATCHED`) link, and every E.3 entity with
`distinct_datasets >= 2` (confidence `>= 0.735`, i.e. every value in this rerun's
distributions except the `0.65` bucket) corresponds to a legacy-`MATCHED` link —
**this correspondence is inferred from the two mechanisms' shared counting logic,
not observed directly, since no API exposes `AnalysisCaseEntityLink` rows; flagged
explicitly as an approximation, not a measurement.**

Under that approximation, "candidate-local coverage" (fraction of the
*already-legacy-filtered* `matched_assets` population that also clears
`entity_identity_confidence >= 0.70`) would be **100% on every one of the 10
Wave 1 cases** — because every entity in that filtered population has
`distinct_datasets >= 2`, i.e. confidence `>= 0.735 > 0.70` by construction of
the very formula that produced it. If this approximation holds, a candidate-local
readiness policy would report `entity_identity.ASSET` fully satisfied on all 10
cases, changing FIELDMAINT-001/002/007/RENTAL-* from BLOCKED/PARTIAL (on this one
dimension) to no-longer-blocked-on-this-dimension — **without altering the
threshold, the formula, or which candidates the rule actually evaluates.**

| Simulation | Case-global coverage (measured) | Candidate-local coverage (reasoned, see caveat above) |
|---|---|---|
| FIELDMAINT-001 | 0.857 | ~1.0 |
| FIELDMAINT-002 | 0.896 | ~1.0 |
| FIELDMAINT-005 | 1.000 | 1.0 (no gap to begin with) |
| FIELDMAINT-007 | 0.847 | ~1.0 |
| RENTAL-001 | 0.732 | ~1.0 |
| RENTAL-003 | 0.500 | ~1.0 |
| RENTAL-011 | 0.756 | ~1.0 |
| RENTAL-012 | 0.756 | ~1.0 |
| RENTAL-015 | 0.330 | ~1.0 |
| RENTAL-018 | 0.840 | ~1.0 |

No finding was published under any altered rule — this table is analysis only,
computed from already-collected live confidence distributions, not a rerun.

## L. Is 1.0 Too Strict? — Classification

**CORRECT_FOR_SOME_MODEL_CLASSES_ONLY.**

Not blanket "too strict" — Section G/J show the requirement is architecturally
sound for a genuine population-statistical model (e.g. a future fleet-utilization
capability), where a large low-confidence tail really would bias an aggregate
number. It is specifically **mismatched to XDOM-A's actual PER_ENTITY /
CANDIDATE_LOCAL execution model** (Section F/H), and structurally inapplicable to
XDOM-B (which never declared it in the first place, Section I). The defect is not
"1.0 is a bad number" in isolation — it is that **one coverage-semantics knob is
being applied uniformly to models with fundamentally different entity-usage
patterns**, inherited from a generic E.5-era default (Section B) rather than
reasoned per model.

## M. Recommended Generic Architecture (design-level, not implemented)

A capability should be able to *declare* which entity-safety semantics it
actually needs, rather than every pack inheriting one blanket policy:

- **PER_ENTITY** (a.k.a. CANDIDATE_LOCAL): the model's own execution path already
  filters to a specific, checkable candidate set (as XDOM-A's `matched_assets`
  already does); readiness should ask "is the population my rule will actually
  touch trustworthy," not "is every entity that happens to exist in the case
  trustworthy."
- **POPULATION_COVERAGE**: the model aggregates or reasons over a population as a
  whole; a coverage-ratio-against-threshold check (today's mechanism) is the
  right tool, with `minimum_coverage_ratio` tunable per model rather than
  defaulted.
- **FULL_POPULATION**: a stricter variant of the above for models with an
  explicit completeness requirement (e.g. "every registered asset must have a
  confirmed identity before this report is trustworthy") — semantically distinct
  from statistical validity, and worth keeping as its own named mode per the
  mission's framing even though no current model needs it.

This is purely a **declaration-time** distinction (`IntelligencePackDefinition`
gains an enum field), computed the same way for every capability regardless of
industry, simulation, or customer — no FieldMaintenance-specific or
Rental-specific branch, no simulation ID or filename anywhere in the proposed
design, matching every prior fix's generalization discipline.

## N. Future Model Safety Matrix

| Model class (illustrative, not exhaustive) | Typical execution pattern | Recommended entity-safety mode |
|---|---|---|
| Per-asset event detection (XDOM-A today) | Iterates a pre-filtered candidate set, one finding per qualifying entity | PER_ENTITY |
| Work-order detection | Same shape — per-work-order candidate evaluation | PER_ENTITY |
| Job-to-cash | Per-transaction/per-invoice matching, existence-based (XDOM-B's own shape) | PER_ENTITY or none, depending on whether it ever resolves a canonical entity at all |
| Fleet utilization | Divides/averages over the full observed asset population | POPULATION_COVERAGE |
| Labor productivity | Aggregates hours/output across a technician or work-order population | POPULATION_COVERAGE |
| Maintenance reliability (MTBF-style) | Statistical aggregation over an asset population's failure history | POPULATION_COVERAGE |
| A regulatory/compliance completeness report | Explicitly requires accounting for every registered instance | FULL_POPULATION |

## O. Interaction with READY / PARTIAL / BLOCKED (conceptual, not implemented)

Recommended conceptual policy, not a code change:

- A **mandatory candidate entity below confidence** (i.e., a specific entity a
  PER_ENTITY model would need for one candidate) should legitimately exclude
  *that candidate* — not the whole rule. This is arguably already how XDOM-A's own
  `matched_assets` filter behaves in practice; the readiness layer should reflect
  that reality rather than impose a stricter, disconnected population check on
  top of it.
- **Population coverage below the preferred level**, for a genuine
  POPULATION_COVERAGE/FULL_POPULATION model, should continue to produce PARTIAL
  (not BLOCKED) when coverage is nonzero but short of the bar — signaling "usable
  with a caveat" rather than "unusable," matching the existing PARTIAL semantics
  documented in `intelligence_readiness_service.py`'s own header comment.
- For a PER_ENTITY model like XDOM-A, the *readiness* signal itself may need to
  become candidate-count-aware (e.g. "0 of N legacy-matched assets clear the
  entity-confidence bar" → BLOCKED; "some clear it" → READY/PARTIAL scoped to
  that subset) rather than a single case-wide pass/fail — a genuinely different
  shape of readiness computation than today's population-fraction check, which
  is exactly why this is flagged as Fix #5 scope rather than a one-line ratio
  change.

## P. Potential Fix #5 Scope (if justified)

Justified, subject to explicit architectural review — **not implemented this
pass**:

1. Add an entity-safety-mode declaration to `IntelligencePackDefinition`
   (PER_ENTITY / POPULATION_COVERAGE / FULL_POPULATION), defaulting existing
   packs to their currently-observed behavior (XDOM-A → PER_ENTITY, once
   confirmed correct by review; anything without `required_canonical_entities`
   stays exempt, as XDOM-B already is).
2. For PER_ENTITY packs, change the population the readiness check considers from
   the full case-global `CanonicalCaseEntity` set to the same
   candidate-determining population the rule itself uses — which likely also
   requires **reconciling** the two independent identity mechanisms found in
   Section F (legacy `EntityResolutionService`/`AnalysisCaseEntityLink` vs. E.3
   `CanonicalCaseEntity`/`entity_identity_confidence`), since today's rule
   execution doesn't consume E.3's confidence signal at all — a real design
   question in its own right, not a mechanical scope reduction.
3. Leave `minimum_coverage_ratio=1.0` and `confidence_aggregation_policy=
   "coverage_above_threshold"` exactly as-is for any future POPULATION_COVERAGE
   or FULL_POPULATION model.

Given finding F's depth (two disconnected identity systems, not merely "the ratio
is strict"), Fix #5's actual first step may need to be its own reconciliation
sub-diagnosis of whether XDOM-A's rule logic should be migrated onto E.3's
`CanonicalCaseEntity` entirely (retiring the legacy `EntityResolutionService`
path), or whether the readiness gate should instead be taught to read the legacy
`matched_assets` population it already trusts for execution — these are two
different architectural directions with different blast radii, and this
diagnosis does not adjudicate between them.

---

## Classification

**NEXT-3 ROOT CAUSE CONFIRMED — READY FOR FIX #5**

The root cause is not simply "1.0 is too strict." It is that XDOM-A's readiness
gate measures a case-global population from a system (`CanonicalCaseEntity`) that
the rule's own execution path never reads, using a coverage ratio inherited
unmodified from a generic E.5-era default rather than reasoned for this model's
actual (PER_ENTITY / candidate-local) execution shape — while a second,
independent, unconnected legacy mechanism (`EntityResolutionService`) already
performs the actual per-candidate filtering the rule relies on. This is confirmed
by direct code inspection (Sections A, F, H) and corroborated by live Wave 1 data
spanning a 33%–100% case-global coverage range (Section D) that, by the two
mechanisms' shared counting logic, collapses to ~100% candidate-local coverage on
every case (Section K). Per the mission's explicit instruction, no code was
changed; Fix #5's scope (Section P) requires its own architectural review before
implementation, specifically because it surfaces a second, deeper open question
(reconciling two independent entity-identity systems) beyond a simple policy
parameterization.

---

## STOP

No code was changed this pass. Fix #5 has not been started. Awaiting explicit
architectural review before any further remediation.
