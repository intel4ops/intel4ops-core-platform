"""P3.12 reference content: Oilfield Services -- Job-to-Cash Value Leakage.

This module is pure declarative data. It carries no detection logic, no
executable rules, and is never invoked by any API path or service that
acts on customer data. It is loaded by the Knowledge Pack seed path
(app/services/knowledge_pack_service.py) into KnowledgePackPattern rows,
where every field is reference content authored for human review -- not
an executable engine, not a proven finding, not a guaranteed recovery.

Doctrine (do not blur in code, tests, or UI copy built on this content):
  Reference Knowledge   != Client-Validated Learning
  Simulation            != Production Evidence
  Detection Pattern     != Actual Finding
  Causal Template        != Proven Root Cause
  Recovery Playbook      != Automatic Action
  Exposure               != Expected Recovery != Realized Value != Verified Value

Grounding: pattern content is written against the platform's existing
Job-to-Cash vocabulary rather than inventing a parallel taxonomy --
process stages reuse the value-chain named in the work order, value-basis
categories reuse ValueCategory (app/engines/recovery_ledger_engine.py),
and related_defect_codes cite OILFIELD_DEFECTS / the J2C-OILFIELD-001
golden scenario already registered in app/validation/simulation.py.
"""

from __future__ import annotations

from typing import TypedDict

PACK_SLUG = "oilfield-services-job-to-cash-value-leakage"
PACK_NAME = "Oilfield Services — Job-to-Cash Value Leakage"
PACK_INDUSTRY = "oilfield_services"
PACK_DOMAIN = "job_to_cash"
PACK_DESCRIPTION = (
    "Reference structure for operational and commercial value leakage across the "
    "oilfield services job-to-cash cycle: job/service-order creation, field "
    "execution, field-ticket and evidence capture, billable-resource validation, "
    "contract/rate validation, invoicing, payment, recovery, and verified value. "
    "This is bounded reference and simulation-derived knowledge for human review, "
    "not a production-validated or client-proven claim, and it never executes "
    "financial actions on its own."
)
PACK_SCOPE = (
    "Operational and commercial leakage from job/service-order creation through "
    "field execution, field-ticket/evidence capture, billable resource validation, "
    "contract/rate validation, invoicing, payment, recovery, and verified value. "
    "Excludes ERP/ticketing system replacement, automated financial execution, and "
    "any claim of production validation beyond what approved Learning evidences."
)
PACK_CHANGE_SUMMARY = "Initial v1.0 reference pattern library for oilfield services job-to-cash."


class PatternContent(TypedDict):
    required_evidence: list[str]
    detection_preconditions: list[str]
    exclusions: list[str]
    ambiguity_conditions: list[str]
    false_positive_risks: list[str]
    causal_hypotheses: list[str]
    investigation_questions: list[str]
    recovery_playbook: list[str]
    closure_evidence: list[str]
    value_basis: dict[str, str]
    limitations: list[str]
    related_defect_codes: list[str]


class PatternDefinition(TypedDict):
    pattern_key: str
    name: str
    process_stage: str
    description: str
    provenance_type: str
    content: PatternContent


