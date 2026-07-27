# Simulation Scenario Authoring Guide

Add a stable code and immutable semantic version to `SCENARIO_CODES`, bind it to one
published industry-pack version, declare capabilities and defects, and create its
approved oracle. Use stable ordering, decimal-safe values, tenant-owned identifiers,
and a local seeded RNG. Never embed customer records, credentials, current timestamps,
or machine-specific paths. A changed active scenario requires a new version.
