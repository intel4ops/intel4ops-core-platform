"""P3.xxE.3 Entity + Relationship Intelligence release-blocking guardrails.

A separate, narrow guardrail file for the entity/relationship surface
(plan review scoping decision C5) rather than folding into
test_semantic_architecture_guardrails.py -- that file's ground-truth and
simulation-literal checks are reused here, but its AI-request-dataframe
check doesn't apply (this package has no AI provider seam at all: it is
deterministic by construction, per the E100 portability requirement).
Fails CI if the production entity/relationship surface:
  - imports anything from app.ground_truth_validation
  - contains a hard-coded simulation ID / industry-name string literal
  - imports any AI-provider-facing module (app.semantic.provider,
    app.semantic.openai_provider, app.semantic.provider_factory) --
    entity/relationship resolution must stay deterministic/local, never
    dependent on cloud AI.
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRODUCTION_ENTITY_FILES = [
    _REPO_ROOT / "app" / "entities" / "__init__.py",
    _REPO_ROOT / "app" / "entities" / "entity_type.py",
    _REPO_ROOT / "app" / "entities" / "identifier_normalization.py",
    _REPO_ROOT / "app" / "entities" / "entity_candidate.py",
    _REPO_ROOT / "app" / "entities" / "entity_type_inference.py",
    _REPO_ROOT / "app" / "entities" / "entity_resolution_tiers.py",
    _REPO_ROOT / "app" / "entities" / "entity_deduplication.py",
    _REPO_ROOT / "app" / "entities" / "case_entity_context.py",
    _REPO_ROOT / "app" / "entities" / "entity_resolution.py",
    _REPO_ROOT / "app" / "entities" / "relationship_type.py",
    _REPO_ROOT / "app" / "entities" / "relationship_candidate.py",
    _REPO_ROOT / "app" / "entities" / "confidence_decomposition.py",
    _REPO_ROOT / "app" / "entities" / "relationship_discovery.py",
    _REPO_ROOT / "app" / "entities" / "intelligence_contract.py",
    _REPO_ROOT / "app" / "models" / "entities_canonical.py",
    _REPO_ROOT / "app" / "services" / "analysis_case_entities_service.py",
    _REPO_ROOT / "app" / "api" / "entities_routes.py",
    _REPO_ROOT / "app" / "schemas" / "entities.py",
]

_FORBIDDEN_IMPORT_PREFIXES = ("app.ground_truth_validation", "app.models.ground_truth_validation")
_FORBIDDEN_AI_PROVIDER_PREFIXES = (
    "app.semantic.provider_factory",
    "app.semantic.openai_provider",
    "app.semantic.provider",
)

_PROHIBITED_LITERAL_TOKENS = {
    "SIM-OFS-FIELDMAINT",
    "SIM-OFS-RENTAL",
    "FIELDMAINT",
    "field_maintenance",
    "pressure_pumping",
    "oilfield_services",
    "sotra",
    "SOTRA",
}


def _imports(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _string_literals(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_entity_modules_never_import_ground_truth_validation() -> None:
    violations = []
    for path in _PRODUCTION_ENTITY_FILES:
        assert path.exists(), f"expected production entity file missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "entity/relationship modules must never import ground-truth validation:\n"
        + "\n".join(violations)
    )


def test_entity_modules_contain_no_hard_coded_simulation_identifiers() -> None:
    violations = []
    for path in _PRODUCTION_ENTITY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for literal in _string_literals(tree):
            for token in _PROHIBITED_LITERAL_TOKENS:
                if token in literal:
                    violations.append(
                        f"{path.relative_to(_REPO_ROOT)} contains literal {literal!r}"
                    )
    assert not violations, (
        "entity/relationship modules must contain no simulation/industry-specific literals:\n"
        + "\n".join(violations)
    )


def test_entity_resolution_modules_never_import_an_ai_provider() -> None:
    """E100 portability: entity/relationship resolution must be
    deterministic/local, never dependent on cloud AI -- unlike
    app/semantic/*, this package has no AI provider seam at all."""
    violations = []
    for path in _PRODUCTION_ENTITY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_AI_PROVIDER_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "entity/relationship modules must never import an AI-provider-facing module:\n"
        + "\n".join(violations)
    )
