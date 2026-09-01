# P3.xxV.2E — Asset Semantic Authority + Entity Identity Diagnosis

**Diagnosis only.** No thresholds, weights, `ACCEPTED_WITH_FLAG` semantics, entity
resolution, aliases, or production code were changed. Every number below is read
directly from the deployed API or the actual source files — nothing here is
inferred.

---

## A. Semantic Confidence Formula (exact, as implemented)

Confidence is the sum of independently-triggered **evidence component weights**,
capped at 0.98, computed across three cooperating modules:

| Module | Component | Weight | Trigger condition |
|---|---|---|---|
| `app/semantic/candidate_generator.py` | `FIELD_NAME_ALIAS_MATCH` | **0.50** | Raw field name matches a registered alias of the concept (always present if the concept was proposed at all) |
| same | `VALUE_PATTERN_MATCH` | **0.20** | `field_profile.value_patterns` intersects the concept's `expected_value_patterns` |
| same | `DATASET_ROLE_COMPATIBILITY` | **0.15** | The dataset's classified `primary_role` (one of 14 `DatasetRole` values: master/transaction/event/snapshot/ledger/schedule/**work_order**/invoice/labor/inventory/measurement/reference/document/contract/unknown) is in the concept's registered `compatible_dataset_roles` set |
| same | `DATATYPE_COMPATIBILITY` | **0.10** | For `concept_type == "identifier"`: `field_profile.is_candidate_identifier` (see Section B) |
| `app/semantic/neighbor_context.py` | `NEIGHBOR_FIELD_CONTEXT` | **0.10** | Another field in the *same* dataset independently aliases to a concept sharing a `compatible_dataset_roles` entry with this concept |
| `app/semantic/cross_dataset_context.py` | `CROSS_DATASET_OVERLAP` | **0.15** | **Gated on `field_profile.is_candidate_identifier`** (see Section B) — then requires a sibling dataset's field to independently alias to the *same* concept AND show value/pattern overlap |

`app/semantic/confidence_engine.py`'s `reconcile()` then: merges same-concept
candidates (summing distinct component types, never double-counting a repeated
type), ranks by confidence, applies the status thresholds
(`auto_accept_min=0.90`, `accepted_with_flag_min=0.70`, `review_required_min=0.40`),
downgrades a too-close (<0.1 apart) tie away from `AUTO_ACCEPTED`, and caps an
AI-only-evidenced winner at `ACCEPTED_WITH_FLAG`. **None of this logic was changed
by, or is inconsistent with, anything in Fixes #1–#3.**

Maximum theoretical sum: 0.5+0.2+0.15+0.1+0.1+0.15 = 1.20, capped at 0.98.
Minimum sum to reach `AUTO_ACCEPTED` (0.90) requires **at least four** of the six
components (any four summing to ≥0.90; three components can reach at most
0.5+0.2+0.15=0.85).

## B. `asset_id` Confidence Decomposition (exact, live)

**FIELDMAINT-001, `work_orders.csv` (227 rows), live confidence 0.80,
`ACCEPTED_WITH_FLAG`:**

| Component | Fired? | Why / why not |
|---|---|---|
| `FIELD_NAME_ALIAS_MATCH` (0.50) | Yes | `asset_id` is a registered alias of itself |
| `VALUE_PATTERN_MATCH` (0.20) | Yes | Values match the `alpha_dash_digits` pattern registered for `asset_id` |
| `DATASET_ROLE_COMPATIBILITY` (0.15) | **No** | `work_orders.csv`'s classified role is `"work_order"` (a specific `DatasetRole` value); `asset_id`'s registered `compatible_dataset_roles = {"master","reference","event","transaction"}` **does not include `"work_order"`** — confirmed directly from `app/semantic/concept_registry.py:89` |
| `DATATYPE_COMPATIBILITY` (0.10) | **No** | For `concept_type=="identifier"`, this checks `field_profile.is_candidate_identifier`, which is `False` here (Section B.1) |
| `NEIGHBOR_FIELD_CONTEXT` (0.10) | Yes | Co-occurs with `work_order_id`, itself recognized and role-compatible |
| `CROSS_DATASET_OVERLAP` (0.15) | **No** | Gated on the same `is_candidate_identifier` flag, which is `False` |
| **Total** | | **0.50+0.20+0.10 = 0.80** — exact match to the live observed value |

