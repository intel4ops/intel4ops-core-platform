# AC-002F — Verified Release Authorization

AC-002F converts the AC-002E owner-review state into a bounded release authorization for the exact verified Codex candidate.

## Preconditions

- The source job is a successful `CODEX_IMPLEMENTATION` job linked to an AC-002C batch.
- The batch is `owner_review_required` and every item is `graduated`.
- The AC-002E result exists and is `VERIFIED_IMPROVEMENT`.
- The owner decision names the exact verified candidate SHA and pull request number.
- The candidate has not already been automatically merged or deployed.

## Approval outcome

An approval writes `agent-jobs/{job_id}/release-authorization.json` with schema `ac002f-release-authorization-v1`.

The artifact records the organization, batch, implementation job, AC-002E verification reference, exact candidate SHA/PR, owner user, owner note, and decision.

Approval sets:

- `merge_allowed = true`
- `deploy_allowed = false`
- `automatic_merge_performed = false`
- `automatic_deploy_performed = false`
- batch status to `complete`

The approved next action is a governed GitHub executor merging only that exact verified candidate.

## Rejection outcome

Rejection keeps merge/deploy disallowed and moves the batch to `paused_safety_gate` with an owner-rejection reason.

## Governance boundary

AC-002F does not merge a pull request and does not deploy anything. It only creates a durable release authorization that a later governed executor may consume.

A stale SHA, wrong PR, cross-batch verification result, non-improving retest, already-crossed merge/deploy boundary, or conflicting repeat decision is rejected.

No schema migration is required.
