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
    # P3.15-promoted Tier 1 patterns
    "min_charge_applicable": False,
    "invoice_amount": 500.0,
    "contractual_minimum": 250.0,
    "minimum_waived_approved": False,
    "job_canceled_before_threshold": False,
    "ticket_billable_line_count": 3,
    "invoice_line_count_for_ticket": 3,
    "missing_lines_voided": False,
    "missing_lines_cross_invoiced": False,
    "lih_incident_exists": False,
    "lih_invoice_or_claim_exists": True,
    "lih_contract_assigns_risk_to_customer": False,
    "lih_caused_by_servicer_negligence": False,
    "lih_insurance_already_claimed": False,
    "lih_fault_determined": True,
    "asset_departure_after_ticket_stop": False,
    "extended_dwell_contractually_non_billable": False,
    "asset_redeployed_to_billed_job": False,
    "asset_telemetry_unreliable": False,
    "demob_departure_after_signoff": False,
    "demob_invoice_reflects_standby_gap": True,
    "demob_delay_customer_caused": False,
    "demob_delay_within_grace_period": False,
    "invoice_discount_tier_applied": False,
    "cumulative_spend": 100000.0,
    "tier_qualifying_threshold": 50000.0,
    "tier_preapproved_exception": False,
    "tier_commitment_based": False,
    "simops_hold_exists": False,
    "simops_hold_customer_attributable": False,
    "simops_hold_billed_as_standby": True,
    "simops_caused_by_servicer_violation": False,
    "simops_below_standby_threshold": False,
    "simops_within_noncompensable_window": False,
    "remittance_amount": 1000.0,
    "invoice_total": 1000.0,
    "short_pay_dispute_record_exists": False,
    "short_pay_aged_beyond_threshold": False,
    "short_pay_matches_approved_credit": False,
    "short_pay_rounding_only": False,
}


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    case_type: str  # "clean" | "leakage" | "edge" | "ambiguous" | "contaminated"
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
    # --- P3.14: contamination cases (data-quality noise, business truth unchanged) ---
    _case(
        "CONTAM-01-A",
        "contaminated",
        (),
        "Clean, correctly invoiced job; completion-feed timestamp arrived stale/duplicated.",
        data_quality_defect="stale_duplicated_completion_timestamp",
    ),
    _case(
        "CONTAM-02-A",
        "contaminated",
        ("J2C-OFS-02",),
        "Billable ticket never invoiced; ticket id duplicated in the source feed.",
        field_ticket_billable=True,
        field_ticket_invoiced=False,
        data_quality_defect="duplicate_ticket_id_in_feed",
    ),
    _case(
        "CONTAM-03-A",
        "contaminated",
        (),
        "Clean labor billing; unit-of-measure recorded inconsistently across systems.",
        data_quality_defect="incorrect_unit_of_measure",
    ),
    _case(
        "CONTAM-04-A",
        "contaminated",
        ("J2C-OFS-04",),
        "Equipment hours underbilled; asset-to-job mapping field is wrong in the source system.",
        equipment_hours_recorded=12.0,
        equipment_hours_invoiced=6.0,
        data_quality_defect="wrong_asset_job_mapping",
    ),
    _case(
        "CONTAM-05-A",
        "contaminated",
        (),
        "Clean material billing; consumption quantity was rounded by an upstream system.",
        data_quality_defect="rounded_quantity",
    ),
    _case(
        "CONTAM-06-A",
        "contaminated",
        ("J2C-OFS-06",),
        "Billable standby omitted; standby events arrived out of order in the field feed.",
        standby_minutes=90,
        standby_minimum_minutes=60,
        standby_customer_caused=True,
        standby_invoiced=False,
        data_quality_defect="out_of_order_event",
    ),
    _case(
        "CONTAM-07-A",
        "contaminated",
        (),
        "Clean job, no mobilization; mobilization flag field missing entirely from the feed.",
        data_quality_defect="missing_field:mobilization_flag",
    ),
    _case(
        "CONTAM-08-A",
        "contaminated",
        ("J2C-OFS-08",),
        "Rate mismatch beyond tolerance; rate-sheet field is corrupted/malformed upstream.",
        billed_rate=130.0,
        authorized_rate=100.0,
        data_quality_defect="corrupted_rate_field",
    ),
    _case(
        "CONTAM-09-A",
        "contaminated",
        (),
        "Clean job, no credit; payment record duplicated in the remittance feed.",
        data_quality_defect="duplicated_payment_record",
    ),
    _case(
        "CONTAM-10-A",
        "contaminated",
        ("J2C-OFS-10",),
        "Invoice issued past turnaround; completion timestamp has an uncorrected timezone offset.",
        invoice_issued_days_after_completion=21,
        expected_invoicing_turnaround_days=7,
        data_quality_defect="timezone_offset_uncorrected",
    ),
    _case(
        "CONTAM-11-A",
        "contaminated",
        (),
        "Clean payment cycle; remittance feed shows a batching-glitch partial-payment artifact.",
        data_quality_defect="partial_payment_batching_artifact",
    ),
    _case(
        "CONTAM-12-A",
        "contaminated",
        ("J2C-OFS-12",),
        "Genuine margin erosion from an unbilled change order; cost feed has an outlier row.",
        expected_margin_pct=25.0,
        actual_margin_pct=15.0,
        margin_variance_is_normal_business_variance=False,
        unbilled_change_order=True,
        data_quality_defect="synthetic_outlier_cost_row",
    ),
    _case(
        "CONTAM-20-A",
        "contaminated",
        (),
        "Clean, at-cost-only vendor pass-through; conflicting contract-version records upstream.",
        vendor_pass_through_eligible=False,
        vendor_pass_through_billed=True,
        data_quality_defect="conflicting_contract_versions",
    ),
    _case(
        "CONTAM-24-A",
        "contaminated",
        ("J2C-OFS-24",),
        "Customer-attributable NPT not billed as standby; DDR event is unmatched to its ticket.",
        npt_event_customer_attributable=True,
        npt_event_duration_meets_threshold=True,
        npt_event_billed_as_standby=False,
        data_quality_defect="unmatched_ticket_reference",
    ),
    _case(
        "CONTAM-30-A",
        "contaminated",
        (),
        "Clean portal submission, no rejection; an unrelated same-job invoice has a bad signature.",
        data_quality_defect="invalid_signature_on_unrelated_invoice",
    ),
    # --- P3.15: Tier 2 -> Tier 1 promotions (evidence-supported readiness) ---
    # J2C-OFS-14: Minimum Charge or Minimum Hour Not Applied
    _case(
        "LEAK-14-A",
        "leakage",
        ("J2C-OFS-14",),
        "Job subject to contractual minimum, invoiced below it.",
        min_charge_applicable=True,
        invoice_amount=150.0,
        contractual_minimum=250.0,
    ),
    _case(
        "EDGE-14-A",
        "edge",
        (),
        "Below minimum, but customer has an approved waiver.",
        min_charge_applicable=True,
        invoice_amount=150.0,
        contractual_minimum=250.0,
        minimum_waived_approved=True,
    ),
    _case(
        "EDGE-14-B",
        "edge",
        (),
        "Below minimum, but job was canceled before the threshold was reached.",
        min_charge_applicable=True,
        invoice_amount=150.0,
        contractual_minimum=250.0,
        job_canceled_before_threshold=True,
    ),
    _case(
        "AMBIG-14-A",
        "ambiguous",
        (),
        "Invoiced amount exactly at the minimum boundary; not clearly under.",
        min_charge_applicable=True,
        invoice_amount=250.0,
        contractual_minimum=250.0,
    ),
    _case(
        "CONTAM-14-A",
        "contaminated",
        ("J2C-OFS-14",),
        "Genuine minimum-charge shortfall; rate-book feed has a duplicated row.",
        min_charge_applicable=True,
        invoice_amount=150.0,
        contractual_minimum=250.0,
        data_quality_defect="duplicated_rate_book_row",
    ),
    # J2C-OFS-15: Partial Ticket Billing
    _case(
        "LEAK-15-A",
        "leakage",
        ("J2C-OFS-15",),
        "Billable ticket invoiced with fewer line items than it has.",
        ticket_billable_line_count=5,
        invoice_line_count_for_ticket=3,
    ),
    _case(
        "EDGE-15-A",
        "edge",
        (),
        "Missing lines were explicitly voided on the ticket itself.",
        ticket_billable_line_count=5,
        invoice_line_count_for_ticket=3,
        missing_lines_voided=True,
    ),
    _case(
        "EDGE-15-B",
        "edge",
        (),
        "Missing lines are covered by a separate, cross-referenced invoice.",
        ticket_billable_line_count=5,
        invoice_line_count_for_ticket=3,
        missing_lines_cross_invoiced=True,
    ),
    _case(
        "AMBIG-15-A",
        "ambiguous",
        (),
        "Line counts match exactly; not a partial-billing case.",
        ticket_billable_line_count=5,
        invoice_line_count_for_ticket=5,
    ),
    _case(
        "CONTAM-15-A",
        "contaminated",
        ("J2C-OFS-15",),
        "Genuine partial billing; ticket-line feed has a stale cached count.",
        ticket_billable_line_count=5,
        invoice_line_count_for_ticket=3,
        data_quality_defect="stale_cached_line_count",
    ),
    # J2C-OFS-16: Loss-in-Hole / Tool Damage
    _case(
        "LEAK-16-A",
        "leakage",
        ("J2C-OFS-16",),
        "Incident recorded, contract assigns risk to customer, fault determined.",
        lih_incident_exists=True,
        lih_invoice_or_claim_exists=False,
        lih_contract_assigns_risk_to_customer=True,
        lih_fault_determined=True,
    ),
    _case(
        "EDGE-16-A",
        "edge",
        (),
        "Incident recorded, but contract places the risk with the operator.",
        lih_incident_exists=True,
        lih_invoice_or_claim_exists=False,
        lih_contract_assigns_risk_to_customer=False,
        lih_fault_determined=True,
    ),
    _case(
        "EDGE-16-B",
        "edge",
        (),
        "Incident caused by servicer negligence, not an operational hazard.",
        lih_incident_exists=True,
        lih_invoice_or_claim_exists=False,
        lih_contract_assigns_risk_to_customer=True,
        lih_caused_by_servicer_negligence=True,
        lih_fault_determined=True,
    ),
    _case(
        "EDGE-16-C",
        "edge",
        (),
        "Asset is fully covered by an insurance claim already made.",
        lih_incident_exists=True,
        lih_invoice_or_claim_exists=False,
        lih_contract_assigns_risk_to_customer=True,
        lih_insurance_already_claimed=True,
        lih_fault_determined=True,
    ),
    _case(
        "AMBIG-16-A",
        "ambiguous",
        (),
        "Contract assigns customer risk, but fault/cause is not yet determined.",
        lih_incident_exists=True,
        lih_invoice_or_claim_exists=False,
        lih_contract_assigns_risk_to_customer=True,
        lih_fault_determined=False,
    ),
    _case(
        "CONTAM-16-A",
        "contaminated",
        ("J2C-OFS-16",),
        "Genuine customer-liable LIH; asset master record has a duplicated serial number.",
        lih_incident_exists=True,
        lih_invoice_or_claim_exists=False,
        lih_contract_assigns_risk_to_customer=True,
        lih_fault_determined=True,
        data_quality_defect="duplicated_asset_serial",
    ),
    # J2C-OFS-18: Extended Idle Asset Rental
    _case(
        "LEAK-18-A",
        "leakage",
        ("J2C-OFS-18",),
        "Asset stayed on site past ticketed stop time and was not billed for it.",
        asset_departure_after_ticket_stop=True,
    ),
    _case(
        "EDGE-18-A",
        "edge",
        (),
        "Extended dwell is contractually non-billable customer-caused delay.",
        asset_departure_after_ticket_stop=True,
        extended_dwell_contractually_non_billable=True,
    ),
    _case(
        "EDGE-18-B",
        "edge",
        (),
        "Asset was redeployed to a different, already-billed job at the same location.",
        asset_departure_after_ticket_stop=True,
        asset_redeployed_to_billed_job=True,
    ),
    _case(
        "AMBIG-18-A",
        "ambiguous",
        (),
        "Telematics data for the dwell period is missing/unreliable -- must not assert certainty.",
        asset_departure_after_ticket_stop=True,
        asset_telemetry_unreliable=True,
    ),
    _case(
        "CONTAM-18-A",
        "contaminated",
        ("J2C-OFS-18",),
        "Genuine extended idle rental; GPS feed has a duplicated ping at the boundary.",
        asset_departure_after_ticket_stop=True,
        data_quality_defect="duplicated_gps_ping",
    ),
    # J2C-OFS-22: Unbilled Demobilization Delay
    _case(
        "LEAK-22-A",
        "leakage",
        ("J2C-OFS-22",),
        "Customer-caused demob delay beyond grace period, not billed.",
        demob_departure_after_signoff=True,
        demob_invoice_reflects_standby_gap=False,
        demob_delay_customer_caused=True,
        demob_delay_within_grace_period=False,
    ),
    _case(
        "EDGE-22-A",
        "edge",
        (),
        "Delay is attributable to the servicer, not the customer.",
        demob_departure_after_signoff=True,
        demob_invoice_reflects_standby_gap=False,
        demob_delay_customer_caused=False,
    ),
    _case(
        "EDGE-22-B",
        "edge",
        (),
        "Delay is within the contractual grace period.",
        demob_departure_after_signoff=True,
        demob_invoice_reflects_standby_gap=False,
        demob_delay_customer_caused=True,
        demob_delay_within_grace_period=True,
    ),
    _case(
        "AMBIG-22-A",
        "ambiguous",
        (),
        "Departure was delayed, but the cause of the delay is undocumented.",
        demob_departure_after_signoff=True,
        demob_invoice_reflects_standby_gap=False,
        demob_delay_customer_caused=False,
        demob_delay_within_grace_period=False,
    ),
    _case(
        "CONTAM-22-A",
        "contaminated",
        ("J2C-OFS-22",),
        "Genuine unbilled demob delay; telematics feed has an out-of-order departure event.",
        demob_departure_after_signoff=True,
        demob_invoice_reflects_standby_gap=False,
        demob_delay_customer_caused=True,
        demob_delay_within_grace_period=False,
        data_quality_defect="out_of_order_departure_event",
    ),
    # J2C-OFS-25: Premature Tiered-Volume Discounting
    _case(
        "LEAK-25-A",
        "leakage",
        ("J2C-OFS-25",),
        "Discount tier applied before cumulative spend qualifies for it.",
        invoice_discount_tier_applied=True,
        cumulative_spend=30000.0,
        tier_qualifying_threshold=50000.0,
    ),
    _case(
        "EDGE-25-A",
        "edge",
        (),
        "Tier was pre-approved for early application by an authorized exception.",
        invoice_discount_tier_applied=True,
        cumulative_spend=30000.0,
        tier_qualifying_threshold=50000.0,
        tier_preapproved_exception=True,
    ),
    _case(
        "EDGE-25-B",
        "edge",
        (),
        "Contract defines the tier on a forward commitment basis, not trailing spend.",
        invoice_discount_tier_applied=True,
        cumulative_spend=30000.0,
        tier_qualifying_threshold=50000.0,
        tier_commitment_based=True,
    ),
    _case(
        "AMBIG-25-A",
        "ambiguous",
        (),
        "Cumulative spend exactly equals the tier threshold; not clearly premature.",
        invoice_discount_tier_applied=True,
        cumulative_spend=50000.0,
        tier_qualifying_threshold=50000.0,
    ),
    _case(
        "CONTAM-25-A",
        "contaminated",
        ("J2C-OFS-25",),
        "Genuine premature discount; CRM cumulative-spend rollup has a rounded total.",
        invoice_discount_tier_applied=True,
        cumulative_spend=30000.0,
        tier_qualifying_threshold=50000.0,
        data_quality_defect="rounded_cumulative_spend_rollup",
    ),
    # J2C-OFS-28: SIMOPS / Site-Access Standdown
    _case(
        "LEAK-28-A",
        "leakage",
        ("J2C-OFS-28",),
        "Customer-attributable access hold, above threshold, not billed as standby.",
        simops_hold_exists=True,
        simops_hold_customer_attributable=True,
        simops_hold_billed_as_standby=False,
    ),
    _case(
        "EDGE-28-A",
        "edge",
        (),
        "Hold was caused by the servicer's own safety violation.",
        simops_hold_exists=True,
        simops_hold_customer_attributable=True,
        simops_hold_billed_as_standby=False,
        simops_caused_by_servicer_violation=True,
    ),
    _case(
        "EDGE-28-B",
        "edge",
        (),
        "Hold duration is below the contractual standby-trigger threshold.",
        simops_hold_exists=True,
        simops_hold_customer_attributable=True,
        simops_hold_billed_as_standby=False,
        simops_below_standby_threshold=True,
    ),
    _case(
        "EDGE-28-C",
        "edge",
        (),
        "Hold is within a contractually non-billable standard access-control window.",
        simops_hold_exists=True,
        simops_hold_customer_attributable=True,
        simops_hold_billed_as_standby=False,
        simops_within_noncompensable_window=True,
    ),
    _case(
        "AMBIG-28-A",
        "ambiguous",
        (),
        "Access hold occurred, but responsibility is not clearly documented.",
        simops_hold_exists=True,
        simops_hold_customer_attributable=False,
        simops_hold_billed_as_standby=False,
    ),
    _case(
        "CONTAM-28-A",
        "contaminated",
        ("J2C-OFS-28",),
        "Genuine customer-caused standdown; site-safety log has a duplicated hold entry.",
        simops_hold_exists=True,
        simops_hold_customer_attributable=True,
        simops_hold_billed_as_standby=False,
        data_quality_defect="duplicated_hold_log_entry",
    ),
    # J2C-OFS-32: Line-Item Short Pay
    _case(
        "LEAK-32-A",
        "leakage",
        ("J2C-OFS-32",),
        "Remittance short of invoice total, no dispute record.",
        remittance_amount=800.0,
        invoice_total=1000.0,
    ),
    _case(
        "EDGE-32-A",
        "edge",
        (),
        "Deduction matches an approved credit memo.",
        remittance_amount=800.0,
        invoice_total=1000.0,
        short_pay_matches_approved_credit=True,
    ),
    _case(
        "EDGE-32-B",
        "edge",
        (),
        "Deduction is a bank rounding difference below materiality.",
        remittance_amount=999.50,
        invoice_total=1000.0,
        short_pay_rounding_only=True,
    ),
    _case(
        "EDGE-32-C",
        "edge",
        (),
        "Dispute record exists and has not yet aged past the review threshold.",
        remittance_amount=800.0,
        invoice_total=1000.0,
        short_pay_dispute_record_exists=True,
        short_pay_aged_beyond_threshold=False,
    ),
    _case(
        "AMBIG-32-A",
        "ambiguous",
        (),
        "Remittance advice states no reason for the deduction; resolution pending.",
        remittance_amount=800.0,
        invoice_total=1000.0,
        short_pay_dispute_record_exists=True,
        short_pay_aged_beyond_threshold=False,
    ),
    _case(
        "CONTAM-32-A",
        "contaminated",
        ("J2C-OFS-32",),
        "Genuine unresolved short pay, aged; remittance feed has a duplicated line entry.",
        remittance_amount=800.0,
        invoice_total=1000.0,
        short_pay_dispute_record_exists=True,
        short_pay_aged_beyond_threshold=True,
        data_quality_defect="duplicated_remittance_line",
    ),
    # --- P3.15: expanded Failure Lab -- matching-key adversarial cases against
    # already-certified Tier 1 patterns (identity/matching correlation-key stress) ---
    _case(
        "ADV-KEY-01-A",
        "edge",
        (),
        "Duplicate PO number reused across two unrelated jobs; job is fully billed.",
        invoice_exists=True,
        data_quality_defect="duplicate_po_reused_across_jobs",
    ),
    _case(
        "ADV-KEY-04-A",
        "edge",
        (),
        "Asset alias/rename mid-job; equipment hours fully and correctly billed.",
        equipment_hours_recorded=8.0,
        equipment_hours_invoiced=8.0,
        data_quality_defect="asset_alias_mid_job",
    ),
    _case(
        "ADV-KEY-08-A",
        "edge",
        (),
        "Customer alias/merged-account record; billed rate matches the authorized rate.",
        billed_rate=100.0,
        authorized_rate=100.0,
        data_quality_defect="customer_alias_merged_account",
    ),
    _case(
        "ADV-KEY-20-A",
        "edge",
        (),
        "Vendor invoice references a superseded PO version; pass-through correctly at cost.",
        vendor_pass_through_eligible=False,
        vendor_pass_through_billed=True,
        data_quality_defect="superseded_po_version_reference",
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


def detect_minimum_charge_not_applied(o: dict[str, Any]) -> bool:
    if not o["min_charge_applicable"]:
        return False
    if o["minimum_waived_approved"] or o["job_canceled_before_threshold"]:
        return False
    return bool(o["invoice_amount"] < o["contractual_minimum"])


def detect_partial_ticket_billing(o: dict[str, Any]) -> bool:
    if o["invoice_line_count_for_ticket"] >= o["ticket_billable_line_count"]:
        return False
    if o["missing_lines_voided"] or o["missing_lines_cross_invoiced"]:
        return False
    return True


def detect_loss_in_hole_tool_damage(o: dict[str, Any]) -> bool:
    if not o["lih_incident_exists"] or o["lih_invoice_or_claim_exists"]:
        return False
    if not o["lih_contract_assigns_risk_to_customer"]:
        return False
    if o["lih_caused_by_servicer_negligence"] or o["lih_insurance_already_claimed"]:
        return False
    # Fault undetermined -> abstain. Asset value alone never establishes recoverability;
    # this detector never reads an asset-value field at all.
    return bool(o["lih_fault_determined"])


def detect_extended_idle_asset_rental(o: dict[str, Any]) -> bool:
    if not o["asset_departure_after_ticket_stop"]:
        return False
    if o["extended_dwell_contractually_non_billable"] or o["asset_redeployed_to_billed_job"]:
        return False
    if o["asset_telemetry_unreliable"]:
        return False
    return True


def detect_unbilled_demob_delay(o: dict[str, Any]) -> bool:
    if not o["demob_departure_after_signoff"] or o["demob_invoice_reflects_standby_gap"]:
        return False
    if not o["demob_delay_customer_caused"] or o["demob_delay_within_grace_period"]:
        return False
    return True


def detect_premature_tiered_discounting(o: dict[str, Any]) -> bool:
    if not o["invoice_discount_tier_applied"]:
        return False
    if o["tier_preapproved_exception"] or o["tier_commitment_based"]:
        return False
    return bool(o["cumulative_spend"] < o["tier_qualifying_threshold"])


def detect_simops_access_standdown(o: dict[str, Any]) -> bool:
    if not o["simops_hold_exists"] or o["simops_hold_billed_as_standby"]:
        return False
    if not o["simops_hold_customer_attributable"]:
        return False
    if (
        o["simops_caused_by_servicer_violation"]
        or o["simops_below_standby_threshold"]
        or o["simops_within_noncompensable_window"]
    ):
        return False
    return True


def detect_line_item_short_pay(o: dict[str, Any]) -> bool:
    if o["remittance_amount"] >= o["invoice_total"]:
        return False
    if o["short_pay_matches_approved_credit"] or o["short_pay_rounding_only"]:
        return False
    if o["short_pay_dispute_record_exists"] and not o["short_pay_aged_beyond_threshold"]:
        return False
    return True


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
    "J2C-OFS-14": detect_minimum_charge_not_applied,
    "J2C-OFS-15": detect_partial_ticket_billing,
    "J2C-OFS-16": detect_loss_in_hole_tool_damage,
    "J2C-OFS-18": detect_extended_idle_asset_rental,
    "J2C-OFS-22": detect_unbilled_demob_delay,
    "J2C-OFS-25": detect_premature_tiered_discounting,
    "J2C-OFS-28": detect_simops_access_standdown,
    "J2C-OFS-32": detect_line_item_short_pay,
}


def detect(observed: dict[str, Any]) -> frozenset[str]:
    return frozenset(key for key, fn in DETECTORS.items() if fn(observed))
