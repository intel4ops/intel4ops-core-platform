# Industry-Pack Validation Guide

Validation checks manifest structure, semantic version, unique components, universal
parents, canonical required fields, rule/evidence contracts, metric units and
currency policy, economic mappings, recovery playbook bindings, entitlement and
meter declarations, and minimum-platform compatibility. Validation results are
append-only records. Publication is rejected unless validation and approval succeed.

Test each pack from canonical input through Trust readiness, governed rule execution,
evidence and calculation trace, exposure, and recovery recommendation. Also test
tenant isolation, entitlement denial, retry idempotency, and migration lifecycle on
SQLite and disposable PostgreSQL.
