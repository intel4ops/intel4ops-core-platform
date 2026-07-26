# Reliability Intelligence Limitations

- Weibull fitting is deterministic probability-plot least squares. Censored counts are reported but
  not incorporated into likelihood estimation.
- Kaplan–Meier confidence intervals and interval censoring are not yet implemented.
- Relative risk scores are not failure probabilities.
- Root cause, exact failure date, autonomous shutdown, work-order creation, and PM schedule changes
  are not asserted or performed.
- Condition deterioration and maintenance-demand forecasts must be supplied by the existing
  statistical and forecasting engines.
- Results depend on governed failure definitions, lifecycle boundaries, exposure quality, and
  comparable peer cohorts. Sparse or left-truncated history lowers confidence and must remain
  visible.
- Production execution is bounded to 10,000 observations per request.
