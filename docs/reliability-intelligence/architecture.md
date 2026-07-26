# Reliability Intelligence Architecture

WP-2.13 adds a governed, tenant-safe reliability bounded context. It consumes trust and
reliability-readiness decisions, resolves only active OIKB definitions, validates lifecycle,
failure, exposure, and censoring contracts, selects a registered versioned method, and persists
reproducible analytical summaries. It does not duplicate canonical assets, work orders, sensor
streams, statistical deterioration analysis, or forecasting.

The execution service is the transaction boundary. Routes only authorize and delegate. The method
registry blocks arbitrary code and exposes capabilities and limitations. Every tenant-owned query
filters `organization_id`; system definitions may be shared, but private observations, parameters,
results, reviews, and evidence never cross tenant boundaries.

Progressive sequencing is Arithmetic → Statistical → Forecasting when required → Reliability.
Reliability outputs are evidence candidates for Findings; publication remains governed and is not
automatic. Risk, probability, confidence, materiality, severity, and criticality are distinct.
Safety-critical or maintenance-interval outputs always require human review.

Current bounded methods are basic reliability metrics, Kaplan–Meier survival, two-parameter Weibull
probability-plot fitting, bad-actor composite scoring, composite asset health, and downtime-risk
scoring. Advanced causal models, deep learning, autonomous control, scheduling, and optimization
are deferred.
