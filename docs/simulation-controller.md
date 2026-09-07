# Simulation Controller v1

Implemented in `app/validation_program/batch_controller.py`
(`SimulationBatchController`), backed by the `SimulationBatch` /
`SimulationBatchItem` models (`app/models/simulation_batch.py`).
Orchestrates **existing** Simulation Factory / Validation Plane / Wave
Coordinator infrastructure -- see `docs/agentic-control-architecture.md`
for the full reuse rationale. Does not create a competing simulator.

## States

```
AVAILABLE -> SELECTED -> IMPORTING -> PRODUCTION_RUNNING -> TERMINAL
   -> FROZEN -> VALIDATING -> SCORED -> MISS_CLASSIFICATION
   -> GAP_CLUSTERING -> REMEDIATION_REVIEW -> RETEST -> REGRESSION
   -> GRADUATED
```

Plus an explicit `BLOCKED` state (not one of the mission's 14 happy-path
states) for a run that never legitimately reached `TERMINAL` or whose
validation itself failed -- **never silently coerced into `TERMINAL` or
`SCORED`**. This is the same discipline `RUN-RELIABILITY-001` found
missing on the production run-status path (see
`docs/run-reliability-001-incident.md`): an item's `block_reason` is
always human-readable and always distinguishable from success.

`RETEST`, `REGRESSION`, and `GRADUATED` are not driven by this
controller in v1 -- they are reachable states in the model, but no
remediation code exists yet to retest against (Phase H: "DO NOT
automatically remediate code in v1").

## Truth isolation (database-enforced, not just conventional)

`SimulationBatchItem` carries a `CHECK` constraint,
`ck_sim_batch_item_truth_isolation`:

```sql
truth_accessed_at IS NULL OR
  (frozen_at IS NOT NULL AND truth_accessed_at >= frozen_at)
```

No application code path -- present or future -- can write a row that
violates this without the database itself rejecting the transaction.
Verified directly in
`tests/test_agent_truth_isolation.py::test_truth_accessed_before_frozen_is_rejected_by_the_database`.

`_freeze_and_score` (the only method that ever sets `truth_accessed_at`)
is only reachable from `run_batch`, which itself only calls it after
`wave_coordinator.run_wave` has already gone through
`validation_service.validate_run` -- which independently refuses to
score a non-terminal `AnalysisCaseRun` (`run_not_terminal`, verified in
`tests/test_simulation_batch_controller.py::test_validate_run_rejects_a_non_terminal_run`).
Truth isolation is therefore enforced at three independent layers:
the Validation Plane's own terminal-status gate, this controller's own
state-machine ordering, and the database constraint as a final backstop.

## Micro-batch policy (Phase I)

Default micro-batch size: 5 simulations
(`SimulationBatchController.select_batch`'s `batch_size` parameter).
`select_batch` refuses to start a new batch while any prior batch for
the organization is `paused_safety_gate` or `owner_review_required`
(`SimulationControllerError("SAFETY_GATE_OPEN", ...)`) -- verified in
`tests/test_simulation_batch_controller.py::test_select_batch_rejects_when_a_prior_batch_is_paused`.
`pause_for_safety(batch_id, reason)` is the hook any future R3 finding,
FP-safety regression, or truth-plane violation would call to force this
gate; none of those callers exist yet in v1 since the controller does
not itself run intelligence capabilities that could trigger them.

## Miss classification -> gap clustering -> decision package (Phase J/K)

`create_miss_classification_jobs` reads `ValidationFindingMatch` rows
(`match_type = FALSE_NEGATIVE`) for a `SCORED` item and groups them by
**reusable truth family** (`ValidationExpectedFinding.expected_detection_family`
or `ValidationLeakageTruth.detection_family` -- whichever side of the
FINDING_DETECTION/LEAKAGE_VALUE dimension pair the match is linked to,
resolved through `_resolve_family_and_value` so one real miss expressed
on both dimensions produces exactly one job, not two). **One R0
`AgentJob` per family per simulation** -- never one per raw truth item,
never one gap per simulation, per the mission's explicit prohibition.
Each job's `EvidencePackage` is built with `evidence_plane="validation"`
and is only ever constructed for an item that has already reached
`SCORED` (i.e. already frozen) -- enforced by a
`TruthIsolationViolation` raise if that invariant is ever somehow
bypassed (structurally unreachable today, checked anyway).

`build_decision_package` aggregates every `SUCCEEDED`/`ESCALATED`
`MISS_CLASSIFICATION` job's structured result by `primary_gap_class`,
writes a `DecisionPackage` JSON artifact (via the same `StorageBackend`
every other artifact in this codebase uses), and sets the batch to
`owner_review_required`. **No remediation implementation is ever
proposed by this method** -- its `recommendation` field is always the
literal string `"OWNER_REVIEW_REQUIRED -- no remediation implementation
proposed by v1 controller"`.

## Verified end to end

`tests/test_simulation_batch_controller.py::test_batch_controller_happy_path_discover_through_gap_clustering`
runs the full pipeline against a synthetic sealed simulation package
(reusing `tests/corpus_discovery_fixtures.py`'s existing builder, the
same fixture `test_corpus_discovery.py` and `test_corpus_registration.py`
already use): discover -> select -> prepare (real `AnalysisCase` +
customer-data-only upload + `register_corpus`) -> run (delegates to
`wave_coordinator`) -> freeze/score (real `ValidationScore`, real FN
count) -> classify (one real `AgentJob`, driven through
claim/heartbeat/submit-result exactly like a live worker would) ->
cluster -> decision package, asserting the final batch status is
`owner_review_required` end to end.

## Not built in v1

- No automated RETEST/REGRESSION execution against a remediated
  capability -- there is no remediation to retest yet.
- No cross-batch/cross-organization dashboard -- the API surface
  (`app/api/agent_job_routes.py`) is enough to inspect jobs; batch
  status itself is read via direct DB query or a future thin read
  endpoint, not built this mission (Phase Q: minimal CLI/API visibility
  is sufficient).
