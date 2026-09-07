# Local Worker Bridge

`local_worker/agent_worker.py` + `local_worker/lm_studio_client.py`.
Runs on the owner's Windows laptop as a plain Python process (no
Windows-service wrapper in v1 -- start it in a terminal or a scheduled
task). It never accepts an inbound connection; it only makes outbound
HTTPS calls to the Intel4Ops backend and to LM Studio on `localhost:1234`.

## Architecture

```
Intel4Ops cloud
    |
    v
Agent Job Queue (AgentJob, status=queued)
    |
    v
LOCAL WORKER polls: POST /organizations/{org}/agent-jobs/claim
    |  (Bearer <worker token> -- app.auth.worker_auth, NOT a Supabase session)
    v
claims eligible LOCAL job (SELECT ... FOR UPDATE SKIP LOCKED, risk_class
    filtered to the credential's allowed_risk_classes -- R2/R3 are
    structurally unclaimable by a local credential)
    |
    v
calls LM Studio REST API (localhost:1234, reasoning_effort forced per profile)
    |
    v
returns a structured result: POST /organizations/{org}/agent-jobs/{id}/result
    |
    v
cloud validates (WorkerStructuredResult, Pydantic) and persists
    |
    v
AgentRoutingPolicy accepts or escalates -- never automatic implementation for R2/R3
```

Heartbeats (`POST .../{id}/heartbeat`) run on a background thread every
`AGENT_HEARTBEAT_INTERVAL_SECONDS` (default 8s) while inference runs,
mirroring `app/workers/mapping_execution.py`'s `HeartbeatPump` exactly.
If the backend's stale-recovery sweep (`AgentJobService.recover_stale`)
reclaims a job because heartbeats stopped, the worker's next heartbeat
or result submission fails with 409 (lease lost) and the worker safely
moves on -- see `tests/test_agent_job_lifecycle.py`'s heartbeat/lease
tests.

## Configuration (environment only -- no secrets in source)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AGENT_API_BASE_URL` | Yes | -- | e.g. `https://intel4ops-core-api.onrender.com/api/v1` |
| `AGENT_ORGANIZATION_ID` | Yes | -- | the organization UUID this worker serves |
| `AGENT_WORKER_TOKEN` | Yes | -- | issued once via `POST /agent-jobs/worker-credentials`, shown once, never logged |
| `AGENT_POLL_INTERVAL_SECONDS` | No | 3 | idle poll cadence |
| `AGENT_HEARTBEAT_INTERVAL_SECONDS` | No | 8 | must stay well under the backend's stale-threshold |
| `LM_STUDIO_BASE_URL` | No | `http://localhost:1234` | |

Issue a worker credential (organization-admin only, `AGENT_WORKER_CREDENTIAL_ADMIN_ROLES`):

```
POST /api/v1/organizations/{org}/agent-jobs/worker-credentials?worker_id=owner-laptop-qwen
-> { "worker_id": "owner-laptop-qwen", "token": "<raw token, shown once>" }
```

## LM Studio integration status: verified live (2026-09-06)

Confirmed against a running LM Studio instance with `qwen/qwen3.5-9b`
and `mistralai/devstral-small-2-2512` both loaded:

- `GET /v1/models` -- both required models present.
- `POST /v1/chat/completions` with `"reasoning_effort": "none"` ->
  `reasoning_content: ""`, `completion_tokens_details.reasoning_tokens: 0`,
  `finish_reason: "stop"` -- matches the mission's "reasoning off"
  requirement exactly once this field is set (see
  `docs/agent-routing-policy.md` for why it is not the default).
- Streaming (`"stream": true, "stream_options": {"include_usage": true}`)
  correctly yields TTFT (measured to first content token, not first
  byte) and a final usage chunk with prompt/completion/reasoning token
  counts.
- The model occasionally wraps its JSON reply in a ` ```json ` fence
  despite instructions not to -- `lm_studio_client.extract_json` strips
  markdown fences before parsing so this never causes a spurious
  malformed-output failure.

Measured performance (single laptop, one real request, not a
statistically rigorous benchmark): TTFT ~3.0s, ~17 tokens/sec generation
once streaming starts, 0 reasoning tokens. The mission's own validated
numbers (TTFT ~0.7-0.9s, ~15.5-15.7 tok/s) are close on throughput; TTFT
measured here is higher, most likely first-request/model-state variance
on this run -- reported honestly rather than adjusted to match.

## Critical Success Test -- verified end to end (2026-09-06)

Run against a local dev FastAPI instance (disposable Postgres, all
AC-001 migrations applied) and the real local LM Studio:

1. An R0 `AgentJob` (`job_type=PRODUCTION_TRIAGE`) was created directly
   via `AgentJobService.create_job` (status `queued`).
2. `local_worker/agent_worker.py`'s `AgentWorker.process_one()` claimed
   it over real HTTP (`POST /agent-jobs/claim`, worker-credential auth).
3. `qwen/qwen3.5-9b` executed with `reasoning_effort: "none"`,
   `max_output_tokens: 180`, `temperature: 0`.
4. Real metrics were captured: `execution_time_ms=13797`,
   `input_tokens=575`, `output_tokens=143`, `reasoning_tokens=0`.
5. The worker submitted a valid `WorkerStructuredResult`
   (`confidence: 95`, `primary_gap_class: "MAPPING_GAP"`) over real HTTP
   (`POST /agent-jobs/{id}/result`).
6. The backend validated it (Pydantic) and the router accepted it
   (confidence >= 90) -- **job reached `status: "succeeded"`**.
7. Zero manual prompt copy/paste at any step.

Escalation demonstration (same session): a second R0 job was claimed,
and a structured result with `confidence: 55` was submitted through the
same live `/result` endpoint. The router correctly refused to accept it
-- **job reached `status: "escalated"`**, `escalation_reason: "R0
confidence 55 < 90 (or worker requested escalation)"`, and no automatic
implementation occurred.

## Not built in v1

- No Windows-service/always-on wrapper -- run manually or via Task
  Scheduler for now.
- No `ModelManager` load/unload orchestration against LM Studio (see
  `docs/agentic-control-architecture.md`'s v1 boundary section).
- No TLS/mTLS pinning beyond whatever the backend's own HTTPS endpoint
  already provides -- the worker token is the only credential in play,
  transmitted only over HTTPS to a URL the owner configures.
