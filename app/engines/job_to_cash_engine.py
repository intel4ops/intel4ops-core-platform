from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Leakage:
    code: str
    job_id: str
    exposure: Decimal
    reason: str
    evidence_ids: tuple[str, ...]


def detect_job_to_cash(records: list[dict[str, object]], as_of: date) -> list[Leakage]:
    jobs = {str(r["id"]): r for r in records if r["type"] == "job"}
    invoices = [r for r in records if r["type"] == "invoice"]
    time = [r for r in records if r["type"] == "time_entry"]
    materials = [r for r in records if r["type"] in {"material", "expense"}]
    payments = [r for r in records if r["type"] == "payment"]
    documents = [r for r in records if r["type"] == "documentation"]
    findings: list[Leakage] = []
    for job_id, job in jobs.items():
        job_invoices = [
            r for r in invoices if str(r.get("job_id")) == job_id and r.get("valid", True)
        ]
        billable_time = sum(
            (_money(r, "billable_amount") for r in time if str(r.get("job_id")) == job_id),
            Decimal(),
        )
        billed_time = sum(
            (_money(r, "billed_amount") for r in time if str(r.get("job_id")) == job_id), Decimal()
        )
        billable_other = sum(
            (_money(r, "billable_amount") for r in materials if str(r.get("job_id")) == job_id),
            Decimal(),
        )
        billed_other = sum(
            (_money(r, "billed_amount") for r in materials if str(r.get("job_id")) == job_id),
            Decimal(),
        )
        invoice_total = sum((_money(r, "amount") for r in job_invoices), Decimal())
        expected = billable_time + billable_other + _money(job, "contractual_charges")
        completed = _date(job.get("completed_at"))
        window = int(str(job.get("billing_window_days", 5)))
        if (
            job.get("status") == "completed"
            and not job_invoices
            and completed
            and (as_of - completed).days > window
        ):
            findings.append(
                _leak(
                    "COMPLETED_UNBILLED",
                    job_id,
                    expected,
                    "Completed job has no valid invoice",
                    job,
                )
            )
        if job_invoices and invoice_total < expected:
            findings.append(
                _leak(
                    "UNDERBILLING",
                    job_id,
                    expected - invoice_total,
                    "Invoice is below governed billable value",
                    job,
                )
            )
        if billed_time < billable_time:
            findings.append(
                _leak(
                    "MISSING_BILLABLE_TIME",
                    job_id,
                    billable_time - billed_time,
                    "Approved time is absent from billing",
                    job,
                )
            )
        if billed_other < billable_other:
            findings.append(
                _leak(
                    "MISSING_MATERIALS_EXPENSES",
                    job_id,
                    billable_other - billed_other,
                    "Billable materials or expenses are absent",
                    job,
                )
            )
        if job_invoices and completed:
            issued = min(_date(r["issued_at"]) for r in job_invoices)
            if (issued - completed).days > window:
                findings.append(
                    _leak(
                        "INVOICE_DELAY",
                        job_id,
                        invoice_total,
                        "Invoice exceeded completion-to-invoice target",
                        job,
                    )
                )
        for invoice in job_invoices:
            due = _date(invoice["due_at"])
            paid = sum(
                (_money(r, "amount") for r in payments if r.get("invoice_id") == invoice["id"]),
                Decimal(),
            )
            if due < as_of and paid < _money(invoice, "amount"):
                findings.append(
                    _leak(
                        "PAYMENT_DELAY",
                        job_id,
                        _money(invoice, "amount") - paid,
                        "Invoice remains outstanding after due date",
                        invoice,
                    )
                )
        revenue = invoice_total or _money(job, "expected_revenue")
        costs = _money(job, "governed_cost")
        if costs > revenue:
            findings.append(
                _leak(
                    "NEGATIVE_MARGIN",
                    job_id,
                    costs - revenue,
                    "Governed job cost exceeds revenue",
                    job,
                )
            )
        required = [r for r in documents if str(r.get("job_id")) == job_id and r.get("required")]
        if any(not r.get("valid") for r in required):
            findings.append(
                _leak(
                    "DOCUMENTATION_BLOCKER",
                    job_id,
                    expected,
                    "Required billing documentation is missing or invalid",
                    job,
                )
            )
    return sorted(findings, key=lambda item: (item.job_id, item.code))


def _money(row: dict[str, object], key: str) -> Decimal:
    return Decimal(str(row.get(key, "0")))


def _date(value: object) -> date:
    return date.fromisoformat(str(value)[:10])


def _leak(
    code: str, job_id: str, exposure: Decimal, reason: str, row: dict[str, object]
) -> Leakage:
    return Leakage(code, job_id, exposure, reason, (f"{row['type']}:{row['id']}",))
