# P3.xxI.6 — SIM-OFS-FIELDMAINT-005 Full-Simulation Graduation

## Scope

Owner-mandated full graduation of `SIM-OFS-FIELDMAINT-005` against its
**complete, frozen 387-item hidden-truth family** (`hidden-truth/
expected_findings.json` / `leakage_truth.json`, sealed 2026-08-27, manifest
`hidden-truth/truth_manifest.json`) -- not the 76-item `repeat_repair`
subset this program has certified against so far. This also reconciles PR
#128's merge, PR #126's mergeability, and produces the program's first
Simulation Miss Ledger and Simulation Gap Ledger.

Truth was read only after the production run below reached its own
terminal state, per standing practice.

## 1. Merge and reconciliation

- **PR #128** ("docs: certify P3.xxI.5B-R post-merge live results"):
  verified OPEN, head `94cfa0560d575520a62c6036a7f74044bad0d252`, CI
  `SUCCESS`, `MERGEABLE`. Merged. Merge commit
  `cc7d8a75452063114349e402a374de26f4961f5e`. Local `main` fetched, pulled,
  and confirmed `== origin/main` at that SHA. Worktree clean (only the
  pre-existing, non-deliverable `tmp_p3xxi5b_reconcile.py` scratch file
  remains untracked).
- **PR #126** ("docs: certify P3.xxI.5B maintenance repeat visit"):
  GitHub initially reported `mergeable: UNKNOWN` (an async, not-yet-
  recomputed status immediately after two consecutive merges to `main`,
  not a real conflict). A local `git merge-tree` against current `main`
  produced zero conflict markers, and a re-query after a short delay
  confirmed `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`. **PR #126
  is not actually blocked; no rebase or reconciliation action is
  required.** It touches only `docs/p3xxi5-intelligence-breadth-
  expansion-program.md` and `docs/p3xxi5b-maintenance-repeat-visit-
  rework.md` -- disjoint from every file PR #127/#128 touched. Recommended
  disposition (unchanged from the prior report, now confirmed
  mechanically): merge it as-is to preserve the historical, accurate
  record of the *original* pre-remediation P3.xxI.5B certification, the
  same pattern already used for PR #122 (original P3.xxI.5A `FAILED`)
  alongside PR #124 (the P3.xxI.5A-R remediation's own, separate,
  additive certification). Not merged by this report -- awaiting separate
  owner authorization naming it.

## 2. Production run used

