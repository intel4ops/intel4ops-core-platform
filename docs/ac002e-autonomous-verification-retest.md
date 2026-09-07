# AC-002E — Autonomous Verification & Retest

AC-002E verifies a Codex-produced implementation candidate before it can progress toward release.

## Preconditions

- AC-002C created the bounded `CODEX_IMPLEMENTATION` AgentJob from an owner-approved engineering handoff.
- AC-002D completed that job successfully and recorded an exact feature branch, head SHA, pull request number, and pull request URL.
- The source simulation batch remains active and its items are in `remediation_review`.

## Retest start

`POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/verification-retest/start`

The service validates the organization, job type, Codex worker profile, successful AC-002D result, source batch, and batch item states. It writes a sealed retest manifest containing:

- the exact candidate head SHA and pull request;
- the exact simulation IDs from the source batch;
- the frozen baseline TP/FP/FN counts;
- truth-isolation rules;
- the deterministic comparison policy;
- explicit `automatic_merge_allowed=false` and `automatic_deploy_allowed=false` controls.

The items move from `remediation_review` to `retest`.

The candidate runtime must never receive hidden-truth files. Truth is used only by the isolated verification/scoring side after the candidate run is terminal/frozen.

## Retest completion

`POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/verification-retest/complete`

Completion must reference the same lease, candidate SHA, pull request, and exact simulation set.

For scored retests, AC-002E applies a conservative deterministic policy:

- **VERIFIED_IMPROVEMENT**: total false negatives decrease, false positives do not increase, and true positives do not decrease.
- **REGRESSION**: false positives increase, false negatives increase, or true positives decrease.
- **NO_IMPROVEMENT**: a scored outcome that is neither an improvement nor a regression.

A verified improvement moves batch items to `graduated` and the batch to `owner_review_required`. This is the release/merge governance gate; AC-002E never merges the implementation PR.

Regression, no improvement, failure, or escalation moves the batch to `paused_safety_gate`; affected items move to `regression`.

## Non-goals

AC-002E does not:

- run candidate code inside the production API process;
- expose hidden truth to candidate execution;
- write directly to `main`;
- merge a pull request;
- deploy production infrastructure;
- weaken tenant, authentication, evidence, or truth-isolation controls.

No schema migration is required.
