# P3.xxV.2H — Systemic Remediation, Fix #5 Report

**Migrate XDOM-A Execution onto Canonical E.3 Entity Evidence**

Scope discipline maintained: only XDOM-A's execution candidate source and its
own readiness aggregation policy were touched. The 0.70 confidence threshold,
`minimum_coverage_ratio`'s global default, the generic evaluator's semantics,
every other pack's registration, XDOM-B, semantic thresholds, and the frozen
truth corpus were all left exactly as they were — confirmed unchanged in
Section M.

---

## A. Legacy/Canonical Entity Reconciliation

| | Legacy (`EntityResolutionService`) | Canonical (E.3) |
|---|---|---|
| Storage | `AnalysisCaseEntityLink` — deleted and fully recreated every run | `CanonicalCaseEntity` + `CanonicalEntityObservation` — new rows per run, never deleted, run-history comparable |
| Matching mechanics | Exact string equality on raw `canonical_frames` column values (post-mapping, pre-semantic), grouped by `(entity_type, subtype, str(raw_value))` | Semantic-gated: only `AUTO_ACCEPTED`/human-governed decisions become `EntityObservation`s (`resolve_effective_decision`), deduplicated by `(entity_type, normalized_value)` |
| "Matched" criterion | `len(dataset_ids) >= 2` → `MATCHED`, else `UNRESOLVED` (binary) | `entity_identity_confidence = 0.65 + 0.085×(distinct_datasets−1)`, capped per tier (continuous, tier-quantized) |
| Datasets considered | Any dataset whose canonical frame has the column, regardless of semantic confidence | Only datasets whose column reached `AUTO_ACCEPTED` (or human-governed) |
| Key casing | Raw (`"A-1"`) | `normalized_key` casefolded (`"a-1"`); `display_label` retains raw casing |
| Current consumers | `resolved_entity_types` (every pack's pre-existing legacy `required_entities` check, `case_capability_index_service.py::_legacy_resolved_entity_types`); was XDOM-A's sole candidate source before this fix | `canonical_entity_identity_confidence_by_type` (readiness); `CanonicalCaseRelationship`/E.4 process interpretation; now XDOM-A's candidate source (this fix) |

### Legacy → Canonical Migration Matrix

| XDOM-A entity dependency | Legacy input | Canonical equivalent | Equivalence status | Gap | Migration requirement |
|---|---|---|---|---|---|
| Stable asset key to iterate | `link.canonical_key` (raw value, `entity_type=="asset"`, `status==MATCHED`) | `EntityCandidate.display_label` (raw value, `entity_type=="ASSET"`, `entity_identity_confidence>=threshold`) | **Equivalent in shape**, different in casing/authority basis | `normalized_key` is casefolded and would silently break the rule's exact-string dataframe filter — confirmed by a real test failure during implementation (Section E) | Use `display_label`, never `normalized_key` |
| Cross-dataset correspondence | `>=2` distinct `dataset_ids`, unconditional | `entity_identity_confidence>=0.70` implies `>=2` distinct datasets under the current formula (Section D of the P3.xxV.2G diagnosis already proved this mathematically) | **Equivalent by construction**, not merely coincidence | None found | No action — the confidence floor already encodes the same cross-dataset requirement, with graded evidence instead of binary |
| Source-row/evidence linkage for auditability | None — legacy carries no lineage beyond `source_dataset_ids` | `CanonicalEntityObservation` (per-observation `analysis_case_dataset_id`, `source_field`, `raw_value`, `semantic_confidence`) | **Canonical is strictly richer** | None — canonical evidence was already persisted by E.3, just unread by XDOM-A | Require `candidate.observations` non-empty (defensive; always true when confidence is computed from that formula) |
| Maintenance-event/operational-activity association | Not entity-mediated at all — XDOM-A's own dataframe filtering (`maint[maint["asset_id"]==asset_id]`) does this directly | Unchanged — still the rule's own dataframe filtering | **N/A to this fix** | None | Not touched — this is Section B's scope boundary |

## B. XDOM-A's Actual Entity Contract (verified by reading the rule, not assumed)

`run_asset_failure_to_lost_activity` (`app/services/cross_domain_intelligence_service.py:64-147`)
needs exactly one thing from "asset identity": **a stable key to iterate**,
used purely as a filter value against two already-canonicalized dataframes
(`maint["asset_id"].astype(str)==asset_id`, `ops["asset_id"]...`). It does
**not** need cross-dataset row linkage, entity type inference, relationship
resolution, or anything else E.3 provides beyond that one key — confirmed by
the fact that zero references to `CanonicalCaseEntity`/`CanonicalEntityObservation`
existed anywhere in this file before this fix, and the rule's own overlap
logic (temporal window matching) operates entirely on the two raw dataframes,
never on entity objects.

**Smallest canonical entity contract, as implemented**: `entity_type==ASSET`
AND `entity_identity_confidence >= pack.minimum_entity_identity_confidence`
AND `len(observations) >= 1`. Nothing more was added — no relationship
requirement, no participation role, no source-row pointer threaded into the
rule itself (lineage stays in `CanonicalEntityObservation`, available for
audit but not required by this rule's own logic).

## C. Candidate-Local Entity Eligibility Architecture

New pure function, `app/entities/intelligence_contract.py::eligible_entity_keys`:

```python
def eligible_entity_keys(
    candidates: list[EntityCandidate],
    entity_type: str,
    minimum_identity_confidence: float,
) -> set[str]:
    return {
        candidate.display_label
        for candidate in candidates
        if candidate.entity_type == entity_type
        and candidate.entity_identity_confidence >= minimum_identity_confidence
        and candidate.observations
    }
```

Framework-free (no DB touch — operates on the `EntityCandidate` list
`_run_case_level_entity_resolution` already produces in-memory this run,
avoiding a redundant round-trip, matching this codebase's established
threading philosophy for `semantic_outcome`/`entity_candidates`).
`minimum_identity_confidence` is always read from the caller's own
`IntelligencePackDefinition.minimum_entity_identity_confidence` — never a
second, independently-chosen number (`app/services/analysis_case_orchestration_service.py`,
via the new `IntelligencePackRegistry.get(rule_code)`), which is what keeps
readiness and execution provably aligned on one threshold against one
population (Section D).

No new abstraction was introduced: `EligibleCanonicalEntity` was considered
and rejected — `EntityCandidate` (E.3's own type) already carries every field
the function needs (`entity_type`, `display_label`, `entity_identity_confidence`,
`observations`). This lives in `app/entities/intelligence_contract.py`
specifically because that file's own header comment, written during P3.xxE.3,
already forecast this exact migration ("roadmap: P3.xxE.5 migrates
Intelligence rules toward this contract") — Fix #5 is that migration's first
real instance, not a new pattern.

## D. Readiness/Execution Alignment — the Core Invariant, Proven Structurally

**Before this fix**: readiness read `CanonicalCaseEntity.entity_identity_confidence`
(all rows, case-global) via `coverage_above_threshold` @ `minimum_coverage_ratio=1.0`;
execution read `AnalysisCaseEntityLink` (a disconnected legacy system,
P3.xxV.2G Section F). Two different tables, two different mechanisms, two
different populations — readiness could report BLOCKED for reasons execution
never even evaluated, and vice versa.

**After this fix**: both read the exact same source — `CanonicalCaseEntity`
rows for `(organization_id, run_id, entity_type=ASSET)` — at the exact same
threshold (`pack.minimum_entity_identity_confidence`). Readiness reduces that
population via `"max"` (does at least one clear the bar); execution filters
that population via `eligible_entity_keys` (which entities clear the bar).
These are the same underlying question asked two different ways, over one
population, not two populations asked the same question.

**Structural proof, not just a claim**: `max(distribution) >= threshold` is
true if and only if at least one `CanonicalCaseEntity` row in that population
has `entity_identity_confidence >= threshold` — which is exactly the
condition `eligible_entity_keys` filters on, against the identical population
(entity resolution runs once per run; both the readiness index and the
execution candidate set are built from that single pass, never re-derived
independently). `tests/test_capability_governed_activation_xdom_a.py::test_mixed_e_readiness_execution_consistency_invariant`
exercises this live, end-to-end: whenever `governed_confidence_summary`
reports `entity_identity.ASSET` clear, the same run's recorded
`eligible_asset_count` is confirmed `> 0`.

## E. Implementation

- **`app/entities/intelligence_contract.py`**: added `eligible_entity_keys()`
  (Section C). **Casing bug caught during implementation**: the first version
  returned `candidate.normalized_key` (casefolded, e.g. `"a-1"`) — this
  silently broke `run_asset_failure_to_lost_activity`'s dataframe filter,
  which compares against the RAW column values (`"A-1"`), causing two
  existing, previously-passing tests
  (`test_xdom_a_ready_governed_execution_occurs_with_real_finding`,
  `test_xdom_a_governed_positive_result_materially_equals_legacy`) to fail
  with zero findings. Root-caused by reading `entity_deduplication.py`
  directly (`display_label = observations[0].raw_value`) and fixed by
  switching to `display_label` — caught by the existing regression suite
  before any commit, exactly the kind of defect the "run pre-existing tests
  before adding new ones" discipline exists to catch.
- **`app/intelligence_packs/registry.py`**: added
  `IntelligencePackRegistry.get(rule_code)`. XDOM-A's registration gained
  `confidence_aggregation_policy="max"` (an already-existing, already-generic
  evaluator option — see `intelligence_readiness_service.py`'s own
  `_meets_confidence`, untouched) with an inline comment citing the P3.xxV.2G
  diagnosis. `minimum_coverage_ratio` was left unset (falls back to the
  class default, unused by `"max"`) rather than deleted, so the field's
  meaning stays legible for any future pack that does need it.
- **`app/services/cross_domain_intelligence_service.py`**:
  `matched_asset_keys` renamed to `eligible_asset_keys`; docstring updated to
  name the new canonical source and the retired legacy one. The rule's loop
  body (`for asset_id in sorted(eligible_asset_keys): ...`) is otherwise
  byte-identical — no matching/temporal/publishing logic touched.
- **`app/services/analysis_case_orchestration_service.py`**: `entity_ids`/
  `entity_candidates` are now initialized before the `if semantic_outcome is
  not None:` block (a **latent gap fixed as a prerequisite**: they were
  previously only ever assigned inside that block or its `except`, and Fix #5
  needed to reference `entity_candidates` later, outside it, for the first
  time — confirmed by grep that no other code path referenced these names
  after that block before this change, so nothing else could have hit the
  gap). `eligible_assets` is computed once, right where legacy `matched_assets`
  already was, from the same in-memory `entity_candidates`. `matched_assets`
  itself is **retained**, not removed (Section N): still the sole source of
  every pack's pre-existing legacy `required_entities` check. Both counts,
  plus their intersection/differences, are recorded on the XDOM-A
  `cross_domain_intelligence` stage event's `detail` JSON for migration-safety
  comparison (Section F).

## F. Legacy Comparison

Both populations are computed and recorded on every run where XDOM-A
actually executes (i.e., reaches `READY`), never silently dropped. Measured
directly via the new end-to-end mixed-population fixture
(`tests/test_capability_governed_activation_xdom_a.py::test_mixed_d_legacy_vs_canonical_comparison_recorded_on_stage_event`):
5 legitimately multi-dataset assets, 1 single-dataset asset —

| | Legacy count | Canonical count | Intersection | Legacy-only | Canonical-only |
|---|---|---|---|---|---|
| Mixed fixture (5 eligible + 1 ineligible) | 5 | 5 | 5 | 0 | 0 |

**The two populations agree exactly on this fixture, and this agreement is
expected, not coincidental**: legacy's own `>=2`-dataset rule independently
excludes the single-dataset asset (A-6) the same way the canonical
0.70-confidence floor does, because both mechanisms ultimately count the same
underlying signal — how many distinct datasets reference a given raw value —
just via two different code paths (Section A). A live production
legacy-vs-canonical count comparison on the real Wave 1 corpus was **not**
independently re-derived this pass beyond what the automated test already
proves: no REST route currently exposes `AnalysisCaseStageEvent.detail`
(confirmed by inspecting `app/main.py`'s router registrations — none exists),
so the six Wave 1 Rental cases that reached `READY` this pass (Section I) had
their comparison recorded server-side but not independently re-fetched via
the browser session; the mechanism is proven correct by the fixture test
above, executed against the same production code this deploy runs.

## G. Tests

- **`tests/test_entities_intelligence_contract.py`** (new, 10 pure unit
  tests, no DB): positive A-D (above-threshold eligible; multiple independent
  eligible entities; one low-confidence entity never contaminates an
  unrelated high-confidence one; entity-type filtering); negative A-E
  (below-threshold excluded; confidence alone without observations
  insufficient; same raw key across different entity types never
  cross-contaminates — the closest real proxy this data model supports for
  "entity collision," since E.3's dedup has no ambiguous/conflicted status
  yet; all-low-confidence population yields empty set; no population at all
  yields empty set); plus a dedicated test proving the threshold is always
  the caller's own parameter, never hardcoded.
- **`tests/test_capability_governed_activation_xdom_a.py`** (extended): all
  13 pre-existing tests (A-G ablations, positive-fixture certification,
  negative no-maintenance-domain path) pass unmodified. New: a
  `_mixed_fixture_csvs()` fixture (5 eligible + 1 single-dataset-ineligible
  asset) backing 5 new end-to-end tests — precondition (confidence values
  really are 0.65 vs >=0.70), readiness (READY, not blocked by the tail),
  execution (eligible assets independently evaluated, tail excluded, with an
  explicit note on the pre-existing finding-count dedup characteristic found
  in Section H), legacy-vs-canonical comparison recorded, and the
  readiness/execution consistency invariant (Section D). Two new pure
  ablation tests: `test_ablation_h_mixed_confidence_population_still_ready`
  (the core fix, at the `evaluate_readiness()` level) and
  `test_ablation_i_all_low_confidence_still_blocks` (the safety side — a
  genuinely all-low-confidence population is still correctly blocked, `"max"`
  didn't just make everything pass).

## H. A Genuine, Pre-Existing, Unrelated Defect Found While Testing

Building the mixed-population execution test surfaced that
`governed_finding_publisher.publish()` (`app/services/governed_finding_publisher.py`)
never attaches an `EvidenceType.affected_record`-typed evidence item
identifying *which* entity a finding concerns — only `EvidenceType.DATASET`
items. `FindingDeduplicationService.key()` (`app/services/finding_platform_service.py`)
hashes `affected_references` from exactly that (always-empty, for this rule)
evidence subset, plus `dataset_reference` (identical across every asset in
one `(maint_cd, ops_cd)` loop iteration) and `occurrence_start`/`occurrence_end`
(never set by this rule, always `None`). The net effect: **every XDOM-A
finding within one dataset pair, for every distinct asset, collapses onto the
same deduplication key**, and `publish_candidate_finding()` silently returns
the first-created `Finding` row for every subsequent asset
(`if existing is not None: return existing`) rather than raising or creating
a new row.

Confirmed **not a Fix #5 regression**: reproduced identically on the
already-existing, unmodified 5-asset `_positive_fixture_csvs()` (5 legitimately
eligible assets under both legacy and canonical population definitions,
predating this fix entirely) — only 1 `Finding` row is ever created there
too, which is exactly why that fixture's own pre-existing test only ever
asserted "at least one finding," never "exactly 5." This is a genuine,
pre-existing, unrelated defect in `governed_finding_publisher`'s evidence
construction / `FindingDeduplicationService`'s key composition — recorded
here, not fixed, per this mission's explicit scope.

## I. PR / CI / Merge / Deploy

| Item | Value |
|---|---|
| Branch | `fix/p3xxv2h-xdom-a-canonical-entity-migration` |
| Implementation SHA | `a27c2d4` |
| PR | [#101](https://github.com/intel4ops/intel4ops-core-platform/pull/101) |
| CI | Green — 20m19s |
| Merge SHA / final main SHA | `7388bd6` |
| Deployment | Confirmed live via the Wave 1 rerun below; one `502` observed on the first post-merge request (Render mid-redeploy), resolved on retry (~30s) |
| Migration | None — pure Python logic change |
| Full pytest | 1649/1649 passed (fresh disposable Postgres reset beforehand) |
| `ruff format --check` / `ruff check` / `mypy` | clean |

## J. Controlled Wave 1 Rerun

Fresh `AnalysisCase`s created for all 10 Wave 1 simulations against
post-merge production, concurrency 1, sequential, same frozen customer-data
CSVs, no truth/manifest touched.

## K. Per-Case Entity Comparison

| Simulation | ASSET count | Confidence distribution | Case-global coverage (>=0.70) | XDOM-A readiness BEFORE (Fix #4 baseline) | XDOM-A readiness AFTER | `entity_identity.ASSET` in `below_confidence_threshold`? | XDOM-A findings | Primary remaining blocker |
|---|---|---|---|---|---|---|---|---|
| FIELDMAINT-001 | 70 | `{0.82:60, 0.65:10}` | 85.7% | BLOCKED | BLOCKED (unchanged classification) | **No (was Yes)** | 0 | `domain:maintenance`/`field:downtime_hours`/`trust:maintenance` — pre-existing, V.2B, untouched |
| FIELDMAINT-002 | 67 | `{0.82:60, 0.65:7}` | 89.6% | BLOCKED | BLOCKED | **No (was Yes)** | 0 | same |
| FIELDMAINT-005 | 350 | `{0.82:350}` | 100.0% | BLOCKED | BLOCKED | No (unchanged — was already 100%) | 0 | same, plus XDOM-B's own `trust:operations` gap (unrelated) |
| FIELDMAINT-007 | 59 | `{0.82:50, 0.65:9}` | 84.7% | BLOCKED | BLOCKED | **No (was Yes)** | 0 | same |
| RENTAL-001 | 41 | `{0.99:8, 0.905:13, 0.82:9, 0.65:11}` | 73.2% | PARTIAL | **READY** | **No (was Yes)** | 0 | raw `maintenance_date` vs. required literal `event_date` on Rental's maintenance-domain dataset (Section L) |
| RENTAL-003 | 40 | `{0.99:6, 0.905:9, 0.82:5, 0.65:20}` | 50.0% | PARTIAL | **READY** | **No (was Yes)** | 0 | same |
| RENTAL-011 | 45 | `{0.99:13, 0.905:14, 0.82:7, 0.65:11}` | 75.6% | PARTIAL | **READY** | **No (was Yes)** | 0 | same |
| RENTAL-012 | 45 | `{0.99:16, 0.905:12, 0.82:6, 0.65:11}` | 75.6% | PARTIAL | **READY** | **No (was Yes)** | 0 | same |
| RENTAL-015 | 351 | `{0.99:21, 0.905:60, 0.82:35, 0.65:235}` | 33.0% (worst in corpus) | PARTIAL | **READY** | **No (was Yes)** | 0 | same |
| RENTAL-018 | 50 | `{0.99:15, 0.905:19, 0.82:8, 0.65:8}` | 84.0% | PARTIAL | **READY** | **No (was Yes)** | 0 | same |

XDOM-B's own activation/findings are unchanged on every case from the Fix #4
baseline (Section L), confirming zero cross-contamination.

## L. XDOM-A Readiness/Findings — What Actually Moved

**Readiness moved on 8/10 cases** (all except FIELDMAINT-005, already at
100% coverage before this fix): `entity_identity.ASSET` cleared from
`below_confidence_threshold` everywhere, and **all 6 Rental cases moved from
PARTIAL to READY** — including RENTAL-015, the single worst case-global
coverage in the entire Wave 1 corpus (33.0%, i.e. two-thirds of its ASSET
population single-dataset), now READY because at least one of its 351
entities individually clears 0.70.

**Findings did not move — traced to a precise, newly-identified, separate
cause, not merely reported as a null result.** XDOM-A executing (READY) on
all 6 Rental cases but producing 0 findings each was investigated (not
fixed): `maintenance.csv`'s own date column is named `maintenance_date`,
never remapped/aliased to the canonical `event_date` name XDOM-A's own guard
requires literally (`if "event_date" not in maintenance_df.columns...: return
[]`, `cross_domain_intelligence_service.py:83-84`) — confirmed directly via
the live semantic profile for RENTAL-001's `maintenance.csv` (role
`"labor"`, fields `maintenance_id`/`asset_id`/`maintenance_date`/`cost`/
`downtime_hours`, no `event_date`). This is structurally the same *class* of
defect NEXT-1 named for `operational_event_id` (Fix #3) — a raw-vs-canonical
field-name gap — but for a different field (`event_date`) on a different
rule input (XDOM-A's maintenance-side temporal guard), not addressed by any
prior fix and explicitly not addressed here.

FieldMaintenance's 4 cases remain BLOCKED for the same pre-existing,
V.2B-documented domain-classification gap this whole program has left
untouched — now visibly narrower (one blocker category instead of two, since
entity confidence no longer contributes).

## M. XDOM-B Regression — Confirmed Unchanged

| | Fix #4 baseline | This pass |
|---|---|---|
| FIELDMAINT-001 findings | 2 | 2 |
| FIELDMAINT-002 findings | 1 | 1 |
| FIELDMAINT-005 findings | 0 (BLOCKED, `trust:operations`) | 0 (BLOCKED, `trust:operations`) |
| FIELDMAINT-007 findings | 1 | 1 |
| RENTAL-* (6) findings | 0 (READY, no candidate match) | 0 (READY, no candidate match) |

Byte-identical on every case. XDOM-B declares no `required_canonical_entities`
(confirmed unchanged, `registry.py:178-210`) and its own rule body was not
touched by any file in this diff — `cross_domain_intelligence_service.py`'s
diff is confined entirely to `run_asset_failure_to_lost_activity`'s parameter.

## N. False-Positive Safety

- **No low-confidence entity accepted**: `eligible_entity_keys` filters
  strictly `>=` the pack's own declared floor — confirmed by
  `test_negative_a_below_threshold_asset_not_eligible` and the mixed-fixture
  end-to-end test excluding A-6.
- **No unrelated assets merged**: `eligible_entity_keys` performs no merging
  of any kind — it is a pure filter over already-deduplicated E.3 candidates;
  entity deduplication itself (`entity_deduplication.py`) was not touched.
- **No broadened raw identifier matching**: the rule's own dataframe
  filtering (`maint["asset_id"].astype(str)==asset_id`) is byte-identical —
  only the source of the `asset_id` values iterated changed, not how they're
  matched against the dataframes.
- **No semantic authority bypassed**: `EntityCandidate`s only exist for
  fields that already cleared `resolve_effective_decision` in E.3's own
  unmodified entity-resolution stage; Fix #5 reads that output, never
  recomputes or relaxes it.
- **No canonical evidence bypassed**: `canonical_evidence_completeness`
  threading into `GovernedFindingRequest` (Fix #3) is untouched — confirmed
  by diff inspection, zero lines in that parameter's construction changed.
- **No simulation-specific behavior**: `eligible_entity_keys` takes only
  `candidates`, `entity_type`, `minimum_identity_confidence` — no simulation
  ID, business family, or filename appears anywhere in the changed files
  (confirmed by direct diff inspection, matching every prior fix's
  discipline).

## O. Legacy Deprecation Plan

**Current remaining consumers of `AnalysisCaseEntityLink`/`EntityResolutionService`**:
`_legacy_resolved_entity_types()` (`case_capability_index_service.py`) feeds
`CaseCapabilityIndex.resolved_entity_types`, which every registered pack's
pre-existing `required_entities` field checks (`missing_entities =
pack.required_entities - index.resolved_entity_types`) — this includes
MAINT-001, XDOM-A (still, for its own separate legacy check — distinct from
the canonical `required_canonical_entities` dimension this fix touched), and
XDOM-B. `matched_assets` itself is retained in the orchestrator purely for
the migration-safety comparison (Section F) — XDOM-A no longer consumes it
for execution.

**Can XDOM-A stop using it entirely?** Not this pass — its legacy
`required_entities={"asset","operational_event"}` readiness check (a
structural presence check, unrelated to confidence) was not in this fix's
scope and was left untouched; removing it would require confirming every
other pack's behavior is unaffected and is a distinct, separately-scoped
question.

**Should it remain for compatibility?** Yes, for now — it is still the sole
implementation of the legacy `required_entities` structural-presence check
for all three registered packs, and no replacement for that specific check
was built or requested this pass.

**What future milestone should retire it?** A dedicated migration of the
legacy `required_entities` structural check onto an E.3-native equivalent
(e.g., "does >=1 canonical entity of this type exist at all," independent of
confidence) — at that point, with zero remaining consumers, `AnalysisCaseEntityLink`/
`EntityResolutionService` could be fully retired. Not proposed as part of
this fix's scope; flagged for a future architectural review, matching this
mission's explicit "do not broadly delete legacy infrastructure in Fix #5"
instruction.

## P. Fix #5 Classification

**FIX #5 VALIDATED**

All 10 success criteria hold:

1. XDOM-A no longer executes from legacy `matched_asset_keys` — confirmed,
   the parameter itself was renamed and re-sourced (Section E).
2. XDOM-A consumes canonical E.3 entities/observations — confirmed,
   `eligible_entity_keys` operates on `EntityCandidate`/`CanonicalEntityObservation`-backed
   data exclusively.
3. Readiness and execution use the same canonical entity population —
   confirmed structurally (Section D) and by a live end-to-end consistency
   test.
4. Unrelated low-confidence tail entities do not incorrectly block valid
   candidate-local analysis — confirmed live: RENTAL-015's 67% single-dataset
   tail no longer blocks readiness (Section K).
5. Low-confidence candidate entities remain excluded — confirmed
   (`test_negative_a`, mixed-fixture execution test).
6. 0.70 threshold remains unchanged — confirmed, `registry.py`'s
   `minimum_entity_identity_confidence=0.70` untouched.
7. No case-specific logic introduced — confirmed by diff inspection.
8. Legacy comparison is materially explainable — confirmed (Section F): the
   two populations agree exactly where expected, and why is traced to the
   shared underlying dataset-count signal, not asserted.
9. XDOM-B does not regress — confirmed byte-identical on all 10 cases
   (Section M).
10. Tenant/truth isolation remains intact — all 10 reruns scoped to the
    single pre-existing pilot organization; no truth/manifest file read or
    modified by any changed source file.

## Q. Next Empirically Observed Blocker

**Two distinct, separately-scoped blockers remain, by family — neither
fixed this pass:**

- **FieldMaintenance (4 cases)**: the pre-existing, V.2B-documented domain-
  classification gap (`domain:maintenance` never detected) plus the
  `field:downtime_hours`/`trust:maintenance` gaps that gap implies — entirely
  unrelated to entity identity, untouched by any fix in this program to date.
- **Rental (6 cases)**: now READY, but produces zero XDOM-A findings because
  `maintenance.csv`'s temporal column (`maintenance_date`) is never mapped to
  the canonical literal `event_date` XDOM-A's own guard requires — a
  raw-vs-canonical field-name gap structurally identical in kind to NEXT-1
  (Fix #3), newly identified this pass, for a different field on a different
  rule input.

A third, entirely separate, genuinely pre-existing defect was also surfaced
(Section H): `governed_finding_publisher`'s deduplication key construction
collapses multiple distinct-asset findings within one dataset pair onto a
single row, because no evidence item ever identifies which specific entity a
finding concerns. This affects XDOM-A's finding *count* whenever it does
execute (both before and after this fix) — orthogonal to entity eligibility,
not fixed here.

## R. Architectural Convergence

```
Fix #1  removed source-name assumption           (operational_event_id alias)
Fix #2  removed raw-status assumption             (canonical operational state)
Fix #3  aligned canonical evidence completeness   (raw-vs-canonical field split)
Fix #4  added repeated-reference identifier semantics (role-aware confidence)
Fix #5  aligned model execution with the canonical entity graph
```

**LEGACY ENTITY DEPENDENCE IS DECREASING.** XDOM-A's execution path no longer
touches `AnalysisCaseEntityLink`/`EntityResolutionService` at all — the one
remaining legacy dependency (the pre-existing `required_entities` structural
presence check, shared by all three packs) is unrelated to confidence,
untouched, and explicitly deferred to a future, separately-scoped milestone
(Section O). This is the first fix in the program to touch the *execution*
layer rather than the semantic/evidence layer that fed it — a genuinely
different kind of correction than Fixes #1-4, all of which operated entirely
upstream of entity/relationship formation.

---

## STOP

No entity confidence threshold was lowered. `minimum_coverage_ratio`'s
global default was not changed. XDOM-B's revenue logic was not touched. No
new intelligence capability was added. Wave 2, E.6, and E.7 were not
started. No frontend code was modified. Awaiting explicit architectural
review before any further remediation.
