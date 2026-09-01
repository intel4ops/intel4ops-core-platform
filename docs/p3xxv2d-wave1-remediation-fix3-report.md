# P3.xxV.2D — Systemic Remediation, Fix #3 Report

**Canonical Evidence Completeness Contract**

Scope discipline maintained: only the governed-publication-time completeness
question was touched. The early Trust pass, its sequencing, XDOM-A/XDOM-B's own
matching/temporal/revenue logic, entity confidence, and `ACCEPTED_WITH_FLAG`
semantics were all left frozen, per explicit instruction — confirmed unchanged in
Section L.

---

## A. Evidence-Contract Reconciliation

Traced the actual evidence path from source to publication before writing any code:

| Representation | Owner | Contents | Canonicalized? | Provenance preserved? | Current consumers | Suitable for completeness validation? |
|---|---|---|---|---|---|---|
| Raw source record | `_reload_canonical_dataframe` (re-parses the original file bytes, despite its name) | Original column names/values | **No** | n/a (it *is* the source) | `RequiredFieldCompletenessRule` (early Trust) | Only for RAW dataset-quality purposes — never for judging whether a MODEL received required canonical evidence |
| `AnalysisCaseFieldMapping` | `analysis_case_mapping_service.py` | One row per `(analysis_case_dataset_id, source_field, canonical_field, mapping_status)` | **Yes** (via `canonicalize_field()`'s alias table) | Yes — `source_field` always retained | `canonical_frames` construction (column rename), a few review-reason queries | Tells you *which* raw field maps to a concept, but carries no confidence/authority signal of its own |
| `SemanticInterpretationDecision` | `analysis_case_semantic_service.py` / E.1 pipeline | One row per `(analysis_case_dataset_id, run_id, source_field)`: `selected_concept`, `status`, `confidence` | Partially — its own concept vocabulary, independent of `canonicalize_field()`'s (V.2B's documented gap) | Yes — `source_field` always retained | E.3 entity formation (`resolve_effective_decision`), E.4 process interpretation, semantic review UI | Carries the actual authority signal, but keyed by the semantic layer's own concept names, not domain_registry's |
| `canonical_frames[dataset.id]` | Orchestration, post-mapping | The renamed (canonical-column) DataFrame | Yes | No (column rename discards which raw name fed it, at the DataFrame level) | XDOM-A/XDOM-B/MAINT-001's own candidate logic | This is what the RULES already consume — but has no confidence signal, so alone it can't answer "is this evidence GOVERNED," only "is a column present" |
| `AnalyticalReadinessDecision` (ARITHMETIC) | Trust engine, via `_DOMAIN_TRUST_RULES` | One row per `(trust_assessment_id, analytical_level)`: status + `blocking_rule_codes` | No — built from the raw-record check above | n/a | `governed_finding_publisher.publish()`'s sole readiness gate (before this fix) | This is the object `publish()` actually reads — its `required_field_completeness` contribution is exactly what's wrong |
| `EffectiveDecision` (`resolve_effective_decision()`) | `app/semantic/review.py` | Not persisted — computed on demand from a `SemanticInterpretationDecision` (+ optional human-governance version) | Governs whether a decision counts as "effective" | Carries `source`/`human_validated` through | E.3 entity formation only, before this fix | **This is the existing authority contract this fix reuses** — no new one was built |

**No new representation was created.** The fix's own module,
`canonical_evidence_completeness.py`, is a thin adapter joining two already-persisted
representations (`AnalysisCaseFieldMapping` + `SemanticInterpretationDecision`)
through the existing authority function (`resolve_effective_decision`) — every input
it consumes already existed for a different purpose.

## B. Canonical Completeness Architecture

```
RAW FIELD PRESENCE                    CANONICAL EVIDENCE AVAILABILITY
(RequiredFieldCompletenessRule,       (CanonicalEvidenceCompletenessRule,
 app/engines/trust_engine.py,          app/services/canonical_evidence_completeness.py,
 EARLY, per-dataset, pre-mapping)      LATE, at governed publication, post-mapping+semantic)
        |                                        |
record.get("operational_event_id")    for each required canonical field:
  -- literal raw dict-key lookup        find raw field(s) AnalysisCaseFieldMapping
  -- unaware mapping/semantics exist    resolved to it, check THAT field's own
  -- correct for raw QUALITY questions  SemanticInterpretationDecision via
                                        resolve_effective_decision -- satisfied only
                                        if HUMAN_CONFIRMED/HUMAN_CORRECTED/AUTO_ACCEPTED
```

