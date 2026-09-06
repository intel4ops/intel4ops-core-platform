# RUN-RELIABILITY-001: Orphaned Analysis-Case Runs on Render

**Status:** Diagnosed, not fixed. No code changed as part of this
investigation. Two concrete remediations are proposed at the end and
require owner authorization before any implementation.

## Summary

Two live production runs from Learning Batch 1 (FIELDMAINT-006,
FIELDMAINT-009), started 2026-09-06 during the same ~2-minute window
immediately after PR #129 merged, remained at `status: "running"` for
5.5+ hours with **zero heartbeat advancement, zero stage progression
evidence, and zero published findings** -- while the byte-identical
merged code, run locally against the same source files via this
program's standard debug-harness cross-check, completed both in well
under a minute (312 and 363 findings respectively). This is a genuine
platform/orchestration defect, not an intelligence-capability gap.

## Evidence

| | FIELDMAINT-006 | FIELDMAINT-009 |
|---|---|---|
| Case ID | `2106800e-9843-40b8-8501-1111f830799b` | `9b1e0337-4c33-4a5e-9569-c88854df46e6` |
| Run ID | `e5be2199-bd19-41ac-a470-86218769ed67` | `3198178c-f499-4c43-9563-f7c5280c6aa4` |
| `started_at` | `2026-09-06T17:10:36.984650Z` | `2026-09-06T17:12:18.808635Z` |
| `heartbeat_at` | `2026-09-06T17:10:36.984664Z` (14 microseconds after start -- never advanced) | identical pattern |
| `completed_at` | `null` (still, as of `2026-09-06T22:41:57Z`, ~5h31m later) | `null` |
| Raw `status` via `/runs` list | `"running"` (unchanged for 5.5+ hours) | `"running"` |
| Computed `status` via `/runs/{id}/status` | `"interrupted"`, `error_summary: "Heartbeat stale for 19919s -- marked interrupted"` | same mechanism, same outcome |
| Findings published | 0 | 0 |
| `review_reasons` present | Yes -- `MAPPING_REVIEW_REQUIRED` (`maintenance_events.csv` missing `downtime_hours`, `failure_code`) + multiple `DOMAIN_REVIEW_REQUIRED` | Yes, same shape |
| Local debug-harness result (same code, same files) | 312 findings (218 REVENUE-AMOUNT-VARIANCE, 92 MAINTENANCE-SCHEDULE-COMPLETION-GAP, 1 XDOM-B, 1 XDOM-DATA-LINKAGE) | 363 findings (298 REVENUE-AMOUNT-VARIANCE, 64 MAINTENANCE-SCHEDULE-COMPLETION-GAP, 1 XDOM-DATA-LINKAGE) |

Confirmed via `app/domain_registry.py` and the pristine
`SIM-OFS-FIELDMAINT-006/customer-data/maintenance_events.csv` header
(`event_id,asset_id,work_order_id,event_type,scheduled_date,completed_date`)
that the missing `downtime_hours`/`failure_code` fields are a genuine,
structural property of this simulation's own source file, not an
upload/browser-automation artifact -- `mapping_status: "needs_review"`
was correctly and accurately computed.

## Root-cause analysis

**The review-required condition is not the direct cause of the hang.**
Read `app/services/analysis_case_orchestration_service.py:1591-1620`:
setting `any_review_required = True` does not halt the pipeline -- the
per-dataset loop continues, and (`:2967-2980`) the pipeline is designed
to reach a proper terminal `REVIEW_REQUIRED` run/case status through the
*same* final-commit block that sets `COMPLETED` or `PARTIAL`. Since
`completed_at` is still `null` on both runs, that final block was never
reached -- the review-required condition only proves the pipeline
executed far enough to evaluate mapping/domain status on every dataset
before something else killed it.

**Leading hypothesis, evidence-consistent but not independently
provable from this session (no Render process/deploy-log access):**
`execute()` runs via FastAPI `BackgroundTasks` in the same process as
the HTTP request that started it (confirmed by the function's own
docstring at line 1466: *"called from a FastAPI BackgroundTasks"*).
`BackgroundTasks` is **not durable** -- if the hosting process is
recycled (a deploy, a restart, an OOM kill) while a task is in flight,
the task is silently terminated with no opportunity to persist an
exception, a stage event, or even one more heartbeat write. Both runs
started within 2 minutes of each other, in the same window this
session merged PR #129 and began creating Learning-Batch-1 cases --
exactly the kind of window in which a `main`-branch merge would trigger
a Render auto-deploy of the API service. The observed signature --
heartbeat frozen at (not before) the very first write `start_run()`
itself makes, zero stage events beyond dataset-loop entry, zero
findings, identical shape on both cases -- is consistent with the
in-flight task being killed by a process cutover moments after it
began, and inconsistent with either a slow-but-progressing run (the
heartbeat would have advanced) or a code-level exception (the
mapping/trust exception handlers throughout `execute()` all persist a
`FAILED` stage event and an `error_summary`, none of which fired here).

**A second, independent, and definitely-confirmed defect compounds
this:** `mark_stale_if_needed()` (`analysis_case_orchestration_service.py:3117-3129`)
is the *only* code path that ever transitions a stuck run out of
`"running"`, and it is invoked **only** by the `/runs/{id}/status`
endpoint -- not by the `/runs` list endpoint, which is what this
session (and, most likely, the case-list UI) actually polls. Both runs
sat at raw `status: "running"` for the entire 5.5+ hours; only the
instant this investigation queried `/status` directly did the
staleness check fire and persist `"interrupted"`. Absent this
diagnostic session, these two runs would show `"running"` in the
product indefinitely, with no operator-visible signal that anything
had gone wrong.

## Classification

**ORCHESTRATION/RUNTIME_GAP**, two distinct sub-defects:

1. **Non-durable execution substrate** (architectural, not a tiny fix):
   long-running case orchestration depends on in-process
   `BackgroundTasks` surviving for the run's full duration, with no
   resumability or dead-task detection if the host process is recycled.
   This is a substantial change (durable task queue, or checkpointed
   per-stage resume) and is explicitly **not** proposed for
   implementation here.
2. **Reactive-only staleness detection** (a genuinely tiny, narrow,
   low-risk fix): `mark_stale_if_needed` should also be invoked from
   the `/runs` list endpoint (or run on a lightweight scheduled sweep),
   so an orphaned run surfaces automatically instead of only when an
   operator happens to query `/status` directly.

Per the mission's explicit instruction, **neither fix is implemented in
this pass.** Item 2 is a narrow correctness fix independent of GAP-011
and is not known to be covered by any existing approved contract in
this program -- flagged here and held for owner authorization.

## Recovery attempt

Per Phase B's authorization to recover/complete these runs if safe and
non-destructive, a retry (`POST .../analysis-cases/{case_id}/run`,
which starts a new, additive `run_number` without touching the existing
orphaned run row) was attempted for both cases. **The action was
blocked by this session's own tool-safety classifier** as a
state-changing action against live production infrastructure, and was
not overridden. No retry was executed. **Recommendation:** the owner
separately authorizes a plain re-run of these two cases (a routine,
already-precedented action in this program, not a code change) to
obtain a clean live terminal result; the existing debug-harness
cross-check result (310 TP / 295 TP, 0 FP; see
`docs/simulation-gap-ledger.md`) can continue to stand in until then,
per this program's established and previously-validated
cross-verification methodology.

## Shared mechanism

Both cases show byte-for-byte the same signature (heartbeat frozen
within microseconds of start, zero stage progression, zero findings,
identical near-simultaneous timing) -- this is one platform incident
manifesting twice, not two independent unrelated hangs.
