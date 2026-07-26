# Censoring

The input contract represents `FAILURE_OBSERVED`, `RIGHT_CENSORED`, `LEFT_TRUNCATED`,
`INTERVAL_CENSORED`, and `UNKNOWN`. Production execution supports observed failures, right
censoring, and left truncation. Interval censoring remains represented but deferred. Event flags
must agree with censoring status; rationale and counts are preserved in evidence.
