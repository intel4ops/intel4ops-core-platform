# AC-002B Autonomous Engineering Handoff

AC-002B is the governed bridge between simulation-derived learning evidence and bounded engineering execution.

## Flow

1. AC-002A stages and runs one sealed simulation package through the production controller.
2. Miss-classification jobs complete through the existing AgentJob worker path.
3. AC-002B scopes classification evidence to the current simulation batch and produces a decision package.
4. AC-002B writes an engineering handoff targeted at the `CODEX_IMPLEMENTATION` worker profile.
5. The batch moves to `OWNER_REVIEW_REQUIRED` and `dispatch_allowed` remains `false`.
6. No implementation worker, remediation code, merge, deployment, or production-infrastructure change is authorized until the owner explicitly approves the bounded work package.

## Non-negotiable controls

- organization and batch scoping on all handoff evidence
- no hidden-truth files exposed to implementation work
- no validation-plane dependency introduced into production execution
- no weakening of evidence, tenant, authentication, or truth-isolation gates
- no automatic remediation before the owner gate

This milestone intentionally creates the implementation-ready artifact and stops at the genuine owner approval boundary.
