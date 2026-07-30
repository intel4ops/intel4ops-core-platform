# Method Registry

Only registered method/version pairs execute. Registrations declare capabilities, exposure bases,
censoring, grouping, condition and uncertainty support, minimum data, schemas, implementation,
support state, deprecation, and limitations. Duplicate and unsupported registrations fail closed.

`WEIBULL_TWO_PARAMETER` version `1.0` is an uncensored probability-plot least-squares fit.
Its registry metadata declares `supports_censoring=false`. Censored observations are rejected
explicitly; they are never silently removed from the fit. `KAPLAN_MEIER` remains the registered
method that supports right-censored observations.
