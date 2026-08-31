"""P3.xxD.1B, Section 7: release-blocking architecture test. Production
execution modules (Connect/Trust/Semantic/Mapping/Entity Resolution/
Intelligence/Command/Recovery/AnalysisCase orchestration execution) must
never import anything from the Validation Plane (app/ground_truth_validation
and app/models/ground_truth_validation.py). Enforced with a plain `ast`
scan -- no extra dependency, and it inspects import statements directly
rather than trusting convention or a docstring."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The full production execution surface this invariant protects. Adding a
# new analysis-case/intelligence/trust/mapping/command/recovery service
# module means adding it here too -- the whole point is an explicit,
# reviewed list, not a broad glob that could silently stop covering a file.
PRODUCTION_EXECUTION_MODULES = [
    "app/services/domain_detection_service.py",  # Semantic
    "app/services/analysis_case_mapping_service.py",  # Mapping
    "app/services/entity_resolution_service.py",  # Entity Resolution
    "app/services/trust_service.py",  # Trust
    "app/services/analysis_case_intelligence_service.py",  # Intelligence
    "app/services/cross_domain_intelligence_service.py",  # Intelligence
    "app/services/intelligence_readiness_service.py",  # Intelligence
    "app/services/governed_finding_publisher.py",  # Intelligence
    "app/services/analysis_case_command_service.py",  # Command
    "app/services/analysis_case_action_service.py",  # Recovery
    "app/services/analysis_case_recovery_service.py",  # Recovery
    "app/services/analysis_case_orchestration_service.py",  # AnalysisCase orchestration execution
    "app/services/analysis_case_service.py",  # Connect
    "app/domain_registry.py",  # Semantic
    "app/api/analysis_case_routes.py",
    "app/models/analysis_case.py",
    "app/semantic/profiler.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/role_classifier.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/concept_registry.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/candidate.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/candidate_generator.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/confidence_engine.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/provider.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/sampling.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/interpreter.py",  # P3.xxE.1 Semantic Understanding
    "app/models/semantic.py",  # P3.xxE.1 Semantic Understanding
    "app/services/analysis_case_semantic_service.py",  # P3.xxE.1 Semantic Understanding
    "app/api/semantic_routes.py",  # P3.xxE.1 Semantic Understanding
    "app/semantic/review.py",  # P3.xxE.1A Semantic Review & Governance
    "app/models/semantic_review.py",  # P3.xxE.1A Semantic Review & Governance
    "app/services/semantic_review_service.py",  # P3.xxE.1A Semantic Review & Governance
    "app/api/semantic_review_routes.py",  # P3.xxE.1A Semantic Review & Governance
    "app/semantic/openai_provider.py",  # P3.xxE.2 Adaptive Field Interpretation
    "app/semantic/provider_factory.py",  # P3.xxE.2 Adaptive Field Interpretation
    "app/semantic/neighbor_context.py",  # P3.xxE.2 Adaptive Field Interpretation
    "app/semantic/cross_dataset_context.py",  # P3.xxE.2 Adaptive Field Interpretation
    "app/semantic/case_context.py",  # P3.xxE.2 Adaptive Field Interpretation
    "app/entities/entity_type.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/identifier_normalization.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/entity_candidate.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/entity_type_inference.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/entity_resolution_tiers.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/entity_deduplication.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/case_entity_context.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/entity_resolution.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/relationship_type.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/relationship_candidate.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/confidence_decomposition.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/relationship_discovery.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/entities/intelligence_contract.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/models/entities_canonical.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/services/analysis_case_entities_service.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/api/entities_routes.py",  # P3.xxE.3 Entity + Relationship Intelligence
    "app/process/activity_type.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/temporal_evidence.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/activity_candidate.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/activity_type_inference.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/state_normalization.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/participation_inference.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/case_process_context.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/activity_discovery.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/process_anchor_discovery.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/process_boundary.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/sequence_discovery.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/precedence_confidence.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/process_confidence.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/process_relationship_support.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/reasoning_provider.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/process_interpretation.py",  # P3.xxE.4 Operational Process Interpretation
    "app/process/intelligence_contract.py",  # P3.xxE.4 Operational Process Interpretation
    "app/models/process_canonical.py",  # P3.xxE.4 Operational Process Interpretation
    "app/services/analysis_case_process_service.py",  # P3.xxE.4 Operational Process Interpretation
    "app/api/process_routes.py",  # P3.xxE.4 Operational Process Interpretation
    "app/intelligence_packs/registry.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/intelligence_packs/confidence_distribution.py",  # P3.xxE.5 Intelligence Activation
    "app/intelligence_packs/case_capability_index.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/intelligence_packs/shadow_comparison.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/services/intelligence_readiness_service.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/services/case_capability_index_service.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/models/intelligence_activation.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/services/analysis_case_capability_service.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
    "app/api/capability_activation_routes.py",  # P3.xxE.5 Intelligence Activation (SHADOW)
]

FORBIDDEN_PREFIXES = ("app.ground_truth_validation", "app.models.ground_truth_validation")


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_production_execution_modules_never_import_validation_plane() -> None:
    violations: dict[str, set[str]] = {}
    for relative_path in PRODUCTION_EXECUTION_MODULES:
        path = REPO_ROOT / relative_path
        assert path.is_file(), f"expected production module not found: {relative_path}"
        imported = _imported_module_names(path)
        forbidden = {
            name
            for name in imported
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PREFIXES)
        }
        if forbidden:
            violations[relative_path] = forbidden

    assert not violations, (
        f"production execution modules must never import the Validation Plane: {violations}"
    )


def test_intelligence_execution_never_imports_adapters_or_family_registry() -> None:
    """P3.xxD.1E section 23: package adapters and the detection-family
    mapping registry are as forbidden to Intelligence as any other part of
    the Validation Plane -- named explicitly here (on top of the blanket
    prefix check above) because section 23 calls them out by name."""
    forbidden_specific = (
        "app.ground_truth_validation.adapters",
        "app.ground_truth_validation.family_registry",
    )
    violations: dict[str, set[str]] = {}
    for relative_path in PRODUCTION_EXECUTION_MODULES:
        imported = _imported_module_names(REPO_ROOT / relative_path)
        found = {
            name
            for name in imported
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_specific)
        }
        if found:
            violations[relative_path] = found
    assert not violations, (
        f"Intelligence/production modules must never import adapters or the "
        f"family registry: {violations}"
    )


def test_validation_plane_is_free_to_import_production_read_paths() -> None:
    """The allowed direction: Validation reading persisted operational
    results is fine and expected -- this is not a blanket ban on
    app.ground_truth_validation importing app.models/app.services, only a
    ban on the reverse (checked above)."""
    service_path = REPO_ROOT / "app/ground_truth_validation/service.py"
    imported = _imported_module_names(service_path)
    assert any(name.startswith("app.services.analysis_case_command_service") for name in imported)
    assert any(name.startswith("app.models.analysis_case") for name in imported)