**B.1 — why `is_candidate_identifier` is `False` here, exactly:**
`app/semantic/profiler.py:185`: `is_identifier = uniqueness_ratio >= 0.95 AND distinct_count > 1`,
where `uniqueness_ratio = distinct_count / non_null_count`. `work_orders.csv` has
227 rows referencing a small, repeated fleet of assets (each asset receives many
work orders — the entire point of a maintenance dataset). `distinct_count` is far
below `227 * 0.95 ≈ 216`, so `uniqueness_ratio` is far below 0.95, and
`is_candidate_identifier = False`. This is not a data-quality problem — it is the
**correct, expected shape** of a genuine foreign-key reference.

**This fully and exactly explains the observed 0.80** — no other mechanism,
weighting, or path is involved.

## C. Wave-1 Asset-Like Field Matrix (live, exact)

Only `asset_id` appears as the asset-identifier alias across the corpus (no
`unit_id`/`equipment_id`/`vehicle_id`/`tool_id`/`fleet_id` present in any Wave 1
file — confirmed by direct inspection of every CSV header used this wave).

| Simulation | Dataset | Confidence | Status | Fired components |
|---|---|---|---|---|
| FIELDMAINT-001 | `assets.csv` (master file, 60 rows) | **0.95** | `AUTO_ACCEPTED` | alias+pattern+role(`event`)+datatype |
| FIELDMAINT-001 | `work_orders.csv` (227 rows) | 0.80 | `ACCEPTED_WITH_FLAG` | alias+pattern+neighbor |
| RENTAL-001 | `assets.csv` (master file) | **0.95** | `AUTO_ACCEPTED` | alias+pattern+role(`master`)+datatype |
| RENTAL-001 | `dispatch.csv` | 0.70 | `ACCEPTED_WITH_FLAG` | alias+pattern only |
| RENTAL-001 | `contracts.csv` | 0.80 | `ACCEPTED_WITH_FLAG` | alias+pattern+neighbor(`customer_id`) |
| RENTAL-001 | `maintenance.csv` | 0.70 | `ACCEPTED_WITH_FLAG` | alias+pattern only |
| RENTAL-001 | `fuel.csv` | 0.85 | `ACCEPTED_WITH_FLAG` | alias+pattern+role (0.15) |

**Pattern, confirmed generic across both families**: the *one* dataset per
simulation family that is genuinely master/reference-shaped (few rows, one row
per real-world asset) reaches `AUTO_ACCEPTED`. Every operational/transactional
dataset that legitimately *references* the same assets repeatedly — regardless of
family, regardless of specific file name — lands at `ACCEPTED_WITH_FLAG`,
0.70–0.85, via the same two missing-component mechanism (Section B). This is not
a FieldMaintenance-specific or Rental-specific artifact.

## D. Exact-Canonical-Name Behavior

- **Is exact canonical-name equality currently considered?** Yes —
  `FIELD_NAME_ALIAS_MATCH` fires identically whether the raw field is spelled
  exactly `asset_id` or matches via any other registered alias (`vehicle_id`,
  `equipment_id`, `unit_id`, `machine_id`). Exact-name and alias-name evidence are
  **not distinguished** — both contribute exactly 0.50, no bonus for literal
  equality.
- **What score does it contribute alone?** 0.50 — never enough alone to clear even
  `ACCEPTED_WITH_FLAG`'s 0.70 floor.
- **What other evidence is required?** At least 0.20 more (pattern, role, datatype,
  neighbor, or cross-dataset, in any combination) to reach `ACCEPTED_WITH_FLAG`;
  at least 0.40 more (effectively 3 more components) to reach `AUTO_ACCEPTED`.
- **Is this intentional?** Yes, and defensible: a column literally named
  `asset_id` could still, in principle, hold something else (a mislabeled export, a
  copy-pasted template column never populated correctly, a foreign key to an
  unrelated "asset" concept in a different domain). Treating a bare name match as
  automatically authoritative would be a real regression in rigor, not an
  improvement.
