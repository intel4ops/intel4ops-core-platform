# Industry-Pack Versioning and Upgrades

Versions follow semantic versioning and published content is immutable. Only
published versions may be assigned. Upgrades explicitly move the tenant assignment
state to another published compatible version while retaining historical executions.
Deprecated versions may execute for existing assignments; new assignment policy can
exclude them. Retirement is blocked by active assignments.

Suspend an assignment to disable a pack safely. Suspension preserves source data,
findings, evidence, economics, recovery actions, usage events, and execution history.
