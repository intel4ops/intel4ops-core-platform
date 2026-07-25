# Statistical Intelligence Operations

Executions use explicit pending, running, succeeded, blocked, insufficient-data,
not-ready, unsupported, failed and cancelled states. Idempotency keys are tenant
scoped; an immutable input fingerprint is reused only for an equivalent request.
Correlation IDs, steps, method/package versions, baseline fingerprints and timestamps
support audit and reproduction.

Requests are bounded to 1,000 observations. Database listing is paginated and indexed;
observations and components persist in batches through one transaction. Current
execution is synchronous and intended for bounded analytical batches. Operators should
monitor duration, error status, missingness, suppressions and review feedback.
