# Simulation Suite

WP-2.20 supplies 36 deterministic scenarios across Job-to-Cash, Manufacturing, Ports,
and Mobility. `SimulationGenerator` uses a scenario version, tenant UUID, and local
seeded random generator; it never reads production data or global random state.
Canonical JSON ordering produces a stable content hash. Generated artifacts belong in
temporary or ignored `build/` directories.

The four golden scenarios are `J2C-OILFIELD-001`, `MFG-SERVO-DEGRADATION-001`,
`PORT-CRANE-001`, and `MOB-FUEL-001`. Clean baselines contain no injected defects.
Defective scenarios declare every intentional defect in their manifest.