The two rules are never merged and never call each other. `RequiredFieldCompletenessRule`
is completely unmodified (Section D confirms byte-identical behavior). The new rule
answers a strictly later, different question, using strictly later-available evidence.

## C. Effective Semantic Authority Policy Used

Reused **exactly** as `app/entities/entity_resolution.py` already applies it for
entity formation — no new policy was invented, no existing one was loosened:

| Semantic status | Grants canonical evidence? |
|---|---|
| `HUMAN_CONFIRMED` / `HUMAN_CORRECTED` | Yes (structurally unreachable within one run, exactly as documented in `entity_resolution.py` — `latest_version` is always `None` at run time; implemented correctly for a future cross-run milestone anyway) |
| `AUTO_ACCEPTED` | Yes |
| `ACCEPTED_WITH_FLAG` | **No** (collapses to "no effective concept" in `resolve_effective_decision`, unchanged) |
| `REVIEW_REQUIRED` | No |
| `UNRESOLVED` | No |

This bar is deliberately the *same* bar E.3 entity formation already uses — not a
weaker one invented to make findings publish. Its consequence for live data is
reported honestly in Section H/K, not engineered around.

## D. Implementation

- **New module**: `app/services/canonical_evidence_completeness.py` —
  `evaluate_canonical_evidence_completeness(required_canonical_fields, candidates)`,
  pure and framework-free. A required field is satisfied only when at least one
  `RawFieldSemanticEvidence` candidate mapped to it also clears
  `resolve_effective_decision`. Lineage (`source_field`, `semantic_status`,
  `semantic_confidence`) is carried on every result, satisfied or not.
- **Orchestration adapter**: `AnalysisCaseOrchestrationService._evaluate_canonical_evidence_completeness`
  queries `AnalysisCaseFieldMapping` (filtered to `AUTO_MAPPED` rows for the required
  fields) and, per matched raw field, the corresponding `SemanticInterpretationDecision`
  for the same `(dataset, run)`, adapts them into `RawFieldSemanticEvidence`, and
  delegates to the pure function above — no duplicated authority logic.
- **`governed_finding_publisher.publish()`**: gains exactly one corrected path. When
  the ARITHMETIC `AnalyticalReadinessDecision` is blocked for *exactly*
  `required_field_completeness` and the caller's canonical evidence result is
  satisfied, a **new, separate** `AnalyticalReadinessDecision` row
  (`READY_WITH_WARNINGS`, `blocking_rule_codes: []`, an explanation naming the
  satisfying raw fields) is persisted and used for that publication. **The original
  row is never mutated** — confirmed by a dedicated test (Section F, "original early
  Trust readiness decision is preserved unchanged"). This was required by a real
  downstream constraint discovered while implementing:
  `finding_platform_service._validate_execution_contract` independently re-queries
  the SAME `AnalyticalReadinessDecision` row by id and re-checks its status — so
  simply bypassing the check inside `publish()` without a genuinely READY row to
  point at caused a hard `FindingPlatformError` (confirmed by reproducing it during
  development). The new-row approach satisfies both this downstream re-validation
  and "never bypass Trust."
- **XDOM-A / XDOM-B**: both gained one new optional parameter,
  `canonical_evidence_completeness`, threaded straight into `GovernedFindingRequest`.
  No other line in either rule function changed.
- **MAINT-001**: deliberately **not** wired this pass (Section E).

## E. Model Exposure Matrix

| Capability | Required canonical fields | Raw-name dependent? | Alias/canonical mapping possible? | Exposed to the bug? | Wired this pass? | Observed consequence |
|---|---|---|---|---|---|---|
| XDOM-A (`run_asset_failure_to_lost_activity`) | `asset_id`, `failure_code`, `downtime_hours` (maintenance domain) | Yes | Yes | Yes | **Yes** | Still BLOCKED on all 10 Wave 1 cases for an *earlier* reason (domain classification / entity confidence, per V.2B) — this fix's effect on XDOM-A could not be empirically observed this wave, since it never reaches the completeness check at all |
| XDOM-B (`run_lost_activity_to_revenue_gap`) | `operational_event_id`, `asset_id` (operations domain) | Yes | Yes | Yes | **Yes** | Confirmed fixed for the `operational_event_id`/alias dimension (Section H); `asset_id`'s own confidence tier is now the observed limiting factor (Section K) |
| MAINT-001 (`run_maintenance_pack` / `detect_repeated_asset_failures`) | `asset_id`, `failure_code`, `downtime_hours`, `repair_cost` (maintenance domain) | Yes | Yes | Yes, in principle | **No** | Never reaches `publish()` in the current corpus (domain gate blocks it upstream, per V.2B/V.2C); wiring it would touch a function with zero current empirical coverage to verify against — deferred, not because it's architecturally hard |

Exactly 4 `governed_finding_publisher.publish()` call sites exist in the entire
codebase (confirmed by direct search): the 3 above, XDOM-A/XDOM-B/MAINT-001, plus
XDOM-B's own secondary `XDOM-DATA-LINKAGE-ISSUE` path (same function, same wiring,
inherits the fix automatically since it shares `run_lost_activity_to_revenue_gap`'s
new parameter).

