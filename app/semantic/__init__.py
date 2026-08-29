"""P3.xxE.1 Semantic Foundation.

Production execution surface -- part of the operational path (Connect ->
Trust -> Semantic Understanding -> Mapping -> Intelligence -> Command ->
Recovery), NOT the Validation Plane. This package must never import
anything from app.ground_truth_validation, and no module here may branch
on a simulation identifier, industry name, or specific client field name
-- see tests/test_semantic_architecture_guardrails.py, release-blocking.

Everything in this package is industry-agnostic by construction: known
terminology lives in CanonicalConceptRegistry entries (data/config), never
in orchestration branches. A new industry or business process is onboarded
by adding registry entries, never by editing app/semantic/*.py.

Pipeline (this milestone implements profiling + role classification only;
see the P3.xxE.1 report for the full staged design):

    ArtifactExtractionResult (existing, from app.ingestion)
        -> DatasetProfiler.profile()          (deterministic, no AI)
        -> DatasetRoleClassifier.classify()    (deterministic, whole-dataset
                                                 evidence, never one field)
        -> [P3.xxE.2+] field-level semantic candidate generation,
           confidence reconciliation, InterpretationDecision persistence

Confidence (interpretation certainty) and Trust (data quality/reliability)
are deliberately never collapsed into one score -- see
app/semantic/confidence_engine.py's module docstring.
"""
