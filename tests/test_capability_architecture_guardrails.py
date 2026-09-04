"""P3.xxE.5 Intelligence Activation (SHADOW) release-blocking guardrails.

A separate, narrow guardrail file for the capability-index/readiness
surface, mirroring test_entities_architecture_guardrails.py's and
test_process_architecture_guardrails.py's own scoping decision. Fails CI
if the production surface:
  - imports anything from app.ground_truth_validation
  - contains a hard-coded simulation ID / industry-name string literal
  - the GENERIC evaluator (evaluate_readiness) branches on a specific
    pack_code/rule_code literal -- plan review instruction 14: requirement
    evaluation and readiness matching must not branch on model code.
    derive_legacy_activation() in shadow_comparison.py is explicitly
    EXEMPT -- its whole job is to faithfully re-derive the pre-existing,
    already-hard-coded legacy activation condition, which is inherently
    per-rule by definition.
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRODUCTION_CAPABILITY_FILES = [
    _REPO_ROOT / "app" / "intelligence_packs" / "__init__.py",
    _REPO_ROOT / "app" / "intelligence_packs" / "registry.py",
    _REPO_ROOT / "app" / "intelligence_packs" / "confidence_distribution.py",
    _REPO_ROOT / "app" / "intelligence_packs" / "case_capability_index.py",
    _REPO_ROOT / "app" / "intelligence_packs" / "shadow_comparison.py",
    _REPO_ROOT / "app" / "services" / "intelligence_readiness_service.py",
    _REPO_ROOT / "app" / "services" / "case_capability_index_service.py",
    _REPO_ROOT / "app" / "services" / "contract_rate_compliance_service.py",
    _REPO_ROOT / "app" / "models" / "intelligence_activation.py",
]

_FORBIDDEN_IMPORT_PREFIXES = ("app.ground_truth_validation", "app.models.ground_truth_validation")

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


def test_capability_modules_never_import_ground_truth_validation() -> None:
    violations = []
    for path in _PRODUCTION_CAPABILITY_FILES:
        assert path.exists(), f"expected production capability file missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "capability modules must never import ground-truth validation:\n" + "\n".join(violations)
    )


def test_capability_modules_contain_no_hard_coded_simulation_identifiers() -> None:
    violations = []
    for path in _PRODUCTION_CAPABILITY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for literal in _string_literals(tree):
            for token in _PROHIBITED_LITERAL_TOKENS:
                if token in literal:
                    violations.append(
                        f"{path.relative_to(_REPO_ROOT)} contains literal {literal!r}"
                    )
    assert not violations, (
        "capability modules must contain no simulation/industry-specific literals:\n"
        + "\n".join(violations)
    )


def test_evaluate_readiness_never_branches_on_pack_or_rule_code() -> None:
    """Plan review instruction 14, enforced structurally: parse
    evaluate_readiness()'s own AST and assert no comparison anywhere
    inside it tests pack.pack_code or pack.rule_code against a literal.
    The function may (and does) read pack.required_* fields generically --
    it must never special-case a specific code."""
    path = _REPO_ROOT / "app" / "services" / "intelligence_readiness_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_readiness":
            target = node
            break
    assert target is not None, "evaluate_readiness() not found"

    violations = []
    for node in ast.walk(target):
        if isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                if isinstance(side, ast.Attribute) and side.attr in ("pack_code", "rule_code"):
                    violations.append(ast.dump(node))
    assert not violations, (
        "evaluate_readiness() must never branch on pack_code/rule_code:\n" + "\n".join(violations)
    )
