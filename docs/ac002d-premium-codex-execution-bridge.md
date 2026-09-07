# AC-002D — Premium Codex Execution Bridge

AC-002D consumes only an owner-approved `CODEX_IMPLEMENTATION` AgentJob created by AC-002C and turns it into a bounded premium execution lease.

## Flow

1. AC-002B produces the engineering handoff.
2. The owner approves the handoff.
3. AC-002C creates the approved `CODEX_IMPLEMENTATION` AgentJob.
4. AC-002D validates the job, creates a lease, and writes a premium execution manifest.
5. The premium executor works only on a dedicated feature branch.
6. A successful result must identify the feature branch, head SHA, and pull request.
7. Intel4Ops records the result but does not merge or deploy it.

## Required controls

AC-002D rejects execution unless all of the following are true:

- the job belongs to the requested organization;
- `job_type == CODEX_IMPLEMENTATION`;
- the assigned worker profile is `CODEX_IMPLEMENTATION`;
- owner approval is required and already approved;
- the evidence plane is `validation`;
- an input evidence package exists;
- the job is still queued.

The execution manifest explicitly prohibits:

- direct writes to `main`;
- automatic pull-request merge;
- deployment or production-infrastructure changes;
- reading hidden-truth simulation package files;
- weakening tenant, authentication, evidence, or truth-isolation controls.

Architecture-boundary, security-boundary, evidence-gate, truth-isolation, and destructive-migration changes must be escalated rather than autonomously implemented.

## Result contract

A successful execution must provide:

- `branch_name`;
- `head_sha`;
- `pull_request_number`;
- `pull_request_url`;
- a summary of the work.

The stored result always records `automatic_merge_performed=false` and `automatic_deploy_performed=false`.

No database schema change is required for AC-002D; it uses the existing AgentJob lease, result, and event fields.
