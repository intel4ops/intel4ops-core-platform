# AC-002H — Deployment Authorization & Controlled Promotion

AC-002H consumes the AC-002G release-promotion artifact only after the candidate has been merged and is in `MERGED_AWAITING_DEPLOYMENT_AUTHORIZATION`.

## Flow

AC-002G merged release candidate
→ owner deployment authorization for one exact merge commit and one environment
→ controlled promotion lease/manifest
→ environment-specific deployment executor
→ deployment result
→ success or safety-gate pause

## Invariants

- Deployment authorization is separate from merge authorization.
- Authorization is bound to the exact AC-002G merge commit SHA.
- Authorization is bound to exactly one environment: `staging` or `production`.
- Authorization for one environment cannot be reused for another.
- A successful promotion must report the exact deployed commit and a deployment reference.
- A failed or escalated promotion pauses the simulation batch safety gate.
- AC-002H does not invoke deployment infrastructure directly; it emits a governed executor contract.
- Cross-environment promotion is always prohibited without a new owner authorization.
- Tenant, auth, evidence-plane, and truth-isolation boundaries are unchanged.
- No schema migration is required.

## API

- `POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/deployment-authorization`
- `POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/controlled-promotion/start`
- `POST /api/v1/organizations/{organization_id}/simulation-controller/codex-jobs/{job_id}/controlled-promotion/complete`

The application never turns an AC-002G merge into an implicit deployment. Every environment requires its own explicit owner authorization.