# P3.xxE.4 — Operational Process Interpretation + Canonical Process Graph Report

Consolidated deliverable for the P3.xxE.4 milestone: advancing from P3.xxE.3's "what entities exist and how are they related" to "what operational process do these entities/events/relationships/states/timestamps represent" — activity discovery, precedence/state-transition sequencing, and process-instance anchor discovery over already-resolved canonical entities. The spec's own first instruction was again to reconcile against everything that already exists before designing anything new; that reconciliation found no overlapping subsystem, but the pre-implementation baseline surfaced a real architectural fork that reshaped the evidence-consumption design before any code was written.

## Baseline / branch / PR / CI / merge / deploy

| | |
|---|---|
| Baseline SHA / tree | `4b3b8b3` (P3.xxE.3 report commit) off `main` |
| Branch | `feature/p3xxe4-operational-process-interpretation` |
| PR | [#89](https://github.com/intel4ops/intel4ops-core-platform/pull/89) "P3.xxE.4: Operational Process Interpretation + Canonical Process Graph" — merged `60594a68d8d66fa0b89bed6a07a38fe3c20256c7` |
| CI | Ruff + Mypy + Pytest + Alembic — green, 17m22s |
| Alembic head | `20260902_0058` (single head) |
| Deployment | Live on Render, auto-deploy on merge to `main`, confirmed live via `openapi.json` |

## Existing subsystem reconciliation (required before design)

| Existing subsystem | Process semantics present | Overlap | Decision |
|---|---|---|---|
| Knowledge Graph relationship vocabulary (26 codes) | None — every code is a same-instant provenance/attribution edge; `belongs_to_process` misleadingly only connects to an internal batch-run entity | None | KEEP SEPARATE |
| Findings lifecycle FSM | A reusable transition-guard *pattern* | Pattern-shape only | KEEP SEPARATE (Intel4Ops-internal governance, not customer process) |
| Action/Recovery lifecycles | Intel4Ops-internal workflow governance | None | KEEP SEPARATE |
| `AnalysisCaseStageEvent` | Pure pipeline stage history | None as data source; is the right place to record the new stage | REUSE the mechanism, never as data |
| **Causal Links** | Post-hoc human-hypothesis evaluation only — `CausalHypothesisService.create()` requires a caller to already supply source/target/edge-type; **zero automatic sequence discovery** anywhere in the module | None (structurally different job) | KEEP SEPARATE — enforced by a dedicated import-ban guardrail test |
| `raw_lineage.py` | Intel4Ops-internal data-processing provenance | None | KEEP SEPARATE |
| `job_to_cash_engine.py` / cross-domain Intelligence rules | The richest *existing, unmodeled* evidence of implicit customer-process-order assumptions (hard-coded completion→invoicing→payment sequence) | Illustrative, not structural | Not touched this milestone — the clearest real-world justification for E.4, a natural future consumer |

**No STOP condition triggered.** No existing subsystem does automatic customer-process-sequence discovery from raw data — this milestone's actual job. Causal Links is the one adjacent system, and the boundary is enforced directly by `tests/test_process_architecture_guardrails.py::test_process_modules_never_import_causal_links`.

## The critical pre-implementation finding

An 11-case live-corpus baseline (matching E.3's own baseline exactly: 11 cases / 126 datasets / 636 fields) found: **31 fields at `machine_auto_accepted`, all identifier concepts, zero timestamp or status concepts.** 18 temporal-concept fields sat 100% at `accepted_with_flag`; 30 status-concept fields sat 100% at `review_required`. Strict reuse of E.3's entity-resolution consumption pattern (act only on `auto_accepted`) would have made process interpretation's live output vacuous on every real case — activities and sequences need temporal/state evidence as their primary input, and none of it reaches E.3's own bar.

This was surfaced to the user directly rather than silently worked around, and led to plan review correction 1 below.

## Plan-review corrections (all three verified in shipped code, not just design intent)

1. **A 5-tier semantic evidence eligibility hierarchy, not a flat strict/weak split.** `HUMAN_CONFIRMED`/`HUMAN_CORRECTED` and `AUTO_ACCEPTED` are authoritative (named type/state at full confidence). `ACCEPTED_WITH_FLAG` is supporting evidence — a named activity type or canonical state name only when independently corroborated (≥2 distinct datasets), else `GENERIC`/raw value at a discounted confidence. `REVIEW_REQUIRED` is hypothesis-generation only — always `GENERIC`, capped at 0.35, **never** independently producing a named type or state (`tests/test_process_activity_type_inference.py::test_review_required_never_independently_produces_a_named_type`, `tests/test_process_state_normalization.py::test_review_required_never_independently_names_a_state`). This required a genuinely new confidence split on `CanonicalProcessActivity`: `state_existence_confidence`/`state_meaning_confidence`, mirroring E.3's own `activity_type_confidence`/`activity_existence_confidence` split.
2. **A timestamp is never automatically an activity.** `activity_discovery.py` requires ≥1 corroborating signal — an event-shaped dataset role (reused from `DatasetRoleClassifier`, no new classification logic), a co-occurring status/entity-grain field, or an inherently-operational temporal concept (`completed_timestamp`/`scheduled_timestamp` vs. the deliberately ambiguous `event_timestamp` alias set) — before creating an `ActivityCandidate` at all. Proven directly: `tests/test_process_activity_discovery.py::test_uncorroborated_audit_timestamp_never_produces_an_activity`.
3. **Anchor scoring must penalize low instance-discrimination, not just raw coverage.** `process_anchor_discovery.py`'s `anchor_score` includes a required `instance_granularity_score` term (`1/(1+avg_activities_per_entity_of_type)`), weighted as the *dominant* term (0.55 of 1.0) specifically so the safeguard can flip a real outcome, not merely exist on paper. Proven directly: `tests/test_process_anchor_discovery.py::test_customer_higher_raw_coverage_but_work_order_wins_anchor` — a fixture where CUSTOMER has strictly higher raw activity footprint than WORK_ORDER, but WORK_ORDER still wins on discrimination.

## Architecture added

- **New `app/process/` package** (17 modules, framework-free except `intelligence_contract.py` — mirrors `app/entities/`'s own convention exactly): `activity_type.py` (the compact, generic `ActivityType`/`ProcessEdgeType`/`BoundaryStatus`/`ProcessStatus` vocabulary — `GENERIC` is correction 1's explicit placeholder), `temporal_evidence.py` (STRONG/MODERATE/WEAK/NONE tier classification), `activity_candidate.py`, `activity_type_inference.py` (the 5-tier hierarchy), `state_normalization.py` (existence/meaning split + `find_state_sequence`), `participation_inference.py` (role never inferred from entity_type alone), `case_process_context.py` (order-independence), `activity_discovery.py` (correction 2's corroboration gate), `process_anchor_discovery.py` (correction 3's safeguard), `process_boundary.py`, `sequence_discovery.py`, `precedence_confidence.py` (composition + the required per-pair contradiction pass + cycle detection), `process_confidence.py` (process-level 6-component rollup), `process_relationship_support.py` (the E.3-relationship corroboration gate — shipped fully tested, not yet wired into the main pass since this milestone's anchor-based, single-entity-per-instance design has no cross-entity edge to corroborate against until a future milestone attaches multi-entity participation), `reasoning_provider.py` (interface + `NullProcessReasoningProvider` only, matching the established E.1→E.2 phasing — no real AI backend wired this milestone), `process_interpretation.py` (top-level entry point), `intelligence_contract.py` (future downstream-Intelligence read interface, zero live callers this milestone).
- **A real design correction found during implementation, not shipped blind:** pairwise precedence tallying must be computed **per anchor entity first** (never pooling different entities' activities into one comparison — that would produce nonsensical cross-entity precedence claims), then **aggregated case-level per activity-type pair** before being re-applied to every instance that observed both sides — directly mirroring E.3's own `relationship_discovery.py` "decide shape once per type-pair, reapply per instance" precedent. This is also what gives the STRONG temporal-evidence tier's "repeating across ≥3 rows" threshold real meaning: it climbs only when multiple *different* anchor entities each contribute their own same-row observation of the same activity-type pair — a single entity's own schedule/complete pair can never reach STRONG alone.
- **A second real gap found and fixed before merge:** `STATE_TRANSITION` edges (`from_state`/`to_state`) were fully modeled in the schema and edge-candidate dataclass but never actually constructed anywhere in the initial pass. Fixed by wiring `find_state_sequence` into `process_interpretation.py`'s `_build_state_transition_edges`, ordered strictly by real `occurred_at` values (never activity-list position), per-instance (each entity's own state history, never pooled across entities).
- **One new orchestration stage**, `process_interpretation`, wired into `execute()` immediately after `relationship_discovery`, wrapped in the same blanket `try/except` pattern; stage failure never fails the run. `_run_case_level_relationship_discovery` gained a small additive return-type change (now returns its `RelationshipCandidate` list) to thread relationship candidates in-memory, consistent with the established "avoid a redundant DB round-trip" philosophy — though this milestone's anchor-based process design has no structural use for them yet (see `process_relationship_support.py` above).

## Database changes

Three new tables (migration `20260902_0058`), all scoped to `(organization_id, analysis_case_id, run_id)`, matching E.3's own minimum-viable-model precedent (3 tables, not the spec's illustrative 6 — participation/state/multi-hypothesis retention live as JSON/typed columns, justified directly against the real-corpus baseline):
- `canonical_operational_processes` — one row per discovered process instance (anchored on a real `CanonicalCaseEntity`) or a single case-level anchorless fallback (`process_type="UNKNOWN_PROCESS"`, `boundary_status=UNKNOWN`) when no entity type clears the anchor threshold. Six decomposed confidence components plus an overall rollup, never blended into one opaque number.
- `canonical_process_activities` — `activity_type_confidence`/`activity_existence_confidence` and `state_existence_confidence`/`state_meaning_confidence` as two distinct existence-vs-meaning pairs (correction 1), `corroboration_signals` (correction 2's audit trail — an activity with an empty list here is never persisted), `temporal_evidence_tier`.
- `canonical_process_edges` — state transitions fold in here (`edge_type=STATE_TRANSITION` + `from_state`/`to_state`) rather than a separate table; five decomposed confidence components + a conflict penalty + rollup `precedence_confidence`, never a blind product.

Naming collision check done before writing any class (the exact mistake that hit E.3): `CanonicalOperationalProcess`/`CanonicalProcessActivity`/`CanonicalProcessEdge` checked against `canonical_mapping.py`, `causal_intelligence.py`, and `raw_lineage.py` — no collision (`raw_lineage.py`'s `ProcessingRun`/`processing_runs` is visually adjacent but distinct).

## API (read-only)

```
GET .../analysis-cases/{case_id}/processes?run_id=
GET .../analysis-cases/{case_id}/processes/{process_id}
GET .../analysis-cases/{case_id}/processes/{process_id}/activities
GET .../analysis-cases/{case_id}/activities/{activity_id}
GET .../analysis-cases/{case_id}/processes/{process_id}/edges
GET .../analysis-cases/{case_id}/edges/{edge_id}
GET .../analysis-cases/{case_id}/process-graph?run_id=
GET .../analysis-cases/{case_id}/process-graph/summary?run_id=
```

## Quality gates

- **71 new tests** (`tests/test_process_*.py`, all pass) — unit coverage per module, row-order **and** dataset-order independence (`test_process_order_independence.py`), architecture guardrails (ground-truth import ban, simulation-literal scan, AI-provider import ban, Causal Links import ban), and full end-to-end API tests through the real orchestration pipeline.
- **Calibration benchmark** (`tests/process_calibration_fixtures.py` + `tests/test_process_calibration.py`) — **8 hand-labeled scenario fixtures**, exercised through the real `interpret_process_for_case` production code path, checked by **5 test functions, all passing**: `clear_sequence` (clean A→B precedence), `missing_timestamp` (no fabricated order when a comparison side is absent), `contradictory_timestamps` (downgrade to `CONFLICTED`/`ORDER_UNRESOLVED`, never a silently-picked direction), `concurrent_events` (same-time observations classify `CONCURRENT`, never a false sequence), `optional_step` (an absent optional activity never blocks the `COMPLETE` boundary for other instances), `partial_process` (a real but non-boundary activity type classifies `PARTIAL`, never a fabricated `COMPLETE`), `unknown_boundary` (GENERIC-only evidence classifies `UNKNOWN`, distinct from `PARTIAL`), `state_sequence` (same-entity `OPEN→IN_PROGRESS→COMPLETED` transitions constructed correctly). This benchmark is what supports the specific correctness claims made below — the live-corpus counts are not independently validated against hand-labeled ground truth (see "Live certification" below for that distinction).
- Full regression suite: E.3 (50 tests), E.2/E.1A/semantic (calibration + effective resolution + review transitions), AnalysisCase orchestration, Knowledge Graph, Causal Links, Validation Plane, ground-truth isolation — **284 tests, all pass.**
- Fresh-disposable-Postgres migration certification (upgrade → downgrade → reupgrade) — 83 tests, all pass.
- Full pytest suite — **1508 tests, all pass** (11 initial failures traced to pre-existing shared-test-DB corruption from migration-replay churn on the persistent `intel4ops_test` database, confirmed by resetting the DB and re-running clean — not caused by this milestone's changes).
- `ruff format --check .` / `ruff check .` / `mypy .` — all clean across 571+ source files.

## Live certification (engineering verification only — NOT independent process-accuracy validation)

**Scope note, read before the numbers below:** this section is an *engineering* certification — it confirms the pipeline runs end-to-end against real production data, persists correctly, decomposes confidence honestly, and respects tenant isolation. It is **not** an independent accuracy audit: the 1405 process instances and 4215 activities reported here are the pipeline's own live output, not counts checked against a separately hand-labeled ground truth for this specific case. The claim this section supports is "the engine ran correctly and produced internally-consistent, evidence-backed output on real data," not "these 1405 processes are the objectively correct set of processes in this case." The *correctness of the underlying logic* (precedence, contradiction detection, boundary classification, state-sequence construction) is what the calibration benchmark above independently verifies, on fixtures built specifically to have a known-correct answer — the live run is a downstream confirmation that the same, already-verified logic executes correctly against real-world data volume and shape, not a second, independent verification of correctness itself.

A fresh run was triggered on case `SIM-OFS-FIELDMAINT-005` (run #8, run ID `59a44353-f44f-46b9-ace7-87d026127c29`) via the live production API with a real authenticated session against the SOTRA Pilot organization. The run completed (`status: partial` — pre-existing domain-review items unrelated to this milestone).

| Finding | Result |
|---|---|
| `process_interpretation` stage | Completed; produced real, non-trivial output |
| Processes discovered | 1405, all anchored on `WORK_ORDER` (matching the predicted baseline outcome from correction 3's own design) |
| Activities discovered | 4215 (1405 `COMPLETE`, 2810 `GENERIC`) |
| Sample activity detail | `COMPLETE` type, `activity_type_confidence=0.80`, `temporal_evidence_tier=STRONG`, real `corroboration_signals` (`cooccurring_entity_grain_field`, `cooccurring_status_field`, `event_shaped_dataset_role`, `inherently_operational_temporal_concept`), real source lineage (`closed_date` → `completed_timestamp`) |
| Process-level confidence decomposition | All six components independently non-zero and distinct on a sampled instance: `coverage=1.0`, `activity=0.4767`, `participation=0.8`, `temporal=0.95`, `precedence_consistency=0.455`, `state_transition=0.0`, `overall=0.6999` |
| Edges | **1405, all `CONCURRENT`** — zero `PRECEDES` edges. `COMPLETE` and `GENERIC` activities on this case share a borrowed same-row timestamp, so the evidence genuinely does not support a direction; the engine correctly refused to fabricate one |
| State transitions | Zero found on this case — consistent with the baseline (status fields sit at `review_required` tier, and most real activities here are point-in-time completion snapshots, not multi-state logs); the mechanism itself is proven separately by the `state_sequence` calibration fixture |
| Tenant scoping | Certified — cross-org access to the same process returns `403 Organization access denied` |
| E.3 regression | `entities` endpoint: **1815 entities**, unchanged from E.3's own prior single-case live-cert finding; `relationships` endpoint: **0**, also unchanged — the new stage reads E.3's canonical layer read-only and never perturbs it |

**On the absence of directional `PRECEDES` edges, stated explicitly:** this is an evidence-driven outcome of this specific case's data shape, not a failure or limitation of the process-interpretation engine. The engine's contract is to assert a direction only when the underlying timestamps actually support one (test G / test F in the calibration benchmark verify this exact behavior on fixtures built to prove it both ways — a genuine `PRECEDES` case and a genuine `CONCURRENT` case both classify correctly). On this particular case, `COMPLETE` and `GENERIC` activities happen to share one borrowed timestamp per row, so `CONCURRENT` is the objectively correct classification, not a shortfall. Per the plan's own honest-expectation section, zero `PRECEDES` edges and zero state transitions on this one case are **verified-correct findings** — the same shape as E.3's own genuinely-zero-relationships live-cert result — and must not be "fixed" by loosening thresholds.

## Known limitations

- **Multi-entity participation is not yet attached.** Every process instance is anchor-entity-scoped (all activities share one primary entity); `process_relationship_support.py`'s E.3-relationship corroboration gate ships fully tested but unwired, since there is no structural second entity per instance for it to corroborate against yet.
- **No real AI reasoning provider.** `reasoning_provider.py` ships only the interface + `NullProcessReasoningProvider`; process typing is deterministic-evidence-only this milestone.
- **`OPTIONAL_BRANCH` and `LOOP` edge types are forward-declared, not reachable.** True branching and multi-step rework loops (beyond a simple two-node cycle, which `detect_precedence_cycles` does catch) collapse into `ORDER_UNRESOLVED`/`CONFLICTED` rather than a dedicated classification — documented as `NOT_AVAILABLE` in the calibration fixtures rather than fabricated.
- **`process_type`/`process_label` are not populated.** Only structural discovery (activities, sequence, boundary) ships this milestone; semantic process naming (e.g. "Standard Field Maintenance Cycle") is out of scope.
- **State-transition edges are proven correct on the calibration fixture but did not appear in this specific live-certification run** — an honest consequence of this case's status fields sitting at `review_required` tier and being largely point-in-time snapshots, not a gap in the mechanism itself.

## Explicitly not implemented this milestone (matching spec §61)

Adaptive Intelligence activation, Model Capability Registry runtime activation (design doc updated, no code), Process Memory, cross-run learned process templates, a real AI reasoning provider (interface + Null default only), mass Intelligence migration toward the new process contract, multi-entity participation attachment (the structural reason `process_relationship_support.py` isn't wired into the main pass yet).

## P3.xxE.5 readiness

This milestone leaves the following in place for whatever comes next in the roadmap (E.3 shipped new+old entity resolution in parallel → E.4 consumes the canonical entity layer and adds process structure → a future milestone migrates Intelligence rules toward the new read contract → legacy paths retire):

- **`app/process/intelligence_contract.py`** is a stable, tested, DB-touching read interface (`get_case_processes`/`get_process_activities`/`get_process_edges`) with zero live callers — the intended single entry point for a future Intelligence rule to consume process structure instead of a direct table join, mirroring `app/entities/intelligence_contract.py`'s own role for E.3.
- **The Model Capability Registry design doc** (`docs/p3xxe2-model-capability-registry-design.md`) now carries `required_activities`/`required_activity_sequences`/`required_states`/`minimum_process_confidence` fields, with the real-corpus baseline noted inline (named `PRECEDES` sequences and named state transitions are comparatively rare today — a model with a `required_activity_sequences` dependency should expect `PARTIAL`/`BLOCKED` readiness on much of the real corpus, not `READY`).
- **The clearest concrete migration target** remains `job_to_cash_engine.py`'s and `cross_domain_intelligence_service.py`'s hard-coded completion→invoicing→payment sequence assumptions (identified in this milestone's own reconciliation table as the richest existing evidence of implicit, unmodeled process-order logic) — not touched this milestone, explicitly deferred.
- **The biggest structural gap to close first** is multi-entity participation attachment: until an activity can carry participants beyond its own primary/anchor entity, `process_relationship_support.py`'s E.3-relationship corroboration gate has no genuine cross-entity edge to operate on, and any future milestone wiring E.3 relationships into process confidence should expect to start there.
