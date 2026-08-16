"""Synthetic golden dataset for the Oilfield Services Job-to-Cash pack (P3.12 + P3.13).

Coverage is scoped to Tier 1 (validated) patterns only. P3.13 promoted three
additional Tier 2 candidates to Tier 1 (J2C-OFS-20, J2C-OFS-24, J2C-OFS-30)
because their preconditions/exclusions support credible deterministic
validation; the rest of the P3.13 portfolio stays Tier 2 (reference
specified) and is deliberately not golden-validated here.

Purely synthetic data -- no client data, no production references. Each case
has an OBSERVED view (the only thing a detector may read) and a separate
HIDDEN TRUTH (expected_patterns / case_type), which tests may assert against
but must never leak into the observed view.

The `detect_*` functions below are a REFERENCE VALIDATION HARNESS ONLY: pure
predicates that mirror each KnowledgePackPattern's documented
detection_preconditions/exclusions closely enough to prove the pattern
content is internally consistent against this dataset. They are test-only
code -- not wired into any API, service, or production code path -- so this
file must never be imported from app/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLEAN_BASE: dict[str, Any] = {
    "status": "completed",
    "billing_grace_period_days": 5,
    "days_since_completion": 10,
    "invoice_exists": True,
    "non_billable": False,
    "milestone_billing": False,
    "canceled": False,
    "field_ticket_billable": True,
    "field_ticket_invoiced": True,
    "field_ticket_duplicate": False,
    "labor_hours_recorded": 40.0,
    "labor_hours_invoiced": 40.0,
    "overtime_hours_recorded": 4.0,
    "overtime_hours_invoiced": 4.0,
    "labor_billable": True,
    "equipment_deployed": True,
    "equipment_billable": True,
    "equipment_hours_recorded": 8.0,
    "equipment_hours_invoiced": 8.0,
    "material_consumed_qty": 10.0,
    "material_invoiced_qty": 10.0,
    "material_billable": True,
    "standby_minutes": 0,
    "standby_minimum_minutes": 60,
    "standby_customer_caused": True,
    "standby_waived": False,
    "standby_invoiced": False,
    "mobilization_occurred": False,
    "mobilization_contract_permits_charge": True,
    "mobilization_waived": False,
    "mobilization_invoiced": False,
    "billed_rate": 100.0,
    "authorized_rate": 100.0,
    "rate_override_approved": False,
    "bundled_pricing": False,
    "credit_applied": 0.0,
    "credit_authorized": 0.0,
    "credit_is_reversal_of_error": False,
    "invoice_issued_days_after_completion": 3,
    "expected_invoicing_turnaround_days": 7,
    "payment_days_outstanding": 20,
    "standard_payment_term_days": 30,
    "documentation_complete": True,
    "extended_payment_term_approved": False,
    "expected_margin_pct": 25.0,
    "actual_margin_pct": 24.0,
    "unbilled_change_order": False,
    "margin_variance_is_normal_business_variance": True,
    # P3.13-promoted Tier 1 patterns
    "vendor_pass_through_eligible": False,
    "vendor_pass_through_billed": True,
    "vendor_pass_through_absorbed_in_flat_rate": False,
    "vendor_pass_through_markup_waived_approved": False,
    "npt_event_customer_attributable": False,
    "npt_event_duration_meets_threshold": False,
    "standby_waiver_in_effect": False,
    "npt_event_billed_as_standby": True,
    "portal_rejection_code_present": False,
    "portal_resubmitted_successfully": True,
    "portal_rejection_is_duplicate": False,
    "portal_invoice_withdrawn_invalid": False,
}


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    case_type: str  # "clean" | "leakage" | "edge" | "ambiguous"
    expected_patterns: tuple[str, ...]
    observed: dict[str, Any]
    notes: str = ""


def _case(
    case_id: str,
    case_type: str,
    expected_patterns: tuple[str, ...],
    notes: str = "",
    **overrides: Any,
) -> GoldenCase:
    observed = {**CLEAN_BASE, **overrides}
    return GoldenCase(
        case_id=case_id,
        case_type=case_type,
        expected_patterns=expected_patterns,
        observed=observed,
        notes=notes,
    )


GOLDEN_CASES: tuple[GoldenCase, ...] = (
    # --- Clean cases: correctly executed, fully billed, no expected pattern ---
    _case("CLEAN-001", "clean", (), "Fully clean baseline job."),
    _case(
        "CLEAN-002",
        "clean",
        (),
        "Clean job with overtime correctly billed.",
        overtime_hours_recorded=6.0,
        overtime_hours_invoiced=6.0,
    ),
    _case(
        "CLEAN-003",
        "clean",
        (),
        "Clean job with standby below contractual minimum.",
        standby_minutes=20,
        standby_minimum_minutes=60,
    ),
    _case(
        "CLEAN-004",
        "clean",
        (),
        "Clean job with approved negotiated rate override.",
        billed_rate=90.0,
        authorized_rate=100.0,
        rate_override_approved=True,
    ),
    _case(
        "CLEAN-005",
        "clean",
        (),
        "Clean job, standard payment cycle, no delay.",
        payment_days_outstanding=15,
    ),
    _case(
        "CLEAN-006",
        "clean",
        (),
        "Clean job with normal, explained margin variance.",
        expected_margin_pct=25.0,
        actual_margin_pct=23.0,
        margin_variance_is_normal_business_variance=True,
    ),
    # --- J2C-OFS-01: Completed Job Not Invoiced ---
    _case(
        "LEAK-01-A",
        "leakage",
        ("J2C-OFS-01",),
        "Completed well past grace period, no invoice.",
        invoice_exists=False,
        days_since_completion=30,
        billing_grace_period_days=5,
    ),
    _case(
        "LEAK-01-B",
        "leakage",
        ("J2C-OFS-01",),
        "Completed, no invoice, far past grace period.",
        invoice_exists=False,
        days_since_completion=60,
        billing_grace_period_days=10,
    ),
    _case(
        "EDGE-01-A",
        "edge",
        (),
        "Completed but still within billing grace period.",
        invoice_exists=False,
        days_since_completion=3,
        billing_grace_period_days=5,
    ),
    _case(
        "EDGE-01-B",
        "edge",
        (),
        "Completed, no invoice, but explicitly non-billable.",
        invoice_exists=False,
        days_since_completion=30,
        non_billable=True,
    ),
    _case(
        "EDGE-01-C",
        "edge",
        (),
        "Completed, no invoice, awaiting milestone billing trigger.",
        invoice_exists=False,
        days_since_completion=30,
        milestone_billing=True,
    ),
    _case(
        "AMBIG-01-A",
        "ambiguous",
        (),
        "No invoice, past a window, but job completion itself is unconfirmed.",
        invoice_exists=False,
        days_since_completion=30,
        status="in_progress",
    ),
    # --- J2C-OFS-02: Field Ticket Not Invoiced ---
    _case(
        "LEAK-02-A",
        "leakage",
        ("J2C-OFS-02",),
        "Billable ticket never invoiced.",
        field_ticket_billable=True,
        field_ticket_invoiced=False,
    ),
    _case(
        "EDGE-02-A",
        "edge",
        (),
        "Ticket not invoiced but explicitly non-billable.",
        field_ticket_billable=False,
        field_ticket_invoiced=False,
    ),
    _case(
        "EDGE-02-B",
        "edge",
        (),
        "Ticket not invoiced because it is a duplicate.",
        field_ticket_billable=True,
        field_ticket_invoiced=False,
        field_ticket_duplicate=True,
    ),
    # --- J2C-OFS-03: Billable Labor Omitted ---
    _case(
        "LEAK-03-A",
        "leakage",
        ("J2C-OFS-03",),
        "Overtime recorded but not invoiced.",
        overtime_hours_recorded=8.0,
        overtime_hours_invoiced=0.0,
    ),
    _case(
        "LEAK-03-B",
        "leakage",
        ("J2C-OFS-03",),
        "Regular labor hours underbilled.",
        labor_hours_recorded=48.0,
        labor_hours_invoiced=40.0,
    ),
    _case(
        "EDGE-03-A",
        "edge",
        (),
        "Overtime recorded but explicitly non-billable.",
        overtime_hours_recorded=8.0,
        overtime_hours_invoiced=0.0,
        labor_billable=False,
    ),
    # --- J2C-OFS-04: Billable Equipment Omitted ---
    _case(
        "LEAK-04-A",
        "leakage",
        ("J2C-OFS-04",),
        "Equipment deployed, never invoiced.",
        equipment_deployed=True,
        equipment_billable=True,
        equipment_hours_recorded=10.0,
        equipment_hours_invoiced=0.0,
    ),
    _case(
        "EDGE-04-A",
        "edge",
        (),
        "Equipment deployed but internal/non-billable.",
        equipment_deployed=True,
        equipment_billable=False,
        equipment_hours_recorded=10.0,
        equipment_hours_invoiced=0.0,
    ),
    # --- J2C-OFS-05: Billable Material Omitted ---
    _case(
        "LEAK-05-A",
        "leakage",
        ("J2C-OFS-05",),
        "Material consumed exceeds material invoiced.",
        material_consumed_qty=25.0,
        material_invoiced_qty=10.0,
        material_billable=True,
    ),
    _case(
        "EDGE-05-A",
        "edge",
        (),
        "Material consumption within contractual allowance.",
        material_consumed_qty=25.0,
        material_invoiced_qty=10.0,
        material_billable=False,
    ),
    # --- J2C-OFS-06: Billable Standby Omitted ---
    _case(
        "LEAK-06-A",
        "leakage",
        ("J2C-OFS-06",),
        "Customer-caused standby over minimum, not billed.",
        standby_minutes=90,
        standby_minimum_minutes=60,
        standby_customer_caused=True,
        standby_waived=False,
        standby_invoiced=False,
    ),
    _case(
        "EDGE-06-A",
        "edge",
        (),
        "Standby below contractual minimum duration.",
        standby_minutes=30,
        standby_minimum_minutes=60,
        standby_customer_caused=True,
        standby_invoiced=False,
    ),
    _case(
        "EDGE-06-B",
        "edge",
        (),
        "Standby caused by servicer, contractually non-billable.",
        standby_minutes=90,
        standby_minimum_minutes=60,
        standby_customer_caused=False,
        standby_invoiced=False,
    ),
    _case(
        "EDGE-06-C",
        "edge",
        (),
        "Standby waived by approved customer agreement.",
        standby_minutes=90,
        standby_minimum_minutes=60,
        standby_customer_caused=True,
        standby_waived=True,
        standby_invoiced=False,
    ),
    # --- J2C-OFS-07: Mob/Demob Charge Omitted ---
    _case(
        "LEAK-07-A",
        "leakage",
        ("J2C-OFS-07",),
        "Mobilization occurred, billable, not invoiced.",
        mobilization_occurred=True,
        mobilization_contract_permits_charge=True,
        mobilization_waived=False,
        mobilization_invoiced=False,
    ),
    _case(
        "EDGE-07-A",
        "edge",
        (),
        "Mobilization occurred but contractually waived.",
        mobilization_occurred=True,
        mobilization_contract_permits_charge=True,
        mobilization_waived=True,
        mobilization_invoiced=False,
    ),
    # --- J2C-OFS-08: Contract Rate Mismatch ---
    _case(
        "LEAK-08-A",
        "leakage",
        ("J2C-OFS-08",),
        "Billed rate materially below authorized rate.",
        billed_rate=80.0,
        authorized_rate=100.0,
        rate_override_approved=False,
    ),
    _case(
        "LEAK-08-B",
        "leakage",
        ("J2C-OFS-08",),
        "Billed rate materially above authorized rate.",
        billed_rate=120.0,
        authorized_rate=100.0,
        rate_override_approved=False,
    ),
    _case(
        "EDGE-08-A",
        "edge",
        (),
        "Rate differs but a valid negotiated override is approved.",
        billed_rate=80.0,
        authorized_rate=100.0,
        rate_override_approved=True,
    ),
    _case(
        "EDGE-08-B",
        "edge",
        (),
        "Rate differs but explained by approved bundled pricing.",
        billed_rate=80.0,
        authorized_rate=100.0,
        bundled_pricing=True,
    ),
    _case(
        "EDGE-08-C",
        "edge",
        (),
        "Rate differs only by immaterial rounding.",
        billed_rate=100.4,
        authorized_rate=100.0,
    ),
    # --- J2C-OFS-09: Unauthorized Discount or Credit ---
    _case(
        "LEAK-09-A",
        "leakage",
        ("J2C-OFS-09",),
        "Credit applied exceeds authorized amount.",
        credit_applied=500.0,
        credit_authorized=0.0,
    ),
    _case(
        "EDGE-09-A",
        "edge",
        (),
        "Credit matches authorized standing commercial term.",
        credit_applied=500.0,
        credit_authorized=500.0,
    ),
    _case(
        "EDGE-09-B",
        "edge",
        (),
        "Credit is a reversal of a prior erroneous charge.",
        credit_applied=500.0,
        credit_authorized=0.0,
        credit_is_reversal_of_error=True,
    ),
    # --- J2C-OFS-10: Invoice Delay After Completion ---
    _case(
        "LEAK-10-A",
        "leakage",
        ("J2C-OFS-10",),
        "Invoice issued well beyond expected turnaround.",
        invoice_issued_days_after_completion=25,
        expected_invoicing_turnaround_days=7,
    ),
    _case(
        "EDGE-10-A",
        "edge",
        (),
        "Delay explained by milestone billing.",
        invoice_issued_days_after_completion=25,
        expected_invoicing_turnaround_days=7,
        milestone_billing=True,
    ),
    # --- J2C-OFS-11: Payment Delay - Documentation Blocker ---
    _case(
        "LEAK-11-A",
        "leakage",
        ("J2C-OFS-11",),
        "Outstanding past term, documentation incomplete.",
        payment_days_outstanding=45,
        standard_payment_term_days=30,
        documentation_complete=False,
    ),
    _case(
        "EDGE-11-A",
        "edge",
        (),
        "Outstanding past term, but extended term is approved.",
        payment_days_outstanding=45,
        standard_payment_term_days=30,
        documentation_complete=False,
        extended_payment_term_approved=True,
    ),
    _case(
        "AMBIG-11-A",
        "ambiguous",
        (),
        "Outstanding past term, documentation complete, cause unclear.",
        payment_days_outstanding=45,
        standard_payment_term_days=30,
        documentation_complete=True,
    ),
    # --- J2C-OFS-12: Job Margin Erosion ---
    _case(
        "LEAK-12-A",
        "leakage",
        ("J2C-OFS-12",),
        "Margin materially below expected, variance not normal/explained, change order unbilled.",
        expected_margin_pct=25.0,
        actual_margin_pct=12.0,
        margin_variance_is_normal_business_variance=False,
        unbilled_change_order=True,
    ),
    _case(
        "EDGE-12-A",
        "edge",
        (),
        "Margin below expected but within normal business variance.",
        expected_margin_pct=25.0,
        actual_margin_pct=21.0,
        margin_variance_is_normal_business_variance=True,
    ),
    _case(
        "AMBIG-12-A",
        "ambiguous",
        (),
        "Margin materially below expected, but variance cause cannot be decomposed.",
        expected_margin_pct=25.0,
        actual_margin_pct=10.0,
        margin_variance_is_normal_business_variance=False,
        unbilled_change_order=False,
    ),
    # --- Composite: a job that legitimately trips more than one pattern ---
    _case(
        "LEAK-COMPOSITE-A",
        "leakage",
        ("J2C-OFS-01", "J2C-OFS-07"),
        "Completed, unbilled, and mobilization was also never charged.",
        invoice_exists=False,
        days_since_completion=30,
        billing_grace_period_days=5,
        mobilization_occurred=True,
        mobilization_contract_permits_charge=True,
        mobilization_waived=False,
        mobilization_invoiced=False,
    ),
    # --- Zero-dollar / bundled edge cases explicitly called out in the work order ---
    _case(
        "EDGE-ZERO-001",
        "edge",
        (),
        "Zero-dollar valid job (no chargeable content at all).",
        field_ticket_billable=False,
        equipment_billable=False,
        material_billable=False,
        overtime_hours_recorded=0.0,
        labor_hours_recorded=0.0,
        labor_hours_invoiced=0.0,
    ),
    _case(
        "EDGE-BUNDLE-001",
        "edge",
        (),
        "Bundled pricing covers equipment and materials together.",
        bundled_pricing=True,
        equipment_hours_recorded=10.0,
        equipment_hours_invoiced=0.0,
        equipment_billable=False,
        material_consumed_qty=15.0,
        material_invoiced_qty=0.0,
        material_billable=False,
    ),
    _case(
        "EDGE-REOPEN-001",
        "edge",
        (),
        "Job reopened after completion; still pending re-close.",
        status="in_progress",
        invoice_exists=False,
        days_since_completion=2,
    ),
    _case(
        "EDGE-SPLIT-001",
        "edge",
        (),
        "Invoice split across two documents; still fully billed.",
        invoice_exists=True,
        field_ticket_invoiced=True,
    ),
    _case(
        "EDGE-PARTIAL-PAY-001",
        "edge",
        (),
        "Partial payment received, remainder within standard term.",
        payment_days_outstanding=10,
        standard_payment_term_days=30,
    ),
    # --- J2C-OFS-20: Third-Party Pass-Through / Re-Rental Not Billed ---
    _case(
        "LEAK-20-A",
        "leakage",
        ("J2C-OFS-20",),
        "Pass-through-eligible vendor cost never carried onto the customer invoice.",
        vendor_pass_through_eligible=True,
        vendor_pass_through_billed=False,
    ),
    _case(
        "EDGE-20-A",
        "edge",
        (),
        "Vendor cost not eligible for customer pass-through under the contract.",
        vendor_pass_through_eligible=False,
        vendor_pass_through_billed=False,
    ),
    _case(
        "EDGE-20-B",
        "edge",
        (),
        "Vendor cost already absorbed in a flat day-rate that includes it.",
        vendor_pass_through_eligible=True,
        vendor_pass_through_billed=False,
        vendor_pass_through_absorbed_in_flat_rate=True,
    ),
    # --- J2C-OFS-24: NPT vs. Standby Misclassification ---
    _case(
        "LEAK-24-A",
        "leakage",
        ("J2C-OFS-24",),
        "Customer-caused downtime meeting the standby threshold, still coded as NPT.",
        npt_event_customer_attributable=True,
        npt_event_duration_meets_threshold=True,
        npt_event_billed_as_standby=False,
    ),
    _case(
        "EDGE-24-A",
        "edge",
        (),
        "Downtime root cause is not customer-attributable.",
        npt_event_customer_attributable=False,
        npt_event_duration_meets_threshold=True,
        npt_event_billed_as_standby=False,
    ),
    _case(
        "EDGE-24-B",
        "edge",
        (),
        "Customer-attributable downtime, but an approved standby waiver is in effect.",
        npt_event_customer_attributable=True,
        npt_event_duration_meets_threshold=True,
        standby_waiver_in_effect=True,
        npt_event_billed_as_standby=False,
    ),
    # --- J2C-OFS-30: E-Invoicing Portal Rejection ---
    _case(
        "LEAK-30-A",
        "leakage",
        ("J2C-OFS-30",),
        "Portal-rejected invoice never resubmitted.",
        portal_rejection_code_present=True,
        portal_resubmitted_successfully=False,
    ),
    _case(
        "EDGE-30-A",
        "edge",
        (),
        "Rejection was for a duplicate submission of an already-accepted invoice.",
        portal_rejection_code_present=True,
        portal_resubmitted_successfully=False,
        portal_rejection_is_duplicate=True,
    ),
    _case(
        "EDGE-30-B",
        "edge",
        (),
        "Invoice was withdrawn because the underlying charge was invalid.",
        portal_rejection_code_present=True,
        portal_resubmitted_successfully=False,
        portal_invoice_withdrawn_invalid=True,
    ),
)


def detect_completed_job_not_invoiced(o: dict[str, Any]) -> bool:
    if o["status"] != "completed" or o["invoice_exists"]:
        return False
    if o["non_billable"] or o["milestone_billing"] or o.get("canceled"):
        return False
    return bool(o["days_since_completion"] > o["billing_grace_period_days"])


def detect_field_ticket_not_invoiced(o: dict[str, Any]) -> bool:
    if not o["field_ticket_billable"] or o["field_ticket_invoiced"]:
        return False
    return not o["field_ticket_duplicate"]


def detect_billable_labor_omitted(o: dict[str, Any]) -> bool:
    if not o["labor_billable"]:
        return False
    return bool(
        o["overtime_hours_recorded"] > o["overtime_hours_invoiced"]
        or o["labor_hours_recorded"] > o["labor_hours_invoiced"]
    )


def detect_billable_equipment_omitted(o: dict[str, Any]) -> bool:
    if not o["equipment_deployed"] or not o["equipment_billable"]:
        return False
    return bool(o["equipment_hours_recorded"] > o["equipment_hours_invoiced"])


def detect_billable_material_omitted(o: dict[str, Any]) -> bool:
    if not o["material_billable"]:
        return False
    return bool(o["material_consumed_qty"] > o["material_invoiced_qty"])


def detect_billable_standby_omitted(o: dict[str, Any]) -> bool:
    if o["standby_invoiced"] or o["standby_waived"] or not o["standby_customer_caused"]:
        return False
    return bool(o["standby_minutes"] >= o["standby_minimum_minutes"])


def detect_mob_demob_charge_omitted(o: dict[str, Any]) -> bool:
    if not o["mobilization_occurred"] or not o["mobilization_contract_permits_charge"]:
        return False
    if o["mobilization_waived"] or o["mobilization_invoiced"]:
        return False
    return True


def detect_contract_rate_mismatch(o: dict[str, Any]) -> bool:
    if o["rate_override_approved"] or o["bundled_pricing"]:
        return False
    delta = abs(o["billed_rate"] - o["authorized_rate"])
    return bool(delta / o["authorized_rate"] > 0.02)


def detect_unauthorized_discount_or_credit(o: dict[str, Any]) -> bool:
    if o["credit_is_reversal_of_error"]:
        return False
    return bool(o["credit_applied"] > o["credit_authorized"])


def detect_invoice_delay_after_completion(o: dict[str, Any]) -> bool:
    if o["milestone_billing"]:
        return False
    return bool(o["invoice_issued_days_after_completion"] > o["expected_invoicing_turnaround_days"])


def detect_payment_delay_documentation_blocker(o: dict[str, Any]) -> bool:
    if o["extended_payment_term_approved"] or o["documentation_complete"]:
        return False
    return bool(o["payment_days_outstanding"] > o["standard_payment_term_days"])


def detect_job_margin_erosion(o: dict[str, Any]) -> bool:
    if o["margin_variance_is_normal_business_variance"]:
        return False
    shortfall = o["expected_margin_pct"] - o["actual_margin_pct"]
    return bool(shortfall > 5.0 and o["unbilled_change_order"])


def detect_third_party_pass_through_not_billed(o: dict[str, Any]) -> bool:
    if not o["vendor_pass_through_eligible"]:
        return False
    if o["vendor_pass_through_absorbed_in_flat_rate"]:
        return False
    if o["vendor_pass_through_markup_waived_approved"]:
        return False
    return not o["vendor_pass_through_billed"]


def detect_npt_vs_standby_misclassification(o: dict[str, Any]) -> bool:
    if not o["npt_event_customer_attributable"]:
        return False
    if not o["npt_event_duration_meets_threshold"]:
        return False
    if o["standby_waiver_in_effect"]:
        return False
    return not o["npt_event_billed_as_standby"]


def detect_einvoicing_portal_rejection(o: dict[str, Any]) -> bool:
    if not o["portal_rejection_code_present"]:
        return False
    if o["portal_rejection_is_duplicate"]:
        return False
    if o["portal_invoice_withdrawn_invalid"]:
        return False
    return not o["portal_resubmitted_successfully"]


DETECTORS: dict[str, Any] = {
    "J2C-OFS-01": detect_completed_job_not_invoiced,
    "J2C-OFS-02": detect_field_ticket_not_invoiced,
    "J2C-OFS-03": detect_billable_labor_omitted,
    "J2C-OFS-04": detect_billable_equipment_omitted,
    "J2C-OFS-05": detect_billable_material_omitted,
    "J2C-OFS-06": detect_billable_standby_omitted,
    "J2C-OFS-07": detect_mob_demob_charge_omitted,
    "J2C-OFS-08": detect_contract_rate_mismatch,
    "J2C-OFS-09": detect_unauthorized_discount_or_credit,
    "J2C-OFS-10": detect_invoice_delay_after_completion,
    "J2C-OFS-11": detect_payment_delay_documentation_blocker,
    "J2C-OFS-12": detect_job_margin_erosion,
    "J2C-OFS-20": detect_third_party_pass_through_not_billed,
    "J2C-OFS-24": detect_npt_vs_standby_misclassification,
    "J2C-OFS-30": detect_einvoicing_portal_rejection,
}


def detect(observed: dict[str, Any]) -> frozenset[str]:
    return frozenset(key for key, fn in DETECTORS.items() if fn(observed))
