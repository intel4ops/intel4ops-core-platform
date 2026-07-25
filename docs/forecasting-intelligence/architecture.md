# Forecasting intelligence architecture

WP-2.12 adds a governed forecasting vertical slice. Trusted canonical history and the
existing analytical-readiness decision enter a bounded preparation pipeline. The pipeline
resolves an active OIKB definition, prepares one stable-unit time series, evaluates registered
candidate methods through leakage-safe backtests, selects the simplest candidate within five
percent of the best governed metric, and persists points, intervals, diagnostics, and trace.

Routes contain authorization and transport concerns only. `ForecastExecutionService`
coordinates governance, readiness, preparation, backtesting, selection, persistence,
scenarios, revisions, actuals, and evidence. `ForecastingMethodRegistry` accepts only compiled
method objects; user-provided imports, SQL, expressions, binaries, and Python are prohibited.

Forecast output supports planning and human review. It is not an autonomous decision or a
guarantee. WP-2.08 consumes evidence references and finding candidates; it remains the owner
of finding publication and lifecycle.
