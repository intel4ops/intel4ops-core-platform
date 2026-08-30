# P3.xxE.2 — Pre-Implementation Semantic Baseline

Captured before any P3.xxE.2 code change, per the milestone's explicit baseline-first gate. This is a read-only measurement against the live deployed backend — no production code was modified to produce it.

## Baseline state

- Branch: `main`
- SHA: `b221ac743169162273718299859cb05d8b802eac`
- Tree: `a72e864b4fbe9952ee48dad0c3ed15440b69874f`
- PR #85 (P3.xxE.1A): merged
- Alembic head: `20260830_0055` (single head)
- Worktree: clean
- Deployment: healthy (`GET /api/v1/health` → `{"status":"ok"}`)

## Corpus / suite membership

The registered live corpus in the SOTRA Pilot organization (`organization_id = 41f93780-1840-426b-95ed-31a5a4478765`) — 11 real `AnalysisCase`s, matching the two known simulation families:

- `SIM-OFS-FIELDMAINT-001` .. `005` (5 cases)
- `SIM-OFS-RENTAL-011` .. `015` (5 cases, note: no `010` exists in this org)

This membership is a live-org fact, not a hard-coded production value — the harness discovered it via `GET /analysis-cases`, and this document is the only place the specific case list is recorded for evaluation purposes.

**Methodology note:** only `SIM-OFS-FIELDMAINT-005` had a run post-dating the P3.xxE.1 semantic-foundation deploy; the other 10 cases' latest runs predated semantic interpretation entirely (0 semantic fields each). To get a genuine full-corpus baseline rather than a 1/11 sample, a fresh run was triggered on each of the other 10 cases (confirmed with the user before doing so — see durable-records note below), then the full corpus was re-measured. All 11 cases now reflect real, current semantic interpretation output.

**Durable records created for this baseline:** 10 new `AnalysisCaseRun` rows (one per case, run_number 2 or 3 depending on case), each with its own real `SemanticDatasetProfile`/`SemanticRoleInterpretation`/`SemanticInterpretationDecision` rows. Permanent by the platform's append-only run-history design; no cleanup action exists or is intended, consistent with prior live-verification practice this session.

## Baseline status distribution (field level)

| Metric | Value |
|---|---|
| Cases | 11 |
| Datasets | 126 |
| Total fields | 636 |
| `AUTO_ACCEPTED` | 12 (1.9%) |
| `ACCEPTED_WITH_FLAG` | 84 (13.2%) |
| `REVIEW_REQUIRED` | 150 (23.6%) |
| `UNRESOLVED` | 390 (61.3%) |

**61.3% of real fields produce no candidate concept at all today.** This is the single largest opportunity for P3.xxE.2 — not "make auto-accept more aggressive," but "give the deterministic-only engine additional evidence sources (AI, neighbor-field, cross-dataset) so it can form a hypothesis at all" for the majority-unresolved case.

## Baseline dataset-role distribution

| Role | Dataset count |
|---|---|
| `labor` | 30 |
| `event` | 30 |
| `master` | 18 |
| `contract` | 18 |
| `work_order` | 12 |
| `inventory` | 6 |
| `schedule` | 6 |
| `transaction` | 6 |

- Mean role confidence: **0.606**, median: **0.600**
- Unknown-role dataset count: **0** (every dataset produced a role once re-run against current code)
- Mean secondary-role count per dataset: **0.476**

## Baseline confidence / ambiguity

- Mean field confidence: **0.258**
- Median field confidence: **0.0** (more than half of all fields sit at exactly zero — the `UNRESOLVED` majority)
- Fields with 2+ alternative candidates: **0** (0.0% ambiguity rate)
- Mean candidate count per field: **0**

**This is a significant finding for the Ambiguity Engine section of P3.xxE.2's design.** The current deterministic `candidate_generator` is effectively single-shot: it either proposes exactly one candidate or none — it never surfaces genuine multi-hypothesis competition (e.g. `amount` → `{invoice_amount, cost_amount, unit_price}` as the spec's own example describes) against this real corpus today. P3.xxE.2's evidence-generation layer needs to actually widen candidate generation (not just add AI) before the ambiguity engine has anything real to reconcile — today there is structurally nothing for it to disambiguate.

## Baseline review burden (P3.xxE.1A governance layer)

| Group | Count |
|---|---|
| `PENDING_REVIEW` | 234 |
| `NEEDS_RESOLUTION` | 389 |
| `RESOLVED` | 1 |
| **Total queue-visible** | **624** |

(624 + 12 `AUTO_ACCEPTED` = 636 total fields — `AUTO_ACCEPTED` items with no human version are correctly excluded from all three queue groups, confirming the P3.xxE.1A design behaves as built.)

Human review activity across the corpus is effectively nil except one deliberate action: the P3.xxE.1A live-certification `reject` → `correct` pair on `SIM-OFS-FIELDMAINT-005`'s `contract_id` field (the one `RESOLVED` item above). Confirmation/correction/rejection *rates* are therefore not statistically meaningful yet — there isn't enough real human-reviewed volume to compute them. This is itself a baseline fact: **99.8% of the review-eligible corpus (623/624) has never been touched by a human reviewer.**

## Baseline accuracy metrics

| Metric | Status |
|---|---|
| `DATASET_ROLE_ACCURACY` | `NOT_AVAILABLE` |
| `SEMANTIC_FIELD_ACCURACY` | `NOT_AVAILABLE` |
| `HIGH_CONFIDENCE_SEMANTIC_ACCURACY` | `NOT_AVAILABLE` |
| `FALSE_AUTO_ACCEPT_RATE` | `NOT_AVAILABLE` |
| `REVIEW_REQUIRED_RATE` | 23.6% (measurable directly, not accuracy-dependent) |
| `UNRESOLVED_RATE` | 61.3% (measurable directly, not accuracy-dependent) |

No semantic-specific ground-truth schema exists anywhere in this system today. `ValidationGroundTruth`'s normalized shapes (`expected_findings`, `leakage_truth`, `causal_truth`, `data_quality_truth`) have no field-level "this column means X" concept at all — there is nothing to compare `SemanticInterpretationDecision.selected_concept` against. Per the spec's explicit instruction, these are reported as `NOT_AVAILABLE`, not fabricated as zero. Building a real semantic-truth fixture (validation-only, never touched by production code) is listed as a P3.xxE.2 task (section 27); until that exists, "accuracy" claims for this milestone will necessarily rest on the directional/structural tests in section 31, not on this corpus's measured accuracy.

## What this baseline means for P3.xxE.2's design

1. The dominant opportunity is **coverage of the 61.3% `UNRESOLVED` bucket**, not tightening/loosening auto-accept thresholds on the already-decided 38.7%.
2. The **Ambiguity Engine has nothing to reconcile yet** — candidate generation itself needs to widen before "detect near-tied candidates" is a real behavior against this corpus, not just a hypothetical.
3. Review burden is almost entirely un-triaged (623/624 untouched) — any burden-reduction claim in the after-report must be read against a near-empty starting point, not a mature review backlog.
4. `AUTO_ACCEPTED` at 1.9% today is very conservative — the spec's guardrail ("false-auto-accept must not materially increase") has a very low bar to clear structurally, but also means there's real room to grow `AUTO_ACCEPTED` coverage if the added evidence genuinely earns it.
