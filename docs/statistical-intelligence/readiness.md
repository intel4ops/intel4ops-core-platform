# Statistical Readiness

Execution requires a persisted `analytical_readiness_decisions` row whose tenant,
Trust assessment, and analytical level all match the request and whose level is
exactly `statistical`. Arithmetic readiness is never treated as statistical readiness.

OIKB and request controls add minimum sample/history/peer requirements, missingness,
unit and currency stability, chronological ordering, duplicate-period rejection, and
complete-period policy. The compatibility bridge is additive: WP-2.06 remains the
decision authority while WP-2.11 enforces method-specific requirements recorded in the
immutable execution package.