## F. Tests

- **`tests/test_canonical_evidence_completeness.py`** — 11 pure unit tests: exact
  canonical name passes; alias-mapped field with sufficient authority passes;
  lineage preserved; missing concept fails; `REVIEW_REQUIRED`/`UNRESOLVED`/
  `ACCEPTED_WITH_FLAG` do not independently satisfy; a candidate for the wrong
  canonical field never cross-satisfies; multi-field partial satisfaction reports
  precisely which field is missing; zero required fields trivially satisfied.
- **`tests/test_canonical_evidence_completeness_publisher.py`** — real end-to-end
  orchestrator tests: a `work_order_id`-aliased, `"CLOSED"`-status operations
  dataset (with a second, corroborating dataset — required empirically, a
  single-dataset fixture never gave the semantic engine enough cross-dataset
  evidence to reach `AUTO_ACCEPTED` for the alias) now produces a genuine XDOM-B
  finding where it previously could not (`test_j_...`); the original early-Trust
  `AnalyticalReadinessDecision` row is confirmed **still blocked**, unchanged,
  alongside the new corrected `READY_WITH_WARNINGS` row (`test_original_early_trust_readiness_decision_is_preserved_unchanged`).
- Full XDOM-A/B, E.5 governed-activation, E.4 process, semantic-review-transition,
  and Trust (engine/rules/service/API, 4 files) suites re-run unmodified and green.

## G. PR / CI / Merge / Deploy

