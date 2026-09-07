# Agent Routing Policy

Implemented in `app/services/agent_routing_service.py`
(`AgentRoutingPolicy`). This is the single, centralized source of
routing truth -- nothing else in the codebase hard-codes a risk-class ->
worker mapping or a confidence threshold.

## Risk classes

| Class | Examples | Default profile | Local allowed | Owner gate |
|---|---|---|---|---|
| R0 | extraction, classification, log triage, schema inventory, pass/fail classification, evidence-presence checks, short structured summaries | `QWEN_R0` | Yes | No |
| R1 | first-pass root cause, gap classification, evidence package creation, layer/file identification, bounded remediation recommendation | `QWEN_R1` | Yes | No |
| R2 | canonical semantic changes, shared entity/relation changes, orchestration architecture, process model changes, multi-domain capability | `CLAUDE_PLATFORM_REVIEW` | No | Yes |
| R3 | predicted FP explosion, ground-truth isolation risk, evidence-gate weakening, arbitrary policy proposal, canonical architecture conflict, cross-currency unsafe aggregation, destructive migration, security boundary change | `CLAUDE_PLATFORM_REVIEW` | No | Yes (mandatory) |

Any of the R3 safety flags forces `R3` regardless of the risk class a
caller requested -- `AgentRoutingPolicy.classify_risk` applies this
before routing, so a mis-labeled R0/R1 job can never bypass the R3 gate
by omission.

## Confidence-based escalation (`evaluate_worker_result`)

| Risk class | Confidence | Outcome |
|---|---:|---|
| R0 | >= 90 | Accepted |
| R0 | < 90 | Escalate to `QWEN_R1` (no owner gate) |
| R1 | >= 90, no architecture/policy flag | Accepted |
| R1 | 70-89, or an architecture/policy flag at any confidence | Escalate to `DEVSTRAL_SPECIALIST` (no owner gate) |
| R1 | < 70 | Escalate to `CLAUDE_PLATFORM_REVIEW`, owner gate required |
| R2 / R3 | any | Never auto-accepted -- always `CLAUDE_PLATFORM_REVIEW` + owner gate |

Tested exhaustively in `tests/test_agent_routing_service.py` (14 cases).

## Frozen model profiles

Stored as **names and versions**, never ad hoc parameters per call site
(`MODEL_PROFILE_PARAMETERS` in `agent_routing_service.py`):

```
QWEN_R0:  model=qwen/qwen3.5-9b, reasoning=off, max_output_tokens=180, temperature=0
QWEN_R1:  model=qwen/qwen3.5-9b, reasoning=off, max_output_tokens=500, temperature=0
DEVSTRAL_SPECIALIST: model=mistralai/devstral-small-2-2512, reasoning=on, max_output_tokens=2000, temperature=0
GEMINI_SYNTHESIS / CLAUDE_PLATFORM_REVIEW / CODEX_IMPLEMENTATION: no local parameters (not locally dispatchable)
```

**Empirical correction to the mission's stated LM Studio behavior**:
`reasoning=off` is not the model's default. Verified live against
`qwen/qwen3.5-9b` on 2026-09-06 -- without an explicit
`"reasoning_effort": "none"` field in the chat-completion request,
Qwen3.5 emits full `reasoning_content` and consumes the entire
`max_output_tokens` budget on it, leaving the actual `content` field
empty. `local_worker/lm_studio_client.py` always sends
`reasoning_effort: "none"` for non-reasoning profiles (and
`"medium"` for Devstral's specialist profile) -- this is not optional
and is not a per-call parameter a caller can accidentally omit.

## GapClass taxonomy mapping

Phase J's structured-output taxonomy (`app.schemas.agent_jobs.GapClass`)
is a superset naming aligned with, not a replacement for, this program's
pre-existing `docs/simulation-gap-ledger.md` classification:

| Phase J (`GapClass`) | Ledger equivalent |
|---|---|
| `DATA_CONTRACT_GAP` | `DATA_CONTRACT_LIMITATION` |
| `SEMANTIC_GAP` | `SEMANTIC_GAP` |
| `GOVERNED_POLICY_GAP` | `GOVERNANCE_GAP` |
| `INTELLIGENCE_CAPABILITY_GAP` | `CAPABILITY_MODEL_GAP` |
| `ORCHESTRATION_RUNTIME_GAP` | (new, introduced by RUN-RELIABILITY-001) |
| `EXTRACTION_GAP`, `MAPPING_GAP`, `ENTITY_RELATIONSHIP_GAP`, `PROCESS_MODEL_GAP`, `ECONOMIC_VALUE_GAP` | new, finer-grained categories the ledger had not previously needed to distinguish |

## Worker credential scoping (Phase N)

`AgentWorkerCredential.allowed_risk_classes` defaults to `["R0", "R1"]`
and is enforced **in the claim query itself**
(`AgentJobService.claim_next` filters `risk_class IN
credential.allowed_risk_classes`) -- a local worker credential cannot
claim an R2/R3 job no matter what the worker script requests. Verified
in `tests/test_agent_job_lifecycle.py::test_worker_credential_cannot_claim_r2_job`.
