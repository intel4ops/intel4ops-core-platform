# P3.xxV.2B — Systemic Failure-Chain Diagnosis Report

**Scope: diagnosis only.** No production code was modified during this milestone. All
findings below trace either live, post-PR#97 production behavior (via the deployed
API against the same frozen Wave 1 corpus) or direct reading of the actual rule
implementations in the repository — nothing here is inferred from naming similarity
alone.

---

## A. Current Production Baseline

Main @ `8ecceac3d86124e84e064063747f6b3d44cc1e6f` (PR #97 merged). No code changed
since. This diagnosis reused the 10 fresh reruns created for the Fix #1 report
(`docs/p3xxv2a-wave1-remediation-fix1-report.md`) as its live evidence base, plus
direct inspection of `app/services/cross_domain_intelligence_service.py`,
`app/rules/maintenance_rules.py`, `app/semantic/review.py`,
`app/entities/entity_deduplication.py`, and `app/services/analysis_case_orchestration_service.py`.

## B. 10-Case Failure-Chain Matrix (condensed)

| Sim | CONNECT | TRUST | SEMANTICS | ENTITIES | CAPABILITY (XDOM-A / XDOM-B) | EXECUTION | EARLIEST FAILURE LAYER | PRIMARY ROOT CAUSE |
|---|---|---|---|---|---|---|---|---|
| FIELDMAINT-001 | ok | completed_with_warnings | asset_id AUTO_ACCEPTED (assets.csv); no `maintenance`-domain evidence anywhere | ASSET only, single-dataset-capped | BLOCKED / READY | XDOM-B attempted, 0 candidates | **SEMANTIC/DOMAIN** (XDOM-A path); **MODEL EXECUTION** (XDOM-B path) | domain signature never sees `maintenance`; XDOM-B's `status=="completed"` literal never matches `work_orders.status="CLOSED"` |
| FIELDMAINT-002 | ok | completed_with_warnings | same pattern | same | BLOCKED / READY | XDOM-B attempted, 0 candidates | same | same |
| FIELDMAINT-005 | ok | **failed** (all domains) | same pattern | same | BLOCKED / BLOCKED | neither attempted | **TRUST** | trust assessment creation fails case-wide, not domain-specific (Section F) |
| FIELDMAINT-007 | ok | completed_with_warnings | same pattern | same | BLOCKED / READY | XDOM-B attempted, 0 candidates | same as 001/002 | same |
| RENTAL-001 | ok | completed_with_warnings | `dispatch_id`→operational_event_id via alias table only; concept-generator UNRESOLVED; asset_id ACCEPTED_WITH_FLAG in 4/5 files | ASSET only (single-dataset, 0.65, below 0.70 threshold); 0 OPERATIONAL_EVENT | PARTIAL / READY | XDOM-B attempted, 0 candidates | **MODEL EXECUTION** (XDOM-B); **ENTITY FORMATION** (XDOM-A) | `dispatch.csv` has no status column at all → Stage-0 filter kills all candidates; ASSET identity confidence capped by AUTO_ACCEPTED-only observation gate |
| RENTAL-003 | ok | completed_with_warnings | same | same | PARTIAL / READY | same | same | same |
| RENTAL-011 | ok | completed_with_warnings | same | same | PARTIAL / READY | same | same | same |
| RENTAL-012 | ok | completed_with_warnings | same | same | PARTIAL / READY | same | same | same |
| RENTAL-015 | ok | completed_with_warnings | same | same | PARTIAL / READY | same | same | same |
| RENTAL-018 | ok | completed_with_warnings | same | same | PARTIAL / READY | same | same | same |

## C. Semantic Interpretation Diagnosis

Fields checked directly via `GET .../semantic?run_id=` on live reruns:

| Field | Dataset | Canonical candidate | Confidence | Status |
|---|---|---|---|---|
| `asset_id` | assets.csv (Rental) | asset_id | 0.95 | AUTO_ACCEPTED |
| `asset_id` | dispatch.csv (Rental) | asset_id | 0.70 | ACCEPTED_WITH_FLAG |
| `asset_id` | contracts.csv (Rental) | asset_id | 0.80 | ACCEPTED_WITH_FLAG |
| `asset_id` | maintenance.csv (Rental) | asset_id | 0.70 | ACCEPTED_WITH_FLAG |
| `asset_id` | fuel.csv (Rental) | asset_id | 0.85 | ACCEPTED_WITH_FLAG |
| `dispatch_id` | dispatch.csv (Rental) | **null** | **0** | **UNRESOLVED** — `"no candidate concept was proposed by any generator"` |
| `work_order_id` | work_orders.csv (FieldMaintenance) | operational_event_id (via alias) | — | resolved via the same alias path as `dispatch_id`'s domain-detection use, not independently checked against the concept generator in this pass |

**Pattern:** the semantic concept generator correctly classifies `asset_id` everywhere
it appears — it is not broken or inconsistent — but scores it lower (0.70–0.85,
`ACCEPTED_WITH_FLAG`) in every file where `asset_id` is a repeated foreign key rather
than the dataset's own unique row key (only `assets.csv` reaches `AUTO_ACCEPTED`).
`dispatch_id` is a completely different failure: the generator proposes **no
candidate at all**, at any confidence — a vocabulary gap, not a confidence-calibration
one.

## D. Semantic Alias vs. Concept-Generator Consistency

Two structurally different systems both feed the pipeline and were confirmed, by
direct code inspection, to disagree on `dispatch_id`:

1. **`app/domain_registry.py`'s `CANONICAL_FIELD_ALIASES`** (the table PR #97 edited)
   — a static, config-driven lookup consumed by `canonicalize_field()`, which in turn
   feeds domain detection (`domain_detection_service.py`), field-mapping/column-rename
   (`analysis_case_mapping_service.py`), and the legacy `entity_resolution_service.py`'s
   `ENTITY_ID_FIELDS` map. `dispatch_id` **is** recognized here (as of PR #97) →
   `domain: operations`, basis `["asset_id","dispatch_id"]`, confirmed live.
2. **The P3.xxE.1 semantic concept generator** (`app/semantic/candidate_generator.py`
   + `confidence_engine.py`, exposed via `GET .../semantic`) — an independent
   evidence-driven system with its own candidate proposals, entirely unaware of
   `domain_registry.py`'s alias table. `dispatch_id` **is not** recognized here →
   `status: unresolved`, `confidence: 0`.

**SEMANTIC CONSISTENCY GAPS:**
- `dispatch_id` → System 1 recognizes it, System 2 does not. Confirmed by direct API
  read, not inferred.
- The two systems have **no mechanism keeping their vocabularies in sync** — nothing
  in the codebase asserts or tests that a concept recognized by one is recognized by
  the other. `app/domain_registry.py`'s own module docstring documents its alias table
  as the industry-vocabulary extension point ("adding a new industry's vocabulary is a
  data change here"), but the concept generator has a **separate**, independently
  maintained vocabulary that PR #97 never touched and that has no equivalent
  "add here" extension point identified in this pass.
- **Downstream consequence, confirmed empirically (Section E):** because
  `resolve_effective_decision()` (`app/semantic/review.py:220`) collapses
  `ACCEPTED_WITH_FLAG` into the **same** "no effective concept" bucket as
  `REVIEW_REQUIRED` (`effective_concept=None` either way), only System 2's
  `AUTO_ACCEPTED`-tier decisions ever produce entity-formation evidence — System 1's
  alias-driven recognition has zero effect on entity formation, no matter how correct
  it is. This is why `dispatch_id` produces domain/mapping/legacy-entity evidence
  (System 1) but **zero** `OPERATIONAL_EVENT` canonical entities (System 2-gated) —
  not a contradiction, but two genuinely separate evidence paths with different
  consumers.

Not fixed in this pass, per instruction.

## E. Entity Formation Diagnosis

Traced the exact mechanism, by reading `app/semantic/review.py` and
`app/entities/entity_deduplication.py` together, for why a recognized semantic
concept can still fail to produce a well-corroborated canonical entity:

```
resolve_effective_decision():
  HUMAN_CONFIRMED / HUMAN_CORRECTED   → effective_concept = <concept>
  machine AUTO_ACCEPTED               → effective_concept = <concept>
  machine ACCEPTED_WITH_FLAG          → effective_concept = None  (same as REVIEW_REQUIRED)
  machine REVIEW_REQUIRED             → effective_concept = None
  machine UNRESOLVED                  → effective_concept = None
```

Only rows where `effective_concept` is non-null become `EntityObservation`s feeding
`deduplicate()`. `deduplicate()`'s own confidence model
(`app/entities/entity_deduplication.py:26-47`):

```
entity_identity_confidence = min(TIER_BASE + TIER_STEP * (distinct_datasets - 1), TIER_CAP)
EXACT tier: base=0.65, step=0.085, cap=0.99
```

**ASSET, Rental (confirmed live, RENTAL-001):** `asset_id` is present with a correct
concept classification in 5 files, but only `assets.csv` reaches `AUTO_ACCEPTED`
(0.95). The other 4 (`dispatch.csv`, `contracts.csv`, `maintenance.csv`, `fuel.csv`,
all `ACCEPTED_WITH_FLAG`, 0.70–0.85) contribute **zero** observations to the E.3
entity pipeline, because their `effective_concept` is `None`. Result:
`distinct_datasets = 1` → `entity_identity_confidence = 0.65 + 0.085*(1-1) = 0.65`,
observed identically across all 6 Rental reruns — below XDOM-A's declared
`minimum_entity_identity_confidence = 0.70` (`app/intelligence_packs/registry.py:163`).

**Why this happens (root, not just symptom):** the concept generator legitimately
scores a repeated foreign-key column lower than a unique primary-key column — that
distinction is semantically real (a FK reference is weaker identity evidence, row for
row, than a PK's own uniqueness). The problem is not that this distinction exists; it
is that `resolve_effective_decision()` uses a **binary** cutoff (`AUTO_ACCEPTED` or
nothing) for entity-formation eligibility rather than letting `ACCEPTED_WITH_FLAG`
observations contribute as **weaker, still-real** evidence — which is exactly what
`entity_identity_confidence`'s own corroboration-step design already anticipates
(more datasets → higher confidence) but never gets to exercise, because those
datasets' observations never enter the pool at all.

**OPERATIONAL_EVENT, Rental:** zero canonical entities on every case (Section D) —
the concept is never proposed at all, so this is a vocabulary gap, not a
confidence-threshold gap; a different mechanism than ASSET's.

**WORK_ORDER:** not separately observed as a canonical entity type in the 6 Rental
cases (`entity_type_counts` showed `ASSET` only in every case) — Rental's schema
uses `contract_id`/`dispatch_id`, no column canonicalizes to `work_order_id`; not
investigated further here as it wasn't load-bearing for either governed capability's
blocking reason.

**This same mechanism (repeated-FK identifier structurally capped below
`AUTO_ACCEPTED`) generalizes beyond Rental** — it will reproduce for any identifier
that is a master-table primary key in exactly one dataset and a foreign-key reference
everywhere else, which is the ordinary shape of almost every real business identifier.
This is the single most reusable finding in this diagnosis.

## F. Trust Diagnosis — FIELDMAINT-005

Confirmed live: FIELDMAINT-005's `maintenance_events.csv`, `field_tickets.csv`,
`labor_entries.csv`, `invoices.csv`, and `payments.csv` **all** show
`trust_status: "failed"`. The sibling cases (001/002/007) show
`trust_status: "completed_with_warnings"` on the equivalent datasets — never
`"failed"`.

Traced the exact code path (`analysis_case_orchestration_service.py:1038-1090`):
`case_dataset.trust_status = "failed"` is set **only** when
`trust_assessment_service.create_and_execute()` raises a bare `ValueError` — a
structurally different, harder failure than the normal
`assessment.status = COMPLETED_WITH_WARNINGS` path (which is what a rule that
executed and failed its own check produces). A `ValueError` here is most plausibly
`NoApplicableTrustRulesError`, raised when `TrustRuleRegistry.applicable()` finds no
matching rule for the given `(dataset_type, rule_configurations)` pair — though the
registered rules use a wildcard `supported_dataset_types = {"*"}`, so this exact
trigger could not be fully confirmed without a working endpoint to inspect the failed
assessment directly (`GET .../latest-trust-assessment` only returns
`COMPLETED`/`COMPLETED_WITH_WARNINGS` assessments by design, and no
list-all-assessments endpoint exists on the dataset). This is flagged honestly as a
diagnostic limit of the available read surface, not resolved by inference.

**What is conclusively established:** the failure is **case-wide, not domain-specific**
— it hit `operations` and `revenue` domain datasets identically within the same case,
while an identical `_DOMAIN_TRUST_RULES["operations"]` configuration succeeds cleanly
on 3 sibling cases. This rules out a domain-classification issue (all 4 cases detect
the same domains) and a threshold/calibration issue (calibration produces
`COMPLETED_WITH_WARNINGS`, not this harder `ValueError`-driven `"failed"` state).
FIELDMAINT-005 is also Wave 1's largest single dataset (387 expected findings vs.
63–114 for its siblings) — a scale correlation, not yet a proven causal mechanism.

**FIELDMAINT-005 TRUST ROOT CAUSE: `TRUST_IMPLEMENTATION_DEFECT`** (tentative,
pending engineering log/DB access) — a case-wide `ValueError` at assessment-creation
time, most likely `NoApplicableTrustRulesError` triggered by something scale- or
shape-related in this specific case's payload, rather than a legitimate,
graduated data-quality block or a calibration issue. Not `LEGITIMATE_BLOCK` (the
failure mode is a hard exception, not a threshold miss) and not
`TRUST_CALIBRATION_ISSUE` (calibration issues manifest as `COMPLETED_WITH_WARNINGS`,
which is exactly what the sibling cases show).

## G. Governed Activation Diagnosis

Re-confirmed across all 10 post-PR#97 reruns (raw `activation-decisions` records,
Fix #1 report Section E): every `agree: false` case (XDOM-A on all 6 Rental sims) is
explained by a **separate, correctly-functioning** confidence gate
(`below_confidence_threshold: ["entity_identity.ASSET"]`) applied on top of
otherwise-satisfied presence requirements (`governed_missing_summary: []`) — the
governed evaluator is doing exactly what it's supposed to: being stricter than the
legacy presence-only check. Every `agree: true` case matches legacy exactly. **No
incorrect activation decision was found anywhere in the 10-case matrix.** Every
BLOCKED/PARTIAL outcome traces to genuinely incomplete or unresolved upstream
evidence (Sections C–F), never to a defect in the P3.xxE.5 evaluator itself. This
confirms Fix #1's own Section L finding and extends it across the full diagnosis.

## H. XDOM-B Verified Contract (read directly from `cross_domain_intelligence_service.py:132-240`)

- **Business phenomenon declared:** a completed operational event with no linked
  revenue record — "activity happened, nothing was ever billed for it."
- **Required inputs:** an `operations`-domain dataset with
  `operational_event_status` present, and a `revenue`-domain dataset.
- **Precondition (Stage 0):** `operational_event_status` column must exist, **and**
  at least one row's value must lowercase-equal exactly `"completed"`. No other
  status value passes. If either condition fails, the function returns `[]`
  immediately — no candidates, no match attempt, no exclusion finding.
- **Matching keys:** primary — exact `operational_event_id` set-membership against
  the revenue dataset's `operational_event_id` column. Fallback — `(route_id,
  event_date)` tuple membership.
- **Temporal logic:** none beyond the fallback key's same-date requirement; no
  "before/after" or "overdue by N days" logic anywhere in the function.
- **Revenue/economic logic:** **binary presence only** — the rule checks whether a
  revenue row with the matching key exists at all. It does **not** compare amounts,
  does **not** check whether an existing matched revenue row's amount is complete,
  and has no concept of a partial or delayed match.
- **Candidate-building logic:** `completed[~completed[key].isin(revenue_keys)]` — a
  single vectorized anti-join; no per-record judgment beyond key presence.
- **Filters:** the status-literal filter (Stage 0) and the key-presence anti-join
  (Stage 2) are the only two filters. No confidence threshold, no severity gating,
  inside this function.
- **Evidence contract:** publishes `affected_record_count`, a title/summary, and
  `limitations: ["Observed activity/revenue-presence gap only -- no amount
  estimated."]` — the rule's own code is explicit that it never estimates value,
  consistent with the "binary presence only" finding above.
- **Finding-generation condition:** at least one `unmatched` row after the anti-join.
- **Exclusions:** if no shared key exists between the two datasets **at all**, the
  rule deliberately publishes a **different**, low-severity
  `XDOM-DATA-LINKAGE-ISSUE` finding instead — explicitly distinguishing "couldn't
  reliably link the datasets" from "linked and found a gap." This exclusion path was
  never reached in Wave 1 because Stage 0 (status filter) always eliminates every
  candidate first.
- **Intended scope, as declared by the code's own docstring:** "Distinguishes a
  genuine 'matched, no revenue' finding from a 'could not be reliably matched'
  data-linkage issue" — i.e., its scope is explicitly an **existence** gap, not an
  amount, timing, or completeness gap.

**No broadening proposed. This is the contract as it exists today.**

## I. XDOM-B Candidate Elimination Traces (read-only, live-data-grounded)

| Simulation | Source op. records | operational_event_status present? | Rows == "completed" | Candidates after Stage 0 | Elimination reason |
|---|---|---|---|---|---|
| FIELDMAINT-001 | `work_orders.csv`, 227 rows | Yes (`status` column) | **0** (all 227 = `"CLOSED"`) | **0** | literal string mismatch: rule requires `"completed"`, data uses `"CLOSED"` |
| FIELDMAINT-002 | `work_orders.csv`, 254 rows | Yes | **0** (all `"CLOSED"`) | **0** | same |
| RENTAL-001 | `dispatch.csv`, 55 rows / `field_tickets.csv`, 55 rows | **No** — neither file has any status-aliased column | n/a | **0** | `"operational_event_status" not in operations_df.columns` — the very first line of the function |
| RENTAL-003 | `dispatch.csv`, 29 rows | **No** | n/a | **0** | same |

In all four representative cases, candidates fall to **zero at Stage 0**, before the
match-key logic (Stage 2) is ever reached. The match-key/temporal stages this section
asked to trace never execute on this corpus — there is nothing to trace past Stage 0.
This is a single, precisely located elimination point, not a diffuse or
hard-to-isolate one.

## J. Capability-Scoped Truth Mapping

Built strictly from the registered contracts' actual mechanics (Sections H and the
equivalent read of `app/rules/maintenance_rules.py:10-14` for MAINT-001 — required
columns `{asset_id, failure_code, downtime_hours, repair_cost}`, grouped by
`(asset_id, failure_code)`, ≥3 occurrences), **not** from scenario-name similarity.
Two concrete truth records were read end-to-end (Section L) specifically to test
whether a name-similar scenario actually satisfies a capability's mechanical
contract — both did not, which drove the classifications below down from an initial
name-based guess of "implemented" to "partially implemented."

**FieldMaintenance (629 findings):**

| scenario_id | count | mapped capability | status | reason |
|---|---|---|---|---|
| repeat_repair | 76 | MAINT-001 | **PARTIALLY_IMPLEMENTED** | Truth is a temporal-proximity, 2-occurrence, `opened_date`/`closed_date`-based pattern (confirmed via LK-2 trace, Section L); MAINT-001 is a categorical `(asset_id, failure_code)` grouping requiring ≥3 occurrences and `downtime_hours`/`repair_cost` columns that don't exist in this data at all. Same general phenomenon family, different mechanism entirely. |
| unbilled_parts | 113 | XDOM-B | **PARTIALLY_IMPLEMENTED** | Truth is an amount-variance-on-an-existing-linked-invoice pattern (confirmed via LK-3 trace); XDOM-B only detects existence gaps, never amount gaps. |
| unbilled_labor_hours | 32 | XDOM-B | PARTIALLY_IMPLEMENTED | same reasoning as unbilled_parts (not individually traced, same structural family) |
| missing_field_ticket_billing | 7 | XDOM-B | PARTIALLY_IMPLEMENTED | same |
| overtime_leakage | 301 | none | **OUT_OF_SCOPE_NOT_IMPLEMENTED** | a labor-cost/overtime-authorization phenomenon; no registered capability addresses labor cost at all |
| contract_rate_mismatch | 26 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | a contracted-vs-actual-rate comparison; no registered capability compares rates |
| preventive_maintenance_missed | 51 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | scheduled-vs-actual maintenance adherence; not covered by any registered rule |
| technician_idle_time | 23 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | labor utilization; not covered |

**Rental (159 findings):**

| scenario_id | count | mapped capability | status | reason |
|---|---|---|---|---|
| excessive_asset_downtime | 44 | XDOM-A (tentative) | **AMBIGUOUS** | XDOM-A's contract requires a maintenance-event downtime window overlapping a *separate* operational event record; whether the simulator's "excessive downtime" injection is generated that way, or as a simple duration threshold, could not be determined from the truth schema alone in this pass |
| delayed_invoicing | 21 | XDOM-B | **PARTIALLY_IMPLEMENTED** | a timing/lateness phenomenon; XDOM-B has no temporal-lateness logic, existence-only |
| late_return_leakage | 12 | XDOM-B | **PARTIALLY_IMPLEMENTED** | confirmed via LK-1 trace (Section L): revenue record exists for the base contract, absent only for the overage portion — XDOM-B's existence check would see this as "matched" |
| unbilled_rental_days | 2 | XDOM-B | PARTIALLY_IMPLEMENTED | same amount-based reasoning |
| late_maintenance | 26 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | schedule adherence; not covered |
| rental_rate_mismatch | 22 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | rate comparison; not covered |
| fuel_discrepancy | 7 | none | OUT_OF_SCOPE_NOT_IMPLEMENTED | fuel cost/volume reconciliation; not covered |
| (unlabeled) | 25 | — | **AMBIGUOUS** | no `scenario_id` recorded in the truth file at all (Section Q) |

## K. Real Denominators

| | Count | Value |
|---|---|---|
| **FULL-TRUTH** (entire wave) | 788 | $2,285,738.56 |
| **IMPLEMENTED-CAPABILITY SCOPE** (`PARTIALLY_IMPLEMENTED`, i.e. a registered capability's declared business phenomenon at least partially overlaps) | 76+113+32+7 (FM) + 21+12+2 (Rental) = **263** | $ not separately summed this pass — see note |
| **OUT-OF-SCOPE PRODUCT COVERAGE GAP** | 301+26+51+23 (FM) + 26+22+7 (Rental) = **456** | not separately summed this pass |
| **AMBIGUOUS** | 44 + 25 (Rental) = **69** | not separately summed this pass |

Note: none of the 263 `PARTIALLY_IMPLEMENTED` items would actually have been detected
even with a perfectly-fixed activation/entity/trust chain, because the mechanical
contract mismatch (existence-only vs. amount/timing-based; categorical-grouping vs.
temporal-proximity) is independent of and downstream of every fix examined in this
report. **Zero items in this wave are cleanly `IN_SCOPE_IMPLEMENTED`** once judged
against actual contract mechanics rather than category-name similarity — this is
itself one of this report's central findings, not an oversight.

## L. Three End-to-End Missed-Finding Traces

**1. FieldMaintenance — LK-3, `unbilled_parts`, FIELDMAINT-001, $633.43**
`SOURCE EVIDENCE`: `WO-000016` on `work_orders.csv` (status=`CLOSED`), parts
`PRT-000022`/`PRT-000023` on `parts_usage.csv`, invoice `INV-000016` on
`invoices.csv` — root cause per truth: "parts consumed on the work order but not
included on the customer invoice" (i.e., invoice **exists**, amount is short).
→ `SEMANTIC`: `work_order_id` resolves to `operational_event_id` correctly (this
data doesn't depend on `dispatch_id` or the semantic-generator gap at all).
→ `ENTITY`: not the blocking layer here.
→ `READINESS`: XDOM-B READY on this case (confirmed, Fix #1 report).
→ `MODEL EXECUTION`: `run_lost_activity_to_revenue_gap` — Stage 0 requires
`operational_event_status == "completed"`; `work_orders.status` is `"CLOSED"` for
all 227 rows including WO-000016 → **zero candidates, function returns before
reaching WO-000016 at all.**
→ `WHY NO FINDING`: even setting the status-literal issue aside, this specific
record would not have been produced as a finding regardless — `INV-000016` exists
and would match on `operational_event_id`, so the anti-join would classify it
`matched`, not `unmatched`. **Two independent, stacked reasons**, both inside Model
Execution: (a) precondition filter too narrow, (b) contract doesn't check amount.
**Earliest failed layer: MODEL EXECUTION.**

**2. Rental — LK-1, `late_return_leakage`, RENTAL-011, $8,400**
`SOURCE EVIDENCE`: `dispatch.csv` row for asset with `contract_end_date=2026-03-23`,
`actual_return_date=2026-03-29` (6-day overage); `CNT-000001`/`DSP-000001` in
`affected_records`; root cause: "no additional rental days were ever billed for the
overage."
→ `SEMANTIC`: `dispatch_id` UNRESOLVED at the concept-generator layer (Section D);
domain-detection/mapping layer (System 1) does correctly see it as `operational_event_id`.
→ `ENTITY`: zero `OPERATIONAL_EVENT` canonical entities case-wide (Section E) — but
this does not block XDOM-B, which reads canonical DataFrames directly, not the E.3
entity graph.
→ `READINESS`: XDOM-B READY (confirmed).
→ `MODEL EXECUTION`: `dispatch.csv` has no `status`-aliased column at all →
`"operational_event_status" not in operations_df.columns` → immediate `return []`.
→ `WHY NO FINDING`: same stacked pattern as trace 1 — even if the status-literal
issue were fixed, this dispatch almost certainly has a **base** invoice/contract
revenue record already linked by `contract_id`/`dispatch_id`; only the **overage
portion** was never billed, which is an amount/scope question XDOM-B's binary
existence check cannot express.
**Earliest failed layer: MODEL EXECUTION.**

**3. FieldMaintenance — LK-2, `repeat_repair`, FIELDMAINT-002, $2,448**
`SOURCE EVIDENCE`: asset `AST-000002`, work orders `WO-000005` (closed) and
`WO-000006` (opened 7 days later) — root cause: "same asset required a repeat repair
shortly after a prior repair closed."
→ `SEMANTIC`: `maintenance_events.csv` never produces `domain: maintenance` (it
resolves to `operations`, Wave 1 Section H) — this is the layer this trace actually
fails at, upstream of everything else.
→ `ENTITY`: not reached.
→ `READINESS`: MAINT-001 has no observable governed-readiness record at all in this
codebase's `activation-decisions` API (it isn't in the migrated/governed rollout
list) — meaning it either runs ungoverned whenever the orchestration-level domain
gate permits it, or doesn't run at all; since the domain gate never resolves to
`maintenance` for this dataset, MAINT-001 is never invoked, confirmed by the absence
of any MAINT-001 finding or trace across all 10 reruns.
→ `MODEL EXECUTION`: never reached.
→ `WHY NO FINDING`: **even if it were reached**, `detect_repeated_asset_failures`
requires `failure_code` and `downtime_hours`/`repair_cost` columns that do not exist
anywhere in this simulation's data (Section J), and requires ≥3 occurrences grouped
by `(asset_id, failure_code)` — this truth record is a 2-occurrence,
temporal-proximity pattern using `opened_date`/`closed_date`, a different algorithm
entirely.
**Earliest failed layer: SEMANTIC INTERPRETATION / DOMAIN CLASSIFICATION** (never
reaches Model Execution at all) — the only one of the three traces where the model
never receives the data in the first place, rather than receiving it and rejecting it.

## M. Systemic Defect Clusters

| cluster_id | name | layer | affected sims | frequency | severity | truth items affected | value impact | downstream effects | reusable fix concept | regression risk |
|---|---|---|---|---|---|---|---|---|---|---|
| DC-1 | SEMANTIC_GENERATOR_INCONSISTENT | Semantic | 6/6 Rental | 100% of Rental | HIGH | indirectly, all Rental | indirect | blocks OPERATIONAL_EVENT entity formation | give the concept generator the same alias-driven fallback the domain_registry table already has, or add `dispatch_id` (and equivalents) to its own vocabulary | LOW — additive vocabulary only |
| DC-2 | ENTITY_IDENTITY_TOO_CONSERVATIVE | Entity formation | 6/6 Rental (ASSET); generalizes to any FK-heavy identifier | 100% of Rental | HIGH | indirectly, all Rental | indirect | caps `entity_identity_confidence` at single-dataset base regardless of real cross-file corroboration | let `ACCEPTED_WITH_FLAG` observations contribute at a discounted weight to identity corroboration, instead of `effective_concept=None` | MEDIUM — touches a shared confidence formula used by every entity type |
| DC-3 | TRUST_SCALE_SENSITIVITY / TRUST_IMPLEMENTATION_DEFECT | Trust | 1/10 (FIELDMAINT-005) | 10% observed, cause unconfirmed | MEDIUM | 387 findings blocked from even attempting execution | $ unknown (largest single case) | blocks both XDOM-A and XDOM-B entirely for this case | needs engineering log access to pin the exact `ValueError`; not diagnosable further from this read surface | unknown until root cause confirmed |
| DC-4 | DOMAIN_CLASSIFICATION_GAP | Semantic/domain | 4/4 FieldMaintenance | 100% of FieldMaintenance | HIGH | 629 (all FieldMaintenance findings gated behind this for XDOM-A/MAINT-001) | $413,414.73 | blocks XDOM-A and MAINT-001 entirely on FieldMaintenance | extend the `maintenance` domain signature's field vocabulary (e.g. recognize `scheduled_date`/`completed_date` pairs as duration evidence) — a bigger, cross-layer change than DC-1/DC-2 | MEDIUM-HIGH — touches domain-detection logic, not just a data table |
| DC-5 | MODEL_MATCHING_DEFECT (status-literal) | Model execution (XDOM-B) | 9/10 (every case where XDOM-B reaches READY) | 100% of READY cases | **CRITICAL LEVERAGE** (highest observed reach) | up to 263 `PARTIALLY_IMPLEMENTED` items structurally can't be reached while this holds | up to full $ value of those items | single largest lever on any future recall improvement | broaden the "completed" precondition to a config-driven status-vocabulary set, or make it evidence-based rather than a literal string | LOW-MEDIUM — localized to one function's Stage-0 filter |
| DC-6 | MODEL_MATCHING_DEFECT (existence-vs-amount contract) | Model execution (XDOM-B) | same 9/10, wherever Stage 0 would otherwise pass | would affect ~152 FM + ~35 Rental items even after DC-5 is fixed | HIGH | ~187 | large fraction of the $263-item scope | XDOM-B structurally cannot detect amount/timing leakage regardless of DC-5 | requires a new or extended contract (amount-variance detection), not a bug fix — likely Type C/coverage territory, not a pure implementation fix | scope decision, not a quick patch |
| DC-7 | MODEL_COVERAGE_GAP | Product/capability registry | 10/10 | 456/788 truth items (58%) have no capability at all | HIGH | 456 | $ majority of wave (needs precise sum) | no amount of upstream fixing changes this | requires new capabilities, explicitly out of scope this milestone | N/A |
| DC-8 | TRUTH_AUTHORING_GAP | Validation/Simulation Factory | 6/6 Rental | 159/159 Rental truth records lack `expected_detection_family`; 25/159 lack `scenario_id` | MEDIUM (reporting fidelity, not production) | 159 (+25) | reporting-only | degrades capability-scoped reporting precision for Rental specifically | ask Simulation Factory to backfill these fields | none — validation-side only |

## N. Architectural Defects (Type A)

- **DC-1** (semantic concept-generator vocabulary gap, independent of the alias
  table) — a reusable upstream capability (the concept generator) is insufficient
  for a legitimate, common identifier naming pattern.
- **DC-2** (entity-formation's binary `AUTO_ACCEPTED` cutoff) — a reusable upstream
  capability (cross-dataset identity corroboration) structurally cannot use evidence
  it has already correctly gathered.

## O. Implementation Defects (Type B)

- **DC-5** (XDOM-B's `"completed"` literal-string precondition) — the capability
  received valid, correctly-domain-detected, correctly-mapped evidence and rejected
  it due to an overly narrow, hardcoded status-vocabulary assumption inside its own
  declared contract.
- FieldMaintenance's `work_orders.status` uses `"CLOSED"`; Rental's `dispatch.csv`
  has no status field at all — two different data shapes, one shared implementation
  defect.

## P. Product Coverage Gaps (Type C)

- **DC-6** (existence-only vs. amount/timing detection) — arguably borderline
  between B and C: XDOM-B's contract is internally consistent and correctly
  implemented for what it declares (existence-only), so the gap is that **no
  capability of any kind** covers amount-variance or timing-lateness leakage, which
  is a coverage gap, not a bug in an existing rule.
- **DC-7** (456/788, 58% of the wave, has zero mapped capability at all) — the
  dominant, largest-value gap in absolute terms, entirely orthogonal to every fix
  examined so far.

## Q. Validation / Simulation Factory Defects (Type D)

- **DC-8**: Rental's `leakage_truth` records never populate `expected_detection_family`
  (0/159) and 25/159 never populate `scenario_id` at all — confirmed by direct
  inspection of the raw truth JSON, not an adapter bug (the field is simply absent
  from the source file). This affects reporting/scoping precision only; it does not
  change the wave's 0% recall result, since TP=0 regardless.

## R. Intel4Ops Maturity Map

| Layer | Rating | Evidence |
|---|---|---|
| CONNECT | **STRONG** | 0 infrastructure failures across 20+ case creations/uploads in this and the prior session; multipart artifact ingestion worked flawlessly at every scale (10 rows to 350+ entities) |
| TRUST | **LIMITED** | Works correctly on 9/10 cases (graduated `COMPLETED_WITH_WARNINGS`), but exhibits a hard, unexplained `FAILED` state on the one largest/densest case — a robustness gap under scale, not yet root-caused |
| SEMANTIC UNDERSTANDING | **BOTTLENECK** | Two independently-maintained vocabularies (alias table vs. concept generator) that can silently disagree; the concept generator's binary accept/no-accept cutoff discards legitimately useful ACCEPTED_WITH_FLAG evidence entirely |
| ENTITY RESOLUTION | **BOTTLENECK** | Directly downstream of the semantic bottleneck — `entity_identity_confidence` is structurally capped for any FK-shaped identifier, which is the common case, not an edge case |
| RELATIONSHIP DISCOVERY | **NOT YET VALIDATED** | Not exercised as a blocking factor in any of the 10 cases this diagnosis traced; no live evidence gathered this pass |
| PROCESS INTERPRETATION | **NOT YET VALIDATED** | Same — not implicated in any traced failure chain |
| CAPABILITY ACTIVATION (P3.xxE.5 governed gate) | **STRONG** | Zero incorrect activation decisions found across 20 rule-evaluations (2 rules × 10 cases); every divergence from legacy traced to a real, separate, correctly-functioning confidence gate |
| MODEL EXECUTION | **BOTTLENECK** | XDOM-B's precondition filter eliminates 100% of candidates on every case it reaches, before its own match logic ever runs; MAINT-001 has analogous hardcoded-column requirements never satisfied by either real dataset shape |
| MODEL COVERAGE | **LIMITED** | 3 registered capabilities against a real corpus with at least 15 distinct injected leakage patterns; 58% of the wave's truth items map to no capability at all |
| COMMAND | **NOT YET VALIDATED** | Out of scope for this diagnosis — no findings were ever published, so Command had nothing to act on in any of the 10 cases |
| RECOVERY | **NOT YET VALIDATED** | Same — no failure/exception state reached Recovery in this diagnosis |

## S. Dependency-Ordered Remediation Plan

| priority | layer | cluster | why now | expected affected sims | expected downstream unlock | regression risk | validation required after |
|---|---|---|---|---|---|---|---|
| 1 | Model Execution | DC-5 (status-literal) | Highest-leverage, most isolated fix found: unblocks the precondition for 9/10 sims with a single, localized change; does not depend on any other fix in this list | 9/10 | lets XDOM-B's real match logic run on real data for the first time in this wave | LOW — one function, already has a documented exclusion path (`XDOM-DATA-LINKAGE-ISSUE`) for the no-shared-key case | rerun all 10, expect: still likely 0 new TPs (DC-6 still blocks the amount-based majority) but the `XDOM-DATA-LINKAGE-ISSUE`/match-stage should now be reachable and observable for the first time — a genuinely new diagnostic signal, not a pass/fail outcome |
| 2 | Semantic (Entity formation) | DC-2 (ACCEPTED_WITH_FLAG discarded) | Second-highest leverage: unblocks XDOM-A on all 6 Rental cases and is a prerequisite for any future capability that depends on ASSET/other FK-shaped entity identity confidence | 6/10 (Rental) | XDOM-A reaches READY on Rental; likely also improves entity identity confidence for future capabilities generically, not just this wave | MEDIUM — touches a formula shared by every entity type; needs a fixture proving low-quality FK evidence still can't single-handedly fabricate high confidence | full entity-resolution regression suite plus a new fixture for "many ACCEPTED_WITH_FLAG observations, still bounded below AUTO_ACCEPTED's own ceiling" |
| 3 | Semantic (concept generator) | DC-1 (dispatch_id vocabulary gap) | Same general layer as #2, lower isolated urgency since DC-2's fix already lets XDOM-A move on ASSET without touching OPERATIONAL_EVENT; still needed before any future capability that depends on the E.3 canonical `OPERATIONAL_EVENT` entity type specifically | 6/10 (Rental) | populates the E.3 canonical entity graph for Rental's operational events, currently empty | LOW-MEDIUM — additive vocabulary, same class of risk as PR #97 itself | semantic regression suite + confirm `OPERATIONAL_EVENT` entities now appear |
| 4 | Trust | DC-3 (FIELDMAINT-005) | Needs root-causing (engineering log/DB access) before any fix can be designed — sequenced here because it's isolated to 1/10 cases and doesn't block anything else in this list, but should not be indefinitely deferred given it's a hard-failure/robustness question, not a calibration one | 1/10 | unblocks both XDOM-A and XDOM-B activation attempts on FIELDMAINT-005 | unknown until diagnosed | full trust regression suite once a fix is designed |
| 5 | Semantic/domain | DC-4 (FieldMaintenance maintenance-domain gap) | Highest engineering cost in this list (a domain-signature/vocabulary extension for duration-implied-by-date-pair, not a simple alias add); sequenced after the lower-risk items above per "upstream reusable defect before downstream tuning" only where cost is comparable — here cost is materially higher, so it's ranked by leverage-per-unit-risk, not pure layer order | 4/10 (FieldMaintenance) | unblocks XDOM-A and MAINT-001 domain gate on FieldMaintenance | MEDIUM-HIGH | full domain-detection + trust + MAINT-001 regression |
| 6 | Model Execution | DC-6 (existence-vs-amount contract) | Only pursue after 1-5 land and are validated live — this is the item most likely to reveal itself as a genuine new-capability decision (Type C) rather than a bug fix once the upstream noise is cleared | up to 9/10 | the largest concrete recall improvement available within the *existing* 3 capabilities' general subject area | scope decision required first — not a pure implementation task | new fixtures + explicit scope/architecture review before implementation, per instruction 16 |
| — | Model Coverage | DC-7 | **Explicitly deferred** — only after 1-6 establish that the existing pipeline is trustworthy, per instruction | 6/10 (58% of items) | largest absolute value, but correctly gated behind pipeline trust per the mission's own ordering principle | N/A this milestone | N/A this milestone |

## T. Recommended Next Fix

**DC-5 — XDOM-B's `operational_event_status == "completed"` precondition.**

This is the earliest high-leverage reusable defect proven by the dependency-chain
analysis that is *also* fully implementation-scoped (no architecture decision or
scope negotiation required, unlike DC-6/DC-7): it is a single function's
config-driven-status-literal, exactly analogous in shape to PR #97's own alias-table
fix, reaches 9/10 simulations, and is a prerequisite for observing whether DC-6 is
real (the match-key logic has never actually run on this corpus — DC-5 is a
precondition for even measuring DC-6's true scope). Selected over DC-2 (also strong)
because DC-5 has zero cross-cutting risk (touches one function, not a
shared confidence formula used by every future entity type) and produces an
immediately observable, falsifiable result on rerun.

---

## Final Determination

**READY FOR SYSTEMIC REMEDIATION**

Every major finding in this report is evidence-grounded (live API reads against the
frozen corpus, or direct reading of the actual rule/service source code) and
resolves to a specific, bounded layer with a concrete, scoped fix concept. No further
diagnosis is required before beginning DC-5; the remaining open item (FIELDMAINT-005's
exact `ValueError`, DC-3) is isolated to 1/10 cases and does not block starting
remediation on the higher-leverage items.
