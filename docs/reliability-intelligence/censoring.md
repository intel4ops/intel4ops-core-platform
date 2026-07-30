# Censoring

The input contract represents `FAILURE_OBSERVED`, `RIGHT_CENSORED`, `LEFT_TRUNCATED`,
`INTERVAL_CENSORED`, and `UNKNOWN`. Event flags must agree with censoring status.

Method support is explicit:

- `KAPLAN_MEIER` supports observed failures and right-censored observations.
- `WEIBULL_TWO_PARAMETER` version `1.0` supports uncensored observed failures only.
- Censored Weibull fitting, left truncation, and interval censoring are deferred until a
  separately approved estimator incorporates those likelihood contributions and passes
  independent numerical validation.

Unsupported censoring is rejected. It is not discarded, coerced, or reported as a successful
fit.
