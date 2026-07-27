# Operational Resilience Testing

Resilience validation covers retry, replay, duplicate delivery, partial failure,
timeouts, downstream errors, invalid configuration, interrupted persistence,
migration rollback, and failure audit emission. Replays must not increase finding,
action, usage, recovery-case, or verified-ledger counts. Destructive migration tests
run only with an explicitly confirmed disposable PostgreSQL URL.
