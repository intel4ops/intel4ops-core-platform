# AC-003 — Autonomous Engineering Control Loop

AC-003 consolidates the AC-002 execution, verification, merge, and deployment guardrails into one deterministic autonomy policy.

## Goal

Remove the owner from routine engineering mechanics while preserving explicit human control for genuinely consequential changes.

## Policy decisions

- `AUTO_EXECUTE`: bounded R0/R1/R2 implementation may proceed without an owner gate.
- `AUTO_MERGE`: an exact candidate that AC-002E proved as `VERIFIED_IMPROVEMENT`, with a fully green Quality Gate, may merge without an owner gate.
- `AUTO_DEPLOY_STAGING`: an exact merged commit with a green quality gate may promote to staging without an owner gate.
- `OWNER_APPROVAL_PRODUCTION`: production deployment remains owner-gated in AC-003.
- `OWNER_APPROVAL_R3`: R3 or protected-boundary changes always require owner review.
- `ESCALATE_ON_REGRESSION`: regression evidence blocks autonomous progression.
- `BLOCKED`: insufficient evidence cannot be promoted.

## Protected boundaries

Any of the following overrides routine autonomy and requires owner review:

- security boundary changes
- tenant boundary changes
- evidence-gate changes
- truth-isolation changes
- destructive migrations
- canonical architecture changes
- material customer-visible product-logic changes

## Operating model

The intended closed loop is:

`detect gap → classify → implement → CI → simulation retest → verify improvement → auto-merge → auto-deploy staging → staging health verification → owner production approval`

Production autonomy is deliberately deferred until Intel4Ops has sufficient operational evidence for automatic rollback and production health governance.

AC-003 does not expose hidden truth to implementation agents, does not allow cross-environment promotion, and does not weaken tenant/auth/evidence controls.
