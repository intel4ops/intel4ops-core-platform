# Orchestrator Integration

WP-2.09 registers `STATISTICAL_INTELLIGENCE_ENGINE` version 1.0 with capability
`bounded_statistical_intelligence`. Registry consistency checks compare persisted and
code-backed contracts before selection.

The orchestrator resolves active OIKB first, requires exact statistical readiness,
selects the statistical adapter, records engine and execution steps, and returns a
locator for the normalized statistical execution. A compatibility
`intelligence_executions` summary preserves existing WP-2.08 result references.
Arithmetic and deterministic-rule selection remain unchanged; statistical execution
augments rather than replaces arithmetic results.