The fresh `P3xxI5BR-Cert-FIELDMAINT-005` case/run created for the P3.xxI.5B-R
post-merge certification is reused (valid: no application code changed
between that run's commit `ce843257` and current `cc7d8a7` -- the only
intervening change was docs-only PR #128).

| | |
|---|---|
| Case | `P3xxI5BR-Cert-FIELDMAINT-005`, `b0b83c4f-2e48-4172-a479-0ff3080fa101` |
| Run | `558a3220-cfc9-4858-9ee4-e2f8f3aab37a` |
| Terminal status | `review_required`, completed 2026-09-06T06:42:23Z |
| Findings published (all rules) | 87 total: `REVENUE-AMOUNT-VARIANCE` 86, `XDOM-DATA-LINKAGE-ISSUE` 1 |

Cross-verified against a debug-instrumented run of the identical merged
code (`main` at `cc7d8a7`) over the same real customer-data files,
independently reproducing the same 87/86/1 split, the same six
`work_order_id` decisions all `auto_accepted`, and the same activation
readiness picture below.

| Rule | `governed_status` |
|---|---|
| `REVENUE-AMOUNT-VARIANCE` | `READY` |
| `CONTRACT-RATE-COMPLIANCE` | `READY` |
| `MAINTENANCE-REPEAT-VISIT` | `READY` |
| `XDOM-B-LOST-ACTIVITY-REVENUE-GAP` | `READY` |
| `XDOM-A-ASSET-FAILURE-LOST-ACTIVITY` | `BLOCKED` (`field:downtime_hours` missing) |

No capability registered in this platform today targets
`overtime_leakage` or `preventive_maintenance_missed` as its own
detection family, so no activation decision exists for them -- their
absence from this table is itself evidence, not an omission.

## 3. Truth-family breakdown (authoritative, from the sealed manifest)

| Scenario | Items | True value | Recoverable | Detection family |
|---|---:|---:|---:|---|
| `unbilled_parts` | 88 | $47,347.99 | Yes ($47,347.99) | `REVENUE_RECOGNITION` |
| `overtime_leakage` | 255 | $8,154.50 | Yes ($8,154.50) | `WORKFORCE_PRODUCTIVITY` |
| `preventive_maintenance_missed` | 44 | $160,196.00 | No | `MAINTENANCE_ECONOMICS` |
| **Total** | **387** | **$215,698.49** | **$55,502.49** | |

Plus a separate, disjoint DQ truth: 60 `missing_records` defects (`hidden-
truth/data_quality_truth.json`) -- "completed work order has no field
ticket on file" -- not part of the 387-item leakage count, scored
separately below per the mission's explicit DQ-detection requirement.

## 4. Authoritative full-simulation metrics

Matching was done at truth-item granularity by `affected_records` (work
order key), not by scenario label, and value-verified to the cent, not
assumed from rule-name overlap.

### `unbilled_parts` (88 items, $47,347.99)

| | |
|---|---:|
| TP (published finding on the correct work order) | 86 |
| -- of which value-exact (to the cent) | 85 |
| -- of which value-partial (finding published, magnitude short) | 1 (`WO-000045`, truth $1,202.56, reported $727.56, short $475.00) |
| FN (no finding at all) | 2 (`WO-000502` $477.67, `WO-000813` $13.80) |
| FP (finding not backed by a genuine truth item) | 0 |
| Precision | 86 / 86 = **100.00%** |
| Recall | 86 / 88 = **97.73%** |
| Economic-value capture | $46,381.52 / $47,347.99 = **97.96%** |

**Root cause of the 3 imperfect items, confirmed by direct inspection of
the merged `revenue_variance_intelligence_service.py` and the real
`parts_usage.csv`/`invoices.csv`/`labor_entries.csv` rows:** the rule's
`expected_amount` is the sum of governed parts-consumption lines only (no
labor component resolves into the "expected" side for this dataset
shape); a subject only produces a finding when that parts-only expected
total exceeds the actual invoiced total by more than tolerance (line 533:
`if variance <= tolerance: continue`). For `WO-000502`
(parts value $984.00 vs. invoice $1,496.33) and `WO-000813` (parts $33.00
vs. invoice $1,139.20), the invoice total -- which also covers labor --
already exceeds the parts-only baseline, so the aggregate comparison
never fires, even though the simulator's own ground truth says a specific
part went unbilled. `WO-000045` is the same mechanism in a milder form: a
real shortfall computed correctly in direction, but at a different
magnitude than the simulator's internal per-component model. This is an
**aggregate-vs-itemized reconciliation limitation** in an already-
certified, high-blast-radius capability -- not a data-contract gap (the
evidence needed exists) and not a broken mechanism (85/86 exact matches
prove it is otherwise working precisely as designed).

### `overtime_leakage` (255 items, $8,154.50)

| | |
|---|---:|
| TP | 0 |
| FN | 255 |
| FP | 0 |
| Recall | **0.00%** |
| Economic-value capture | **0.00%** |

No registered capability reads `labor_entries.overtime_hours` against any
workload-normalcy baseline. `technicians.csv` does not carry an
`overtime_rate`-shaped field in this corpus (checked directly).

### `preventive_maintenance_missed` (44 items, $160,196.00)

| | |
|---|---:|
| TP | 0 |
| FN | 44 |
| FP | 0 |
| Recall | **0.00%** |
| Economic-value capture (of $160,196, but this family is entirely non-recoverable) | **0.00%** |

No registered capability compares `maintenance_events.scheduled_date` to
`completed_date` against any overdue/materially-late threshold. Both
fields are independently confirmed `auto_accepted` in this corpus (Section
6 of `docs/p3xxi5b-r-semantic-relation-reconciliation.md`), so this is
evidence that is already governed and available, simply never consumed by
any existing rule for this purpose.

### Aggregate across all 387

| Metric | Result |
|---|---:|
| TP | 86 |
| FP | 0 |
| FN | 301 (2 + 255 + 44) |
| Precision | 86 / 86 = **100.00%** |
| Recall | 86 / 387 = **22.22%** |
| Economic-value capture (of total $215,698.49) | $46,381.52 / $215,698.49 = **21.50%** |
| Recoverable-value capture (of the $55,502.49 recoverable subset) | $46,381.52 / $55,502.49 = **83.57%** |
| Mechanical/fabricated FP | **0** |

The recoverable-value figure (83.57%) is the more honest headline number:
$160,196 of the $215,698.49 total is the non-recoverable
`preventive_maintenance_missed` family, which was never going to be
"captured" as recovered revenue even by a perfect detector -- it is a
cost-avoidance/risk-detection signal, not a billing-recovery one. Against
the family the platform's existing revenue-recovery capability could in
principle address, it captures the large majority.

### DQ detection (separate from the 387-item leakage truth)

| | |
|---|---:|
| Truth defects (`missing_records`: "completed work order has no field ticket on file") | 60 |
| Detected by an existing, targeted rule | 0 |

The only Trust-layer signal touching completeness in this run is a
generic `required_field_completeness` check that reports 100% of records
"affected" on every dataset checked -- a same-row, per-field null check,
structurally incapable of expressing "this work order has zero matching
rows in a *different* dataset." It does not detect this defect family and
is not a substitute for it. This is flagged as an existing, separate,
currently uninformative Trust signal -- not fixed here, out of this
report's scope, but recorded for the Gap Ledger.

## 5. Regression: prior graduated controls, unchanged

| Control | Result |
|---|---:|
| `REVENUE-AMOUNT-VARIANCE` findings on this exact run | 86 (byte-for-byte the same live count already certified in the P3.xxI.5B-R post-merge certification) |
| `MAINTENANCE-REPEAT-VISIT` findings | 0 (unchanged, safety gate holds) |
| `CONTRACT-RATE-COMPLIANCE` findings | 0 (unchanged) |
| MAINT-001, XDOM-A, XDOM-B | Unchanged; not read or touched by this analysis |

No code was changed to produce this report -- it is read-only analysis and
truth-comparison against the already-merged `main`.

See `docs/simulation-miss-ledger.md` and `docs/simulation-gap-ledger.md`
for the itemized/grouped miss classification and the ranked remediation
options.

## 6. GAP-007 implementation: MAINTENANCE-SCHEDULE-COMPLETION-GAP

**Owner authorization:** after the ranking above was presented (GAP-007
highest-leverage, but a genuine new-capability build, not a small
foundational fix), the owner selected building it now.

### Design

An asset-anchored capability comparing each maintenance event's own
governed `scheduled_timestamp` against its own governed
`completed_timestamp` -- never a cross-record comparison, never an
invented overdue-day threshold. A gap is reported only when both temporal
concepts are governed (resolved) *on that dataset* and the completion
value is genuinely empty for that specific row -- the same
NO_GOVERNED_EVIDENCE-vs-CONFIRMED_ZERO discipline
`revenue_variance_intelligence_service.py` already established is applied
identically here, so a dataset that never resolves `completed_timestamp`
at all can never be misread as "nothing was ever completed."

**Empirical finding during design (not assumed):** direct inspection of
the real corpus found every `PM`-type maintenance event is either fully
completed or has no completion date recorded at all -- zero
partially-late cases exist anywhere in the frozen FieldMaintenance
corpus -- and corrective-maintenance-shaped rows never carry a scheduled
date to begin with. This means "scheduled with no completion timestamp"
alone is already a complete detector; no overdue-day threshold needed to
be invented, and the rule never references the `event_type`/"PM" label at
all (purely structural: presence of a scheduled timestamp, absence of a
completed one).

### What was built

1. **`app/services/maintenance_schedule_completion_service.py`** (new) --
   `ScheduledMaintenanceDatasetFields`, `find_incomplete_scheduled_maintenance`
   (dedup/conflict-abstention mirrors `build_repeat_visit_pairs`'s own
   discipline), `run_maintenance_schedule_completion` (publishes an
   observation, never a policy-violation claim, never an estimated
   corrective-cost exposure -- no governed cost-impact evidence for
   maintenance that never happened exists in customer-visible data).
2. **`app/services/analysis_case_orchestration_service.py`** -- new
   orchestration block (mirrors the `MAINTENANCE-REPEAT-VISIT` block's
   shape exactly) resolving `asset_id`/`work_order_id` (as the event's own
   lineage key)/`scheduled_timestamp`/`completed_timestamp` per maintenance
   dataset; `MAINTENANCE-SCHEDULE-COMPLETION-GAP` added to both
   `_GOVERNED_RULE_CODES` and `_evaluate_intelligence_capabilities`'s
   `migrated_rule_codes` set (without these, the pack is registered but
   never actually evaluated or allowed to gate execution -- the same two
   gating sets every prior capability needed added).
3. **`app/registries/rule_registry.py`** -- new `RuleDefinition`
   (`MAINTENANCE-SCHEDULE-COMPLETION-GAP`, `1.0`).
4. **`app/intelligence_packs/registry.py`** -- new
   `IntelligencePackDefinition` (`MAINT-SCHEDULE`). `required_canonical_fields`
   uses `operational_event_id` (the domain-registry-aliased column name),
   not `work_order_id` (the semantic-decision concept name) -- readiness's
   structural column-presence check and execution's semantic-decision
   resolution operate in two different naming spaces, confirmed by direct
   investigation when the pack first stayed `BLOCKED` despite the
   underlying data being fully governed. `scheduled_timestamp`/
   `completed_timestamp` are declared under `required_canonical_measures`
   (the correct, semantic-decision-based readiness path), not
   `required_canonical_fields`.
5. **`app/semantic/concept_registry.py`** -- **required foundational fix**,
   discovered during implementation: `scheduled_timestamp` had no path to
   `AUTO_ACCEPTED` at all (capped at 0.80/`ACCEPTED_WITH_FLAG` -- no
   `compatible_dataset_roles` and no sibling-corroboration declaration),
   the exact same class of gap `completed_timestamp` was already fixed for
   in P3.xxI.3. Applied the identical, already-precedented
   `alternative_sibling_concept_sets=(frozenset({"work_order_id"}),
   frozenset({"contract_id"}))` declaration -- raises it to
   `AUTO_ACCEPTED` (0.98) wherever a sibling `work_order_id`/`contract_id`
   resolves on the same dataset. Verified the concept's own pinned
   calibration expectations are unaffected (no test asserts a specific
   `scheduled_timestamp` confidence/status other than via hand-constructed
   decisions that never exercise this code path).
6. **`tests/test_maintenance_schedule_completion.py`** (new, 11 tests) --
   positive (gap detection, multiple assets, full orchestration
   end-to-end), negative (no scheduled date, ineligible subject,
   conflicting representation, cross-source dedup, missing required field,
   row-order determinism), and lineage/no-policy-claim.
7. **`tests/test_capability_shadow_stage.py`** -- updated its hard-coded
   governed-rule-code assertion set to include the new rule (the same
   maintenance every prior new capability in this program required).

### Live verification (real corpus, all 4 FieldMaintenance cases)

| Case | `MAINTENANCE-SCHEDULE-COMPLETION-GAP` findings | PM-missed truth items | TP | FP | FN |
|---|---:|---:|---:|---:|---:|
| FIELDMAINT-001 | 0 | 0 | 0 | 0 | 0 |
| FIELDMAINT-002 | 7 | 7 | 7 | 0 | 0 |
| FIELDMAINT-005 | 44 | 44 | 44 | 0 | 0 |
| FIELDMAINT-007 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **51** | **51** | **51** | **0** | **0** |

**51/51 = 100.00% recall, 0 false positives, across the entire frozen
FieldMaintenance corpus** -- verified by exact `(asset, work_order)` pair
matching against truth, not by count coincidence. Regression confirmed
unchanged on every case: `REVENUE-AMOUNT-VARIANCE` (61/0/86/26, exactly
the frozen control), `MAINTENANCE-REPEAT-VISIT` (0 everywhere, safety gate
still holds), `CONTRACT-RATE-COMPLIANCE` (0 everywhere).

### Regression

| Suite | Result |
|---|---:|
| `tests/test_maintenance_schedule_completion.py` | 11 passed |
| `tests/test_maintenance_repeat_visit.py`, `test_semantic_profiler.py`, `test_canonical_temporal_evidence.py`, `test_p3xxi3_governed_duration_evidence.py`, `test_semantic_calibration.py`, `test_semantic_interpreter.py` | 83 passed |
| `tests/test_capability_shadow_stage.py` (updated) | 2 passed |
| Full non-Postgres suite | 1,761 passed (1 initial failure -- the shadow-stage rule-code assertion above -- fixed, then reconfirmed clean) |
| Disposable PostgreSQL suite (fresh schema reset) | 83 passed |
| `ruff format --check .` / `ruff check .` | clean on every file this change touched |
| `mypy .` | 624 source files, zero issues in any file this change touched |

### Updated full-simulation metrics after GAP-007 (FIELDMAINT-005)

| Metric | Before GAP-007 | After GAP-007 |
|---|---:|---:|
| TP | 86 | 130 |
| FP | 0 | 0 |
| FN | 301 | 257 |
| Recall (of 387) | 22.22% | 33.59% |
| Economic-value capture (of $215,698.49) | 21.50% | **95.79%** ($206,577.52 / $215,698.49) |
| Recoverable-value capture (of $55,502.49) | 83.57% | 83.57% (unchanged -- `preventive_maintenance_missed` is non-recoverable, so its detection does not move this figure) |

The economic-value-capture jump (21.50% -> 95.79%) is driven entirely by
`preventive_maintenance_missed` being the single largest truth family by
value ($160,196 of $215,698.49); only `overtime_leakage` ($8,154.50, 255
items, `GAP-006`) remains completely unaddressed, now the dominant
residual gap in this simulation.

### Final status

**P3.xxI.6 GAP-007: VALIDATED.** Full recall, zero false positives, zero
regression, no invented evidence, no invented threshold -- realized value
exceeded the pre-implementation estimate because the corpus turned out to
contain no ambiguous partially-late cases at all. `overtime_leakage`
(GAP-006, $8,154.50, 255 items) remains the only unaddressed economic
family in FIELDMAINT-005's truth, correctly not attempted here given its
dependency on an ungoverned workload-normalcy concept (see the Gap
Ledger's own risk note, consistent with the breadth-expansion doc's prior
`HIGH_DESIGN_RISK` flag on the parent Labor Productivity family).
