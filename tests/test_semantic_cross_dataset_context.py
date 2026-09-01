"""P3.xxE.2 section 12/required-correction: order-independent cross-dataset
semantic corroboration. Part A is pure unit tests against
generate_cross_dataset_evidence(); part B is the required dataset-order-
permutation proof against the real two-pass orchestration stage."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.models.semantic import SemanticInterpretationDecision
from app.schemas.contracts import OrganizationCreate
from app.semantic.case_context import CaseSemanticContext
from app.semantic.concept_registry import default_canonical_concept_registry
from app.semantic.cross_dataset_context import generate_cross_dataset_evidence
from app.semantic.profiler import DatasetProfile, FieldProfile
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _field(
    name: str,
    samples: list[str],
    identifier: bool = True,
    reference_identifier: bool = False,
) -> FieldProfile:
    return FieldProfile(
        source_field=name,
        physical_type="object",
        null_count=0,
        row_count=len(samples),
        null_rate=0.0,
        distinct_count=len(set(samples)),
        uniqueness_ratio=1.0,
        sample_values=samples,
        is_candidate_identifier=identifier,
        is_candidate_reference_identifier=reference_identifier,
    )


def _dataset(label: str, fields: list[FieldProfile]) -> DatasetProfile:
    return DatasetProfile(
        dataset_label=label,
        row_count=10,
        column_count=len(fields),
        fields=fields,
        candidate_grain=[],
        candidate_primary_keys=[],
        candidate_foreign_keys=[],
        is_append_or_event_like=False,
        is_snapshot_like=False,
        is_master_or_reference_like=False,
        is_transaction_like=False,
        is_ledger_like=False,
        is_measurement_like=False,
    )


# F. Cross-dataset overlap strengthens semantic confidence.
def test_overlapping_identifier_values_produce_cross_dataset_evidence() -> None:
    current_field = _field("job_ref", ["A1", "A2", "A3"])
    sibling_field = _field("work_order_id", ["A1", "A2", "A9"])
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    candidates = generate_cross_dataset_evidence(
        "this-ds",
        current_field,
        {"work_order_id"},
        case_context,
        default_canonical_concept_registry,
    )
    assert len(candidates) == 1
    assert candidates[0].candidate_concept == "work_order_id"
    assert candidates[0].evidence_components[0].component_type == "cross_dataset_overlap"


def test_no_value_overlap_produces_no_cross_dataset_evidence() -> None:
    current_field = _field("job_ref", ["A1", "A2", "A3"])
    sibling_field = _field("work_order_id", ["Z1", "Z2", "Z3"])
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    candidates = generate_cross_dataset_evidence(
        "this-ds",
        current_field,
        {"work_order_id"},
        case_context,
        default_canonical_concept_registry,
    )
    assert candidates == []


def test_non_identifier_field_never_gets_cross_dataset_evidence() -> None:
    current_field = _field("job_ref", ["A1", "A2"], identifier=False)
    sibling_field = _field("work_order_id", ["A1", "A2"])
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    assert (
        generate_cross_dataset_evidence(
            "this-ds",
            current_field,
            {"work_order_id"},
            case_context,
            default_canonical_concept_registry,
        )
        == []
    )


def test_same_dataset_key_is_excluded_from_its_own_comparison() -> None:
    current_field = _field("job_ref", ["A1", "A2"])
    case_context = CaseSemanticContext(
        profiles={"this-ds": _dataset("this.csv", [current_field])}, roles={}
    )
    assert (
        generate_cross_dataset_evidence(
            "this-ds",
            current_field,
            {"work_order_id"},
            case_context,
            default_canonical_concept_registry,
        )
        == []
    )


def test_no_case_context_returns_no_evidence() -> None:
    current_field = _field("job_ref", ["A1"])
    assert (
        generate_cross_dataset_evidence(
            "this-ds", current_field, {"work_order_id"}, None, default_canonical_concept_registry
        )
        == []
    )


# --- P3.xxV.2F: repeated reference/foreign-key identifier eligibility ---


def test_reference_identifier_field_now_gets_cross_dataset_evidence() -> None:
    """B (generic FK): a field that is NOT near-unique (is_candidate_identifier
    False) but IS a plausible repeated reference identifier can still be
    corroborated -- the exact NEXT-2 mechanism, exercised generically here
    with no simulation-specific data."""
    current_field = _field(
        "job_ref", ["A1", "A2", "A1"], identifier=False, reference_identifier=True
    )
    sibling_field = _field("work_order_id", ["A1", "A2", "A9"])
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    candidates = generate_cross_dataset_evidence(
        "this-ds",
        current_field,
        {"work_order_id"},
        case_context,
        default_canonical_concept_registry,
    )
    assert len(candidates) == 1
    assert candidates[0].candidate_concept == "work_order_id"


def test_reference_identifier_sibling_field_also_eligible() -> None:
    """The broadened eligibility applies symmetrically to the SIBLING field
    too, not just the field under evaluation."""
    current_field = _field("job_ref", ["A1", "A2", "A9"])
    sibling_field = _field(
        "work_order_id", ["A1", "A2", "A1"], identifier=False, reference_identifier=True
    )
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    candidates = generate_cross_dataset_evidence(
        "this-ds",
        current_field,
        {"work_order_id"},
        case_context,
        default_canonical_concept_registry,
    )
    assert len(candidates) == 1


def test_low_cardinality_non_reference_field_still_gets_no_evidence() -> None:
    """A (negative, mirrors Section 12.A): neither near-unique nor a
    plausible reference population (is_candidate_identifier and
    is_candidate_reference_identifier both False, e.g. a 3-value
    categorical/status-shaped field) -- must not receive cross-dataset
    evidence merely because it shares a value with a sibling field."""
    current_field = _field(
        "status_id", ["OPEN", "CLOSED", "OPEN"], identifier=False, reference_identifier=False
    )
    sibling_field = _field("work_order_id", ["OPEN", "Z2", "Z9"])
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    assert (
        generate_cross_dataset_evidence(
            "this-ds",
            current_field,
            {"work_order_id"},
            case_context,
            default_canonical_concept_registry,
        )
        == []
    )


def test_placeholder_only_overlap_produces_no_false_corroboration() -> None:
    """D (negative, Section 12.D): a shared value that is a known
    placeholder/default (here "0000" and "n/a") must never itself count as
    corroborating overlap, even between two otherwise-eligible reference
    identifiers."""
    current_field = _field(
        "job_ref", ["0000", "n/a", "A2"], identifier=False, reference_identifier=True
    )
    sibling_field = _field(
        "work_order_id", ["0000", "N/A", "Z9"], identifier=False, reference_identifier=True
    )
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    assert (
        generate_cross_dataset_evidence(
            "this-ds",
            current_field,
            {"work_order_id"},
            case_context,
            default_canonical_concept_registry,
        )
        == []
    )


def test_genuine_overlap_still_works_alongside_placeholder_values() -> None:
    """A genuine shared non-placeholder value ("A2") still corroborates,
    even when placeholder values are ALSO present on both sides -- the
    placeholder filter removes noise, it does not require a placeholder-free
    dataset."""
    current_field = _field(
        "job_ref", ["0000", "A2", "A1"], identifier=False, reference_identifier=True
    )
    sibling_field = _field(
        "work_order_id", ["0000", "A2", "Z9"], identifier=False, reference_identifier=True
    )
    case_context = CaseSemanticContext(
        profiles={"other-ds": _dataset("other.csv", [sibling_field])}, roles={}
    )
    candidates = generate_cross_dataset_evidence(
        "this-ds",
        current_field,
        {"work_order_id"},
        case_context,
        default_canonical_concept_registry,
    )
    assert len(candidates) == 1


# --- Part B: real orchestration, order-permutation proof ---

INVOICES_CSV = b"invoice_id,work_order_id,amount\nINV-1,WO-100,500\nINV-2,WO-101,750\n"
WORK_ORDERS_CSV = b"wo_id,technician_id,status\nWO-100,T-1,closed\nWO-101,T-2,closed\n"


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case_with_order(
    db: Session, tmp_path: Path, slug: str, filenames_in_order: list[str]
) -> dict[str, SemanticInterpretationDecision]:
    """Registers both fixture files but controls which is uploaded (hence
    processed) first, to prove order doesn't affect the result."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, slug)
    actor = uuid4()
    case = service.create(db, org.id, "Case", "single", actor)
    files_by_name = {
        "invoices.csv": UploadedFile("invoices.csv", INVOICES_CSV),
        "work_orders.csv": UploadedFile("work_orders.csv", WORK_ORDERS_CSV),
    }
    service.register_artifacts(
        db, org.id, case.id, [files_by_name[name] for name in filenames_in_order], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    decisions = list(
        db.scalars(
            select(SemanticInterpretationDecision).where(
                SemanticInterpretationDecision.run_id == run.id
            )
        ).all()
    )
    return {f"{d.analysis_case_dataset_id}:{d.source_field}": d for d in decisions}


def test_cross_dataset_evidence_is_order_independent(db: Session, tmp_path: Path) -> None:
    forward = _run_case_with_order(db, tmp_path, "cdc-order-a", ["invoices.csv", "work_orders.csv"])
    reversed_order = _run_case_with_order(
        db, tmp_path, "cdc-order-b", ["work_orders.csv", "invoices.csv"]
    )

    def _by_field(
        decisions: dict[str, SemanticInterpretationDecision],
    ) -> dict[str, tuple[str | None, str]]:
        return {d.source_field: (d.selected_concept, d.status) for d in decisions.values()}

    forward_by_field = _by_field(forward)
    reversed_by_field = _by_field(reversed_order)

    assert set(forward_by_field) == set(reversed_by_field)
    for field_name in forward_by_field:
        assert forward_by_field[field_name] == reversed_by_field[field_name], (
            f"field {field_name!r} differed by dataset-processing order: "
            f"{forward_by_field[field_name]} vs {reversed_by_field[field_name]}"
        )
