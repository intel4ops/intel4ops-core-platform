# AGENTIC-CONTROL-001: Agent Router + Local Worker Bridge + Simulation Controller v1

This is the automation/control layer for the existing Intel4Ops learning
program. It replaces the owner manually acting as the message bus
between ChatGPT, Claude, Codex, Gemini, local Qwen/Devstral, GitHub, the
Simulation Factory, and the Intel4Ops production API. **It is not a
chatbot feature, not a frontend-first project, and not a replacement for
Intel4Ops architecture** -- it is a thin control layer that routes work,
tracks it durably, and stops at governed owner-approval gates.

## Roles

| Role | Responsibility |
|---|---|
| ChatGPT | Control/orchestration layer, owner interface, prioritization, approval preparation (outside this codebase) |
| Qwen (`qwen/qwen3.5-9b`, local, LM Studio) | Fast R0/R1 routine classification -- extraction, gap classification, triage |
| Devstral (`mistralai/devstral-small-2-2512`, local, LM Studio) | Local specialist review for R1 confidence in the 70-89 band or an architecture/policy flag |
| Claude | Architecture/governance conflicts, high-FP-risk changes, R2/R3 review, safety/truth-isolation issues |
| Codex | Bounded implementation, tests, refactoring, PR preparation |
| Gemini | Large-context synthesis, cross-simulation comparison, batch gap clustering, independent challenge |

## Why this design reuses, not replaces, existing infrastructure

Phase A of this mission's owner instructions required reconciling
existing architecture before writing anything new. Three
already-existing, already-tested subsystems turned out to cover most of
what a naive from-scratch build would have duplicated:

1. **Worker lease/claim mechanics** already exist for canonical mapping
   execution (`app/services/canonical_mapping_service.py`'s
   `claim_next`/`heartbeat`/`recover_stale`/`execute_claimed`, backed by
   `MappingRun.execution_lease_id`/`execution_worker_id`/`heartbeat_at`,
   and `app/workers/mapping_execution.py`'s standalone worker process).
   `AgentJob`'s own claim/heartbeat/stale-recovery in
   `app/services/agent_job_service.py` is modeled on this pattern field
   for field, not invented separately -- see that module's own docstring.
2. **The Validation Plane** (`app/ground_truth_validation/`) already
   does structurally-isolated ground-truth scoring: corpus discovery
   (`SimulationCorpusDiscovery`), idempotent registration
   (`validation_service.register_corpus`), and terminal-status-gated
   scoring (`validation_service.validate_run`, which itself refuses to
   run against a non-terminal `AnalysisCaseRun`). None of this is
   duplicated by the new Simulation Controller.
3. **The Wave Coordinator** (`app/validation_program/wave_coordinator.py`)
   already runs a production case to completion and validates it,
   synchronously, one simulation at a time, resumable across
   interruptions. `SimulationBatchController.run_batch` (Phase H)
   delegates directly to it rather than re-implementing execution.

What this mission actually adds, net-new:

- `AgentJob` / `AgentJobEvent` / `AgentWorkerCredential` (Phase B/N) --
  a durable, idempotent, leased job queue reachable over HTTP by a
  remote (not in-process) worker.
- `AgentRoutingPolicy` (Phase D) -- centralized risk-class routing and
  confidence-based escalation, replacing ad hoc judgment calls.
- The Local Worker Bridge (Phase E) -- a pull/claim Python process that
  bridges the cloud job queue to LM Studio on the owner's laptop.
- `SimulationBatch` / `SimulationBatchItem` (Phase H) -- a persistent
  micro-batch state machine and a database-enforced truth-isolation
  invariant (`ck_sim_batch_item_truth_isolation`), sitting on top of the
  three subsystems above.
- Miss-classification job generation, gap clustering, and the
  `DecisionPackage` owner-approval gate (Phase J/K) -- new, AgentJob-
  driven automation of what this program previously did by hand in
  markdown ledgers.

## Data flow

```
Owner authorizes a micro-batch
  -> SimulationBatchController.select_batch()        (SimulationBatch/Item rows)
  -> SimulationBatchController.prepare_batch()        (AnalysisCase + customer-data upload + register_corpus)
  -> SimulationBatchController.run_batch()            (delegates to wave_coordinator: execute() + validate_run())
  -> item reaches SCORED, frozen_at set, truth read exactly once, after terminal
  -> create_miss_classification_jobs()                (one R0 AgentJob per reusable truth family)
  -> local worker claims R0 jobs, runs Qwen, submits structured results
  -> AgentRoutingPolicy accepts (confidence >= 90) or escalates
  -> build_decision_package()                         (gap-class clusters, OWNER_REVIEW_REQUIRED)
  -> owner reviews/approves -- no remediation code is ever proposed by v1
```

## v1 boundary (intentionally not built this mission)

- **Premium-agent API wiring.** `AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW`,
  `GEMINI_SYNTHESIS`, and `CODEX_IMPLEMENTATION` exist as routing targets
  and are recorded on `AgentJob`, but no outbound API call to
  Anthropic/Google/OpenAI Codex is wired up. R2/R3 jobs correctly land at
  `OWNER_REVIEW_REQUIRED` and stop there -- exactly the mission's
  required behavior ("No automatic implementation"). Wiring an actual
  API call is a distinct, credentialed integration effort for a future
  milestone, not required to satisfy this mission's acceptance criteria.
- **ModelManager load/unload orchestration.** `LmStudioClient`
  (`local_worker/lm_studio_client.py`) queries loaded models and runs
  inference against whichever model LM Studio already has loaded; it
  does not send LM Studio a load/unload command (LM Studio's REST
  surface for that is UI-driven / version-dependent). v1 assumes the
  owner keeps the needed model loaded in LM Studio, which matches
  today's actual usage pattern (only one large local model needs to be
  active at a time, exactly as the mission specifies).
- **Frontend.** None. No Lovable changes. A minimal API/CLI surface is
  the only visibility layer, per the mission's explicit instruction.

## Verified end-to-end (2026-09-06)

A live local dev server (disposable Postgres, all AC-001 migrations
applied) plus a live LM Studio instance on the same machine were used to
run the mission's exact "Critical Success Test": an R0 job was created,
claimed over real HTTP by `local_worker/agent_worker.py`, executed by
`qwen/qwen3.5-9b` with `reasoning_effort: "none"` and
`max_output_tokens: 180`, and returned a valid structured result
(confidence 95, `MAPPING_GAP`) that the router accepted -- job reached
`succeeded` with zero manual prompt copy/paste. A second run
demonstrated the escalation path: a submitted confidence of 55 on an R0
job produced `status: "escalated"` with no automatic implementation.
Full numbers in `docs/local-worker-bridge.md`.