| Item | Value |
|---|---|
| Branch | `fix/p3xxv2d-canonical-evidence-completeness` |
| Implementation SHA | `4b602aa3278781904fb8089b1c1343a86d8b6979` |
| PR | [#99](https://github.com/intel4ops/intel4ops-core-platform/pull/99) |
| CI | Green — 19m33s (one `gh pr checks --watch` connectivity blip mid-poll, confirmed transient by re-querying `gh pr checks` directly, unrelated to the PR itself) |
| Merge SHA / final main SHA | `cfe6d2ad098fef990c8f731fdb696832c42321eb` |
| Deployment | Confirmed live functionally via the Wave 1 rerun below; one `502` observed on the first post-merge request (Render mid-redeploy), resolved within ~30s on retry, service healthy thereafter |
| Migration | None — pure Python logic change |
| Full pytest | 1619 passed (disposable Postgres reset before the run) |
| `ruff` / `mypy` | clean |

## H. Controlled Wave 1 Rerun

Fresh `AnalysisCase`s were created for all 10 Wave 1 simulations against post-merge
production, concurrency 1, sequential, reusing the same frozen customer-data CSVs.
No truth, manifest, or membership was touched.

**The exact NEXT-1 symptom is confirmed fixed.** Direct proof, live, on
FIELDMAINT-001's rerun: `work_order_id`'s semantic decision
(`status: auto_accepted, confidence: 0.98`) now grants effective canonical evidence
for `operational_event_id` — the identical mechanism proven in the synthetic
end-to-end test (Section F). This is the alias-vs-raw-name mismatch NEXT-1 named,
and it no longer blocks completeness.

**A second, separate, pre-existing requirement is now the observed limiting factor.**
`asset_id`'s own semantic decision on the same live dataset:
`status: accepted_with_flag, confidence: 0.8` — genuinely below the `AUTO_ACCEPTED`
bar `resolve_effective_decision` requires, unrelated to raw-vs-canonical naming
(`asset_id` is spelled identically in both the raw data and the canonical
vocabulary; this is a confidence-tier question, not a naming one). Confirmed
identically on FIELDMAINT-002, FIELDMAINT-007 (only one readiness row exists on each
case post-run — the original, still `blocked` — no corrected row was created,
because `canonical_evidence_completeness.satisfied` was `False` on `asset_id`
specifically). This is an honest, expected "peel the onion" result, not a fix
failure — see Section M/N.

## I. Before/After Completeness Failures

| Simulation | `required_field_completeness` failures BEFORE (raw check) | AFTER (raw check, unchanged) | Canonical evidence check result AFTER | Publisher rejected BEFORE | Publisher rejected AFTER |
|---|---|---|---|---|---|
| FIELDMAINT-001 | 227/227 records | 227/227 (unchanged — early Trust untouched) | `operational_event_id`: satisfied (work_order_id, auto_accepted 0.98). `asset_id`: **not satisfied** (accepted_with_flag 0.8) | Yes (arithmetic blocked) | Still yes — one required field remains unsatisfied |
| FIELDMAINT-002 | 254/254 | 254/254 | same pattern | Yes | Still yes |
| FIELDMAINT-005 | n/a (case-wide trust `failed`, unrelated) | unchanged | not evaluated (never READY) | Yes | Still yes (unrelated blocker) |
| FIELDMAINT-007 | 201/201 | 201/201 | same pattern | Yes | Still yes |
| RENTAL-001..018 (6) | Stage 0 already empty (no status column) — canonical evidence never evaluated | unchanged | not evaluated | n/a (never reaches publish) | n/a (unchanged) |

## J. Publisher Acceptance Changes

Zero net new findings this wave (Section K explains why), but the *mechanism* change
is real and directly observable: for the first time, a second, additional
`AnalyticalReadinessDecision` row *would* be created and used whenever canonical
evidence is genuinely sufficient — proven by the synthetic end-to-end test producing
a real finding through exactly this path. On live FieldMaintenance data specifically,
no such row was created on any of the 3 READY cases, because `asset_id`'s own
confidence never cleared the bar — confirmed by checking `AnalyticalReadinessDecision`
counts directly on FIELDMAINT-001's rerun: exactly one row (the original, still
blocked).

## K. Finding Metrics

| | Before Fix #3 | After Fix #3 |
|---|---|---|
| Findings (all 10) | 0 | 0 |
| TP / FP / FN | 0/0/788 | 0/0/788 |

Unchanged. Per instruction, this is not the primary metric — Section H/I/J establish
that the *mechanism* NEXT-1 named is fixed and independently verified; live
FieldMaintenance data simply carries a second, different, unresolved requirement
(`asset_id` confidence) that this fix correctly does not paper over.

## L. Safety / Regression

- **Trust never bypassed**: confirmed by a dedicated test — the original early-Trust
  `AnalyticalReadinessDecision` row is unchanged (still `blocked`,
  `required_field_completeness`) after governed publication succeeds via the new,
  separate row.
- **Unresolved semantics never treated as valid**: `ACCEPTED_WITH_FLAG`/
  `REVIEW_REQUIRED`/`UNRESOLVED` all confirmed, by unit test, to not independently
  satisfy — and this is exactly what blocks FieldMaintenance's `asset_id` live,
  proving the policy is real, not decorative.
- **No fields fabricated**: a required field with zero mapped-and-authoritative raw
  candidates always reports `satisfied: False`, `missing_canonical_fields` includes
  it.
- **Raw evidence lineage never removed**: every `CanonicalFieldEvidenceResult`
  carries `source_field`/`semantic_status`/`semantic_confidence`; the new
  `AnalyticalReadinessDecision.explanation` string names the satisfying raw fields
  explicitly.
- **Entity confidence unweakened**: `app/entities/*`, `entity_resolution.py`, and
  `entity_deduplication.py` were not touched; `resolve_effective_decision` itself
  was not touched.
- **No unrelated aliases allowed**: a candidate for a *different* canonical field
  never satisfies an unrelated required one (unit-tested).
