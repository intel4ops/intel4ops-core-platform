"""P3.xxE.2 section 11: generic neighboring-field semantic context. Pure
unit tests against generate_neighbor_context_evidence() -- no DB needed."""

from app.semantic.concept_registry import default_canonical_concept_registry
from app.semantic.neighbor_context import generate_neighbor_context_evidence
from app.semantic.profiler import DatasetProfile, FieldProfile


def _field(name: str) -> FieldProfile:
    return FieldProfile(
        source_field=name,
        physical_type="object",
        null_count=0,
        row_count=10,
        null_rate=0.0,
        distinct_count=10,
        uniqueness_ratio=1.0,
    )


def _dataset(fields: list[str]) -> DatasetProfile:
    field_profiles = [_field(f) for f in fields]
    return DatasetProfile(
        dataset_label="ds.csv",
        row_count=10,
        column_count=len(fields),
        fields=field_profiles,
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


# E. Neighbor-field context changes candidate evidence appropriately.
def test_work_order_shaped_siblings_corroborate_work_order_id() -> None:
    dataset = _dataset(["svc_ord", "technician_id", "scheduled_date", "status"])
    field = dataset.fields[0]  # svc_ord has no direct alias itself
    candidates = generate_neighbor_context_evidence(
        "ds-1", dataset, field, {"work_order_id"}, default_canonical_concept_registry
    )
    assert len(candidates) == 1
    assert candidates[0].candidate_concept == "work_order_id"
    assert candidates[0].evidence_components[0].component_type == "neighbor_field_context"


def test_sensor_shaped_siblings_do_not_corroborate_anything() -> None:
    dataset = _dataset(["svc_ord", "temperature", "pressure", "flow_rate"])
    field = dataset.fields[0]
    candidates = generate_neighbor_context_evidence(
        "ds-1", dataset, field, {"work_order_id"}, default_canonical_concept_registry
    )
    assert candidates == []


def test_no_candidate_concepts_produces_no_neighbor_evidence() -> None:
    dataset = _dataset(["svc_ord", "technician_id"])
    field = dataset.fields[0]
    assert (
        generate_neighbor_context_evidence(
            "ds-1", dataset, field, set(), default_canonical_concept_registry
        )
        == []
    )


def test_neighbor_evidence_excludes_the_field_itself_as_a_sibling() -> None:
    # asset_id is itself an alias -- verify comparing against itself isn't
    # what produces the corroboration (single-field dataset -> no siblings).
    dataset = _dataset(["asset_id"])
    field = dataset.fields[0]
    candidates = generate_neighbor_context_evidence(
        "ds-1", dataset, field, {"asset_id"}, default_canonical_concept_registry
    )
    assert candidates == []
