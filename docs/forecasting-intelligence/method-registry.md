# Method registry

Version 1.0 registers naïve, seasonal naïve, drift, historical mean/median, moving and
weighted-moving averages, expanding mean, simple exponential smoothing, Holt linear and
damped trend, Holt-Winters additive, linear and bounded quadratic trend, seasonal dummy
regression, Croston, SBA Croston, and a deterministic weighted ensemble. Bounded multivariate
regression is registered as unsupported until governed future exogenous inputs are available.

Methods expose fixed metadata and deterministic code references. Duplicate method/version
registration and unknown methods fail explicitly. Multiplicative seasonality is not supported.
