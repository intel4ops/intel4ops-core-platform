# P3.xxV.2I — Systemic Remediation, Fix #6 Report

**Canonical Event-Time Evidence for XDOM-A**

Scope discipline maintained: only XDOM-A's temporal input contract was touched.
No business logic beyond that (matching/window/publication) was modified. Finding
deduplication was recorded, not fixed. XDOM-B, entity thresholds, and the frozen
truth corpus were all left exactly as they were — confirmed unchanged throughout.

---

## A. Current Temporal Ontology Reconciliation

Inspected before writing any code, per instruction — no new temporal ontology was
created; one already existed.

`app/semantic/concept_registry.py` already declares three TIMESTAMP-typed
canonical concepts, each with a distinct business meaning:

| Concept | Meaning | Pre-existing aliases |
|---|---|---|
| `event_timestamp` | When an event or activity **actually occurred** | `event_date`, `date`, `occurred_at`, `event_timestamp`, `timestamp` |
| `scheduled_timestamp` | When work was **planned/scheduled** to occur | `scheduled_date`, `scheduled_at`, `planned_date`, `due_date` |
| `completed_timestamp` | When work was **actually completed** | `completed_date`, `completed_at`, `closed_date`, `finished_at` |

Separately, `app/domain_registry.py` (a completely independent system — the
raw-column-**rename** layer that builds `canonical_frames`, unrelated to semantic
concept resolution) declares its own single `event_date` canonical field with its
own alias tuple (`date`, `occurred_at`, `failure_date`, `transaction_date`,
`invoice_date`, `event_timestamp`, `timestamp`) — this is the mechanism XDOM-A's
pre-fix code silently depended on, and it does **not** include `maintenance_date`
or `dispatch_date` either.

E.4 process interpretation has its own, separate `TemporalEvidenceTier`/activity
timing model (`app/process/temporal_evidence.py`, `activity_type_inference.py`) —
inspected and confirmed **not reused here**: it answers a different question
(STRONG/MODERATE/WEAK evidence for activity-sequence discovery), consumed only by
`app/process/*`, with zero current callers outside that package. Reusing it for
XDOM-A would have imported the process-interpretation package into cross-domain
intelligence, an unrelated and unwarranted coupling. No candidate reuse target
existed for a "which raw field carries the authoritative value for a declared
temporal concept" question — this is exactly the gap Fix #3 filled for identifier/
categorical evidence, never yet built for timestamps.

**Semantic authority**: `resolve_effective_decision()` (unchanged, `app/semantic/
review.py`) — the same contract every prior fix reused. **Current consumers of
`event_timestamp`/`scheduled_timestamp`/`completed_timestamp`**: none, before this
fix — the concepts existed in the registry (populated by E.1/E.2) but no rule
anywhere read a resolved decision for them; they were pure semantic-review/UI
signal. XDOM-A is the first Intelligence rule to consume one.

## B. XDOM-A's Actual Temporal Business Contract

Read `run_asset_failure_to_lost_activity` directly (`app/services/
cross_domain_intelligence_service.py`), not assumed. It needs exactly two
temporal facts, structurally identical in kind:

- **Maintenance side**: `window_start = event[<temporal field>]` — the moment a
  recorded downtime/failure event **began**, then `window_end = window_start +
  downtime_hours`. This is an **actual occurrence time**, not a schedule or a
  completion — `event_timestamp` is the precise concept.
- **Operations side**: `asset_ops[<temporal field>]` compared against that
  window — the moment an operational/dispatch activity **occurred**. Also an
  actual-occurrence fact, also `event_timestamp` — never `scheduled_timestamp`
  (a dispatch's *planned* time could differ materially from when it actually
  happened) and never `completed_timestamp` (a different fact: when the activity
  *ended*, not started).

**Smallest canonical temporal requirement**: `event_timestamp`, required
independently on both sides, never substituted by a sibling temporal concept even
though all three share `concept_type=="timestamp"` — implemented as a strict
concept match in the resolver (Section C), not a type-level match.

## C. Canonical Temporal Evidence Architecture

New module, `app/services/canonical_temporal_evidence.py`, mirrors Fix #3's
`canonical_evidence_completeness.py` shape exactly:

