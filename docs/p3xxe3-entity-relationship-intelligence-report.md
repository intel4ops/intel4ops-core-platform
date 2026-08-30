# P3.xxE.3 — Entity + Relationship Intelligence Report

Consolidated deliverable for the P3.xxE.3 milestone: resolving which source records refer to the same real-world entity within one AnalysisCase run, and discovering how those entities connect. The spec's own first instruction was to reconcile against everything that already exists before designing anything new — that reconciliation surfaced a real conflict and shaped the entire architecture below.

## Baseline / branch / PR / CI / merge / deploy

| | |
|---|---|
| Baseline SHA / tree | `b0f86fd83786ba6b6f8b945e9fce6a7c7cab1227` / `cc0cf6bef8f70ef26ae83745cb68991ef3678c52` off `main` |
| Branch | `feature/p3xxe3-entity-relationship-intelligence` |
| PR | [#88](https://github.com/intel4ops/intel4ops-core-platform/pull/88) "P3.xxE.3: Entity + Relationship Intelligence" — merged `1be4cf9bceb625cc11c6d2a71bc9967cde6ad9e9`, 2026-08-30T08:23:19Z |
| CI | Ruff + Mypy + Pytest + Alembic — green, 13m19s |
| Alembic head | `20260901_0057` (single head) |
| Deployment | Live on Render, auto-deploy on merge to `main` |

## Existing subsystem reconciliation (required before design)

Four rounds of research (three parallel deep-dives plus one focused follow-up) examined every entity/relationship-adjacent subsystem already in the codebase, producing this table before any implementation began:

| Existing subsystem | Purpose | Overlap | Decision | Rationale |
|---|---|---|---|---|
| **Knowledge Graph** (WP-3.01) | Governed reference/projection layer over *already-canonical* Phase 2 records | Low | KEEP SEPARATE | Only 1 of 25 entity types has any write path, zero AnalysisCase coupling. Explicitly out of scope for extracting new entities from raw data. |
| **`entity_resolution_service.py`** (live, wired into every AnalysisCase run today) | Exact-match-only cross-dataset linking, per-run, no cross-run persistence | High | EXTEND in spirit, kept running in parallel this milestone | Its scoping model already matches what E.3 needs. Cutover is a named future item, not this milestone — avoids risking already-shipped cross-domain-intelligence behavior. |
| **Canonical Mapping's own `EntityResolutionService`** | Governed Phase-2 pre-analysis pipeline, persistent org-wide entity master | High on algorithm shape, real conflict on scoping | **KEEP SEPARATE** | Its `EntityMatchMethod` enum (`exact_identifier`/`normalized_identifier`/`deterministic_composite`/`fuzzy_candidate`) is almost verbatim what this spec asked for — but its `CanonicalEntity` table has no run/dataset column at all: every mapping run ever, forever, accretes onto one entity master per org+type. Reusing it would have silently introduced cross-run entity memory on day one, directly contradicting this milestone's own invariant. Algorithm shapes (trim/casefold normalization, `difflib.SequenceMatcher` fuzzy ratio) were reused as fresh, independent code — not the table, not the persistence model. |
| **Causal Links** | Human/analyst-proposed causal hypothesis testing over already-computed domain outputs | Low | KEEP SEPARATE | No entity-to-entity structural relationship model exists there, confirmed by a full read — causal reasoning and structural connection are different domains. |

**The structural fix that follows directly from the one real conflict:** every new table this milestone introduces is scoped to `(organization_id, analysis_case_id, run_id)` — no query can ever span more than one run, by construction. No entity-to-entity relationship model existed anywhere in the codebase prior to this milestone (confirmed across all four subsystems).

## Plan-review corrections (all four verified in shipped code, not just design intent)

1. **No universal confidence ceiling.** The first design draft let semantic/type confidence cap identity confidence. Corrected: `entity_type_confidence` (confidence the canonical entity type is correct) and `entity_identity_confidence` (confidence multiple observations are the same real-world entity) are computed independently and both persist unmerged. Strong corroborated identifier evidence can produce near-certain identity confidence even under moderate type confidence — proven live (§ below), not just asserted.
2. **Relationship semantics are evidence-gated, never type-pair-asserted.** A static `(entity_type, entity_type) → relationship_type` lookup table was removed entirely from the design. The same `(INVOICE, WORK_ORDER)` entity-type pair produces `BELONGS_TO` under clean many-to-one evidence and `ASSOCIATED_WITH` under many-to-many evidence in the same test — direct proof relationship type isn't inferred from the type pair alone (`tests/test_entities_relationship_discovery.py::test_same_type_pair_produces_different_relationship_type_by_evidence_shape`).
3. **Explicit legacy cutover roadmap.** `CanonicalCaseEntity`/`CanonicalCaseRelationship` is designated the future authoritative layer; `AnalysisCaseEntityLink` is compatibility-only from this milestone forward. Roadmap: E.3 ships the new layer alongside the untouched legacy path → E.4 (Process Interpretation) consumes the canonical layer → E.5 migrates Intelligence rules via the new read contract → legacy path is deprecated and retired after successful migration. No API response blends the two systems' outputs.
4. **Live certification is engineering verification only.** Not tied to any specific organization; accuracy claims come only from the calibration benchmark, never from live data.

## Architecture added

- **New `app/entities/` package** (14 modules, framework-free — no SQLAlchemy or FastAPI import — mirroring `app/semantic/`'s existing convention): `entity_type.py` (the `EntityType` vocabulary, extending `concept_registry.py`'s existing UPPER_SNAKE_CASE values), `identifier_normalization.py`, `entity_candidate.py` (ephemeral `EntityObservation`/`EntityCandidate`/`FuzzyCandidateScore`), `entity_type_inference.py` (semantic-first — infers type only from a governed effective concept, never a raw field name; returns `None` on ambiguous multi-type concepts rather than silently picking one), `entity_resolution_tiers.py` (exact/normalized/composite grouping plus fuzzy scoring), `entity_deduplication.py` (the corrected confidence model), `case_entity_context.py` (order-independence, mirrors `case_context.py`'s Pass-1 role), `entity_resolution.py` (top-level entry point, consumes P3.xxE.1A effective semantic decisions), `relationship_type.py`/`relationship_candidate.py`/`confidence_decomposition.py`/`relationship_discovery.py` (evidence-gated relationship discovery, including a real per-entity contradiction pass — see below), `intelligence_contract.py` (the future downstream-Intelligence read interface, defined but not wired into any existing rule this milestone).
- **Fuzzy resolution — contracts + scoring only**, using the spec's own explicit escape hatch: `score_fuzzy_candidates()` computes bounded similarity scores but never creates or merges an `EntityCandidate` from one. Full activation would need a review-queue governance layer on the scale of P3.xxE.1A itself; a fuzzy candidate is by definition non-authoritative anyway, so nothing downstream loses real capability.
- **Two new orchestration stages** — `canonical_entity_resolution` and `relationship_discovery`, inserted immediately after `semantic_interpretation` in `analysis_case_orchestration_service.py`'s `execute()`. `_run_case_level_semantic_interpretation` now returns a `SemanticInterpretationOutcome` (its `CaseSemanticContext` plus in-memory `InterpretationDecision` lists) instead of discarding them after persistence, so the new stage consumes them directly — avoiding both a redundant DB round-trip and any drift between persisted and reasoned-about state. Both new stages are wrapped in the same blanket `try/except` pattern `semantic_interpretation` already uses; stage failure never fails the run. The legacy `entity_resolution_service.resolve()` call site is completely untouched and still feeds cross-domain rule XDOM-A.
- **A real per-entity contradiction pass** (`_flag_contradictory_many_to_one_pairs` in `relationship_discovery.py`) — found necessary during this milestone's own test-writing, not shipped blind: aggregate type-pair-level cardinality *shape* agreement across datasets isn't sufficient to catch a real contradiction, since two datasets can agree on the shape ("many-to-one") while disagreeing on which *specific* entity a given "many"-side entity belongs to. The pass groups all `BELONGS_TO` candidates by their "many"-side entity and flags any with more than one distinct partner as `CONFLICTED`, regardless of per-pair confidence.
- **Confidence composition** (`confidence_decomposition.py`): `relationship_confidence` is composed from both sides' `entity_identity_confidence` (never `entity_type_confidence`) plus a distinct `structural_evidence_confidence` — the weaker side's identity confidence is the floor, structural evidence can raise the result within a bounded contribution, capped at 0.98. `CONFLICTED` status bypasses the confidence ladder entirely as a structural state.

## Database changes

Three new tables (migration `20260901_0057`), each scoped to `(organization_id, analysis_case_id, run_id)`:
- `canonical_case_entities` — `entity_type_confidence`/`entity_identity_confidence` as two separate columns (not one blended score), `resolution_method`, `evidence_summary`, `resolution_policy_version`.
- `canonical_case_entity_observations` — persisted source lineage (Invariant E). **Privacy-corrected persistence policy:** `raw_value` is stored verbatim only for non-sensitive entity types (business codes like `asset_id`/`work_order_id`); for `PERSON`/`CUSTOMER`, `raw_value` stays `NULL` and a sha256 `raw_value_hash` is stored instead — enough for dedup/explainability audit without duplicating personal identifiers.
- `canonical_case_relationships` — `left_entity_identity_confidence`/`right_entity_identity_confidence`/`structural_evidence_confidence`/`relationship_confidence` as four separate columns, `conflict_reason`.

Composite foreign keys require a matching unique constraint on the referenced table (`UniqueConstraint("organization_id", "id")` on `canonical_case_entities`, mirroring `AnalysisCase`'s own pattern) — caught and fixed before the first migration test run.

**A genuine naming collision was caught and fixed before merge:** Canonical Mapping's own (rejected-as-reuse-target) system already defines a class named `CanonicalEntity` in `app/models/canonical_mapping.py`. A first pass at wiring up `app/models/__init__.py` silently shadowed it. Fixed by renaming this milestone's models to `CanonicalCaseEntity`/`CanonicalCaseRelationship` throughout — exactly the kind of quiet conflict the reconciliation exercise exists to surface, caught here by `ruff check`'s `F811` (redefinition) rule rather than a hidden runtime bug.

## API (read-only)

```
GET .../analysis-cases/{case_id}/entities?run_id=
GET .../analysis-cases/{case_id}/entities/{entity_id}
GET .../analysis-cases/{case_id}/relationships?run_id=
GET .../analysis-cases/{case_id}/relationships/{relationship_id}
GET .../analysis-cases/{case_id}/entity-graph?run_id=
```

`entity-graph` is a pure relational read composition (join of `CanonicalCaseEntity` + `CanonicalCaseRelationship` for one run), never a graph database, and reflects only the new layer — never blended with legacy `AnalysisCaseEntityLink` data in any response.

## Order invariance

`tests/test_entities_order_independence.py` runs the same fixture case through real orchestration twice, with dataset registration order reversed, and asserts the resulting `CanonicalCaseEntity`/`CanonicalCaseRelationship` sets (by content, not id/timestamp) are identical — the same structural argument already proven for P3.xxE.2's cross-dataset semantic evidence: every observation is gathered into a flat, unordered collection before any grouping or pairwise logic runs, so no result can depend on which dataset was processed first.

## Validation-only calibration benchmark

`tests/entity_relationship_calibration_fixtures.py` + `tests/test_entity_relationship_calibration.py`, same pattern as P3.xxE.2's semantic calibration benchmark — flat files under `tests/`, no `app/` module imports either, hand-labeled expectations run through real orchestration.

Two cases: a clean case (each work order consistently references exactly one asset across both datasets) and a deliberately contradictory case (the same work order references a *different* asset in a second dataset than the first, for every single occurrence).

| Metric | Value |
|---|---|
| `ENTITY_RESOLUTION_PRECISION` | 1.00 |
| `ENTITY_RESOLUTION_RECALL` | 1.00 |
| `RELATIONSHIP_PRECISION` | 1.00 |
| `RELATIONSHIP_RECALL` | 1.00 |
| `HIGH_CONFIDENCE_ENTITY_ACCURACY` | 1.00 |
| `FALSE_ENTITY_MERGE_RATE` | 0.00 (verified 0/N, not a fabricated absence) |
| `MISSED_ENTITY_LINK_RATE` | 0.00 |
| `RELATIONSHIP_CONFLICT_RATE` | genuine non-trivial rate (>0, <1) across the two cases combined |
| Conflict-case recall | 1.00 — every deliberately contradictory relationship landed `CONFLICTED` |
| `COMPOSITE_MATCH_ACCURACY` | `N/A` — no compound-identifier concept registered this milestone, correctly unreported |
| `FUZZY_CANDIDATE_ACCURACY` | `N/A` — fuzzy resolution is contracts-only this milestone, correctly unreported |

## Test results

- 50 new tests (unit tests per module, the required order-permutation test, the calibration benchmark, API route tests, a dedicated architecture guardrail file) — all passing.
- Full existing suite: 1436 passed / 1 failed. The one failure (`test_mapping_execution_contract.py::test_list_is_tenant_scoped_filtered_paginated_and_read_only`) is pre-existing, order-dependent flakiness in Canonical Mapping's pagination test — a module this milestone never touched; confirmed by re-running it in isolation, where it passes cleanly.
- A separate full-suite run before the final push surfaced 16 failures against the shared Postgres test database: 5 were the expected, mechanical hardcoded-Alembic-head-assertion bumps (`tests/test_postgres_migrations.py`, now bumped to `20260901_0057`); the remaining 11 were confirmed to be the shared test database's own recurring migration-replay-churn corruption (unrelated `lineage_edges`/forecasting/causal-intelligence constraint violations) — resolved by resetting the shared database, a standing practice for this project.
- Fresh-disposable-Postgres migration certification: 83/83 passed on a genuinely empty database — full upgrade → downgrade → reupgrade round trip.
- `ruff format --check`, `ruff check`, `mypy .` all clean across the complete diff.

## Guardrails

Every new production file registered in `tests/test_validation_import_boundary.py`'s `PRODUCTION_EXECUTION_MODULES`. A new, separate guardrail file (`tests/test_entities_architecture_guardrails.py`) rather than folding into the semantic-specific one — reuses the same ground-truth-import ban and simulation-literal-token scan, plus one new check specific to this package: no import of any AI-provider-facing module (`app.semantic.provider`/`openai_provider`/`provider_factory`) anywhere under `app/entities/`, since this package is deterministic and local by construction (E100 portability).

## Live certification (engineering verification, not an accuracy claim)

Against a real registered AnalysisCase with genuine cross-dataset identifiers (Field Maintenance family): triggered a fresh run (`AnalysisCaseRun` run_number=7, `id=bea9686a-b705-4ac6-9429-683aae0dc6a9`), completed with status `partial` (matching pre-existing, unrelated Intelligence domain-review behavior).

- `canonical_entity_resolution` stage completed: **1815 real `CanonicalCaseEntity` rows** resolved across `WORK_ORDER`/`ASSET`/`CUSTOMER`.
- A real entity, `WO-000001`: `entity_type_confidence=0.98`, `entity_identity_confidence=0.905`, corroborated across 4 distinct real datasets via exact identifier match — two honestly distinct numbers, neither capping the other, live proof of the corrected confidence model (correction 1).
- `relationship_discovery` stage completed: **zero relationships** this run. Investigated directly rather than assumed correct (per this project's own no-blind-retry-loops practice): of 24 real datasets in this case, only 8 have any auto-accepted identifier field, and none has two different entity types auto-accepted simultaneously in the same dataset — no co-occurrence, no relationship to find. A genuine property of this run's data, not a defect in the discovery mechanism, which the calibration benchmark above independently proves works correctly when the evidence exists.
- Entity-graph API responded (200), node count matched entity count exactly (1815), edge count matched relationship count exactly (0) — confirmed the API reflects only the new layer, never blended with the legacy link table.
- Existing findings/Intelligence endpoint on the same run responded normally (200, data-dependent empty result — not a regression).

**Durable record created:** `AnalysisCaseRun` run_number=7 on the real SOTRA Pilot org's `SIM-OFS-FIELDMAINT-005` case, plus its 1815 `CanonicalCaseEntity` rows. Append-only by design, no cleanup action exists or is intended, consistent with this system's governance pattern.

## Known limitations

- `LOCATION`/`CONTRACT`/`PRODUCT`/`TRANSACTION`/`EVENT` entity types have no backing `CanonicalConcept` registered in `concept_registry.py` yet — unreachable this milestone, an accepted and documented gap rather than an oversight. Concept curation stays P3.xxE.1's responsibility, not P3.xxE.3's.
- `USES`/`GENERATES`/`PERFORMED_BY`/`LOCATED_AT` relationship types are defined in the vocabulary but never asserted by any code this milestone — they require explicit semantic/process evidence this milestone's evidence sources (FK-overlap, co-occurrence, cardinality, coarse temporal consistency) don't produce. Forward-declared for P3.xxE.4 Process Interpretation.
- Relationship discovery requires two different entity types to both independently clear the semantic auto-accept threshold *within the same dataset* — on the real live corpus today, this is a real coverage bottleneck (confirmed directly during live certification: only 8/24 datasets in the certified case have any auto-accepted field, none has two). The mechanism itself is proven correct by the calibration benchmark; broadening real-corpus coverage is a function of the underlying semantic auto-accept rate, not a gap in this milestone's own logic.
- The legacy `entity_resolution_service.py`/`AnalysisCaseEntityLink` path remains fully live and unmigrated, by design — cutover is scheduled for a later milestone per the roadmap above, not this one.

## P3.xxE.4 readiness

The canonical entity/relationship layer is in place and tested; Process Interpretation's natural first job is populating the `USES`/`GENERATES`/`PERFORMED_BY`/`LOCATED_AT` relationship types this milestone deliberately left unreachable. The `intelligence_contract.py` read interface is defined and ready for P3.xxE.5's Intelligence-rule migration. Cross-run entity/relationship memory (P3.xxE.6) remains explicitly out of scope and structurally impossible in the current schema — every table is `run_id`-scoped with no cross-run query path.
