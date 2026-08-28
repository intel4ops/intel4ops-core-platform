"""P3.xxD.1B Validation Plane.

Not the same thing as app/validation/ (a pre-existing, unrelated
CI/release-gate certification system -- ValidationRun/ValidationSuite/
ValidationScenarioVersion, commit_sha/branch/migration_head, used only by
app/cli/certify.py). This package validates simulation ground truth against
an AnalysisCase's real, persisted analysis output.

NON-NEGOTIABLE DEPENDENCY DIRECTION:

    Operational Plane (Connect/Trust/Semantic/Mapping/Entity Resolution/
    Intelligence/Command/Recovery/AnalysisCase orchestration execution)
        --  writes  -->  persisted results (Finding, AnalysisCaseRun, ...)
                              ^
                              |  read-only, after a run reaches a terminal
                              |  state
                              |
    Validation Plane (this package)

Never the reverse. Nothing under app/services/analysis_case_*.py,
app/services/domain_detection_service.py,
app/services/analysis_case_mapping_service.py,
app/services/entity_resolution_service.py, app/services/trust_service.py,
app/services/*intelligence*.py, app/services/analysis_case_command_service.py,
app/services/analysis_case_recovery_service.py,
app/services/analysis_case_action_service.py, or
app/api/analysis_case_routes.py may import anything from this package.
tests/test_validation_import_boundary.py enforces this with an AST scan and
is release-blocking -- see its docstring for the exact module list checked.

Modules in this package MAY import production models/services to read
already-persisted results (e.g. app.models.entities.Finding,
app.services.analysis_case_command_service) -- that is the one allowed
direction. What must never happen is a production execution module
importing app.ground_truth_validation.repository (the only place ground
truth is queryable) or any other symbol from this package.

No `ground_truth_id` (or any validation-plane foreign key) exists anywhere
on AnalysisCase/AnalysisCaseRun. The two systems are linked only by
ValidationSimulation.analysis_case_id (see
app/models/ground_truth_validation.py), which points one way, into
AnalysisCase, and is never read by AnalysisCase orchestration itself.
"""
