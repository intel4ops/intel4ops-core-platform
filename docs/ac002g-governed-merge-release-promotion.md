# AC-002G — Governed Merge & Release Promotion

AC-002G consumes the durable AC-002F release authorization and creates a bounded contract for merging only the exact verified candidate into `main`, then recording the merged commit as a release candidate.

## Preconditions

- The source job is a successful `CODEX_IMPLEMENTATION` job linked to an AC-002C batch.
- AC-002F release authorization exists with `decision = APPROVED`.
- `merge_allowed = true` and `deploy_allowed = false`.
- The authorization candidate SHA and PR number still match the Codex result.
- The batch is in the AC-002F approved `complete` state.

## Start

`POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/governed-merge/start`

The service writes `agent-jobs/{job_id}/governed-merge-manifest.json` with:

- repository and exact PR number
- exact expected head SHA
- source and target branches
- merge method
- owner authorization reference
- lease identifier and worker identifier
- explicit prohibition on deployment

The external governed executor must reject a stale PR head and must use the exact authorized SHA.

## Complete

`POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/governed-merge/complete`

A successful merge requires the same lease, candidate SHA, PR number, target branch `main`, and a reported merge commit SHA.

The service writes `agent-jobs/{job_id}/release-promotion.json` with release stage `MERGED_AWAITING_DEPLOYMENT_AUTHORIZATION`.

A failed or escalated merge pauses the simulation batch safety gate.

## Governance boundary

AC-002G does not call GitHub itself. It issues and validates the governed executor contract. The executor is expected to use an exact-head guarded GitHub merge operation.

AC-002G never:

- changes the authorized candidate
- merges a different PR or SHA
- deploys
- invokes deployment workflows
- permits hidden-truth access
- weakens tenant, authentication, evidence, or truth-isolation controls

Deployment requires a separate later authorization phase.

No database migration is required for AC-002G.