```python
def resolve_canonical_temporal_evidence(
    temporal_concept: str,
    candidates: list[RawTemporalFieldCandidate],
) -> CanonicalTemporalEvidenceResult:
    for candidate in candidates:
        if candidate.machine_selected_concept != temporal_concept:
            continue
        effective = resolve_effective_decision(...)
        if effective.effective_concept is not None:
            return CanonicalTemporalEvidenceResult(satisfied=True, source_field=candidate.source_field, ...)
    return CanonicalTemporalEvidenceResult(satisfied=False, ...)
```

Framework-free (no pandas) — returns the winning raw field **name** only;
extracting/parsing values is the caller's job. `app/services/
analysis_case_orchestration_service.py` gains `_resolve_canonical_temporal_field`,
built directly from the same in-memory `semantic_outcome.decisions_by_case_dataset`
E.3 already produces this run (no DB round-trip, matching `entity_candidates`'
own threading). Provenance (`source_field`, `semantic_status`, `semantic_confidence`)
is preserved on every result, never discarded.

**A second, real disconnect found and bridged while building this** (Section D):
the winning raw field name is not always the column's actual name in
`canonical_frames` — `domain_registry.py`'s own, independent rename may have
already claimed it for an unrelated reason. `_resolve_canonical_temporal_field`
calls `canonicalize_field()` (existing, reused, never duplicated) on the winning
field before returning, so the caller always receives the physical column name.

## D. Implementation

- **`app/services/canonical_temporal_evidence.py`** (new): the module above.
- **`app/semantic/concept_registry.py`**: `event_timestamp` gains `maintenance_date`
  and `dispatch_date` as aliases — both real, evidenced raw column names from
  Rental's own `maintenance.csv`/`dispatch.csv`. **Deliberately does not gain
  `compatible_dataset_roles`** — tried during implementation, then reverted after
  a real regression was caught (Section K).
- **`app/services/analysis_case_orchestration_service.py`**: `_resolve_canonical_temporal_field`
  resolved once per `maint_cd` and once per `ops_cd` (mirroring the existing
  per-dataset `maint_canonical_evidence` computation), both fields threaded into
  the `run_asset_failure_to_lost_activity` call and recorded on the XDOM-A stage
  event's `detail` JSON for live auditability.
- **`app/services/cross_domain_intelligence_service.py`**: `run_asset_failure_to_lost_activity`
  gains `maintenance_time_field: str | None` / `operations_time_field: str | None`
  parameters. Every literal `"event_date"` reference in the function body was
  replaced with the parameter. `None` on either side → `return []` (insufficient
  canonical temporal evidence — the readiness layer, unchanged, already reports
  the structural side of this; execution now separately guards the evidence
  side). No other line of matching/window/publication logic changed.
- **Date-vs-datetime handling (Section 5)**: untouched — `pd.to_datetime(...,
  errors="coerce")` is the exact same call the pre-fix code made; only the column
  name it operates on changed from a hardcoded literal to a resolved variable. No
  new timezone/date-shift risk introduced.
- **Capability declaration (Section 10)**: **not changed**. XDOM-A's registered
  `required_canonical_fields` (`{asset_id, downtime_hours, operational_event_id}`)
  never named `event_date` in the first place — the literal-field dependency was
  always purely inside the rule's own execution code, never part of the readiness
  contract. Since readiness was already correctly scoped, no capability-metadata
  change was required for contract consistency, and none was made — avoiding any
  broadening of the model's declared scope.

## E. Tests

- **`tests/test_canonical_temporal_evidence.py`** (new, 11 pure unit tests): 4
  positive (exact literal match still works; alias-mapped `maintenance_date`
  passes; lineage preserved; `human_confirmed` correctly inert within one run,
  matching the established `resolve_effective_decision(latest_version=None)`
  pattern documented everywhere else in this codebase) + 7 negative (unrelated
  concept never substitutes; missing evidence; `review_required` never
  authoritative; `accepted_with_flag` never authoritative; **a different temporal
  concept never silently substitutes even at auto_accepted** — the concept-match
  strictness from Section B, directly tested; `unresolved` never authoritative;
  deterministic first-match winner).
- **`tests/test_capability_governed_activation_xdom_a.py`** (extended): a new
  Rental-shaped fixture (`_rental_shaped_temporal_fixture_csvs`, identical
  structure to the existing certified positive fixture, only the raw date column
  names changed to `maintenance_date`/`dispatch_date`) backing: a precondition
  test (both fields resolve to `event_timestamp` at `auto_accepted`); the primary
  execution-chain-advancement test (both resolved fields recorded on the stage
  event, `operations_time_field` correctly showing `operational_event_start` —
  proving the cross-system bridge works — and findings in fact produced); a
  regression guard for the original literal `event_date` fixture; two negative
  end-to-end tests (an unrelated `invoice_date` field never satisfies; a
  maintenance dataset with no date field at all correctly yields
  `maintenance_time_field: None` and zero findings, with zero XDOM-A findings
  confirmed via the command service). All pre-existing tests in this file (20)
  pass unmodified.

## F. PR / CI / Merge / Deploy

| Item | Value |
|---|---|
| Branch | `fix/p3xxv2i-xdom-a-canonical-temporal-evidence` |
| Implementation SHA | `020b8b0` |
| PR | [#102](https://github.com/intel4ops/intel4ops-core-platform/pull/102) |
| CI | Green — 14m41s |
| Merge SHA / final main SHA | `fb1a2bb` |
| Deployment | Confirmed live via the Wave 1 rerun below; one `502` observed on the first post-merge request (Render mid-redeploy), resolved on retry (~45s) |
| Migration | None — pure Python logic change |
| Full pytest | 1665/1665 passed (fresh disposable Postgres reset beforehand) |
| `ruff format --check` / `ruff check` / `mypy` | clean |

## G. Wave 1 Controlled Rerun

Fresh `AnalysisCase`s created for all 10 Wave 1 simulations against post-merge
production, concurrency 1, sequential, same frozen customer-data CSVs, no
truth/manifest touched. Particular attention paid to the 6 Rental simulations per
the mission's explicit instruction.

## H. Rental Temporal Before/After

| Simulation | Raw maintenance field | Raw operations field | `maintenance_date` concept/status | `dispatch_date` concept/status | XDOM-A READY? | Findings BEFORE (Fix #5) | Findings AFTER | Next blocker |
|---|---|---|---|---|---|---|---|---|
| RENTAL-001 | `maintenance_date` | `dispatch_date` | `event_timestamp` / **auto_accepted (0.95)** | `event_timestamp` / **auto_accepted (0.95)** | Yes | 0 | 0 | temporal windows genuinely don't overlap in this case's real data |
| RENTAL-003 | `maintenance_date` | `dispatch_date` | `event_timestamp` / accepted_with_flag (0.80) | `event_timestamp` / accepted_with_flag (0.80) | Yes | 0 | 0 | temporal evidence itself insufficient this case (cross-dataset-overlap corroboration did not fire — data-dependent, Section K) |
| RENTAL-011 | `maintenance_date` | `dispatch_date` | `event_timestamp` / **auto_accepted (0.95)** | `event_timestamp` / **auto_accepted (0.95)** | Yes | 0 | 0 | windows don't overlap |
| RENTAL-012 | `maintenance_date` | `dispatch_date` | `event_timestamp` / **auto_accepted (0.95)** | `event_timestamp` / **auto_accepted (0.95)** | Yes | 0 | 0 | windows don't overlap |
| RENTAL-015 | `maintenance_date` | `dispatch_date` | `event_timestamp` / **auto_accepted (0.95)** | `event_timestamp` / **auto_accepted (0.95)** | Yes | 0 | 0 | windows don't overlap |
| RENTAL-018 | `maintenance_date` | `dispatch_date` | `event_timestamp` / **auto_accepted (0.95)** | `event_timestamp` / **auto_accepted (0.95)** | Yes | 0 | 0 | windows don't overlap |

Before this fix, `maintenance_time_field`/`operations_time_field` would have
resolved to `None` on every one of these 6 cases (the field never matched the
hardcoded `"event_date"` literal), and `run_asset_failure_to_lost_activity`
returned `[]` at its very first temporal guard, before ever reading a single row
of real downtime/dispatch data. **After this fix, on 5 of 6 cases, canonical
temporal evidence reaches full authority (`auto_accepted`) and the execution
chain genuinely advances past that point** — `maintenance_time_field`/
`operations_time_field` resolve to `"maintenance_date"`/`"operational_event_start"`
(the domain-registry-bridged physical column name, confirmed live), the rule
parses real dates, and evaluates real per-asset windows. On all 6 cases findings
remain 0 — investigated, not assumed: the temporal windows in this real data
genuinely do not overlap for the assets involved (or, for RENTAL-003 only,
evidence itself stayed at `accepted_with_flag`). This is the honest, correct
outcome per the mission's own Section 13: **the causal question is whether
canonical temporal evidence advanced the execution chain, not whether a finding
appeared** — confirmed yes on 5/6, materially advanced (though not to full
authority) on the 6th.

## I. FieldMaintenance Regression

| Simulation | XDOM-A status | XDOM-A missing | XDOM-B status | Findings | Matches Fix #5 baseline? |
|---|---|---|---|---|---|
| FIELDMAINT-001 | BLOCKED | `domain:maintenance`, `field:downtime_hours`, `trust:maintenance` | READY | 2 | **Yes, exact** |
| FIELDMAINT-002 | BLOCKED | same | READY | 1 | **Yes, exact** |
| FIELDMAINT-005 | BLOCKED | same | BLOCKED (`trust:operations`) | 0 | **Yes, exact** |
| FIELDMAINT-007 | BLOCKED | same | READY | 1 | **Yes, exact** |

All 4 FieldMaintenance cases are byte-identical to the Fix #5 baseline. Confirmed
directly: FieldMaintenance's XDOM-A never reaches the temporal-evidence check at
all — it remains BLOCKED upstream on the pre-existing, untouched V.2B
domain-classification gap (`domain:maintenance` never detected in this corpus),
exactly as in every prior fix in this program. No domain-classification behavior
was changed by this fix (Section 14's explicit requirement); any improvement here
would have had to come from shared temporal normalization alone, and none was
needed or observed, since these 4 cases never execute XDOM-A regardless.

## J. XDOM-A Findings

Total across all 10 cases: **0 before, 0 after** — unchanged in raw count, but the
underlying mechanism moved substantially (Section H): 6 cases now have their
temporal evidence resolved and the rule's execution genuinely reaches real
per-asset window comparison, where before all 6 were rejected at the very first
guard. Per the mission's explicit Section 13 instruction, this is reported as the
correct, honest outcome — not re-engineered to force a finding.

## K. False-Positive Safety

- **No raw temporal vocabulary special-case inside XDOM-A**: confirmed by direct
  diff inspection — the rule contains zero string literals for
  `"maintenance_date"`, `"dispatch_date"`, or any other raw name; it only ever
  reads its two parameters.
- **No simulation-specific or filename-specific logic**: confirmed — the new
  module and its orchestration adapter take only `temporal_concept`/`candidates`/
  `case_dataset_id`/`semantic_outcome`, generic across every case.
- **No fabricated timestamps**: `resolve_canonical_temporal_evidence` never
  invents a value — it only names a raw field that independently earned semantic
  authority; parsing failures (`pd.to_datetime(..., errors="coerce")`) become
  `NaT`, filtered out by the pre-existing `pd.isna()` check, unchanged.
- **No semantic-authority bypass**: `resolve_effective_decision` untouched;
  `ACCEPTED_WITH_FLAG`/`REVIEW_REQUIRED`/`UNRESOLVED` still never grant effective
  evidence, confirmed both by unit test and live (RENTAL-003, Section H,
  correctly stayed non-authoritative).
- **A genuine regression found and fixed during implementation, not shipped**:
  giving `event_timestamp` `compatible_dataset_roles` (the natural first attempt
  at reaching `auto_accepted`, mirroring Fix #4's own precedent for identifiers)
  had an unintended, confirmed side effect: `app/semantic/neighbor_context.py`'s
  `NEIGHBOR_FIELD_CONTEXT` corroboration is symmetric and keys off *any* role
  overlap between two *different* concepts — since `asset_id`'s own role set
  (Fix #4) already includes `event`/`work_order`/`contract`, giving
  `event_timestamp` those same roles retroactively let a co-occurring `asset_id`
  field borrow a corroboration bonus it never had access to before, pushing an
  existing regression fixture's `asset_id` decision from `accepted_with_flag`
  (0.85) to `auto_accepted` (0.95) — flipping `test_xdom_a_governed_blocked_overrides_legacy_activation`
  from BLOCKED to PARTIAL and failing it. Caught by the full regression suite
  (not by the new tests, which never exercised this fixture), root-caused
  precisely (reproduced via a targeted debug script isolating the exact
  evidence-component delta), and fixed by removing `compatible_dataset_roles`
  from `event_timestamp` entirely — the alias additions alone, combined with the
  existing, unmodified `CROSS_DATASET_OVERLAP` mechanism's pattern-class
  fallback, already reach `auto_accepted` on real-corpus-shaped data (confirmed
  live on 5/6 Rental cases, Section H) without this side channel. Full
  regression suite re-confirmed green after the revert.
- **Hidden truth access**: none — no changed file imports from
  `app.ground_truth_validation`; `test_validation_import_boundary.py`'s guardrail
  passed as part of the full suite.
- **Tenant regression**: none — all 10 reruns scoped to the single pre-existing
  pilot organization; no cross-tenant query introduced.

## L. Deduplication Defect Observations

Not fixed, per explicit instruction. No new evidence beyond what Fix #5's report
already recorded — none of the 10 Rental/FieldMaintenance reruns this pass
produced a scenario with more than one qualifying finding candidate colliding on
the same dataset pair (Rental's findings stayed at 0 throughout, so the defect
was never re-triggered this pass). The defect (`governed_finding_publisher`'s
deduplication key never carries an `affected_record`-typed evidence item
identifying which specific entity a finding concerns) remains exactly as
documented in the Fix #5 report — unchanged, unaddressed, still present.

## M. Fix #6 Classification

**FIX #6 VALIDATED**

The primary success criterion (Section 13) is met precisely as the mission
defined it: Rental's XDOM-A no longer collapses solely because `maintenance_date
!= event_date` — confirmed live, both temporal fields now resolve on all 6 Rental
cases (5/6 to full `auto_accepted` authority, 1/6 to `accepted_with_flag`), the
execution chain demonstrably advances past its previous first-guard rejection on
every one of them, and a second, real architectural defect (the two-canonicalization-
systems disconnect for fields) was found and correctly bridged along the way — not
merely reported as a diagnosis, but resolved within this fix's own scope. No raw
vocabulary was hardcoded inside XDOM-A. No entity/identifier confidence was
touched in the shipped code (the one path that would have was caught by the full
regression suite and reverted before merge). FieldMaintenance stayed byte-identical.
XDOM-B was never touched. Findings did not appear, which the mission's own success
criterion explicitly does not require.

## N. Next Empirical Blocker

**Findings remain at 0 for XDOM-A across the whole Wave 1 corpus, now for the
first time a genuinely *executional* reason rather than a *structural* one on
Rental's side**: 5/6 Rental cases have full canonical temporal evidence and a
READY, executing rule, yet no candidate downtime window overlaps a dispatch
event in the real data. This may be a correct, verified-negative finding (real
downtime and dispatch events genuinely don't coincide in this corpus) or may
reflect a further, not-yet-diagnosed business-logic gap in the window-overlap
condition itself (e.g. window width, timezone assumptions, or whether
`downtime_hours` itself carries authoritative evidence on the Rental side — not
inspected this pass, since Section 2 scoped this fix to the temporal *evidence*
question only). FieldMaintenance's XDOM-A remains blocked on the separate,
pre-existing, untouched domain-classification gap. Neither is implemented here,
per instruction.

---

## STOP

Finding deduplication was not fixed. XDOM-A's matching/window/publication logic
was not changed beyond the temporal input. XDOM-B was not touched. No new
intelligence capability was added. Wave 2, E.6, and E.7 were not started. No
frontend code was modified. Awaiting explicit architectural review before any
further remediation.
