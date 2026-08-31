"""P3.xxE.4 Operational Process Interpretation release-blocking guardrails.

A separate, narrow guardrail file for the process surface (mirrors
test_entities_architecture_guardrails.py's own scoping decision). Fails CI
if the production process surface:
  - imports anything from app.ground_truth_validation
  - contains a hard-coded simulation ID / industry-name string literal
  - imports any AI-provider-facing module (app.semantic.provider,
    app.semantic.openai_provider, app.semantic.provider_factory) --
    process interpretation must stay deterministic/local by default, never
    dependent on cloud AI (reasoning_provider.py ships an interface +
    NullProcessReasoningProvider only, no real backend wired this
    milestone)
  - imports anything from app.services.causal_intelligence_service or
    app.models.causal_intelligence -- Causal Links' precedes/causes edges
    must never be silently treated as discovered process-sequence
    evidence (spec test X; see the approved plan's reconciliation table:
    Causal Links has zero automatic discovery, only post-hoc human-
    hypothesis evaluation, structurally non-overlapping with this
    milestone's actual job)
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRODUCTION_PROCESS_FILES = [
    _REPO_ROOT / "app" / "process" / "__init__.py",
    _REPO_ROOT / "app" / "process" / "activity_type.py",
    _REPO_ROOT / "app" / "process" / "temporal_evidence.py",
    _REPO_ROOT / "app" / "process" / "activity_candidate.py",
    _REPO_ROOT / "app" / "process" / "activity_type_inference.py",
    _REPO_ROOT / "app" / "process" / "state_normalization.py",
    _REPO_ROOT / "app" / "process" / "participation_inference.py",
    _REPO_ROOT / "app" / "process" / "case_process_context.py",
    _REPO_ROOT / "app" / "process" / "activity_discovery.py",
    _REPO_ROOT / "app" / "process" / "process_anchor_discovery.py",
    _REPO_ROOT / "app" / "process" / "process_boundary.py",
    _REPO_ROOT / "app" / "process" / "sequence_discovery.py",
    _REPO_ROOT / "app" / "process" / "precedence_confidence.py",
    _REPO_ROOT / "app" / "process" / "process_confidence.py",
    _REPO_ROOT / "app" / "process" / "process_relationship_support.py",
    _REPO_ROOT / "app" / "process" / "reasoning_provider.py",
    _REPO_ROOT / "app" / "process" / "process_interpretation.py",
    _REPO_ROOT / "app" / "process" / "intelligence_contract.py",
    _REPO_ROOT / "app" / "models" / "process_canonical.py",
    _REPO_ROOT / "app" / "services" / "analysis_case_process_service.py",
    _REPO_ROOT / "app" / "api" / "process_routes.py",
    _REPO_ROOT / "app" / "schemas" / "process.py",
]

_FORBIDDEN_IMPORT_PREFIXES = ("app.ground_truth_validation", "app.models.ground_truth_validation")
_FORBIDDEN_AI_PROVIDER_PREFIXES = (
    "app.semantic.provider_factory",
    "app.semantic.openai_provider",
    "app.semantic.provider",
)
_FORBIDDEN_CAUSAL_LINKS_PREFIXES = (
    "app.services.causal_intelligence_service",
    "app.models.causal_intelligence",
    "app.schemas.causal_intelligence",
    "app.api.causal_intelligence_routes",
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


def test_process_modules_never_import_ground_truth_validation() -> None:
    violations = []
    for path in _PRODUCTION_PROCESS_FILES:
        assert path.exists(), f"expected production process file missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "process modules must never import ground-truth validation:\n" + "\n".join(violations)
    )


def test_process_modules_contain_no_hard_coded_simulation_identifiers() -> None:
    violations = []
    for path in _PRODUCTION_PROCESS_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for literal in _string_literals(tree):
            for token in _PROHIBITED_LITERAL_TOKENS:
                if token in literal:
                    violations.append(
                        f"{path.relative_to(_REPO_ROOT)} contains literal {literal!r}"
                    )
    assert not violations, (
        "process modules must contain no simulation/industry-specific literals:\n"
        + "\n".join(violations)
    )


def test_process_modules_never_import_an_ai_provider() -> None:
    """process_interpretation must not be MADE DEPENDENT on an LLM (spec
    section 30) -- reasoning_provider.py's NullProcessReasoningProvider is
    the only shipped default this milestone."""
    violations = []
    for path in _PRODUCTION_PROCESS_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_AI_PROVIDER_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "process modules must never import an AI-provider-facing module:\n" + "\n".join(violations)
    )


def test_process_modules_never_import_causal_links() -> None:
    """Spec test X: Causal Links' precedes/causes edges (post-hoc,
    human-hypothesis-evaluation only, per the plan's reconciliation
    table) must never be silently converted into discovered process-
    sequence evidence."""
    violations = []
    for path in _PRODUCTION_PROCESS_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_CAUSAL_LINKS_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "process modules must never import Causal Links as a process-sequence source:\n"
        + "\n".join(violations)
    )
