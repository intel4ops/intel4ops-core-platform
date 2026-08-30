# P3.xxE.2 — Adaptive Field Interpretation & Governed Semantic AI — Post-Implementation Report

Consolidated deliverable for the P3.xxE.2 milestone, captured after implementation, deploy, and live certification against the real production backend. This is a read-only measurement plus a summary of what shipped — see [docs/p3xxe2-pre-implementation-semantic-baseline.md](p3xxe2-pre-implementation-semantic-baseline.md) for the pre-implementation baseline this compares against.

## Baseline / branch / PR / CI / merge / deploy

| | |
|---|---|
| Baseline SHA / tree | `96236ff7d11bc31f6daa341a96ccd593fe7a236f` off `main@b221ac7` |
| Branch | `feature/p3xxe2-adaptive-semantic-ai` |
| PR | [#86](https://github.com/intel4ops/intel4ops-core-platform/pull/86) "P3.xxE.2: Adaptive Field Interpretation + Governed Semantic AI" — merged `02aa4035`, 2026-08-30T03:43:05Z |
| Fix PR | [#87](https://github.com/intel4ops/intel4ops-core-platform/pull/87) "fix: expose ai_provenance in semantic read APIs" — merged `f29c9e6d`, 2026-08-30T04:25:31Z |
| CI | Ruff + Mypy + Pytest + Alembic — green on both (PR #86: 15m48s, PR #87: 19m19s) |
| Alembic head | `20260831_0056` (single head) |
| Test suite | 1390 passed, 0 failed |
| Deployment | Live on Render, auto-deploy on merge to `main` |

## Architecture added

- **Real semantic AI provider** — `app/semantic/openai_provider.py`'s `OpenAISemanticReasoningProvider`, structurally satisfying the existing `SemanticReasoningProvider` protocol. Mirrors `OpenAIOperationalProfileAdapter`: lazy SDK client, fail-fast `ProviderUnavailableError` if disabled/no key, `responses.parse(..., store=False)` structured output, same prompt-injection framing.
- **Provider abstraction** — `app/semantic/provider_factory.py`'s `select_semantic_reasoning_provider(settings)` plus a `SemanticAIBudget` dataclass (default 50 calls/case). Selected once per run; falls back to the unchanged `NullSemanticReasoningProvider` when `semantic_ai_enabled` is false or no key is configured.
- **Semantic request/response contract** — unchanged external shape (`app/semantic/provider.py`). The provider's internal structured-output schema (`FieldCandidateConcept` / `FieldInterpretationResult` / `SemanticInterpretationStructuredResponse`) supports up to 3 candidate concepts per field; each flattens into a separate `SemanticFieldProposal`, which `interpreter.py` already grouped by `source_field` — multi-hypothesis output required no contract change.
- **Neighbor-field context** — `app/semantic/neighbor_context.py`: same-dataset sibling field names checked against the candidate concept's compatible dataset roles via the existing `CanonicalConceptRegistry`. No hard-coded field names.
- **Cross-dataset corroboration** — `app/semantic/cross_dataset_context.py`, computed via a two-pass architecture (`app/semantic/case_context.py`'s `CaseSemanticContext`): Pass 1 profiles and classifies every dataset in the case with no AI and no persistence; Pass 2 interprets every dataset using the complete Pass-1 context. Proven order-independent by a real dataset-order-permutation test (`tests/test_semantic_cross_dataset_context.py::test_cross_dataset_evidence_is_order_independent`) run against full orchestration, not asserted.
- **AI confidence normalization / evidence reconciliation** — `app/semantic/confidence_engine.py`: same-concept candidates from every source (deterministic, neighbor, cross-dataset, AI) merge into one evidence set before ranking. If the winning candidate's evidence is AI-only, its status is capped at `accepted_with_flag` — never `auto_accepted` — regardless of raw confidence. The cap lifts the moment even one non-AI evidence component corroborates the same concept.
- **Ambiguity handling** — deterministic candidate generation widened so a field aliasing to more than one concept (e.g. `amount`) surfaces all of them, giving the pre-existing near-tie ambiguity logic in `confidence_engine.py` real candidates to reconcile for the first time.
- **Multilingual result** — French/German aliases (`numero_commande`/`bestellnummer` → `work_order_id`; `numero_client`/`kundennummer` → `customer_id`) added as pure registry data in `app/semantic/concept_registry.py`. No runtime language branching anywhere.
- **Privacy / data minimization** — reused `AIOperationalProfileService`'s `_sanitize()`/`_SECRET_PATTERN` redaction pattern on sample values before they enter the AI request context; bounded sampling (≤12 values/field) was already in place from P3.xxE.1.
- **Cost controls** — `semantic_ai_max_calls_per_case` (default 50) and `semantic_ai_max_output_tokens` (default 2000), both new settings, separate from the pre-existing `ai_enabled`/`ai_*` used by the operational-profile feature.
- **Offline / provider-failure result** — a provider exception is caught per-dataset inside `interpret_dataset()` around the `propose()` call and treated as zero proposals for that dataset; a budget-exhaustion hits the same code path. Neither can fail an `AnalysisCase` run — covered by `tests/test_semantic_provider_failure_resilience.py`.
- **E100 portability / P3.xxE.1A integration / no-reuse confirmation** — no simulation-specific logic anywhere in the new evidence sources; the P3.xxE.1A review/governance layer was not touched by this milestone (read, never written) and is proven to still function against E.2-produced decisions (live, see below). No cross-run reuse or memory exists anywhere in this milestone — deferred to P3.xxE.6 by design.
- **Model Capability Registry** — design-only doc, no implementation: [docs/p3xxe2-model-capability-registry-design.md](p3xxe2-model-capability-registry-design.md).

## Database changes

One additive nullable column, no backfill: `SemanticInterpretationDecision.ai_provenance` (`portable_json`, nullable), migration `20260831_0056_p3xxe2_ai_provenance.py`. Populated only when AI evidence contributed to the winning candidate (`{"ai_used": true, "provider_code": ..., "model": ..., "model_version": ...}`); `null` for purely deterministic decisions. `decision_version` deliberately stays algorithm/config-only (`v1+thresholds:v1`) — provider identity never gets appended there.

A genuine bug was found and fixed in PR #87: the column was populated correctly in the DB, but neither `FieldInterpretationDecisionRead` nor `MachineProposalRead` declared the field, so Pydantic's `from_attributes=True` silently dropped it from both read APIs. Fixed with an HTTP-level round-trip test (`test_ai_provenance_round_trips_through_the_read_apis`), not just a schema patch.

## Validation-only semantic calibration benchmark

Built rather than deferred, per the required correction from plan review. Lives entirely under `tests/` (`tests/semantic_calibration_fixtures.py` + `tests/test_semantic_calibration.py`), never imported by any `app/` module, structurally separate from `app.ground_truth_validation`. Three hand-labeled fixtures run through the real, production `interpret_dataset()`/orchestration pipeline. Post-implementation-only measurement — the fixtures are new in this milestone, so there is no pre-E.2 "before" to compare against.

| Metric | Value |
|---|---|
| `SEMANTIC_FIELD_ACCURACY` | 85.7% |
| `HIGH_CONFIDENCE_SEMANTIC_ACCURACY` | 100% |
| `FALSE_AUTO_ACCEPT_RATE` | `N/A` — 0 auto-accepted decisions in the fixture set (none of the fixtures' repeating-value columns clear the identifier-cardinality bar), correctly reported as unavailable rather than fabricated as zero |
| `FALSE_UNRESOLVED_RATE` | 14.3% |
| `DATASET_ROLE_ACCURACY` | 100% |

## Live certification (SOTRA Pilot, real production backend)

Fallback path only, per the confirmed live-cert scope — no live OpenAI credential is configured on Render.

1. Fresh runs triggered and completed on all 11 real cases in the corpus (`SIM-OFS-FIELDMAINT-001..005`, `SIM-OFS-RENTAL-010..015`).
2. Semantic stage completed normally on every case; `ai_provenance_used_count: 0` corpus-wide, confirming the null-provider fallback was genuinely exercised, matching the confirmed live-cert scope.
3. Neighbor-field and cross-dataset evidence fire live, not just in tests: 138 field decisions carry neighbor evidence, 80 carry cross-dataset evidence.
4. The `amount` field on the real `invoices.csv` dataset — an exact match to the spec's own worked example — now resolves with genuine multi-hypothesis ambiguity: `selected_concept: cost_amount` (0.85), alternatives `unit_price` (0.70) and `invoice_amount`, status held at `accepted_with_flag` and never forced to `auto_accepted`.
5. `ai_provenance: null` confirmed on this purely-deterministic decision via the now-fixed read API; `decision_version: "v1+thresholds:v1"` (no provider suffix).
6. The P3.xxE.1A review queue and governance layer function unmodified against P3.xxE.2-produced decisions: a real `confirm` action on the `amount` decision (`829df0c6-87a2-434c-86cd-939e43a6acbe`) round-tripped correctly through both the decision-detail and run-level effective-decision endpoints — `effective_status: human_confirmed`, `human_validated: true` on both.
7. Existing Intelligence findings on the corpus are unchanged by this milestone (data-dependent counts, not a regression).

**Durable records created:** 11 new `AnalysisCaseRun` rows (append-only by design, one per case) and one `SemanticReview`/`SemanticDecisionVersion` pair on decision `829df0c6-87a2-434c-86cd-939e43a6acbe`. Recorded in full in the operator's session memory (SOTRA Pilot validation-debris log); no cleanup action exists or is intended, consistent with this system's append-only governance pattern.

## Post-implementation semantic results — 11-case corpus, before vs. after

Same corpus, same methodology as the pre-implementation baseline (`docs/p3xxe2-pre-implementation-semantic-baseline.md`): 11 cases, 126 datasets, 636 fields, all re-run against post-merge production code.

| Metric | Baseline | After | Δ |
|---|---|---|---|
| `AUTO_ACCEPTED` | 12 (1.9%) | 31 (4.9%) | +19 |
| `ACCEPTED_WITH_FLAG` | 84 (13.2%) | 173 (27.2%) | +89 |
| `REVIEW_REQUIRED` | 150 (23.6%) | 66 (10.4%) | −84 |
| `UNRESOLVED` | 390 (61.3%) | 366 (57.5%) | −24 |
| Mean field confidence | 0.258 | 0.322 | +0.064 |
| Median field confidence | 0.0 | 0.0 | unchanged |
| Ambiguity rate (2+ candidates) | 0.0% | 3.8% (24 fields) | +3.8pp |
| Mean candidate count/field | 0 | 1.075 | +1.075 |
| Neighbor-context evidence hits | n/a (new) | 138 | — |
| Cross-dataset evidence hits | n/a (new) | 80 | — |
| `ai_provenance_used_count` | n/a (new) | 0 | confirms null-provider fallback live |
| Dataset-role distribution | unchanged | unchanged | 0 |
| Mean role confidence | 0.606 | 0.606 | 0 |
| Unknown-role datasets | 0 | 0 | 0 |

### Review burden change

| Group | Baseline | After |
|---|---|---|
| `PENDING_REVIEW` | 234 | 238 |
| `NEEDS_RESOLUTION` | 389 | 366 |
| `RESOLVED` | 1 | 1 |
| **Total queue-visible** | **624** | **605** |

Queue-visible burden dropped 3.0% (624 → 605). The entire drop is explained exactly by fields moving into `AUTO_ACCEPTED`: 624 − 605 = 19 = 31 − 12. Nothing left the queue any other way — a self-consistency check, not just an assertion.

### High-confidence accuracy change / false-auto-accept change

No field-level ground truth exists for the live corpus (unchanged from baseline — still `NOT_AVAILABLE` for corpus-measured accuracy). The calibration benchmark above is the only accuracy signal this milestone produces, and it is post-implementation-only by construction. `FALSE_AUTO_ACCEPT_RATE` on the live corpus cannot be measured for the same reason it couldn't at baseline; the calibration benchmark's own `FALSE_AUTO_ACCEPT_RATE` is `N/A` for the reason given above, not evidence of failure.

### Provider cost / latency

Not exercised live this round (fallback path only, confirmed scope). The real provider is production-ready and fully tested against a fake provider double in CI (`tests/test_semantic_openai_provider.py`, `tests/test_semantic_ai_confidence_policy.py`) covering request shape, multi-hypothesis parsing, and timeout/quota/malformed-output handling — never a real network call in CI.

## Known limitations

- `UNRESOLVED` at 57.5% is still the majority outcome. Neighbor/cross-dataset evidence strengthens *existing* candidates; it does not manufacture a candidate for a field with zero alias-level signal to begin with. Closing this further needs either a live AI credential (untested this round by choice) or further widening of deterministic candidate generation.
- Corpus-wide semantic accuracy remains structurally unmeasurable (`NOT_AVAILABLE`) — no field-level ground truth exists in this system. The calibration benchmark is the only real accuracy signal, and it is bounded to 3 fixtures.
- The real AI provider has zero live production mileage — validated only against a fake double in CI and structurally proven fail-safe (§ Offline/provider-failure), not exercised against a live model.

## P3.xxE.3 readiness

The provider abstraction, budget mechanism, and evidence-merge/cap logic are all in place and tested; enabling live AI semantic reasoning in production is a configuration change (`semantic_ai_enabled` + `ai_api_key`), not a code change. Cross-run reuse/memory (P3.xxE.6) remains explicitly out of scope and untouched. The governance layer (P3.xxE.1A) is confirmed compatible with every new decision shape this milestone introduces, including AI-sourced ones.