- **Could an exact canonical field still be legitimately ambiguous?** Yes — see
  Section J.
- **Is the current policy overly conservative?** Not for the *name-match*
  component specifically. The conservatism problem, precisely located in Section
  B, is in the **role-list completeness** (Section C's finding) and the
  **identifier-detection gate's reuse for corroboration-eligibility** (Section
  B.1) — two narrower, more surgical issues, not the name-match weight itself.

## E. Cross-Dataset Corroboration Behavior

Cross-dataset semantic corroboration **does exist**
(`app/semantic/cross_dataset_context.py`) and is architecturally real, generic
evidence-generation — but it is **gated on `field_profile.is_candidate_identifier`**
(the same uniqueness-ratio flag from Section B.1). This means: for a field that is
*already* highly unique (a near-1:1 master-key shape), cross-dataset corroboration
can add further confidence on top of what role/datatype evidence likely already
supplied. For a field that is a *genuine, repeated foreign key* — the shape that
most needs independent corroboration to establish trust, since its own
role/datatype evidence is the part most likely to be missing (Section B) — the
mechanism is **structurally unavailable**, precisely backwards from where it would
add the most value.

This evidence is **correctly kept separate from E.3 entity resolution** as a
distinct concern: this module never resolves "do these values refer to the same
real-world asset" (that is `app/entities/entity_resolution.py`'s job, using
`entity_identity_confidence`'s own, later, dataset-count-based corroboration
formula — Section H). `cross_dataset_context.py` only ever asks "does another
field independently support the same *meaning* for this field" — a semantic, not
an entity-identity, question. The two are not mixed in the code.

## F. `ACCEPTED_WITH_FLAG` Intended Contract

Two different, both real, precedents exist in the codebase, and they disagree —
**not accidentally**:

