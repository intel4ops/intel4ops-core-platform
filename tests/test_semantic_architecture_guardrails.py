"""P3.xxE.1 section 36 (release-blocking) + section 35 I/K/M.

Fails CI if the production semantic surface:
  - imports anything from app.ground_truth_validation (isolation, section 1A)
  - contains a hard-coded simulation ID / industry-name string literal
    (section 1B/1C) -- scanned narrowly (known SIM-* prefixes and this
    repo's actual named simulation families) so ordinary English words
    used in docstrings/descriptions never trigger a false positive
  - sends a full dataset to an AI provider (section 28/35-M)
"""

import ast
from pathlib import Path

import pandas as pd

from app.semantic.provider import FieldInterpretationContext, SemanticInterpretationRequest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRODUCTION_SEMANTIC_FILES = [
    _REPO_ROOT / "app" / "semantic" / "__init__.py",
    _REPO_ROOT / "app" / "semantic" / "profiler.py",
    _REPO_ROOT / "app" / "semantic" / "role_classifier.py",
    _REPO_ROOT / "app" / "semantic" / "concept_registry.py",
    _REPO_ROOT / "app" / "semantic" / "candidate.py",
    _REPO_ROOT / "app" / "semantic" / "candidate_generator.py",
    _REPO_ROOT / "app" / "semantic" / "confidence_engine.py",
    _REPO_ROOT / "app" / "semantic" / "provider.py",
    _REPO_ROOT / "app" / "semantic" / "sampling.py",
    _REPO_ROOT / "app" / "semantic" / "interpreter.py",
    _REPO_ROOT / "app" / "models" / "semantic.py",
    _REPO_ROOT / "app" / "services" / "analysis_case_semantic_service.py",
    _REPO_ROOT / "app" / "api" / "semantic_routes.py",
    _REPO_ROOT / "app" / "schemas" / "semantic.py",
    _REPO_ROOT / "app" / "semantic" / "review.py",
    _REPO_ROOT / "app" / "models" / "semantic_review.py",
    _REPO_ROOT / "app" / "services" / "semantic_review_service.py",
    _REPO_ROOT / "app" / "api" / "semantic_review_routes.py",
    _REPO_ROOT / "app" / "schemas" / "semantic_review.py",
    _REPO_ROOT / "app" / "semantic" / "openai_provider.py",
    _REPO_ROOT / "app" / "semantic" / "provider_factory.py",
    _REPO_ROOT / "app" / "semantic" / "neighbor_context.py",
    _REPO_ROOT / "app" / "semantic" / "cross_dataset_context.py",
    _REPO_ROOT / "app" / "semantic" / "case_context.py",
]

# Also re-verify the pre-existing production execution surface from
# P3.xxD.1B/1E stays clean of app.semantic imports of ground truth --
# semantic modules must never appear as a validation import EITHER
# direction is checked, but this file's job is specifically the semantic
# side: semantic -> validation must never exist.
_FORBIDDEN_IMPORT_PREFIXES = ("app.ground_truth_validation", "app.models.ground_truth_validation")

# Deliberately narrow and literal (section 36: "do not make this so
# brittle that fixture/test strings trigger failures") -- these are the
# exact simulation-code prefixes and industry family names this program
# has actually used as certification fixtures. A docstring mentioning
# "maintenance" or "invoice" as an English word is fine; a string literal
# equal to one of these tokens is the actual prohibited pattern.
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


def test_semantic_modules_never_import_ground_truth_validation() -> None:
    violations = []
    for path in _PRODUCTION_SEMANTIC_FILES:
        assert path.exists(), f"expected production semantic file missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imports(tree):
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {module!r}")
    assert not violations, (
        "semantic modules must never import ground-truth validation:\n" + "\n".join(violations)
    )


def test_semantic_modules_contain_no_hard_coded_simulation_identifiers() -> None:
    violations = []
    for path in _PRODUCTION_SEMANTIC_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for literal in _string_literals(tree):
            for token in _PROHIBITED_LITERAL_TOKENS:
                if token in literal:
                    violations.append(
                        f"{path.relative_to(_REPO_ROOT)} contains literal {literal!r}"
                    )
    assert not violations, (
        "semantic modules must contain no simulation/industry-specific literals:\n"
        + "\n".join(violations)
    )


def test_orchestration_service_semantic_call_site_has_no_simulation_branch() -> None:
    """The one call site outside app/semantic/ that invokes this layer
    (AnalysisCaseOrchestrationService._run_semantic_interpretation) must
    also stay free of the same prohibited tokens."""
    path = _REPO_ROOT / "app" / "services" / "analysis_case_orchestration_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = [
        literal
        for literal in _string_literals(tree)
        if any(token in literal for token in _PROHIBITED_LITERAL_TOKENS)
    ]
    assert not violations, (
        f"orchestration service contains simulation-specific literals: {violations}"
    )


def test_semantic_interpretation_request_never_carries_a_full_dataframe() -> None:
    """Section 35-M: structurally, the AI request contract has no field
    capable of holding a full dataset -- only bounded per-field context
    objects with a `sample_values: list[str]`, never a DataFrame/Series."""
    from dataclasses import fields as dataclass_fields

    request_field_types = {f.name: f.type for f in dataclass_fields(SemanticInterpretationRequest)}
    context_field_types = {f.name: f.type for f in dataclass_fields(FieldInterpretationContext)}
    for type_repr in {**request_field_types, **context_field_types}.values():
        assert "DataFrame" not in str(type_repr)
        assert "Series" not in str(type_repr)


def test_interpret_dataset_never_sends_more_than_the_bounded_sample() -> None:
    """Runtime proof, not just a type-level one: a 10,000-row dataset
    still produces a bounded (<=12 value) sample per field in the request
    handed to the provider."""
    from app.semantic.interpreter import interpret_dataset

    captured: dict[str, object] = {}

    class _SpyProvider:
        provider_name = "spy"
        provider_version = "1.0"

        def propose(self, request: SemanticInterpretationRequest):  # type: ignore[no-untyped-def]
            captured["request"] = request
            from app.semantic.provider import SemanticInterpretationResponse

            return SemanticInterpretationResponse(
                proposals=[],
                provider_name=self.provider_name,
                provider_version=self.provider_version,
            )

    large_df = pd.DataFrame({"asset_id": [f"A{i}" for i in range(10_000)]})
    interpret_dataset("ds-large", "large.csv", large_df, provider=_SpyProvider())
    request = captured["request"]
    assert isinstance(request, SemanticInterpretationRequest)
    for field_context in request.fields:
        assert len(field_context.sample_values) <= 12
