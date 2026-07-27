from datetime import date
from decimal import Decimal

from app.engines.job_to_cash_engine import detect_job_to_cash


def test_all_bounded_job_to_cash_leakage_rules_are_traceable() -> None:
    records: list[dict[str, object]] = [
        {
            "type": "job",
            "id": "J1",
            "status": "completed",
            "completed_at": "2026-01-01",
            "billing_window_days": 5,
            "contractual_charges": "100",
            "expected_revenue": "100",
            "governed_cost": "150",
        },
        {
            "type": "job",
            "id": "J2",
            "status": "completed",
            "completed_at": "2026-01-01",
            "billing_window_days": 5,
            "contractual_charges": "20",
            "expected_revenue": "120",
            "governed_cost": "50",
        },
        {
            "type": "time_entry",
            "id": "T2",
            "job_id": "J2",
            "billable_amount": "100",
            "billed_amount": "50",
        },
        {
            "type": "material",
            "id": "M2",
            "job_id": "J2",
            "billable_amount": "30",
            "billed_amount": "0",
        },
        {
            "type": "invoice",
            "id": "I2",
            "job_id": "J2",
            "amount": "80",
            "issued_at": "2026-01-20",
            "due_at": "2026-02-01",
            "valid": True,
        },
        {"type": "payment", "id": "P2", "invoice_id": "I2", "amount": "10"},
        {
            "type": "documentation",
            "id": "D2",
            "job_id": "J2",
            "required": True,
            "valid": False,
        },
    ]

    rows = detect_job_to_cash(records, date(2026, 3, 1))
    codes = {row.code for row in rows}

    assert codes == {
        "COMPLETED_UNBILLED",
        "UNDERBILLING",
        "MISSING_BILLABLE_TIME",
        "MISSING_MATERIALS_EXPENSES",
        "INVOICE_DELAY",
        "PAYMENT_DELAY",
        "NEGATIVE_MARGIN",
        "DOCUMENTATION_BLOCKER",
    }
    assert all(row.exposure >= Decimal("0") and row.evidence_ids for row in rows)


def test_healthy_job_has_no_leakage() -> None:
    rows = detect_job_to_cash(
        [
            {
                "type": "job",
                "id": "healthy",
                "status": "completed",
                "completed_at": "2026-01-01",
                "billing_window_days": 5,
                "expected_revenue": "100",
                "governed_cost": "50",
            },
            {
                "type": "invoice",
                "id": "invoice",
                "job_id": "healthy",
                "amount": "100",
                "issued_at": "2026-01-02",
                "due_at": "2026-02-01",
                "valid": True,
            },
            {"type": "payment", "id": "payment", "invoice_id": "invoice", "amount": "100"},
        ],
        date(2026, 1, 15),
    )
    assert rows == []
