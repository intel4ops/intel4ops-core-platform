"""P3.xxV.1: the Validation Program orchestration layer -- coordinates
PRODUCTION execution (app.services.analysis_case_orchestration_service)
and the VALIDATION Plane (app.ground_truth_validation) for a set of
simulations, one at a time.

This package is deliberately its own thing, distinct from both:
  - app/services/ (production execution) -- those modules must never
    import app.ground_truth_validation (enforced by
    tests/test_validation_import_boundary.py's AST guardrail).
  - app/ground_truth_validation/ (the Validation Plane) -- that package
    must never write production tables (its own module docstring's
    one-way dependency rule).

A coordinator that triggers a production run AND THEN validates it against
registered truth necessarily needs to call both sides -- that is exactly
this package's job, and only this package's job. Nothing under
app/services/ or app/ground_truth_validation/ may import from here.
"""