- **No simulation-specific or filename-specific logic**: `evaluate_canonical_evidence_completeness`
  takes only `required_canonical_fields: frozenset[str]` and a generic candidate
  list; no simulation ID, business family, or filename appears anywhere in the
  changed files (confirmed by direct diff inspection).
- **Tenant isolation**: all 10 reruns scoped to the single pre-existing pilot
  organization, consistent with every prior fix pass.
- **Ground-truth isolation**: `canonical_evidence_completeness.py` is not in and does
  not import from `app.ground_truth_validation`; `test_validation_import_boundary.py`'s
  guardrail passed.
- **Full pytest**: 1619/1619 passed, including all XDOM-A, MAINT-001 (existing
  fixtures in `test_analysis_case_orchestration_service.py`,
  `test_analysis_case_review_required.py`, `test_analysis_case_semantic_orchestration.py`,
  `test_capability_shadow_stage.py`, `test_validation_dimension_matchers.py`), E.5,
  and Trust regression tests, unmodified and green.

## M. Fix Classification

**FIX #3 VALIDATED**

All 8 stated success criteria hold:
1. Canonical model requirements are now checked against governed canonical
   evidence, not raw dict-key presence — confirmed by the new module's logic and
   its live behavior on `operational_event_id`.
2. Source aliases (`work_order_id`) satisfy canonical field requirements when
   semantic authority is sufficient — confirmed live and by end-to-end test.
3. Raw lineage is preserved on every result — confirmed by test and by the
   persisted `AnalyticalReadinessDecision.explanation`.
4. Missing/unresolved evidence still fails — confirmed live (`asset_id`) and by
   unit test.
5. FieldMaintenance candidates are no longer rejected *solely* because raw source
   keys differ from canonical names — this is precisely and only what was fixed;
   confirmed both synthetically (a clean positive case) and live (the
   `operational_event_id` dimension specifically no longer blocks).
6. No Trust weakening — the original early-Trust decision is provably unchanged.
7. No false activation/finding regression — zero findings before, zero after, on
   the live corpus; XDOM-A/XDOM-B activation decisions identical to the Fix #2
   baseline on every case.
8. No simulation-specific code — confirmed by direct inspection of every changed
   file.

## N. Next Empirically Observed Blocker

**NEXT-2: `asset_id`'s semantic confidence sits at `ACCEPTED_WITH_FLAG` (0.8), not
`AUTO_ACCEPTED`, on live FieldMaintenance data.**

- **Layer**: Semantic interpretation (confidence engine), not raw naming and not
  Trust's rule logic — a different layer than NEXT-1.
- **Mechanism**: `resolve_effective_decision` requires `AUTO_ACCEPTED` (or human
  governance, structurally unreachable in-run) to grant effective canonical
  evidence; `ACCEPTED_WITH_FLAG` is deliberately, correctly excluded. `asset_id` is
  spelled identically in raw and canonical form here — this is not a naming
  mismatch, it is the confidence engine's own scoring of this particular column
  landing below the bar, for reasons not investigated this pass (out of scope,
  same class of question as V.2B's DC-2/entity-identity-confidence finding, though
  a distinct code path — `resolve_effective_decision` on a field decision here, vs.
  `entity_identity_confidence`'s corroboration-step formula there).
- **Affected simulations**: FIELDMAINT-001, 002, 007 (3/10) — the 3 cases where
  XDOM-B is READY and now correctly reaches the canonical-evidence check at all.
  FIELDMAINT-005 is blocked earlier (unrelated, case-wide trust failure). All 6
  Rental cases never reach this check (Stage 0 empty, unaffected).
- **Candidate counts**: all 227/254/201 work-order rows correctly pass the
  `operational_event_id` dimension; all fail the combined completeness check
  because `asset_id` alone does not clear its bar — a single missing dimension is
  enough to block the whole requirement set, by design (Section 5's mandated
  A/B separation, working exactly as intended here in the negative direction).
- **Downstream impact**: until `asset_id`'s confidence question is resolved (or
  found to be correctly low), governed publication cannot proceed on any
  FieldMaintenance case via this path, regardless of anything else — this is now
  the binding constraint, having fully superseded NEXT-1.

**Not investigated further or fixed this pass**, per instruction (explicitly listed
as out of scope: "do not alter entity confidence," "do not alter
`ACCEPTED_WITH_FLAG` semantics").

---

## Final Classification

**FIX #3 VALIDATED**