- **`resolve_effective_decision()`** (`app/semantic/review.py`, used by E.3 entity
  formation and, since Fix #3, `canonical_evidence_completeness.py`): `ACCEPTED_WITH_FLAG`
  is collapsed into the *same* "no effective concept" bucket as `REVIEW_REQUIRED` —
  reading **(B)**: still insufficiently authoritative for downstream canonical use,
  full stop, no corroboration path.
- **`activity_type_inference.py`** (E.4 process interpretation,
  `app/process/activity_type_inference.py`): `ACCEPTED_WITH_FLAG` is treated as
  reading **(A)** — accepted with a quality/confidence caveat — *specifically when
  independently corroborated* by evidence beyond the bare observation itself
  (temporal/structural/entity evidence); otherwise it falls back to a generic,
  existence-only conclusion at a discounted confidence
  (`machine_confidence * 0.5`), never fully discarded.

**This divergence is explicitly, deliberately documented as intentional and
narrowly scoped**, in `activity_type_inference.py`'s own module docstring: *"This
is TIMESTAMP-concept-specific — identifier-concept inference for entity typing
stays exactly as strict as `app/entities/entity_type_inference.py` ... this file
only governs how EXISTING thresholds are CONSUMED for activity typing, never
lowers them."* E.4's own author was already aware of E.3's strict bar and chose
not to touch it, for TIMESTAMP/STATE concepts specifically.

**Net reading**: `ACCEPTED_WITH_FLAG`'s *design intent*, evidenced by the codebase
itself, is reading (A) with a corroboration prerequisite — E.4 is the fuller,
more mature implementation of the intended contract. E.3 (and now, by inheritance,
Fix #3's `canonical_evidence_completeness.py`) implements a **narrower, incomplete
instance** of the same intended contract — not a competing design, an earlier,
not-yet-extended one.

## G. `ACCEPTED_WITH_FLAG` Consumer Matrix

| Consumer | Accepted as evidence? | Ignored? | Supporting only? | Requires corroboration? | Rationale |
|---|---|---|---|---|---|
| `canonical_evidence_completeness.py` (Fix #3) | No | Yes | — | — | Inherits `resolve_effective_decision`'s binary bar unmodified, by design (Fix #3 explicitly reused the existing contract rather than inventing a new one) |
| E.3 entity formation (`entity_resolution.py`) | No | Yes | — | — | Same `resolve_effective_decision` call, `latest_version=None` always |
| E.4 process activity typing (`activity_type_inference.py`) | Yes | No | Yes (discounted 0.5x if uncorroborated) | Yes, for full-confidence *naming*; existence-only otherwise | Explicitly, narrowly scoped to timestamp/state concepts per its own docstring |
| E.4 state normalization (`state_normalization.py`) | Yes | No | Yes | Yes, identical shape to activity typing | Same corrected-evidence-tier pattern, same author intent |
| Governed readiness / capability index (`intelligence_readiness_service.py`, `case_capability_index.py`) | N/A | N/A | N/A | N/A | These consume *entity*/*trust* confidence outputs, not raw semantic decisions directly — no independent `ACCEPTED_WITH_FLAG` handling of their own found |

## H. Semantic → Entity Confidence Chain (exact, live)

**FIELDMAINT-001** (representative; RENTAL-001/003 confirmed identical mechanism,
same numbers pattern, in the Fix #1 report):

```
raw asset_id (assets.csv, 60 rows, master-shaped)
  -> semantic candidate confidence 0.95 (alias+pattern+role[event/master]+datatype)
  -> machine status: auto_accepted
  -> resolve_effective_decision: effective_concept = "asset_id" (GRANTED)
  -> EntityObservation created for this dataset's 60 asset_id values

raw asset_id (work_orders.csv, 227 rows, FK-repeated)
  -> semantic candidate confidence 0.80 (alias+pattern+neighbor)
  -> machine status: accepted_with_flag
  -> resolve_effective_decision: effective_concept = None (DENIED)
  -> ZERO EntityObservations from this dataset -- 227 rows' worth of
     genuinely-valid asset references never reach entity_deduplication.py at all

deduplicate() (app/entities/entity_deduplication.py):
  -> only assets.csv's 60 observations exist in the pool
  -> distinct_datasets = 1 (structurally, since work_orders.csv was excluded)
  -> entity_identity_confidence = EXACT_TIER_BASE(0.65) + STEP(0.085)*(1-1) = 0.65
     (confirmed live: entity_type_confidence=0.95, entity_identity_confidence=0.65,
      evidence_summary: "single-dataset observation -- not yet corroborated across datasets")

XDOM-A governed readiness: below_confidence_threshold: ["entity_identity.ASSET"]
  (0.65 < minimum_entity_identity_confidence = 0.70, app/intelligence_packs/registry.py:163)
  -> XDOM-A: PARTIAL, not READY
```

**Earliest limiting gate**: the semantic layer (`work_orders.csv`'s `asset_id`
never reaching `AUTO_ACCEPTED`) — everything downstream (entity formation's
single-dataset cap, entity identity confidence staying at 0.65, XDOM-A's
`entity_identity` threshold) is a **correct, mechanical consequence** of that one
upstream fact, not an independent defect at each layer. This confirms and sharpens
V.2B's DC-2 finding with exact numbers and an exact mechanism (Sections B.1 and E),
rather than the earlier, less precise framing.

## I. Comparison: `AUTO_ACCEPTED` Identifier vs. `asset_id`

| | `work_order_id` (FIELDMAINT-001, `work_orders.csv`, 227 rows) — reaches AUTO_ACCEPTED (0.98) | `asset_id` (same dataset) — stays at ACCEPTED_WITH_FLAG (0.80) |
|---|---|---|
| Name evidence | 0.50 (alias match) | 0.50 (alias match) |
| Pattern evidence | not fired this case | 0.20 (fired) |
| Cardinality | High (`WO-0001..WO-0227`, ~1:1 with rows) → `is_candidate_identifier = True` | Low (small fleet, many work orders each) → `is_candidate_identifier = False` |
| Role compatibility | 0.15 — `work_order_id`'s registered `compatible_dataset_roles` **does include** `"work_order"` | 0.00 — `asset_id`'s registered set **does not include** `"work_order"` |
| Datatype | 0.10 (gated on `is_candidate_identifier=True`) | 0.00 (gated on `is_candidate_identifier=False`) |
| Neighbor context | 0.10 | 0.10 |
| Cross-dataset overlap | 0.15 (gated on `is_candidate_identifier=True`, corroborated by `field_tickets.csv.ticket_id`) | 0.00 (gated on `is_candidate_identifier=False`) |
| **Total** | **1.00, capped 0.98** | **0.80** |

**What `asset_id` lacks, precisely**: not name/pattern evidence (it has both) — it
lacks the two components gated on high row-level uniqueness (datatype,
cross-dataset), and it lacks role compatibility purely because the concept
registry's role list for `asset_id` doesn't enumerate `"work_order"` (or, by the
same gap, `"schedule"`, `"labor"`, `"invoice"`, `"contract"`, `"measurement"`,
`"inventory"` — every specific `DatasetRole` beyond the four generic ones already
listed). `work_order_id` doesn't have this role-list gap because `"work_order"` is
its own concept's namesake role, already registered.

## J. False-Positive Safety Analysis

Constraints genuinely present in this evidence, not hypothetical:

- **Reused IDs across sites/contexts**: nothing in the current evidence rules out
  the same `asset_id`-shaped value meaning *different* real-world assets in
  different datasets (e.g., a per-site numbering scheme). Cross-dataset
  corroboration, if broadened to low-cardinality fields, would need a value-overlap
  check (which `cross_dataset_context.py` already requires) — but value overlap
  alone does not prove *referential* identity, only *lexical* similarity.
- **Low-cardinality categorical pseudo-IDs**: a field named similarly and holding a
  small set of repeated short alphanumeric codes could, in a different registry
  configuration, coincidentally resemble a real identifier concept's alias/pattern
  without being one (e.g. a status-code column). The uniqueness gate is a genuine,
  reasonable defense against this class of false positive today — broadening it
  without a replacement safeguard would reintroduce that risk.
- **Composite IDs**: not observed in this corpus (every `asset_id` here is a
  single flat column), but the current single-field evidence model has no explicit
  handling for a composite grain — not exercised by this diagnosis, flagged for
  completeness only.
- **Placeholder/dummy values**: not observed in this corpus's `asset_id` columns
  (values inspected are well-formed `alpha_dash_digits`), so not a live concern
  here, but a generic remediation should not assume clean data.
- **Mixed entity populations**: a repeated-FK column that references two *different*
  entity types under one name was not observed in this corpus, but is a real,
  generic risk any remediation must consider (e.g. an `asset_id` column that
  actually mixes vehicle and equipment references under a shared numbering scheme).

**None of these argue for lowering the name-match weight or the `AUTO_ACCEPTED`
threshold itself.** They argue specifically for caution in whichever of the two
precise gaps (Section B) gets addressed: broadening the role list is low-risk
(pure registry data, no logic change); relaxing or replacing the
uniqueness-ratio gate for datatype/cross-dataset eligibility carries more of the
above risks and would need its own corroboration safeguard, not a blanket bypass.

## K. Primary NEXT-2 Classification

**Primary: `SEMANTIC_EVIDENCE_MODEL_GAP`**, with a secondary, distinct
**`CROSS_LAYER_CONTRACT_DEFECT`** (Section F/G) that compounds it but is not
itself the root cause.

Evidence:
- Section B/C establish this mechanically, exactly, and reproducibly: two
  specific evidence-generation conditions (registered `compatible_dataset_roles`
  completeness; `is_candidate_identifier`'s reuse as a corroboration-eligibility
  gate) fail to recognize legitimate evidence for a common, correctly-shaped data
  pattern (a low-cardinality foreign-key identifier). This is a gap in what the
  evidence *model* considers, not a miscalibrated weight or threshold value — the
  0.50/0.20/0.15/0.10/0.10/0.15 weights themselves are not shown to be wrong
  anywhere in this diagnosis.
- It is explicitly **not** `SEMANTIC_CONFIDENCE_CALIBRATION_DEFECT` — no weight or
  threshold number is implicated; the mechanism is binary (component fires or
  doesn't), not a magnitude-tuning question.
- It is explicitly **not** `LEGITIMATE_AMBIGUITY` — every missing signal here has
  a mechanically identifiable, generic cause (Section B), not a case where the
  evidence genuinely conflicts or the concept is truly uncertain.
- It is explicitly **not** primarily `ENTITY_RESOLUTION_DEFECT` — Section H shows
  `entity_deduplication.py`'s own formula behaves exactly as designed given its
  input; the limiting gate is upstream, at the semantic layer.
- The `CROSS_LAYER_CONTRACT_DEFECT` (Section F/G) is real and independently
  confirmed but is best understood as a **second, compounding** finding: even if
  Section B's evidence-model gap were closed and `asset_id` reached
  `AUTO_ACCEPTED` reliably, the *inconsistent* `ACCEPTED_WITH_FLAG` treatment
  across E.3/Fix#3 vs. E.4 would remain a separate, real question about whether
  E.4's already-validated graduated-corroboration pattern should be extended to
  identifier concepts too — orthogonal to, not a substitute for, fixing Section B.

## L. Candidate Remediation Options (not implemented)

| Option | Architectural correctness | False-positive risk | Generalization benefit | Affected layers | Regression surface | Level-7 alignment |
|---|---|---|---|---|---|---|
| **A.** Improve exact canonical-name evidence weighting (raise the 0.50 base, or add an "exact spelling" bonus) | Low — Section D shows the *name* weight isn't the bottleneck; this would move the threshold without fixing the actual gap, and would broadly and non-specifically increase confidence for every concept, including cases where that's unwarranted | Higher — a global weight increase affects every concept, not just identifier/role-list gaps | Low — doesn't target the actual mechanism | All semantic interpretation | Wide (touches every concept's scoring) | Poor — treats a symptom, not Section B's actual mechanism |
| **B.** Add cross-dataset semantic corroboration | Already exists (Section E) — the real question is *broadening its eligibility gate*, not adding it from scratch | Low-moderate if scoped to value-overlap-confirmed cases only (already required) | High — directly targets the FK-shaped-identifier pattern, generically, across any industry | `cross_dataset_context.py`'s gate condition only | Narrow, well-isolated (one gate condition) | Strong — reuses an already-built, tested mechanism |
| **C.** Allow `ACCEPTED_WITH_FLAG` as supporting canonical evidence with independent corroboration | Already validated architecturally by E.4 (Section F) — extending, not inventing | Low, if the corroboration requirement is genuine (not just "any second component fired") — mirrors E.4's own discipline | High — reusable across every downstream consumer currently binary (E.3, Fix #3) | `resolve_effective_decision` callers (E.3 entity formation, `canonical_evidence_completeness.py`) — NOT `resolve_effective_decision` itself, which could stay as the raw-tier function while callers add a corroboration-aware wrapper, matching E.4's own pattern of not modifying the underlying thresholds | Moderate — touches two live consumers (entity formation, Fix #3's completeness check), needs care not to silently change unrelated concepts' behavior | Strong — directly extends an already-validated, in-production pattern to a second, related use |
| **D.** Separate concept-authority threshold from entity-identity threshold more cleanly | Partially already true (Section H shows they ARE separate numbers/formulas) — the actual ask here would be re-examining whether `entity_identity_confidence`'s own single-dataset-base (0.65) and step size (0.085) are separately worth revisiting | Low — orthogonal to Section B's fix | Moderate — helps XDOM-A's specific 0.70 threshold gap, but doesn't fix the semantic-layer root cause | `entity_deduplication.py` only | Narrow | Out of explicit scope this pass ("do not modify entity confidence") |
| **E.** Improve semantic context evidence generally (broader neighbor/role heuristics beyond exact registry-list membership) | Moderate — more powerful but less precisely scoped than B; risks becoming a second, parallel heuristic layer | Moderate — harder to bound without case-by-case review | Moderate | `neighbor_context.py`, `role_classifier.py`, concept registry | Wide | Weaker — less surgical than B |
| **F.** No change — ambiguity is legitimate | N/A | None | None | None | None | Rejected by Section K's own findings — this is not legitimate ambiguity |

## M. Recommended Architecture (diagnosis-level; not implemented)

The evidence in Sections B, C, and K points to **two narrow, additive, low-risk,
data-and-gate-scoped corrections** — not a threshold change, not a weight change,
not a new ontology:

1. **Complete `asset_id`'s (and, by the same audit, other identifier concepts')
   `compatible_dataset_roles` registry entry** to include the specific operational
   `DatasetRole` values a legitimate identifier commonly co-occurs with beyond the
   four generic ones already listed (`work_order`, `schedule`, `labor`, `invoice`,
   `contract`, `measurement`, `inventory`, as applicable per concept) — pure
   registry data, matching the exact "add data, not code" pattern already used for
   PR #97's `dispatch_id` alias fix. This is Option B/E's registry-completeness
   half.
2. **Reconsider `is_candidate_identifier`'s dual role** as both a datatype signal
   and a cross-dataset-corroboration eligibility gate (Section B.1/E) — the
   generalizable question is whether cross-dataset/datatype evidence for a
   *repeated, FK-shaped* identifier should be reachable through a *different*,
   corroboration-aware path (matching Option C/E.4's own precedent) rather than
   the same single uniqueness-ratio boolean a master-key column uses. Section J's
   safety constraints (categorical pseudo-IDs, mixed populations) mean any such
   path must still require genuine corroborating evidence (e.g. verified
   cross-dataset value overlap, or role compatibility once #1 lands) — never a
   blanket "identifier-shaped name → treat as unique-enough."

**Both are additive, generic, and match patterns already proven in this codebase**
(#1 mirrors PR #97 exactly; #2 mirrors E.4's already-validated
corroboration-gated `ACCEPTED_WITH_FLAG` upgrade, Option C). Neither requires
touching `resolve_effective_decision`'s thresholds, `ACCEPTED_WITH_FLAG`'s
definition, or entity-identity confidence's own formula.

## N. Expected Wave 1 Impact (estimate only, not measured — no code changed)

| | FieldMaintenance | Rental |
|---|---|---|
| XDOM-A (needs `entity_identity.ASSET ≥ 0.70`) | If #1 lands, `work_orders.csv`'s `asset_id` gains role compatibility (0.80→0.95, AUTO_ACCEPTED) — `work_orders.csv` would then contribute an `EntityObservation`, likely raising `entity_identity_confidence` above 0.70 via genuine two-dataset corroboration (0.65+0.085=0.735) | Same mechanism — `dispatch.csv`/`contracts.csv`/`maintenance.csv`/`fuel.csv` all currently miss role compatibility for the same reason; #1 could lift several of them past 0.70 combined |
| XDOM-B | Not directly gated on `entity_identity.ASSET` (its own contract needs `operational_event`, already resolved by Fix #3) — no expected change from this specific fix | Same — no expected direct effect |
| MAINT-001 | Requires `asset_id` + `failure_code` + `downtime_hours` + `repair_cost` as raw columns regardless (V.2B) — unaffected by semantic confidence at all, since it still never reaches domain gate | Same, unaffected |
| Future capabilities | Any future rule requiring `entity_identity.ASSET` (or any concept whose registry role-list is similarly incomplete) would benefit generically — this is the actual reusability case for #1 | Same |
| Unrelated concepts whose acceptance could change | Any identifier concept (not just `asset_id`) whose registry `compatible_dataset_roles` list is similarly incomplete relative to the 14-value `DatasetRole` enum — **not audited this pass**; a real fix would need the same completeness check applied to every registered identifier concept, not `asset_id` alone, to stay generic per the mission's own instruction |

This is an estimate grounded in the exact mechanism (Section H), not a guess — but
it is explicitly unmeasured, since no code was changed this pass.

---

## Final Determination

**NEXT-2 ROOT CAUSE CONFIRMED — READY FOR FIX #4**

Both contributing mechanisms are mechanically, exactly identified and reproduced
(Section B), generalize across both simulation families without any
family-specific explanation needed (Section C), and map to two narrow, additive,
low-regression-risk remediation options that reuse patterns already proven
elsewhere in this codebase (Section L/M) — no further diagnosis is required before
scoping Fix #4.
