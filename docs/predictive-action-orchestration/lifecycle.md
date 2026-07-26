# Action Lifecycle and Governance

Allowed transitions are:

| From | To |
|---|---|
| proposed | pending_approval, approved, cancelled |
| pending_approval | approved, rejected, cancelled |
| approved | assigned, cancelled |
| assigned | scheduled, in_progress, cancelled |
| scheduled | in_progress, cancelled |
| in_progress | blocked, completed, cancelled |
| blocked | in_progress, cancelled |
| completed | verification_pending, cancelled |
| verification_pending | verified, verification_rejected |
| verification_rejected | in_progress, completed, cancelled |

Rejected, verified, and cancelled are terminal. Completion is a report of work performed and never
implies verification. Verification requires evidence. Realized value requires a verified action and
verification evidence. Expected value can be recorded earlier but remains a separate outcome row.
Every material operation creates an organization-scoped audit event with actor, role, reason,
timestamp, status context, metadata, and idempotency key.

Mandatory unresolved dependencies or unavailable resources block completion. Self-dependencies and
direct two-action cycles are rejected; deeper graph cycle detection is deferred.