PATTERNS: tuple[PatternDefinition, ...] = (
    {
        "pattern_key": "J2C-OFS-01",
        "name": "Completed Job Not Invoiced",
        "process_stage": "invoicing",
        "description": (
            "A completed operational job exists but no corresponding invoice exists "
            "within an appropriate bounded period after completion."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "job/service-order completion timestamp",
                "field ticket or service ticket confirming work performed",
                "customer approval or signature where contractually required",
                "absence of a matching invoice record for the job",
            ],
            "detection_preconditions": [
                "job/service-order status is completed",
                "no invoice references the job/service-order id",
                "elapsed time since completion exceeds the configured billing grace period",
            ],
            "exclusions": [
                "job is within the configured billing grace period",
                "job was canceled or voided after completion",
                "job is explicitly marked non-billable (internal, warranty, goodwill)",
                "job is awaiting an approved milestone-billing trigger not yet reached",
            ],
            "ambiguity_conditions": [
                "job completion status is itself unconfirmed or pending customer sign-off",
                "billing grace period configuration is missing or undocumented for this contract",
            ],
            "false_positive_risks": [
                "milestone/progress billing arrangements where invoicing intentionally lags "
                "completion",
                "batch invoicing cycles that legitimately group multiple jobs on a fixed "
                "calendar date",
            ],
            "causal_hypotheses": [
                "missing or delayed field documentation blocked invoice creation",
                "manual handoff between field operations and billing was omitted",
                "dispatch and billing systems are disconnected, so completion never reached "
                "billing",
                "customer approval/signature was never captured, blocking invoice release",
            ],
            "investigation_questions": [
                "Does a field ticket exist and is it billing-ready?",
                "Is there a billing-system record referencing this job at all?",
                "Was the job assigned to a billing queue or otherwise routed for invoicing?",
                "Is the customer contractually eligible for immediate invoicing at completion?",
            ],
            "recovery_playbook": [
                "confirm operational completion",
                "confirm contractual billability",
                "reconcile ticket/service evidence",
                "reconcile labor/equipment/material evidence",
                "identify missing PO/document/signature blocker",
                "validate rate",
                "approve billing correction",
                "create/correct invoice through the existing operating process",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "invoice created and issued referencing the job/service-order",
                "finance sign-off on the corrective billing action",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Exposure is the unbilled job value; it is not Expected Recovery until a "
                    "recovery case is opened against an approved baseline, not Realized Value "
                    "until measured, and not Verified Value until finance-verified and "
                    "ledger-posted."
                ),
            },
            "limitations": [
                "does not distinguish legitimate milestone-billing delay from true leakage without "
                "contract-level billing-schedule configuration",
                "reference/simulation content only; no production Learning currently supports this "
                "pattern for any tenant",
            ],
            "related_defect_codes": ["completed_without_invoice"],
        },
    },
    {
        "pattern_key": "J2C-OFS-02",
        "name": "Field Ticket Not Invoiced",
        "process_stage": "evidence_capture",
        "description": (
            "A billable field/service ticket is present but is not represented correctly, "
            "or at all, on any invoice."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "field/service ticket marked billable",
                "invoice line items for the associated job",
                "ticket-to-invoice cross-reference (or its absence)",
            ],
            "detection_preconditions": [
                "field ticket exists and is flagged billable",
                "no invoice line item references the ticket, or the referenced line item's "
                "quantity/amount does not reconcile to the ticket",
            ],
            "exclusions": [
                "ticket is explicitly marked non-billable or internal",
                "ticket is a duplicate of an already-invoiced ticket (see duplicate-ticket "
                "handling, "
                "not a leakage case)",
                "ticket is still within an active field-to-billing transfer window",
            ],
            "ambiguity_conditions": [
                "ticket billability flag is missing or defaults ambiguously",
                "multiple tickets exist for the same job with unclear which is authoritative",
            ],
            "false_positive_risks": [
                "consolidated invoicing that intentionally rolls several tickets into one line "
                "item",
                "ticket correction/reissue workflows that temporarily orphan an earlier ticket "
                "version",
            ],
            "causal_hypotheses": [
                "ticket-to-billing transfer step was skipped in a manual handoff",
                "ticket data failed validation on ingestion into the billing system silently",
                "duplicate field ticket suppressed the ticket believed to already be invoiced",
            ],
            "investigation_questions": [
                "Is the ticket billable per contract terms?",
                "Does the billing system have any record of this ticket id?",
                "Is this ticket superseded by a corrected or duplicate version?",
            ],
            "recovery_playbook": [
                "confirm ticket billability against contract terms",
                "reconcile ticket to invoice line items",
                "identify the specific transfer-step failure",
                "approve billing correction",
                "create/correct invoice line item",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "invoice line item created or corrected referencing the ticket id",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the unbilled ticket value; recovery stages are unchanged.",
            },
            "limitations": [
                "cannot distinguish a legitimately consolidated invoice from a missed ticket "
                "without "
                "an explicit ticket-to-invoice mapping convention",
            ],
            "related_defect_codes": ["duplicate_field_ticket"],
        },
    },
    {
        "pattern_key": "J2C-OFS-03",
        "name": "Billable Labor Omitted",
        "process_stage": "resource_validation",
        "description": (
            "Billable labor recorded against the job, including overtime and premium time, "
            "is missing or underrepresented on the invoice."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "labor time entries (regular and overtime) tied to the job",
                "invoice line items for labor",
                "labor classification/rate schedule",
            ],
            "detection_preconditions": [
                "labor hours recorded operationally exceed labor hours reflected on the invoice",
                "overtime/premium hours are recorded but billed at a rate that does not reflect a "
                "premium differential where the contract requires one",
            ],
            "exclusions": [
                "labor is explicitly classified as non-billable (training, standby covered "
                "elsewhere, "
                "internal support)",
                "contract caps billable labor hours per job and the excess is a contractual "
                "write-off",
                "time entry was voided/corrected as an operational data-entry error, not leakage",
            ],
            "ambiguity_conditions": [
                "labor classification (billable vs. non-billable) is not recorded for the entry",
                "late time entries make it unclear whether the invoice period already closed",
            ],
            "false_positive_risks": [
                "bundled day-rate labor pricing where hours do not map 1:1 to invoice lines",
                "union/contract minimums that legitimately differ from recorded hours",
            ],
            "causal_hypotheses": [
                "labor classification error caused overtime hours to be dropped or misfiled",
                "late time entry missed the invoice cutoff for the billing period",
                "material/labor consumption was not transferred to billing from the field system",
            ],
            "investigation_questions": [
                "Were all recorded hours classified billable per the contract?",
                "Did any time entries post after the invoice was issued?",
                "Does the rate applied to overtime hours match the contractual premium?",
            ],
            "recovery_playbook": [
                "reconcile recorded labor hours to invoiced labor hours",
                "validate billability classification per contract",
                "validate rate applied including overtime premium",
                "approve billing correction",
                "create supplemental invoice or credit-and-rebill as appropriate",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "supplemental invoice or corrected invoice referencing the omitted labor hours",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of omitted labor hours at the applicable "
                "contract rate.",
            },
            "limitations": [
                "does not itself determine day-rate vs. hourly billing structure; requires "
                "contract "
                "context to avoid false positives on bundled pricing",
            ],
            "related_defect_codes": ["missing_overtime", "late_time_entry"],
        },
    },
    {
        "pattern_key": "J2C-OFS-04",
        "name": "Billable Equipment Omitted",
        "process_stage": "resource_validation",
        "description": (
            "Billable equipment usage is captured operationally but missing or "
            "underrepresented commercially on the invoice."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "equipment deployment/usage records tied to the job",
                "invoice line items for equipment",
                "equipment rate schedule",
            ],
            "detection_preconditions": [
                "equipment deployment record exists for the job with a billable equipment class",
                "no corresponding invoice line item exists, or the billed duration understates the "
                "recorded deployment duration",
            ],
            "exclusions": [
                "equipment is explicitly internal/non-billable (company-owned support equipment "
                "provided at no charge under the contract)",
                "equipment usage is bundled into a flat job rate that already includes it",
            ],
            "ambiguity_conditions": [
                "equipment billability classification is not recorded",
                "deployment record lacks a clear start/end time to compute duration",
            ],
            "false_positive_risks": [
                "standard-inclusion equipment bundled into the base job rate by contract",
                "shared equipment across multiple concurrent jobs with unclear allocation",
            ],
            "causal_hypotheses": [
                "equipment usage record was posted late to the billing system",
                "equipment record was not transferred from the field system to billing at all",
                "equipment classification error treated billable equipment as internal",
            ],
            "investigation_questions": [
                "Is this equipment class billable under the governing contract?",
                "Does the invoiced duration match the recorded deployment duration?",
                "Was the equipment record posted before or after the invoice was issued?",
            ],
            "recovery_playbook": [
                "confirm equipment billability against contract terms",
                "reconcile deployment duration to invoiced duration",
                "validate applicable equipment rate",
                "approve billing correction",
                "create supplemental invoice or corrected invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "supplemental or corrected invoice referencing the omitted equipment usage",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of omitted or underbilled equipment usage.",
            },
            "limitations": [
                "cannot reliably attribute shared equipment across concurrent jobs without an "
                "explicit allocation rule",
            ],
            "related_defect_codes": ["missing_equipment_charge"],
        },
    },
    {
        "pattern_key": "J2C-OFS-05",
        "name": "Billable Material Omitted",
        "process_stage": "resource_validation",
        "description": (
            "Billable materials consumed on the job are not fully reflected on the invoice."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "material consumption records tied to the job",
                "invoice line items for materials",
                "material price list or contract material markup terms",
            ],
            "detection_preconditions": [
                "material consumption recorded operationally exceeds material quantity billed",
            ],
            "exclusions": [
                "material is explicitly a customer-supplied item (not billable by the servicer)",
                "material consumption is within a contractual allowance already included in the "
                "base job rate",
                "material was consumed on a warranty or goodwill job",
            ],
            "ambiguity_conditions": [
                "material consumption record lacks a clear billable/non-billable flag",
                "unit-of-measure mismatch between field consumption record and invoice line item "
                "makes reconciliation uncertain",
            ],
            "false_positive_risks": [
                "consumables bundled into a flat service fee by contract",
                "material substitutions logged under a different SKU than the one invoiced",
            ],
            "causal_hypotheses": [
                "material consumption was not transferred to billing from the field/inventory "
                "system",
                "unit-of-measure mismatch caused the billing system to silently drop the line item",
                "material was miscoded as a non-billable internal-use item",
            ],
            "investigation_questions": [
                "Is this material billable per contract terms and allowances?",
                "Does the invoiced quantity match the recorded consumption quantity and unit of "
                "measure?",
                "Was the material transferred to the billing system at all?",
            ],
            "recovery_playbook": [
                "confirm material billability against contract allowances",
                "reconcile consumed quantity to invoiced quantity",
                "validate applicable material pricing/markup",
                "approve billing correction",
                "create supplemental invoice or corrected invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "supplemental or corrected invoice referencing the omitted material consumption",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of unbilled or underbilled material consumption.",
            },
            "limitations": [
                "unit-of-measure reconciliation between field and billing systems is a known "
                "source of false positives; this pattern does not itself normalize units",
                "no OILFIELD_DEFECTS code in the existing platform golden scenario maps directly "
                "to material omission; this pattern extends that vocabulary rather than reusing it",
            ],
            "related_defect_codes": [],
        },
    },
    {
        "pattern_key": "J2C-OFS-06",
        "name": "Billable Standby Omitted",
        "process_stage": "resource_validation",
        "description": (
            "Contractually billable standby time exists operationally but is not charged."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "standby time record tied to the job",
                "contract clause establishing standby billability and any minimum duration",
                "invoice line items for standby",
            ],
            "detection_preconditions": [
                "recorded standby duration meets or exceeds the contractual minimum billable "
                "threshold",
                "no corresponding standby line item appears on the invoice",
            ],
            "exclusions": [
                "recorded standby duration is below the contractual minimum billable threshold",
                "standby was caused by the servicer's own fault and is contractually non-billable",
                "customer pre-approved a standby waiver for this occurrence",
            ],
            "ambiguity_conditions": [
                "cause of standby (customer-caused vs. servicer-caused) is not recorded",
                "contract does not clearly state a standby minimum-duration threshold",
            ],
            "false_positive_risks": [
                "standby within a grace window explicitly excluded by contract",
                "standby absorbed into a day-rate that already prices in reasonable wait time",
            ],
            "causal_hypotheses": [
                "standby time was not classified as billable at the point of capture",
                "contract standby terms were not reflected in the billing configuration for this "
                "job",
                "manual handoff omission dropped the standby record before invoicing",
            ],
            "investigation_questions": [
                "What caused the standby, and does the contract make that cause billable?",
                "Does recorded standby duration clear the contractual minimum?",
                "Is there a customer-approved waiver on file for this standby period?",
            ],
            "recovery_playbook": [
                "confirm standby cause and contractual billability",
                "validate standby duration against contractual minimum",
                "approve billing correction",
                "create supplemental invoice for standby charge",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "supplemental invoice referencing the standby occurrence and duration",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of billable standby time at the contractual "
                "standby rate.",
            },
            "limitations": [
                "requires contract-level standby terms (minimum duration, applicable rate) that "
                "this "
                "pattern documents as a required precondition but does not itself supply",
            ],
            "related_defect_codes": [],
        },
    },
    {
        "pattern_key": "J2C-OFS-07",
        "name": "Mobilization / Demobilization Charge Omitted",
        "process_stage": "contract_rate_validation",
        "description": (
            "Contractually permitted mobilization and/or demobilization charges are missing "
            "from the invoice."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "mobilization and demobilization event records for the job",
                "contract clause establishing mob/demob billability and rate",
                "invoice line items for mob/demob",
            ],
            "detection_preconditions": [
                "mobilization and/or demobilization event is recorded for the job",
                "contract permits a mob/demob charge for this job type/distance/duration",
                "no corresponding invoice line item exists",
            ],
            "exclusions": [
                "mob/demob is contractually waived for this customer or job type",
                "mob/demob is bundled into the base job rate by contract",
                "job is part of a multi-stop route where mob/demob is billed once per route, not "
                "per stop",
            ],
            "ambiguity_conditions": [
                "route/multi-stop structure is unclear, making per-job vs. per-route mob/demob "
                "attribution ambiguous",
            ],
            "false_positive_risks": [
                "customer negotiated waived mobilization as part of a broader commercial agreement",
                "short-haul jobs explicitly below the contractual mobilization-charge distance "
                "threshold",
            ],
            "causal_hypotheses": [
                "mob/demob charge was never configured in the billing system for this contract",
                "manual handoff omission dropped the mob/demob line item before invoicing",
                "route attribution error double-suppressed a legitimately single mob/demob charge",
            ],
            "investigation_questions": [
                "Does the contract permit a mob/demob charge for this job type and distance?",
                "Is this job part of a multi-stop route with a different mob/demob billing unit?",
                "Was a waiver approved for this customer or job?",
            ],
            "recovery_playbook": [
                "confirm contractual mob/demob billability",
                "confirm route attribution (per-job vs. per-route)",
                "approve billing correction",
                "create supplemental invoice for mob/demob charge",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "supplemental invoice referencing the mobilization/demobilization event",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of the omitted mob/demob charge at the contract "
                "rate.",
            },
            "limitations": [
                "route-level attribution logic (per-stop vs. per-route) is not itself part of this "
                "pattern and must be supplied by the calling context",
            ],
            "related_defect_codes": ["missing_mobilization"],
        },
    },
    {
        "pattern_key": "J2C-OFS-08",
        "name": "Contract Rate Mismatch",
        "process_stage": "contract_rate_validation",
        "description": (
            "The billed rate differs materially from the authoritative contractual or "
            "rate-sheet rate."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "invoice line-item rate",
                "authoritative contract or rate-sheet rate for the same service/date/customer",
            ],
            "detection_preconditions": [
                "billed rate differs from the authoritative rate by more than a configured "
                "materiality threshold",
            ],
            "exclusions": [
                "difference is explained by a valid, currently-active promotional or negotiated "
                "override rate",
                "difference is explained by approved bundled pricing that intentionally departs "
                "from the line-item rate sheet",
                "difference is within the configured immaterial rounding tolerance",
            ],
            "ambiguity_conditions": [
                "multiple, conflicting rate sheets exist for the same customer/service with no "
                "clear precedence",
                "the rate-sheet effective-date window is unclear relative to the job date",
            ],
            "false_positive_risks": [
                "approved negotiated adjustment not yet reflected in the reference rate sheet used "
                "for comparison",
                "currency or unit-of-measure mismatch that only appears to be a rate difference",
            ],
            "causal_hypotheses": [
                "rate-table mismatch: billing system rate table was not updated after a contract "
                "amendment",
                "incorrect job master data attributed the job to the wrong customer/contract "
                "rate tier",
                "customer master-data mismatch routed the job to a stale rate agreement",
            ],
            "investigation_questions": [
                "Which rate sheet or contract amendment is authoritative for this job's date?",
                "Was a negotiated override approved for this customer, and is it on file?",
                "Is the discrepancy explained by currency or unit-of-measure conversion?",
            ],
            "recovery_playbook": [
                "identify the governing contract/rate sheet",
                "compare billed rate to the authorized rate",
                "determine applicability of exclusions/overrides",
                "quantify exposure",
                "approve corrective action",
                "correct invoice, debit, or credit as appropriate",
                "settle/collect",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "corrected invoice, debit memo, or credit memo referencing the rate correction",
            ],
            "value_basis": {
                "category": "MARGIN_PROTECTION",
                "notes": (
                    "Exposure is the margin impact of the rate discrepancy; direction (underbilled "
                    "vs. overbilled) determines whether the correction is a supplemental charge or "
                    "a credit."
                ),
            },
            "limitations": [
                "requires an authoritative, current rate source; if the reference rate sheet "
                "itself "
                "is stale, this pattern will misclassify a correctly-billed job as a mismatch",
            ],
            "related_defect_codes": ["incorrect_contract_rate", "currency_mismatch"],
        },
    },
    {
        "pattern_key": "J2C-OFS-09",
        "name": "Unauthorized Discount or Credit",
        "process_stage": "invoicing",
        "description": (
            "A discount, credit, or price reduction is inconsistent with authorized "
            "commercial terms."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "credit memo or discount line item",
                "authorization record (approval workflow, signed commercial term) for the "
                "discount/credit",
            ],
            "detection_preconditions": [
                "a discount or credit is applied to an invoice",
                "no matching authorization record exists, or the applied amount exceeds the "
                "authorized amount",
            ],
            "exclusions": [
                "discount/credit matches an approved standing commercial term (e.g. volume rebate) "
                "on file",
                "credit is a like-for-like reversal of a previously issued erroneous charge",
            ],
            "ambiguity_conditions": [
                "authorization record exists but its scope (which invoices/period it covers) is "
                "unclear",
            ],
            "false_positive_risks": [
                "goodwill credits approved verbally or through a channel not yet reflected in the "
                "authorization record system",
                "credit issued as part of a broader settlement not itself visible in job-level "
                "data",
            ],
            "causal_hypotheses": [
                "credit authorization failure: credit was applied before or without required "
                "approval",
                "manual handoff omission: an approved discount was applied to the wrong invoice or "
                "amount",
            ],
            "investigation_questions": [
                "Is there an approval on file authorizing this discount or credit?",
                "Does the authorized amount match the applied amount?",
                "Is this a reversal of a prior erroneous charge rather than a new discount?",
            ],
            "recovery_playbook": [
                "identify the discount/credit and its stated basis",
                "locate or request retroactive authorization",
                "quantify exposure if unauthorized",
                "approve corrective action (reverse, adjust, or ratify)",
                "correct invoice or issue offsetting debit as approved",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "authorization record reconciled to the applied discount/credit, or corrective "
                "debit issued",
            ],
            "value_basis": {
                "category": "MARGIN_PROTECTION",
                "notes": "Exposure is the unauthorized portion of the discount or credit.",
            },
            "limitations": [
                "cannot verify verbal or off-system approvals; absence of a system record is "
                "evidence of missing authorization, not proof commercial intent was violated",
            ],
            "related_defect_codes": ["credit_after_recovery"],
        },
    },
    {
        "pattern_key": "J2C-OFS-10",
        "name": "Invoice Delay After Completion",
        "process_stage": "invoicing",
        "description": (
            "Invoice issuance materially lags operational completion beyond the configured "
            "expectation."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "job/service completion timestamp",
                "invoice issuance timestamp",
                "configured expected invoicing turnaround for this contract/customer",
            ],
            "detection_preconditions": [
                "elapsed time between completion and invoice issuance exceeds the configured "
                "expected turnaround",
            ],
            "exclusions": [
                "contract uses milestone/progress billing where a longer lag is expected by design",
                "batch invoicing cycle legitimately explains the observed lag",
            ],
            "ambiguity_conditions": [
                "expected turnaround is not configured for this contract, so materiality cannot be "
                "assessed",
            ],
            "false_positive_risks": [
                "customer-requested invoice hold pending a documentation exchange, not an internal "
                "process delay",
            ],
            "causal_hypotheses": [
                "invoice workflow delay in the billing queue",
                "missing field documentation blocked invoice release until resolved",
                "dispatch/billing system disconnect delayed job data reaching billing at all",
            ],
            "investigation_questions": [
                "What blocked invoice issuance during the delay window?",
                "Is the delay attributable to a documentation gap already tracked elsewhere?",
                "Is this a systemic queue delay affecting multiple jobs, not just this one?",
            ],
            "recovery_playbook": [
                "confirm expected turnaround for this contract",
                "identify the specific blocker causing the delay",
                "escalate and approve clearing the blocker",
                "issue the invoice",
                "monitor payment",
                "record realized value (cash-acceleration impact of faster future cycles)",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "invoice issued, and where the delay is systemic, a process-improvement record "
                "documenting the root workflow fix",
            ],
            "value_basis": {
                "category": "CASH_ACCELERATION",
                "notes": (
                    "This is a cash-timing pattern, not a revenue pattern: the job may already be "
                    "fully billable, and the leakage is the cost of delayed cash, not lost revenue."
                ),
            },
            "limitations": [
                "materiality depends entirely on a configured expected-turnaround value; without "
                "one, this pattern cannot distinguish normal variation from true delay",
            ],
            "related_defect_codes": ["completed_without_invoice"],
        },
    },
    {
        "pattern_key": "J2C-OFS-11",
        "name": "Payment Delay — Documentation Blocker",
        "process_stage": "payment",
        "description": (
            "Collection is delayed due to incomplete purchase order, ticket, signature, "
            "approval, or other supporting documentation."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "invoice aging / days-outstanding record",
                "documentation completeness check (PO reference, ticket, customer "
                "signature/approval)",
                "customer dispute or hold notation, if any",
            ],
            "detection_preconditions": [
                "invoice is outstanding beyond the standard payment term",
                "at least one required supporting document (PO, ticket, signature, approval) is "
                "missing or unmatched",
            ],
            "exclusions": [
                "customer has an approved extended payment term on file that explains the aging",
                "delay is explained by a documented, unrelated commercial dispute rather than "
                "missing documentation",
            ],
            "ambiguity_conditions": [
                "which specific document is blocking payment is not recorded by the customer or "
                "the servicer's collections process",
            ],
            "false_positive_risks": [
                "customer's own internal AP processing time exceeding the nominal term, unrelated "
                "to documentation completeness",
            ],
            "causal_hypotheses": [
                "purchase order was exhausted or not referenced correctly on the invoice",
                "customer approval/signature was never captured at job completion",
                "PO mismatch: invoice PO reference does not match the customer's PO record",
            ],
            "investigation_questions": [
                "Which specific document does the customer's AP team say is missing?",
                "Does the invoice's PO reference match an active, unexhausted PO?",
                "Was customer sign-off captured at the time of service?",
            ],
            "recovery_playbook": [
                "identify the specific documentation blocker",
                "obtain or correct the missing document",
                "approve resubmission to customer AP with the completed documentation package",
                "monitor payment",
                "record realized value (cash-acceleration impact)",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "payment received, or documentation package confirmed accepted by customer AP",
            ],
            "value_basis": {
                "category": "CASH_ACCELERATION",
                "notes": "Exposure is the carrying cost of delayed collection, not lost revenue.",
            },
            "limitations": [
                "relies on the servicer's own record of which document is missing; if that record "
                "is itself incomplete, root cause cannot be isolated from this pattern alone",
            ],
            "related_defect_codes": [
                "missing_customer_signature",
                "exhausted_purchase_order",
                "partial_payment",
            ],
        },
    },
    {
        "pattern_key": "J2C-OFS-12",
        "name": "Job Margin Erosion",
        "process_stage": "recovery",
        "description": (
            "Actual job economics materially underperform expected economics due to an "
            "identifiable operational or commercial variance."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "expected job economics (estimated revenue, estimated cost, expected margin)",
                "actual job economics (invoiced revenue, actual cost)",
                "variance decomposition by cost/revenue category",
            ],
            "detection_preconditions": [
                "actual margin falls below expected margin by more than a configured materiality "
                "threshold",
                "the variance is attributable to an identifiable category (labor, equipment, "
                "material, rework, rate, or an unbilled-item pattern above) rather than "
                "unexplained",
            ],
            "exclusions": [
                "variance is within normal, previously-observed business variance for this job "
                "type",
                "variance is explained by an approved change order that reset the economic "
                "baseline",
            ],
            "ambiguity_conditions": [
                "variance cannot be decomposed to a specific category with available data",
                "expected economics baseline itself is missing, stale, or was never approved",
            ],
            "false_positive_risks": [
                "treating expected operational variance (weather delay, standard rework rate) as "
                "leakage without enough evidence to separate it from recoverable causes",
                "estimate quality issues at the bidding stage masquerading as execution-stage "
                "leakage",
            ],
            "causal_hypotheses": [
                "one or more of the resource-omission patterns above (labor/equipment/material/"
                "standby/mob-demob) individually contributed to the shortfall",
                "unbilled change order: scope grew but the change order was never billed",
                "rework: work had to be repeated at the servicer's cost due to a quality issue",
            ],
            "investigation_questions": [
                "Does the margin shortfall decompose cleanly into one or more of the specific "
                "resource-omission patterns in this pack?",
                "Was there an approved change order that should have reset the economic baseline?",
                "Is the shortfall consistent with known, expected variance for this job type?",
            ],
            "recovery_playbook": [
                "decompose the variance by category",
                "cross-reference each category against the relevant specific leakage pattern",
                "quantify the recoverable portion versus expected business variance",
                "approve corrective action for the recoverable portion",
                "execute corrective billing/collection per the applicable specific pattern",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "variance decomposition record with recoverable/non-recoverable split and finance "
                "sign-off",
            ],
            "value_basis": {
                "category": "MARGIN_PROTECTION",
                "notes": (
                    "This is a portfolio/aggregate pattern: only the portion of variance "
                    "attributable to an identifiable, recoverable cause is Exposure; the remainder "
                    "is expected business variance, not leakage."
                ),
            },
            "limitations": [
                "highest false-positive risk in the pack; must not be classified as leakage "
                "without "
                "sufficient evidence to distinguish recoverable variance from expected variance",
                "depends on the quality of the job-level expected-economics baseline, which this "
                "pattern consumes but does not itself produce",
            ],
            "related_defect_codes": ["unbilled_change_order"],
        },
    },
)


def pattern_by_key(pattern_key: str) -> PatternDefinition:
    for pattern in PATTERNS:
        if pattern["pattern_key"] == pattern_key:
            return pattern
    raise KeyError(pattern_key)
