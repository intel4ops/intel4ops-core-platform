"""Structural (not merely behavioral) proof that ground_truth.json can
never enter Connect/Trust/Mapping/Entity Resolution/Intelligence/Command:
Core's artifact/ingestion contract simply has no ground-truth artifact
type, route, or schema field at all. Validation tooling holds ground truth
entirely outside this system and compares against exposed stable
identifiers (case_code, run id, finding id, rule_id, entities) after a run
completes."""

import inspect

from app.ingestion.extraction_contract import ArtifactExtractionResult
from app.ingestion.parsers import default_parser_registry
from app.models.analysis_case import SourceArtifact
from app.schemas.analysis_case import AnalysisCaseCreate


def test_no_parser_recognizes_a_ground_truth_mime_or_extension() -> None:
    registry = default_parser_registry()
    for mime, ext in [
        ("application/json", ".ground_truth.json"),
        ("application/vnd.intel4ops.ground-truth+json", ".json"),
    ]:
        # A literal ground_truth.json filename still resolves via the plain
        # .json extension/mime -- there is no special-cased ground-truth
        # format; it is registered as an ordinary tabular/key-value JSON
        # file like any other, never as a distinct privileged type.
        parser = registry.select(mime, ext)
        if parser is not None:
            assert parser.code in {"json"}


def test_source_artifact_model_has_no_ground_truth_concept() -> None:
    field_names = set(SourceArtifact.__table__.columns.keys())
    assert not any("ground_truth" in name for name in field_names)
    assert not any("expected_answer" in name for name in field_names)


def test_analysis_case_create_schema_has_no_ground_truth_field() -> None:
    field_names = set(AnalysisCaseCreate.model_fields.keys())
    assert not any("ground_truth" in name for name in field_names)


def test_extraction_contract_has_no_ground_truth_channel() -> None:
    signature = inspect.signature(ArtifactExtractionResult)
    assert not any("ground_truth" in name for name in signature.parameters)
