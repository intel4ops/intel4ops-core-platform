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
