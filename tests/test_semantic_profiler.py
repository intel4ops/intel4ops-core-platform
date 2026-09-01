"""P3.xxE.1 section 35 A/B/C: dataset profiling and role classification are
schema-general -- renaming a file, reordering columns, or a single generic
field never changes the result."""

import pandas as pd

from app.semantic.profiler import dataset_profiler
from app.semantic.role_classifier import dataset_role_classifier

WORK_ORDER_DF = pd.DataFrame(
    {
        "work_order_id": ["WO-1", "WO-2", "WO-3", "WO-4"],
        "status": ["open", "closed", "open", "closed"],
        "scheduled_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "asset_id": ["A1", "A1", "A2", "A2"],
    }
)


def test_a_renaming_the_dataset_label_does_not_change_role_result() -> None:
    profile_a = dataset_profiler.profile("work_orders.csv", WORK_ORDER_DF)
    profile_b = dataset_profiler.profile("wo_export_2026_08_29_final_v3.csv", WORK_ORDER_DF)
    role_a = dataset_role_classifier.classify(profile_a)
    role_b = dataset_role_classifier.classify(profile_b)
    assert role_a.primary_role == role_b.primary_role
    assert role_a.confidence == role_b.confidence
    assert role_a.evidence == role_b.evidence


def test_b_column_reordering_does_not_change_role_result() -> None:
    reordered = WORK_ORDER_DF[["asset_id", "scheduled_date", "work_order_id", "status"]]
    profile_a = dataset_profiler.profile("work_orders.csv", WORK_ORDER_DF)
    profile_b = dataset_profiler.profile("work_orders.csv", reordered)
    role_a = dataset_role_classifier.classify(profile_a)
    role_b = dataset_role_classifier.classify(profile_b)
    assert role_a.primary_role == role_b.primary_role
    assert role_a.confidence == role_b.confidence


def test_c_generic_fields_alone_never_force_a_specialized_role() -> None:
    """asset_id + amount + date together satisfy the generic dataset-level
    TRANSACTION shape (weak, catch-all) but must never independently
    produce a SPECIALIZED role like WORK_ORDER, INVOICE, or LABOR -- none
    of the field names carry any order/invoice/labor-specific evidence."""
    generic_df = pd.DataFrame(
        {
            "asset_id": ["A1", "A2", "A3", "A4"],
            "amount": ["100.50", "200.00", "50.25", "999.99"],
            "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        }
    )
    profile = dataset_profiler.profile("generic.csv", generic_df)
    role = dataset_role_classifier.classify(profile)
    assert role.primary_role not in {"work_order", "invoice", "labor", "inventory", "contract"}


def test_c_asset_id_alone_never_forces_any_specialized_role() -> None:
    single_field_df = pd.DataFrame({"asset_id": ["A1", "A2", "A3", "A4", "A5"]})
    profile = dataset_profiler.profile("assets.csv", single_field_df)
    role = dataset_role_classifier.classify(profile)
    assert role.primary_role not in {"work_order", "invoice", "labor", "inventory", "contract"}


def test_amount_field_alone_never_forces_invoice_role() -> None:
    amount_only_df = pd.DataFrame({"amount": ["100.50", "200.00", "50.25"]})
    profile = dataset_profiler.profile("amounts.csv", amount_only_df)
    role = dataset_role_classifier.classify(profile)
    assert role.primary_role != "invoice"


def _field(profile: object, name: str):  # type: ignore[no-untyped-def]
    return next(f for f in profile.fields if f.source_field == name)  # type: ignore[attr-defined]


# --- P3.xxV.2F: is_candidate_reference_identifier ---


def test_a_primary_key_shaped_field_is_identifier_not_reference() -> None:
    """A (PRIMARY ID): near-unique values -- is_candidate_identifier True,
    is_candidate_reference_identifier False (mutually exclusive, primary-key
    behavior is unchanged)."""
    df = pd.DataFrame({"asset_id": [f"A{i}" for i in range(20)]})
    profile = dataset_profiler.profile("assets.csv", df)
    field = _field(profile, "asset_id")
    assert field.is_candidate_identifier is True
    assert field.is_candidate_reference_identifier is False


def test_b_repeated_foreign_key_shaped_field_is_reference_identifier() -> None:
    """B (FOREIGN KEY): many rows, few distinct real-world entities
    (>10 distinct, well below the 0.95 uniqueness bar) -- is_candidate_identifier
    False, is_candidate_reference_identifier True."""
    # 15 distinct assets, each referenced ~10 times = 150 rows, ratio ~0.10
    values = [f"A{i % 15}" for i in range(150)]
    df = pd.DataFrame({"asset_id": values})
    profile = dataset_profiler.profile("work_orders.csv", df)
    field = _field(profile, "asset_id")
    assert field.is_candidate_identifier is False
    assert field.is_candidate_reference_identifier is True


def test_negative_a_low_cardinality_status_shaped_field_is_neither() -> None:
    """Negative A (Section 12.A): a 3-value categorical/status-shaped field
    must not be flagged as a reference identifier merely by repeating --
    the >10-distinct floor excludes it generically, regardless of column
    name."""
    values = ["OPEN", "CLOSED", "PENDING"] * 40
    df = pd.DataFrame({"status_id": values})
    profile = dataset_profiler.profile("tickets.csv", df)
    field = _field(profile, "status_id")
    assert field.is_candidate_identifier is False
    assert field.is_candidate_reference_identifier is False


def test_negative_b_constant_field_is_neither() -> None:
    """Negative B: a constant value (distinct_count == 1) never qualifies as
    any kind of identifier."""
    df = pd.DataFrame({"asset_id": ["A1"] * 50})
    profile = dataset_profiler.profile("constant.csv", df)
    field = _field(profile, "asset_id")
    assert field.is_candidate_identifier is False
    assert field.is_candidate_reference_identifier is False


def test_profiler_never_hits_the_network_or_requires_ai() -> None:
    """Deterministic profiling has no provider dependency at all -- import
    the profiler module in isolation and confirm it never imports
    app.semantic.provider."""
    import app.semantic.profiler as profiler_module

    assert "provider" not in profiler_module.__name__
    source = profiler_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        content = handle.read()
    assert "app.semantic.provider" not in content
    assert "requests" not in content
    assert "httpx" not in content
