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

from typing import NotRequired, TypedDict

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
    # P3.13 additions: family/tier/status drive portfolio grouping and honest maturity
    # labeling; source_systems/correlation_fields answer "what must be correlated, through
    # which keys, to investigate this leakage" -- the primary P3.13 product concept.
    family: str
    validation_tier: str
    validation_status: str
    source_systems: list[str]
    correlation_fields: list[str]
    # P3.14 additions: exactly one of the two is present, depending on validation_tier.
    # Both are static, pre-computed, deterministically-reproducible content -- see
    # tests/oilfield_validation_lab.py for the scoring engine that generated them and
    # tests/test_p3_14_oilfield_validation_lab.py for the drift check against it.
    validation_evidence: NotRequired[dict[str, object]]
    validation_plan: NotRequired[dict[str, object]]
    # P3.15 addition: declarative service-family relevance, present only on Tier 1
    # (validated) patterns -- the representative Oilfield Services contexts each
    # pattern's golden-dataset cases were designed against.
    service_families: NotRequired[list[str]]


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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["field ticketing", "dispatch", "ERP billing"],
            "service_families": ["field_maintenance", "artificial_lift"],
            "correlation_fields": ["job/service order ID", "completion timestamp", "invoice ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-01-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-01-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 3,
                    "false_positive": 0,
                    "true_negative": 118,
                    "false_negative": 0,
                    "exclusion_cases": 3,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "446997d32c969f6ab57d4c0cda4d194941833f0aed1cadc9a17eaf60a20ff67c",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["field ticketing", "ERP billing"],
            "service_families": ["wireline_coiled_tubing", "field_maintenance"],
            "correlation_fields": ["ticket ID", "job/service order ID", "invoice line ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-02-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-02-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "0938501b726975cfadea56f2ad7771d57ab8a6fdbb1e4ac5cecf83a3bd128e96",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["field ticketing", "time & labor", "ERP billing"],
            "service_families": ["pressure_pumping", "field_maintenance"],
            "correlation_fields": [
                "job/service order ID",
                "labor time entry ID",
                "invoice line ID",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-03-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-03-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "aa1a265a05287c5807d12acbe6e4a5db03ec39cdf0f555512cca3df868a854cd",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["EAM / asset management", "field ticketing", "ERP billing"],
            "service_families": ["equipment_rental", "artificial_lift"],
            "correlation_fields": ["asset ID", "job/service order ID", "invoice line ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-04-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-04-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "19ca5af1ce4962c04f984127cd41c945c0051dc39c531d4036194ff07a2ca967",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["inventory/ERP", "field ticketing", "ERP billing"],
            "service_families": ["pressure_pumping", "artificial_lift"],
            "correlation_fields": ["SKU", "job/service order ID", "invoice line ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-05-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-05-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 1,
                    "false_positive": 0,
                    "true_negative": 120,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "d31f60433742794b1b1510035015e4607662bef0ef61f1fc9af3ca855bb7cfd0",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["field ticketing", "dispatch", "ERP billing"],
            "service_families": ["pressure_pumping", "wireline_coiled_tubing"],
            "correlation_fields": [
                "job/service order ID",
                "standby start/end timestamp",
                "invoice line ID",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-06-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-06-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 3,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "d87abf3e4edb34a625827854bcd70178a2c5d58ae489f547c4071ca5053ec737",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "C",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["GPS/telematics", "EAM", "field ticketing", "ERP billing"],
            "service_families": ["equipment_rental", "pressure_pumping"],
            "correlation_fields": [
                "asset serial",
                "job/service order ID",
                "mobilization/demobilization timestamp",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-07-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-07-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "f03b9409b5e31ec11c231c4b1008464fd8b859aeeb2d5dd18f3fa3094d0296aa",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "D",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["CLM/MSA", "rate book", "ERP billing"],
            "service_families": ["artificial_lift", "field_maintenance"],
            "correlation_fields": ["contract ID", "rate schedule version", "invoice line ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-08-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-08-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 3,
                    "false_positive": 0,
                    "true_negative": 118,
                    "false_negative": 0,
                    "exclusion_cases": 3,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "007150bc96fd293607bbfc6d1109bb5aa02a6337f22be9bc95a06121c42e2282",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "D",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["ERP AR", "credit memo/adjustment", "approval workflow"],
            "service_families": ["artificial_lift"],
            "correlation_fields": ["invoice ID", "credit memo ID", "approval authority"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-09-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-09-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 1,
                    "false_positive": 0,
                    "true_negative": 120,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "2cb91684dde4dcf615d9a5aacbef157a5662f3bfb8db0a8c7fb9fd09d03ac41a",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["field ticketing", "ERP billing"],
            "service_families": ["field_maintenance"],
            "correlation_fields": [
                "job/service order ID",
                "completion timestamp",
                "invoice issue date",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-10-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-10-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "1236347e755664dc309c432654c7a246f78943e278b00213688c5573e1a4ad8c",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "F",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["ERP AR", "document management", "customer approval workflow"],
            "service_families": ["field_maintenance"],
            "correlation_fields": ["invoice ID", "PO", "supporting document status"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-11-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-11-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 1,
                    "false_positive": 0,
                    "true_negative": 120,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "ce09fe94562de5489b43eff4d85e689ee74e0c5950c7286a4cd478f717798260",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
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
            "family": "D",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["ERP billing", "cost accounting", "change order/AFE"],
            "service_families": ["artificial_lift", "field_maintenance"],
            "correlation_fields": [
                "job/service order ID",
                "expected margin baseline",
                "change order ID",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-12-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-12-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 1,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "6de84a450e704eb1d6e15df7012061ce76238d8fffe452aabd5de569dd726c76",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-13",
        "name": "Out-of-Scope Oral Work",
        "process_stage": "field_execution",
        "description": (
            "Work was performed at a customer representative's verbal request outside the "
            "authorized scope of the job/service order, with no field ticket or change order "
            "capturing it."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "crew/foreman notes or radio/dispatch log referencing work beyond the original "
                "scope",
                "absence of a matching field ticket or change order for the extra work",
            ],
            "detection_preconditions": [
                "crew log or supervisor note references work not covered by the original "
                "job/service order scope",
                "no field ticket or change order exists for that work",
            ],
            "exclusions": [
                "work is within a pre-authorized minor-variance tolerance in the contract",
                "work was later formalized by a change order before invoicing",
            ],
            "ambiguity_conditions": [
                "it is unclear whether the verbal request came from someone with authority to "
                "expand scope",
            ],
            "false_positive_risks": [
                "crew notes using informal language for work that was, in fact, in scope",
            ],
            "causal_hypotheses": [
                "field crew accepted a verbal scope change without routing it through the change "
                "order process",
                "no field-level process exists to capture out-of-scope requests as billable events",
            ],
            "investigation_questions": [
                "Who requested the extra work, and did they hold contractual authority to expand "
                "scope?",
                "Can the extra work be reconstructed and quantified from crew records?",
            ],
            "recovery_playbook": [
                "confirm the work occurred and was outside original scope",
                "confirm requester authority per contract",
                "quantify the work",
                "approve retroactive change order and billing",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "retroactive change order and supplemental invoice referencing the out-of-scope "
                "work",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Exposure exists only once the work and its authorization are reconstructed "
                    "from field records; it is not Expected Recovery until a change order is "
                    "approved."
                ),
            },
            "limitations": [
                "highly dependent on the quality of informal field documentation; weak "
                "documentation may make quantification unreliable",
            ],
            "related_defect_codes": [],
            "family": "A",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["dispatch/crew log", "field ticketing", "change order/CLM"],
            "correlation_fields": ["job/service order ID", "crew log entry", "change order ID"],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["dispatch/crew log", "field ticketing", "change order/CLM"],
                "required_fields": ["job/service order ID", "crew log entry", "change order ID"],
                "scenario_concept": "Verbally-authorized field work with no ticket ever opened.",
                "clean_case_concept": (
                    "Crew log entry exists and a matching ticket was opened same-shift."
                ),
                "positive_case_concept": (
                    "Crew log shows hours worked; no ticket exists for that window."
                ),
                "exclusion_case_concept": (
                    "Work was pre-work (setup) time explicitly excluded from billing."
                ),
                "ambiguity_case_concept": (
                    "Crew log entry lacks a clear job/service order reference."
                ),
                "blocker_to_promotion": (
                    "requires a synthetic crew-log/dispatch data source distinct from the existing "
                    "field-ticket-centric golden dataset before a credible detector can be written"
                ),
                "readiness": "BLOCKED_UNSAFE_TO_AUTOMATE",
                "next_validation_action": "requires crew-log interpretation; no structured source",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-14",
        "name": "Minimum Charge or Minimum Hour Not Applied",
        "process_stage": "invoicing",
        "description": (
            "The contract specifies a minimum charge or minimum billable hours for a job/call-out "
            "type, but the invoice reflects less than the contractual minimum."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "contract minimum-charge or minimum-hour clause",
                "invoice line item for the job",
                "actual hours/charge billed",
            ],
            "detection_preconditions": [
                "job type is subject to a contractual minimum",
                "billed amount or hours is below the contractual minimum",
            ],
            "exclusions": [
                "customer has an approved waiver of the minimum for this job type",
                "job was canceled before the minimum-triggering threshold was reached",
            ],
            "ambiguity_conditions": [
                "it is unclear which minimum-charge clause (if any) applies to this job type",
            ],
            "false_positive_risks": [
                "bundled/package pricing where the minimum is already embedded in a flat fee",
            ],
            "causal_hypotheses": [
                "billing system does not enforce contractual minimums automatically",
                "job type was miscategorized, so the minimum-charge rule was never triggered",
            ],
            "investigation_questions": [
                "Does the governing contract specify a minimum for this job type?",
                "Was the job type correctly categorized at billing time?",
            ],
            "recovery_playbook": [
                "confirm the applicable minimum-charge clause",
                "confirm no waiver applies",
                "quantify the shortfall",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice reflecting the contractual minimum"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the gap between billed amount and the contractual minimum.",
            },
            "limitations": [
                "requires an accurate, current mapping of job types to minimum-charge clauses",
            ],
            "related_defect_codes": [],
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["CLM/MSA", "rate book", "ERP billing"],
            "service_families": ["artificial_lift"],
            "correlation_fields": ["job type code", "contract ID", "invoice line ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-14-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-14-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "6efc7100a051537c97643fd32bd7708c9df721571f6f3f5b98273fdd096ff9f2",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-15",
        "name": "Partial Ticket Billing",
        "process_stage": "invoicing",
        "description": (
            "A field ticket has multiple billable line items, but only some of them were carried "
            "onto the invoice."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "field ticket with itemized billable lines",
                "invoice lines referencing the same ticket",
            ],
            "detection_preconditions": [
                "ticket has N billable line items",
                "invoice references the ticket with fewer than N line items",
            ],
            "exclusions": [
                "omitted lines were explicitly voided or deemed non-billable on the ticket itself",
                "omitted lines are covered by a separate, cross-referenced invoice",
            ],
            "ambiguity_conditions": [
                "ticket line-item billability flags are missing or inconsistent",
            ],
            "false_positive_risks": [
                "ticket line items intentionally consolidated into a single summary invoice line",
            ],
            "causal_hypotheses": [
                "billing system import truncated or dropped some ticket line items",
                "manual re-keying of the ticket into the billing system omitted line items",
            ],
            "investigation_questions": [
                "Which specific ticket line items are missing from the invoice, and why?",
                "Were the missing lines explicitly voided, or simply dropped?",
            ],
            "recovery_playbook": [
                "reconcile every ticket line item to an invoice line",
                "confirm billability of each missing line",
                "approve billing correction",
                "create supplemental invoice for missing lines",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice covering the previously omitted lines"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the sum of the omitted, still-billable ticket line items.",
            },
            "limitations": [
                "requires line-item-level ticket-to-invoice reconciliation, not just ticket-level "
                "presence/absence",
            ],
            "related_defect_codes": ["duplicate_field_ticket"],
            "family": "A",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["field ticketing", "ERP billing"],
            "service_families": ["artificial_lift", "field_maintenance"],
            "correlation_fields": ["ticket ID", "ticket line item ID", "invoice line ID"],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-15-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-15-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "0e8611c10cb2056bebf0b8e5e51d77add3f401e7191fcf215c1330831484bf77",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-16",
        "name": "Loss-in-Hole / Tool Damage",
        "process_stage": "field_execution",
        "description": (
            "A tool or asset is lost in hole or damaged in a context where some contractual "
            "customer recovery may be possible. Asset value alone does not establish "
            "recoverability."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "incident record describing the loss/damage",
                "asset identity and book/replacement value",
                "governing contract's loss-in-hole or damage-liability clause",
                "field ticket for the job during which the incident occurred",
            ],
            "detection_preconditions": [
                "an incident record exists for a lost or damaged asset tied to a job",
                "no corresponding invoice line or recovery claim exists for the incident",
            ],
            "exclusions": [
                "contract explicitly assigns loss-in-hole risk to the servicer, not the customer",
                "loss/damage was caused by servicer negligence or equipment failure, not an "
                "operational hazard the contract allocates to the customer",
                "asset is fully covered by insurance already claimed",
            ],
            "ambiguity_conditions": [
                "fault/cause of the incident is not yet determined",
                "the governing contract's liability-allocation clause is missing or ambiguous",
            ],
            "false_positive_risks": [
                "treating full replacement/book value as automatically recoverable when the "
                "contract caps recovery, requires a deductible, or splits liability",
            ],
            "causal_hypotheses": [
                "incident was never routed to the billing/claims process after being logged "
                "operationally",
                "liability determination was never made, so no claim was ever initiated",
            ],
            "investigation_questions": [
                "What does the contract say about liability allocation for downhole loss/damage?",
                "Has a fault/liability determination been made for this specific incident?",
                "Is the claim within any applicable value cap or deductible?",
            ],
            "recovery_playbook": [
                "confirm the incident and the affected asset",
                "confirm the contract's liability-allocation clause",
                "determine cause/fault where required by contract",
                "quantify the claim within any contractual cap or deductible",
                "approve claim submission",
                "submit claim/invoice for the customer-recoverable portion",
                "monitor resolution and payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "claim resolution record with the finance-verified recoverable amount",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Asset replacement/book value is not Exposure. Exposure is only the "
                    "contractually customer-recoverable portion after liability allocation and any "
                    "cap/deductible are applied -- and it remains Exposure, not Expected Recovery, "
                    "until a claim is approved."
                ),
            },
            "limitations": [
                "requires a documented liability/fault determination; without one, no reliable "
                "exposure figure can be produced",
                "reference/simulation content only; no production Learning currently supports this "
                "pattern for any tenant",
            ],
            "related_defect_codes": [],
            "family": "B",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": [
                "field ticketing",
                "EAM / asset management",
                "incident record",
                "CLM/MSA",
                "ERP billing",
            ],
            "service_families": ["wireline_coiled_tubing", "equipment_rental"],
            "correlation_fields": [
                "asset ID",
                "job/well ID",
                "incident ID",
                "contract liability clause ID",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-16-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-16-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 3,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "e13f2c91dca3467bbc3e271309e03de445af5d537d99734e55f53f7351e7d6fd",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-17",
        "name": "Bulk Material Shrinkage and Transfers",
        "process_stage": "resource_validation",
        "description": (
            "Bulk material issued to a job shows a variance between issued, transferred, "
            "consumed, and billed quantities. Inventory variance alone is not automatic revenue "
            "leakage."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "inventory issue record (SKU, quantity, job)",
                "warehouse/inter-job transfer records",
                "consumption record",
                "invoice line item for the material",
            ],
            "detection_preconditions": [
                "issued quantity exceeds the sum of consumed-and-billed plus transferred-out "
                "quantity by more than a configured shrinkage tolerance",
            ],
            "exclusions": [
                "variance is within a documented, expected shrinkage/wastage allowance for the "
                "material type",
                "material was transferred to another job and billed there",
                "material was returned to inventory and the return is recorded",
            ],
            "ambiguity_conditions": [
                "transfer records are incomplete, so it is unclear whether material moved to "
                "another job",
            ],
            "false_positive_risks": [
                "normal handling loss/wastage rates being misclassified as billable-material "
                "leakage",
            ],
            "causal_hypotheses": [
                "material was transferred to another job without a recorded transfer, so it "
                "appears consumed but unbilled at the original job",
                "inventory record-keeping error rather than a true billing gap",
            ],
            "investigation_questions": [
                "Does the variance reconcile against inter-job transfer records?",
                "Is the variance within the documented shrinkage tolerance for this material?",
            ],
            "recovery_playbook": [
                "reconcile issued, transferred, consumed, and billed quantities",
                "confirm the variance exceeds the shrinkage tolerance",
                "identify the job(s) where the material was actually billable",
                "approve billing correction",
                "create supplemental invoice at the correct job",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["reconciled material ledger and corrected invoice"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Inventory variance is not, by itself, billable amount. Exposure exists only "
                    "for the portion of the variance traced to a specific billable job and not "
                    "already invoiced there."
                ),
            },
            "limitations": [
                "requires reasonably complete inter-job transfer records; without them this "
                "pattern cannot distinguish leakage from ordinary shrinkage",
            ],
            "related_defect_codes": [],
            "family": "B",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["inventory/ERP", "field ticketing", "warehouse transfer log"],
            "correlation_fields": [
                "SKU",
                "job/well ID",
                "issued qty",
                "transferred qty",
                "consumed qty",
                "billed qty",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["inventory/ERP", "field ticketing", "warehouse transfer log"],
                "required_fields": [
                    "SKU",
                    "job/well ID",
                    "issued qty",
                    "transferred qty",
                    "consumed qty",
                    "billed qty",
                ],
                "scenario_concept": (
                    "Bulk material issued/transferred quantities "
                    "do not reconcile to billed quantities."
                ),
                "clean_case_concept": (
                    "Issued, transferred, consumed, and billed "
                    "quantities reconcile within tolerance."
                ),
                "positive_case_concept": (
                    "Consumed quantity exceeds billed quantity "
                    "beyond the customer-billable threshold."
                ),
                "exclusion_case_concept": (
                    "Variance is within normal operational shrinkage "
                    "tolerance for the material class."
                ),
                "ambiguity_case_concept": (
                    "Transfer log has gaps that prevent a clean issued-to-consumed reconciliation."
                ),
                "blocker_to_promotion": (
                    "requires a clear, contract-sourced distinction between operational shrinkage "
                    "tolerance and customer-billable quantity, not yet represented as a fixture"
                ),
                "readiness": "DEFERRED",
                "next_validation_action": "needs dedicated transfer/return fixtures; high FP risk",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-18",
        "name": "Extended Idle Asset Rental",
        "process_stage": "resource_validation",
        "description": (
            "A rented or company asset remains on customer location, tracked as deployed, beyond "
            "the billable rental/usage window recognized on the invoice."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "asset location/telematics history",
                "field ticket stop/departure time",
                "rental or billable-window terms",
            ],
            "detection_preconditions": [
                "asset location data shows the asset remained on site after the ticketed stop time",
                "invoice billable window ends at or before the ticketed stop time, not the actual "
                "departure time",
            ],
            "exclusions": [
                "the extended dwell time is explicitly non-billable per contract (customer-caused "
                "delay with a contractual waiver)",
                "the asset was deployed to a different, already-billed job at the same location",
            ],
            "ambiguity_conditions": [
                "telematics data is missing or unreliable for the period in question",
            ],
            "false_positive_risks": [
                "asset staged nearby for an upcoming job at the same site, not idle-billable time",
            ],
            "causal_hypotheses": [
                "ticket close-out used a planned stop time rather than the actual departure time",
                "no process exists to reconcile telematics dwell time against the billed window",
            ],
            "investigation_questions": [
                "What does telematics show as the actual departure time versus the ticketed stop "
                "time?",
                "Is the extended dwell time billable per the rental/rate terms?",
            ],
            "recovery_playbook": [
                "reconcile telematics dwell time to the ticketed and invoiced window",
                "confirm billability of the extended period",
                "approve billing correction",
                "create supplemental invoice for the extended window",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice for the reconciled billable window"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of the billable window between ticketed stop time "
                "and confirmed actual departure.",
            },
            "limitations": [
                "depends on telematics/location data coverage and accuracy",
            ],
            "related_defect_codes": [],
            "family": "B",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": [
                "EAM / asset management",
                "GPS/telematics",
                "field ticketing",
                "CLM/MSA",
            ],
            "service_families": ["equipment_rental"],
            "correlation_fields": [
                "asset serial",
                "job ID",
                "location",
                "ticket stop time",
                "departure time",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-18-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-18-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "21e37e1452c01cd5b92a69e0576e26f1b36a1c36218bbc95d3fe37b9d5253644",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-19",
        "name": "Customer-Chargeable Tool Repair Not Recovered",
        "process_stage": "resource_validation",
        "description": (
            "A tool required repair after customer-caused misuse or downhole conditions covered "
            "by contract, but the repair cost was absorbed internally rather than billed."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "repair work order/cost record for the tool",
                "root-cause/damage-cause notation on the repair record",
                "governing contract's customer-chargeable-repair clause",
            ],
            "detection_preconditions": [
                "a repair cost record exists tagged with a customer-caused or contractually "
                "chargeable damage cause",
                "no invoice line item references the repair",
            ],
            "exclusions": [
                "damage cause is normal wear-and-tear, not customer-caused or contractually "
                "chargeable",
                "repair is covered by an existing insurance/warranty claim already recovered "
                "elsewhere",
            ],
            "ambiguity_conditions": [
                "damage-cause classification on the repair record is missing or disputed",
            ],
            "false_positive_risks": [
                "misclassifying routine maintenance as a chargeable repair",
            ],
            "causal_hypotheses": [
                "repair shop process does not route customer-caused damage to billing",
                "damage-cause classification was never made at intake",
            ],
            "investigation_questions": [
                "Is the damage cause customer-caused or otherwise contractually chargeable?",
                "Does the contract specify a chargeable-repair clause covering this scenario?",
            ],
            "recovery_playbook": [
                "confirm the damage cause classification",
                "confirm the contractual chargeable-repair basis",
                "quantify the repair cost eligible for recovery",
                "approve billing action",
                "create invoice for the chargeable repair",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["invoice referencing the repair work order"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the repair cost attributable to a customer-caused or "
                "contractually chargeable event, not routine maintenance cost.",
            },
            "limitations": [
                "requires a reliable damage-cause classification at the point of repair intake",
            ],
            "related_defect_codes": [],
            "family": "B",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": [
                "EAM / asset management",
                "repair shop work order",
                "CLM/MSA",
                "ERP billing",
            ],
            "correlation_fields": [
                "asset ID",
                "repair work order ID",
                "job/well ID",
                "damage cause code",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": [
                    "EAM / asset management",
                    "repair shop work order",
                    "CLM/MSA",
                    "ERP billing",
                ],
                "required_fields": [
                    "asset ID",
                    "repair work order ID",
                    "job/well ID",
                    "damage cause code",
                ],
                "scenario_concept": (
                    "Customer-caused tool damage generates a repair "
                    "work order not billed to the customer."
                ),
                "clean_case_concept": (
                    "Repair work order exists, damage cause "
                    "is company-caused; correctly not billed."
                ),
                "positive_case_concept": (
                    "Repair work order exists, damage cause is customer-attributable; not billed."
                ),
                "exclusion_case_concept": (
                    "Damage is within normal wear-and-tear, contractually non-billable."
                ),
                "ambiguity_case_concept": "Damage cause code is missing or unresolved.",
                "blocker_to_promotion": (
                    "requires an authoritative damage-cause-code taxonomy shared with Loss-in-Hole "
                    "(J2C-OFS-16) before both can be validated without cross-pattern ambiguity"
                ),
                "readiness": "DEFERRED",
                "next_validation_action": "near-duplicate of J2C-OFS-16; revisit once it matures",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-20",
        "name": "Third-Party Pass-Through / Re-Rental Not Billed",
        "process_stage": "invoicing",
        "description": (
            "A third-party vendor cost (sub-rental, subcontractor service) approved for "
            "customer pass-through under the contract was not carried onto the customer invoice "
            "with the permitted markup."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "vendor/AP invoice referencing the job",
                "purchase order authorizing the pass-through vendor cost",
                "governing contract's pass-through and markup terms",
                "customer AR invoice for the job",
            ],
            "detection_preconditions": [
                "a vendor invoice exists, referenced by a PO tied to the job, tagged as "
                "customer-pass-through eligible",
                "no customer invoice line item references the vendor cost with the contractual "
                "markup applied",
            ],
            "exclusions": [
                "the contract does not permit pass-through of this vendor cost category",
                "the vendor cost is already absorbed in a flat day-rate that includes third-party "
                "costs",
                "markup was intentionally waived under an approved customer concession",
            ],
            "ambiguity_conditions": [
                "the PO does not clearly indicate pass-through eligibility or markup percentage",
            ],
            "false_positive_risks": [
                "vendor costs legitimately absorbed into the servicer's own margin by contract "
                "design",
            ],
            "causal_hypotheses": [
                "AP-to-AR handoff for pass-through costs is manual and was skipped",
                "vendor invoice arrived after the customer invoice for the same period was already "
                "issued",
            ],
            "investigation_questions": [
                "Does the contract permit pass-through of this specific vendor cost category, and "
                "at what markup?",
                "Was the vendor invoice received before or after the customer invoice for the same "
                "period?",
            ],
            "recovery_playbook": [
                "confirm pass-through eligibility and markup terms",
                "reconcile vendor invoice to PO and job",
                "quantify the pass-through amount including markup",
                "approve billing correction",
                "create supplemental customer invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "supplemental customer invoice referencing the vendor invoice and PO",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Vendor cost alone is not customer-billable amount; only the contractually "
                    "permitted pass-through-plus-markup portion is Exposure, and only once "
                    "eligibility is confirmed."
                ),
            },
            "limitations": [
                "requires PO-level pass-through/markup metadata; without it this pattern cannot "
                "reliably distinguish leakage from intentionally-absorbed vendor cost",
            ],
            "related_defect_codes": [],
            "family": "C",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["AP", "vendor invoice", "PO", "CLM/MSA", "ERP AR"],
            "service_families": ["wireline_coiled_tubing", "field_maintenance"],
            "correlation_fields": [
                "vendor invoice ID",
                "PO",
                "job ID",
                "contractual markup %",
                "customer invoice line ID",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-20-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-20-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 1,
                    "false_positive": 0,
                    "true_negative": 120,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "6302a22d80ef9f90eac17d2cf6e6e48dfa30ff1274db4233df7e1274baf4f367",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-21",
        "name": "Travel, Mobilization Camp, and Per-Diem Allowances Not Billed",
        "process_stage": "invoicing",
        "description": (
            "Crew travel, camp, or per-diem allowances incurred for a remote job under contract "
            "terms were not reflected on the customer invoice."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "crew roster and travel/mileage records for the job",
                "expense records for camp/per-diem",
                "contractual travel/camp allowance rate card",
                "invoice line items",
            ],
            "detection_preconditions": [
                "travel or camp expense records exist for the job",
                "no invoice line item reflects the corresponding allowance",
            ],
            "exclusions": [
                "travel/camp costs are bundled into a flat day rate that already includes them",
                "job is within the contract's non-billable local-radius zone",
            ],
            "ambiguity_conditions": [
                "it is unclear whether the job falls within a billable-travel radius or zone",
            ],
            "false_positive_risks": [
                "crew travel between two jobs on the same day, allocated incorrectly to one job",
            ],
            "causal_hypotheses": [
                "expense system and billing system are not integrated, so travel/camp costs never "
                "reach invoicing",
                "allowance rate card was not applied at time of ticket creation",
            ],
            "investigation_questions": [
                "Does the contract's travel/camp allowance apply to this job's location?",
                "Were travel/camp costs correctly allocated to this job versus another?",
            ],
            "recovery_playbook": [
                "confirm contractual travel/camp allowance applicability",
                "reconcile expense records to the job",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice for travel/camp allowances"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the contractual allowance amount for confirmed, "
                "job-attributable travel/camp cost.",
            },
            "limitations": [
                "requires reliable job-level allocation of travel/camp expense records",
            ],
            "related_defect_codes": [],
            "family": "C",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["fleet/GPS", "expense management", "crew roster", "CLM/MSA"],
            "correlation_fields": [
                "job/well ID",
                "employee/crew ID",
                "mileage",
                "travel dates",
                "per-diem rate",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["fleet/GPS", "expense management", "crew roster", "CLM/MSA"],
                "required_fields": [
                    "job/well ID",
                    "employee/crew ID",
                    "mileage",
                    "travel dates",
                    "per-diem rate",
                ],
                "scenario_concept": (
                    "Contractually billable travel/camp/per-diem "
                    "allowances not reflected on the invoice."
                ),
                "clean_case_concept": (
                    "Travel/camp days billed matches crew roster and contractual per-diem rate."
                ),
                "positive_case_concept": (
                    "Crew roster shows travel/camp days not reflected on any invoice line."
                ),
                "exclusion_case_concept": (
                    "Travel policy caps per-diem below what was informally claimed."
                ),
                "ambiguity_case_concept": (
                    "Crew roster and expense system disagree on travel-day count."
                ),
                "blocker_to_promotion": (
                    "requires expense-management and crew-roster fixtures, systems "
                    "not yet represented anywhere in the current golden dataset"
                ),
                "readiness": "READY_WITH_BOUNDED_FIXTURE_EXPANSION",
                "next_validation_action": "needs a travel-radius/zone fixture, not a boolean flag",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-22",
        "name": "Unbilled Demobilization Delay",
        "process_stage": "field_execution",
        "description": (
            "Demobilization from a customer site was delayed beyond the ticketed/contractual "
            "window for reasons attributable to the customer, but the delay period was not "
            "billed as standby or extended demob time."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "asset telematics/location history",
                "field ticket demob signoff time",
                "contractual demob/standby terms",
            ],
            "detection_preconditions": [
                "telematics shows actual site departure later than the ticketed demob signoff time",
                "invoice does not reflect standby/extended-demob billing for the gap",
            ],
            "exclusions": [
                "delay is attributable to the servicer, not the customer",
                "delay is within a contractual grace period",
            ],
            "ambiguity_conditions": [
                "cause of the delay (customer-caused versus operational) is not documented",
            ],
            "false_positive_risks": [
                "asset staged for a subsequent job at the same site rather than genuinely delayed "
                "demob",
            ],
            "causal_hypotheses": [
                "demob signoff time recorded on the ticket did not reflect actual departure",
                "no process exists to bill standby for customer-caused demob delay",
            ],
            "investigation_questions": [
                "What caused the demobilization delay, and is it customer-attributable per "
                "contract?",
                "Does telematics confirm the actual departure time versus the ticketed signoff?",
            ],
            "recovery_playbook": [
                "confirm the delay and its cause",
                "confirm contractual billability of customer-caused demob delay",
                "quantify the delay period",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice for the confirmed demob delay period"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure exists only for delay confirmed as customer-attributable and "
                "contractually billable; operational or servicer-caused delay is not leakage.",
            },
            "limitations": [
                "depends on telematics coverage and a documented delay-cause determination",
            ],
            "related_defect_codes": [],
            "family": "C",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["GPS/telematics", "field ticketing", "EAM", "CLM/MSA"],
            "service_families": ["equipment_rental", "field_maintenance"],
            "correlation_fields": [
                "asset",
                "ticket signoff time",
                "actual departure time",
                "demob/standby clause",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-22-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-22-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "91f395c9b82b3fbf687671554a23638b72790afe351dac3756ccaeee4967e7ad",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-23",
        "name": "Freight / Hotshot Delivery Charge Omitted",
        "process_stage": "invoicing",
        "description": (
            "An expedited freight or hotshot delivery was arranged and paid for a job, but the "
            "corresponding contractually billable delivery charge was not invoiced to the "
            "customer."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "freight/hotshot vendor invoice or dispatch record referencing the job",
                "contractual freight pass-through terms",
                "invoice line items",
            ],
            "detection_preconditions": [
                "a freight/hotshot cost record exists tied to the job and tagged pass-through "
                "eligible",
                "no invoice line item reflects the freight charge",
            ],
            "exclusions": [
                "freight is a routine, non-billable logistics cost absorbed by the servicer under "
                "contract",
                "customer pre-approved and separately settled the freight cost outside the invoice "
                "cycle",
            ],
            "ambiguity_conditions": [
                "it is unclear whether this specific freight event was expedited/chargeable or "
                "routine",
            ],
            "false_positive_risks": [
                "routine restocking freight misclassified as job-specific expedited delivery",
            ],
            "causal_hypotheses": [
                "freight cost was paid through a general logistics account not linked to the job "
                "for billing purposes",
            ],
            "investigation_questions": [
                "Was this freight event expedited/chargeable per contract, or routine?",
                "Is the freight cost clearly attributable to this specific job?",
            ],
            "recovery_playbook": [
                "confirm freight chargeability and job attribution",
                "quantify the freight charge",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice referencing the freight/hotshot record"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the confirmed, job-attributable, contractually chargeable "
                "freight cost.",
            },
            "limitations": [
                "requires job-level attribution of freight cost, which is not always captured at "
                "point of shipment",
            ],
            "related_defect_codes": [],
            "family": "C",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["AP", "dispatch/logistics", "CLM/MSA", "ERP billing"],
            "correlation_fields": ["freight/hotshot record ID", "job ID", "vendor invoice ID"],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["AP", "dispatch/logistics", "CLM/MSA", "ERP billing"],
                "required_fields": ["freight/hotshot record ID", "job ID", "vendor invoice ID"],
                "scenario_concept": (
                    "Freight/hotshot delivery cost incurred for "
                    "a job but never invoiced to the customer."
                ),
                "clean_case_concept": (
                    "Freight cost incurred and correctly passed through per contract terms."
                ),
                "positive_case_concept": (
                    "Freight cost incurred, contract permits pass-through, not invoiced."
                ),
                "exclusion_case_concept": (
                    "Contract treats freight as a servicer-absorbed cost of doing business."
                ),
                "ambiguity_case_concept": (
                    "Freight/hotshot record cannot be tied to a specific job."
                ),
                "blocker_to_promotion": (
                    "shares its pass-through-eligibility shape with the already-Tier-1 "
                    "Third-Party Pass-Through pattern (J2C-OFS-20); "
                    "promotion should reuse that detector's structure "
                    "once a freight-specific fixture exists"
                ),
                "readiness": "READY_WITH_BOUNDED_FIXTURE_EXPANSION",
                "next_validation_action": "feasible; deprioritized vs. higher-value candidates",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-24",
        "name": "NPT vs. Standby Misclassification",
        "process_stage": "field_execution",
        "description": (
            "Downtime recorded in the daily drilling/morning report as non-productive time (NPT) "
            "should instead be classified and billed as contractual standby, or vice versa. "
            "NPT is not standby, and standby is not automatically billable."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "daily drilling report (DDR) or morning report event entry",
                "NPT/root-cause code assigned to the event",
                "field ticket hours for the same period",
                "governing contract's standby trigger and responsibility clause",
            ],
            "detection_preconditions": [
                "a DDR/morning-report event is coded as NPT with a root cause attributable to the "
                "customer (e.g. waiting on customer instruction, customer equipment, customer "
                "personnel)",
                "the contract defines a standby trigger for that root-cause category",
                "the event hours are not reflected as billed standby on the invoice",
            ],
            "exclusions": [
                "root cause is attributable to the servicer's own equipment or personnel",
                "event duration is below the contractual minimum standby-trigger threshold",
                "customer has an approved standby waiver in effect for this period",
            ],
            "ambiguity_conditions": [
                "root-cause coding on the DDR is missing, generic, or contested between customer "
                "and servicer",
                "responsibility for the downtime cause is disputed",
            ],
            "false_positive_risks": [
                "weather or force-majeure downtime that neither party is contractually responsible "
                "for",
                "planned operational downtime that is not standby under the contract at all",
            ],
            "causal_hypotheses": [
                "field crew defaulted to an NPT code rather than a standby code at time of entry",
                "billing system does not cross-reference DDR root-cause codes against the "
                "contract's standby trigger table",
            ],
            "investigation_questions": [
                "What is the documented root cause for this downtime, and who does the contract "
                "assign responsibility to?",
                "Does the event duration meet the contract's standby-trigger threshold?",
                "Is there a customer-approved waiver in effect for this period?",
            ],
            "recovery_playbook": [
                "confirm the DDR root-cause code and responsible party",
                "confirm the applicable standby trigger and threshold in the contract",
                "confirm no waiver is in effect",
                "reclassify and quantify the billable standby period",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "corrected DDR classification and supplemental invoice referencing the standby "
                "period",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "NPT is not standby, and standby is not automatically billable. Exposure "
                    "exists only where root cause is customer-attributable, the contractual "
                    "standby trigger and threshold are met, and no waiver applies."
                ),
            },
            "limitations": [
                "root-cause responsibility is frequently a matter of contractual/operational "
                "judgment; this pattern flags candidates for review, it does not itself adjudicate "
                "responsibility",
            ],
            "related_defect_codes": [],
            "family": "D",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["DDR / morning report", "field ticketing", "CLM/MSA", "ERP billing"],
            "service_families": ["pressure_pumping"],
            "correlation_fields": [
                "job/well ID",
                "event timestamp",
                "NPT code",
                "root-cause code",
                "standby hours",
                "contract trigger clause",
                "billed hours",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-24-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-24-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "d382d1fcbcfcfe62d08bcf611304a3929fd13760901d5e268249e32948ef7d64",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-25",
        "name": "Premature Tiered-Volume Discounting",
        "process_stage": "invoicing",
        "description": (
            "A customer's contractually tiered volume discount was applied before the customer's "
            "cumulative spend actually reached the qualifying threshold for that tier."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "contract's tiered-discount schedule",
                "customer cumulative spend record as of the invoice date",
                "invoice discount line item",
            ],
            "detection_preconditions": [
                "invoice reflects a discount tier",
                "customer's cumulative spend as of the invoice date is below that tier's "
                "qualifying threshold",
            ],
            "exclusions": [
                "tier was pre-approved for early application by an authorized commercial exception",
                "contract defines the tier on a forward-looking commitment basis rather than "
                "trailing spend",
            ],
            "ambiguity_conditions": [
                "it is unclear whether the tier schedule is trailing-spend-based or "
                "commitment-based",
            ],
            "false_positive_risks": [
                "multi-entity customer spend aggregation rules that are not reflected in the "
                "single-entity spend record being checked",
            ],
            "causal_hypotheses": [
                "billing system applies the customer's most recently negotiated tier by default "
                "rather than checking cumulative spend",
                "manual pricing override was applied without verifying threshold attainment",
            ],
            "investigation_questions": [
                "What does the contract's tier schedule actually require to qualify for this "
                "discount?",
                "Was there an approved exception authorizing early application?",
            ],
            "recovery_playbook": [
                "confirm the tier schedule and qualifying threshold",
                "confirm cumulative spend as of the invoice date",
                "confirm no approved exception applies",
                "approve billing correction",
                "create corrected invoice or debit memo for the discount overage",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["corrected invoice or debit memo reflecting the qualifying tier"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the discount overage between the tier actually applied and "
                "the tier the customer's cumulative spend actually qualifies for.",
            },
            "limitations": [
                "requires accurate, current cumulative-spend tracking at the contractually correct "
                "entity level",
            ],
            "related_defect_codes": [],
            "family": "D",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["ERP revenue", "CRM", "CLM/rate schedule"],
            "service_families": ["artificial_lift"],
            "correlation_fields": [
                "customer ID",
                "cumulative spend",
                "tier threshold",
                "effective date",
                "applied discount tier",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-25-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-25-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "d03a75087294ac48ca981b2e8c89bb79874f69fef194933d2db93f891291d711",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-26",
        "name": "Contractual Indexing / Escalation Missed",
        "process_stage": "contract_rate_validation",
        "description": (
            "The contract specifies a rate-escalation clause tied to a named index or schedule, "
            "but the escalation was never applied at the specified effective date."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "contract's escalation clause including the named index/source and effective "
                "cadence",
                "the index value at the relevant effective date",
                "rate actually billed on or after the effective date",
            ],
            "detection_preconditions": [
                "contract's escalation effective date has passed",
                "billed rate on or after that date does not reflect the contractually specified "
                "escalation",
            ],
            "exclusions": [
                "escalation was contractually deferred or waived by an approved amendment",
                "the named index was not published/available, and the contract specifies a "
                "fallback that was correctly applied instead",
            ],
            "ambiguity_conditions": [
                "the contract does not clearly specify which index source or version governs",
            ],
            "false_positive_risks": [
                "assuming a generic CPI or fuel-index escalation applies when the contract does "
                "not actually reference that index",
            ],
            "causal_hypotheses": [
                "no process exists to track contract escalation effective dates and trigger a rate "
                "update",
                "index value was not sourced at the effective date",
            ],
            "investigation_questions": [
                "Does the contract specify a named index/source for escalation, and what does it "
                "require at this effective date?",
                "Was an approved amendment deferring or waiving the escalation ever executed?",
            ],
            "recovery_playbook": [
                "confirm the escalation clause and its effective date",
                "source the correct index value",
                "confirm no waiver/deferral applies",
                "quantify the rate gap since the effective date",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["corrected rate schedule and supplemental invoice"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Exposure is the cumulative gap between the escalated contractual rate and the "
                    "rate actually billed since the effective date. Do not assume a generic "
                    "escalation basis without contract support."
                ),
            },
            "limitations": [
                "requires contract-specific index sourcing; cannot be generalized across "
                "contracts with different escalation clauses",
            ],
            "related_defect_codes": [],
            "family": "D",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": [
                "CLM/MSA",
                "rate book",
                "contract-specified index source",
                "ERP billing",
            ],
            "correlation_fields": [
                "contract ID",
                "base rate",
                "index clause",
                "effective date",
                "invoice date",
                "applied rate",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": [
                    "CLM/MSA",
                    "rate book",
                    "contract-specified index source",
                    "ERP billing",
                ],
                "required_fields": [
                    "contract ID",
                    "base rate",
                    "index clause",
                    "effective date",
                    "invoice date",
                    "applied rate",
                ],
                "scenario_concept": (
                    "A contract's index/escalation clause should have "
                    "raised the rate but the old rate persisted."
                ),
                "clean_case_concept": (
                    "Applied rate reflects the contractually "
                    "specified index as of the invoice date."
                ),
                "positive_case_concept": (
                    "Index clause is due to apply; invoice still reflects the prior, lower rate."
                ),
                "exclusion_case_concept": (
                    "Contract has no indexing/escalation clause for this rate line."
                ),
                "ambiguity_case_concept": (
                    "Index source data is unavailable for the relevant effective date."
                ),
                "blocker_to_promotion": (
                    "requires an authoritative contractual index-source fixture "
                    "-- explicitly, per pack doctrine, this must never assume "
                    "a generic CPI/fuel index without contract support, so "
                    "no generic fixture can substitute for a real clause"
                ),
                "readiness": "READY_WITH_BOUNDED_FIXTURE_EXPANSION",
                "next_validation_action": "needs an index/fallback fixture to avoid false flags",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-27",
        "name": "Scope Change / AFE Leakage Without Formal Change Order",
        "process_stage": "field_execution",
        "description": (
            "Job scope materially expanded relative to the original authorization for "
            "expenditure (AFE) or job order, but no formal change order was created to capture "
            "and bill the expanded scope."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "original job/AFE scope definition",
                "field records indicating expanded scope (additional line items, extended "
                "duration, added services)",
                "absence of a corresponding change order",
            ],
            "detection_preconditions": [
                "recorded field activity materially exceeds the original AFE/job scope",
                "no change order exists documenting the expansion",
            ],
            "exclusions": [
                "expansion is within a contractually pre-authorized scope-variance tolerance",
                "expansion was later formalized by a change order prior to invoicing",
            ],
            "ambiguity_conditions": [
                "it is unclear whether the additional activity constitutes a material scope "
                "expansion or normal execution variance",
            ],
            "false_positive_risks": [
                "activity that appears expanded but is actually within the original scope's "
                "described variance range",
            ],
            "causal_hypotheses": [
                "field execution outpaced the administrative change-order process",
                "no field-level trigger exists to flag scope expansion for change-order creation",
            ],
            "investigation_questions": [
                "Does the field record show activity beyond the original AFE/job scope?",
                "Should a change order have been created, and by whom?",
            ],
            "recovery_playbook": [
                "confirm the scope expansion against the original AFE/job order",
                "quantify the expanded scope",
                "approve retroactive change order",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["retroactive change order and supplemental invoice"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the value of the confirmed scope expansion not covered by a "
                "change order.",
            },
            "limitations": [
                "requires a clear, current AFE/job-scope baseline to detect expansion against",
            ],
            "related_defect_codes": ["unbilled_change_order"],
            "family": "D",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["AFE/change order system", "field ticketing", "ERP billing"],
            "correlation_fields": ["AFE/job order ID", "change order ID", "job/service order ID"],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["AFE/change order system", "field ticketing", "ERP billing"],
                "required_fields": ["AFE/job order ID", "change order ID", "job/service order ID"],
                "scenario_concept": (
                    "Job scope grew beyond the original AFE/order without a formal change order."
                ),
                "clean_case_concept": (
                    "Scope change captured via an approved change order before billing."
                ),
                "positive_case_concept": (
                    "Field evidence shows expanded scope; no change order exists."
                ),
                "exclusion_case_concept": (
                    "Scope variance is within the AFE's approved contingency allowance."
                ),
                "ambiguity_case_concept": (
                    "Whether the additional work was in- or out-of-original-scope is disputed."
                ),
                "blocker_to_promotion": (
                    "requires an AFE/change-order fixture distinct from the field-ticket-only "
                    "shape the golden dataset currently models"
                ),
                "readiness": "READY_WITH_BOUNDED_FIXTURE_EXPANSION",
                "next_validation_action": "needs an explicit scope-materiality-threshold fixture",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-28",
        "name": "SIMOPS / Site-Access Standdown",
        "process_stage": "field_execution",
        "description": (
            "Simultaneous-operations (SIMOPS) restrictions or a customer-directed site-access "
            "hold prevented crew/equipment from working, but the resulting hold time was not "
            "billed as standby. An operational stand-down is not automatically recoverable "
            "standby."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "JSA/site safety log or access-control record documenting the hold",
                "DDR/operations record spanning the hold period",
                "field ticket for the affected period",
                "contractual standby clause covering access holds",
            ],
            "detection_preconditions": [
                "a documented access hold or SIMOPS restriction exists for the job",
                "hold is attributable to the customer or site operator, not the servicer",
                "hold period is not reflected as billed standby",
            ],
            "exclusions": [
                "hold was caused by the servicer's own safety violation",
                "hold duration is below the contractual standby-trigger threshold",
                "hold is within a contractually non-billable standard access-control window",
            ],
            "ambiguity_conditions": [
                "responsibility for the SIMOPS/access restriction is not clearly documented",
            ],
            "false_positive_risks": [
                "routine, expected access-control procedures that are not standby-triggering under "
                "the contract",
            ],
            "causal_hypotheses": [
                "field crew logged the hold operationally but it was never routed to billing",
                "responsibility for the hold was never determined",
            ],
            "investigation_questions": [
                "Who was responsible for the access restriction or SIMOPS hold?",
                "Does the hold duration meet the contractual standby-trigger threshold?",
            ],
            "recovery_playbook": [
                "confirm the hold, its cause, and responsible party",
                "confirm contractual standby applicability",
                "quantify the billable hold period",
                "approve billing correction",
                "create supplemental invoice",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["supplemental invoice for the confirmed standby period"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "An operational stand-down is not automatically recoverable standby; "
                "Exposure exists only where responsibility, contractual trigger, and threshold "
                "are all confirmed.",
            },
            "limitations": [
                "responsibility determination for access holds is often contested and may require "
                "customer sign-off",
            ],
            "related_defect_codes": [],
            "family": "E",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": ["JSA/site safety", "DDR/operations", "field ticketing", "CLM/MSA"],
            "service_families": ["artificial_lift", "field_maintenance"],
            "correlation_fields": [
                "hold timestamp",
                "job/well ID",
                "responsible party",
                "access restriction ID",
                "standby clause",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-28-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-28-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 3,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "6d4548a203b8c424790bd195283aad1b7e136bcafcc03c2ea773076a4fcba481",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-29",
        "name": "Unauthorized Ticket Sign-Off",
        "process_stage": "evidence_capture",
        "description": (
            "A field ticket was signed off by a customer-site individual who does not appear in "
            "the customer's authorized-approver list, creating dispute risk on an otherwise "
            "billable ticket."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "ticket signature/approval record",
                "customer's authorized-approver list or delegation matrix",
            ],
            "detection_preconditions": [
                "ticket signature identity does not match any entry in the customer's authorized "
                "approver list",
            ],
            "exclusions": [
                "signer holds a valid, current delegation of authority not yet reflected in the "
                "approver list",
                "customer has a blanket-acceptance policy that supersedes named-approver "
                "requirements",
            ],
            "ambiguity_conditions": [
                "the customer's authorized-approver list is stale or was never formally "
                "established",
            ],
            "false_positive_risks": [
                "legitimate site personnel turnover not yet reflected administratively in the "
                "approver list",
            ],
            "causal_hypotheses": [
                "field crew obtained the most readily available signature rather than confirming "
                "authorization",
                "customer never provided or updated an authorized-approver list",
            ],
            "investigation_questions": [
                "Is the signer's authorization status confirmable through another channel (email, "
                "customer contact)?",
                "Has the customer's approver list been updated recently?",
            ],
            "recovery_playbook": [
                "confirm the signer's authorization status with the customer",
                "obtain ratification from an authorized approver if the signer was not authorized",
                "proceed to normal invoicing once ratified",
                "monitor payment",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "ratification record from an authorized approver, or confirmation of the "
                "original signer's authority",
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "This pattern flags dispute risk on an otherwise billable ticket; it does "
                "not itself establish that the work is unbillable.",
            },
            "limitations": [
                "highly dependent on the customer maintaining a current authorized-approver list",
            ],
            "related_defect_codes": [],
            "family": "E",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": [
                "signature/approval log",
                "CRM/customer contacts",
                "field ticketing",
            ],
            "correlation_fields": [
                "approver ID/email",
                "customer/company",
                "authorization threshold",
                "ticket ID",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": [
                    "signature/approval log",
                    "CRM/customer contacts",
                    "field ticketing",
                ],
                "required_fields": [
                    "approver ID/email",
                    "customer/company",
                    "authorization threshold",
                    "ticket ID",
                ],
                "scenario_concept": (
                    "A ticket is signed off by someone without authority to approve billable work."
                ),
                "clean_case_concept": (
                    "Signer matches an authorized approver on file for the customer."
                ),
                "positive_case_concept": (
                    "Signer is not on the customer's authorized-approver list."
                ),
                "exclusion_case_concept": (
                    "Verbal/emergency-authorization exception applies per contract."
                ),
                "ambiguity_case_concept": (
                    "Customer's authorized-approver list is stale or unavailable."
                ),
                "blocker_to_promotion": (
                    "requires a customer authorized-approver-list fixture, not "
                    "modeled in the current golden dataset's per-job shape"
                ),
                "readiness": "READY_NOW",
                "next_validation_action": "clean boolean check; deprioritized, no fixture needed",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-30",
        "name": "E-Invoicing Portal Rejection",
        "process_stage": "invoicing",
        "description": (
            "An invoice submitted through a customer e-invoicing portal was rejected (PO "
            "mismatch, missing document, threshold exceeded) and not resubmitted. A portal "
            "rejection is process blockage and exposure, not realized revenue loss."
        ),
        "provenance_type": "simulation",
        "content": {
            "required_evidence": [
                "e-invoicing portal submission record with rejection code",
                "PO reference and remaining PO balance/cap",
                "supporting ticket/document status required by the portal",
            ],
            "detection_preconditions": [
                "portal submission record shows a rejection code",
                "no successful resubmission exists within a configured resolution window",
            ],
            "exclusions": [
                "rejection was for a duplicate submission of an already-accepted invoice",
                "invoice was subsequently withdrawn because the underlying charge was invalid",
            ],
            "ambiguity_conditions": [
                "the rejection code is generic or undocumented by the portal, making the cause "
                "unclear",
            ],
            "false_positive_risks": [
                "treating the rejected invoice amount as a realized loss when it is, in fact, "
                "still collectible once resubmitted correctly",
            ],
            "causal_hypotheses": [
                "PO reference on the invoice does not match the customer's PO record",
                "PO cap/balance was exhausted before the invoice was submitted",
                "required supporting ticket/document was missing at submission time",
            ],
            "investigation_questions": [
                "What specific rejection code was returned, and what does it require to resolve?",
                "Is the referenced PO valid and does it have sufficient remaining balance?",
                "Is all required supporting documentation attached?",
            ],
            "recovery_playbook": [
                "identify the specific rejection cause from the portal code",
                "correct the PO reference, documentation, or amount as required",
                "approve the corrected invoice for resubmission",
                "resubmit through the portal",
                "monitor for acceptance",
                "record realized value once accepted",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["portal acceptance confirmation for the resubmitted invoice"],
            "value_basis": {
                "category": "CASH_ACCELERATION",
                "notes": (
                    "A portal rejection is process blockage and Exposure to delayed cash, not "
                    "Realized or Verified revenue loss -- the underlying charge typically remains "
                    "collectible once resubmitted correctly."
                ),
            },
            "limitations": [
                "portal rejection codes and resolution requirements vary by customer/portal and "
                "are not fully standardized",
            ],
            "related_defect_codes": [],
            "family": "F",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": [
                "ERP AR",
                "customer e-invoice portal",
                "PO",
                "field ticketing evidence",
            ],
            "service_families": ["artificial_lift"],
            "correlation_fields": [
                "invoice ID",
                "rejection code",
                "PO",
                "PO balance/cap",
                "supporting document status",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-30-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-30-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 1,
                    "false_positive": 0,
                    "true_negative": 120,
                    "false_negative": 0,
                    "exclusion_cases": 2,
                    "ambiguous_cases": 0,
                    "contaminated_cases": 1,
                },
                "score": 0.9833,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "34e7e5dec6c6d93f055f86f213166cc3f4889d19918912e2dcaa148386d23d96",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-31",
        "name": "Unearned Early-Payment Discount",
        "process_stage": "payment",
        "description": (
            "A customer took an early-payment discount on a remittance even though payment "
            "arrived after the contractual discount window closed."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "invoice date and contractual payment terms including discount window",
                "actual payment/remittance date",
                "discount amount taken on the remittance",
            ],
            "detection_preconditions": [
                "payment date is after the contractual early-payment discount window",
                "remittance reflects the discount amount as taken",
            ],
            "exclusions": [
                "customer terms were amended to extend the discount window and the amendment is on "
                "file",
                "discount was pre-approved as a goodwill exception",
            ],
            "ambiguity_conditions": [
                "payment date used for the check is the bank-received date rather than the "
                "contractually defined date (e.g. postmark date)",
            ],
            "false_positive_risks": [
                "processing/clearing delay between the customer's actual payment initiation date "
                "and the bank-recorded receipt date",
            ],
            "causal_hypotheses": [
                "AR system does not enforce the discount window at cash-application time",
                "customer self-calculates payment and takes the discount regardless of timing",
            ],
            "investigation_questions": [
                "What payment date does the contract use to determine discount eligibility?",
                "Is there an on-file amendment extending the discount window?",
            ],
            "recovery_playbook": [
                "confirm the contractual discount window and the payment date basis",
                "confirm no amendment or approved exception applies",
                "quantify the unearned discount",
                "approve billing action",
                "issue a debit memo or apply to the next invoice",
                "monitor collection",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "debit memo or corrected application referencing the unearned discount"
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "Exposure is the discount amount taken outside the contractually defined "
                "window.",
            },
            "limitations": [
                "depends on an unambiguous contractual definition of the payment date used for "
                "discount eligibility",
            ],
            "related_defect_codes": [],
            "family": "F",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["ERP AR", "bank/remittance", "CLM customer terms"],
            "correlation_fields": [
                "invoice date",
                "payment date",
                "discount window",
                "discount taken",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["ERP AR", "bank/remittance", "CLM customer terms"],
                "required_fields": [
                    "invoice date",
                    "payment date",
                    "discount window",
                    "discount taken",
                ],
                "scenario_concept": (
                    "Customer takes an early-payment discount "
                    "without paying inside the discount window."
                ),
                "clean_case_concept": (
                    "Discount taken only when payment date falls inside the contractual window."
                ),
                "positive_case_concept": (
                    "Discount taken despite payment landing after the window closed."
                ),
                "exclusion_case_concept": (
                    "Contract grants a grace period beyond the nominal discount window."
                ),
                "ambiguity_case_concept": (
                    "Payment date in the remittance feed conflicts with the bank-posted date."
                ),
                "blocker_to_promotion": (
                    "requires a bank/remittance fixture with reconciled payment-posting "
                    "dates, a data source not yet represented in the golden dataset"
                ),
                "readiness": "READY_NOW",
                "next_validation_action": "needs a postmark-vs-received-date fixture for ambiguity",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-32",
        "name": "Line-Item Short Pay",
        "process_stage": "payment",
        "description": (
            "A customer paid an invoice short of the billed amount, deducting one or more line "
            "items, and the deduction was never investigated, disputed, or resolved. A "
            "deduction is not automatically an invalid short pay."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "invoice line items and total",
                "remittance advice showing the deduction and any stated reason",
                "dispute/deduction-resolution record if one exists",
            ],
            "detection_preconditions": [
                "remittance amount is less than the invoice total",
                "no dispute-resolution record exists, or the deduction has remained open beyond a "
                "configured aging threshold",
            ],
            "exclusions": [
                "deduction matches an approved credit memo or agreed price adjustment",
                "deduction is a bank/processing rounding difference below a materiality threshold",
            ],
            "ambiguity_conditions": [
                "remittance advice does not state a reason for the deduction",
            ],
            "false_positive_risks": [
                "treating every deduction as invalid when the customer's stated reason may be "
                "legitimate (pricing error, duplicate billing, quality claim)",
            ],
            "causal_hypotheses": [
                "customer deducted for a disputed line item and the dispute was never routed to "
                "resolution",
                "short pay was not flagged at cash-application time and simply aged unresolved",
            ],
            "investigation_questions": [
                "What reason, if any, did the customer state for the deduction?",
                "Is the deduction valid per contract terms, or does it warrant dispute?",
                "How long has the deduction been outstanding?",
            ],
            "recovery_playbook": [
                "identify the deducted line item(s) and stated reason",
                "validate whether the deduction is contractually valid",
                "open a formal dispute for invalid deductions",
                "resolve dispute with the customer",
                "approve collection of the resolved amount or issuance of a credit",
                "collect the resolved amount or issue a credit as appropriate",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "dispute resolution record and, where applicable, supplemental collection"
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "A deduction is not automatically an invalid short pay; Exposure exists "
                "only for the portion determined, after investigation, to be contractually "
                "invalid.",
            },
            "limitations": [
                "requires timely remittance-advice capture with deduction reasons to investigate "
                "effectively",
            ],
            "related_defect_codes": [],
            "family": "F",
            "validation_tier": "tier_1_validated",
            "validation_status": "validated",
            "source_systems": [
                "ERP AR",
                "bank/remittance",
                "dispute/deduction system",
                "invoice lines",
            ],
            "service_families": ["field_maintenance"],
            "correlation_fields": [
                "invoice line",
                "remittance",
                "deduction amount",
                "dispute reason",
                "deduction age",
            ],
            "validation_evidence": {
                "scenario_id": "J2C-OFS-32-VALIDATION-001",
                "scenario_version": "1.0.0",
                "dataset_version": "p3.15-oilfield-golden-v2",
                "provenance": "simulation",
                "certification_run_id": "J2C-OFS-32-CERT-p3.15-oilfield-golden-v2",
                "metrics_summary": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "specificity": 1.0,
                    "false_positive_rate": 0.0,
                    "false_negative_rate": 0.0,
                    "exclusion_correctness": 1.0,
                    "ambiguity_handling_rate": 1.0,
                    "contamination_robustness": 1.0,
                },
                "case_counts": {
                    "true_positive": 2,
                    "false_positive": 0,
                    "true_negative": 119,
                    "false_negative": 0,
                    "exclusion_cases": 3,
                    "ambiguous_cases": 1,
                    "contaminated_cases": 1,
                },
                "score": 1.0,
                "passed": True,
                "replay_consistent": True,
                "evidence_hash": "978ab829a3d7f5909811bd22f9a57a7d25b72a9df8562d16cc03d8afd555256d",
                "related_platform_scenario": "J2C-OILFIELD-001",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-33",
        "name": "Unjustified Write-Off",
        "process_stage": "recovery",
        "description": (
            "An invoice or invoice line item was written off in the general ledger without a "
            "documented reason code or an approval consistent with the authorization matrix. A "
            "write-off is not automatically recoverable, but an undocumented one warrants "
            "review."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "write-off/adjustment record and its GL posting",
                "reason code (if any) and approval record",
                "authorization matrix defining who may approve write-offs at what amount",
            ],
            "detection_preconditions": [
                "a write-off record exists without a reason code, or with an approval below the "
                "authorization matrix's required level for the amount",
            ],
            "exclusions": [
                "write-off is a routine, small-dollar, policy-defined tolerance write-off",
                "write-off is properly documented and approved at the correct authority level",
            ],
            "ambiguity_conditions": [
                "the authorization matrix itself is out of date or does not clearly cover this "
                "write-off category",
            ],
            "false_positive_risks": [
                "legitimate write-offs where the reason code was recorded in a free-text field not "
                "captured by this review",
            ],
            "causal_hypotheses": [
                "write-off was processed as a year-end cleanup without individual review",
                "approval workflow was bypassed or not enforced in the GL system",
            ],
            "investigation_questions": [
                "Is there a documented business reason for this write-off?",
                "Was the write-off approved at the authority level the matrix requires for its "
                "amount?",
            ],
            "recovery_playbook": [
                "identify undocumented or under-approved write-offs",
                "determine whether the underlying invoice/line item is still collectible",
                "obtain retroactive documentation and approval, or reverse the write-off",
                "pursue collection where still valid and collectible",
                "record realized value where recovered",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": [
                "documented reason/approval on file, or reversal and successful collection"
            ],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": "A write-off is not automatically recoverable; Exposure exists only where "
                "the underlying invoice is confirmed still valid and collectible after review.",
            },
            "limitations": [
                "many legitimate write-offs are undocumented for operational-efficiency reasons; "
                "this pattern is a governance/review flag, not proof of recoverability",
            ],
            "related_defect_codes": ["credit_after_recovery"],
            "family": "F",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["AR adjustments", "credit memo", "GL", "approval workflow"],
            "correlation_fields": [
                "invoice",
                "adjustment ID",
                "write-off GL code",
                "approval authority",
                "reason code",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": ["AR adjustments", "credit memo", "GL", "approval workflow"],
                "required_fields": [
                    "invoice",
                    "adjustment ID",
                    "write-off GL code",
                    "approval authority",
                    "reason code",
                ],
                "scenario_concept": (
                    "An AR write-off is posted without approval commensurate with its amount."
                ),
                "clean_case_concept": (
                    "Write-off amount is within the posting approver's delegated authority."
                ),
                "positive_case_concept": (
                    "Write-off amount exceeds the posting approver's delegated authority."
                ),
                "exclusion_case_concept": (
                    "Write-off is a contractually pre-approved standing adjustment."
                ),
                "ambiguity_case_concept": (
                    "Approval-authority table does not cover the posting approver's role."
                ),
                "blocker_to_promotion": (
                    "requires a delegation-of-authority fixture (amount thresholds "
                    "per role), not modeled anywhere in the current dataset"
                ),
                "readiness": "READY_WITH_BOUNDED_FIXTURE_EXPANSION",
                "next_validation_action": "needs an authorization-matrix fixture (tier->approver)",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-34",
        "name": "Sales/Use Tax Misapplication",
        "process_stage": "invoicing",
        "description": (
            "A jurisdiction's sales/use tax rules were applied inconsistently with the job "
            "location and the customer's exemption status. This pattern is an investigation "
            "flag only; it is not tax advice and a tax difference is not automatically a "
            "recoverable error."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "job/site location and taxing jurisdiction",
                "customer exemption certificate status, if any",
                "tax amount and taxability flag applied on the invoice",
            ],
            "detection_preconditions": [
                "the taxability flag or rate applied on the invoice is inconsistent with the "
                "customer's on-file exemption status or the job location's jurisdiction rules as "
                "configured in the tax engine",
            ],
            "exclusions": [
                "difference is explained by a documented, current tax-engine jurisdiction rule not "
                "reflected in this review's reference data",
                "customer exemption certificate had expired or was not on file at invoice time",
            ],
            "ambiguity_conditions": [
                "jurisdiction rules for this specific service type are genuinely unsettled or "
                "recently changed",
            ],
            "false_positive_risks": [
                "flagging a correctly-applied, jurisdiction-specific tax treatment as an error due "
                "to incomplete reference data",
            ],
            "causal_hypotheses": [
                "customer exemption certificate was not updated in the billing system",
                "job location was miscoded to the wrong taxing jurisdiction",
            ],
            "investigation_questions": [
                "Does the customer have a current, on-file exemption certificate for this "
                "jurisdiction and service type?",
                "Is the job location correctly mapped to its taxing jurisdiction?",
            ],
            "recovery_playbook": [
                "flag the invoice for tax/finance team review",
                "confirm jurisdiction and exemption status with the tax function",
                "obtain tax/finance team approval before correcting the tax treatment",
                "correct the tax treatment prospectively once approved",
                "assess whether a prior-period correction is warranted, per tax guidance",
                "finance verification",
                "verified-value ledger posting where a corrected amount is realized",
            ],
            "closure_evidence": ["tax/finance team review record and any corrected invoice"],
            "value_basis": {
                "category": "COST_REDUCTION",
                "notes": (
                    "A tax difference is not automatically a recoverable error; this pattern is a "
                    "reference detection flag for the tax/finance function to investigate, not a "
                    "tax determination or tax advice."
                ),
            },
            "limitations": [
                "this pattern does not encode tax law or make tax determinations; all flagged "
                "cases require review by the tax/finance function",
            ],
            "related_defect_codes": [],
            "family": "F",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": [
                "tax engine",
                "ERP AR",
                "customer exemption certificates",
                "site/job location",
            ],
            "correlation_fields": [
                "jurisdiction",
                "taxability flag",
                "exemption status",
                "invoice date",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": [
                    "tax engine",
                    "ERP AR",
                    "customer exemption certificates",
                    "site/job location",
                ],
                "required_fields": [
                    "jurisdiction",
                    "taxability flag",
                    "exemption status",
                    "invoice date",
                ],
                "scenario_concept": (
                    "Sales/use tax applied does not match the job "
                    "location's jurisdiction and exemption status."
                ),
                "clean_case_concept": (
                    "Tax applied matches jurisdiction rules and any valid exemption certificate."
                ),
                "positive_case_concept": (
                    "Exemption certificate is on file and valid, but tax was charged anyway."
                ),
                "exclusion_case_concept": (
                    "Exemption certificate is expired as of the invoice date."
                ),
                "ambiguity_case_concept": (
                    "Job location spans a jurisdiction boundary with unclear tax authority."
                ),
                "blocker_to_promotion": (
                    "requires authoritative tax-jurisdiction/rule fixture "
                    "before executable validation is possible "
                    "-- this pattern must remain investigation/reference "
                    "only and must never encode tax advice"
                ),
                "readiness": "BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
                "next_validation_action": "requires a governed tax-jurisdiction rule source",
            },
        },
    },
    {
        "pattern_key": "J2C-OFS-35",
        "name": "Cross-Border FX Gap",
        "process_stage": "payment",
        "description": (
            "A cross-border invoice's realized proceeds differ from the contractual amount due "
            "to a currency conversion inconsistent with the contract's specified FX basis. "
            "Normal FX movement is not, by itself, leakage."
        ),
        "provenance_type": "manual",
        "content": {
            "required_evidence": [
                "contract's specified currency and FX-basis clause",
                "invoice currency and amount",
                "payment currency, amount, and conversion rate/date used",
            ],
            "detection_preconditions": [
                "the FX rate/date actually used to convert payment differs from the contract's "
                "specified FX basis (e.g. invoice-date rate vs. payment-date rate) by more than a "
                "configured tolerance",
            ],
            "exclusions": [
                "the contract does not specify an FX basis, and the FX movement is ordinary market "
                "movement between invoice and payment dates",
                "difference is within a contractually agreed FX tolerance band",
            ],
            "ambiguity_conditions": [
                "the contract's FX-basis clause is silent or ambiguous on which date's rate "
                "governs",
            ],
            "false_positive_risks": [
                "treating normal, contractually-permitted FX movement between invoice and payment "
                "dates as leakage",
            ],
            "causal_hypotheses": [
                "AR system applied the bank's settlement-date rate rather than the contractually "
                "specified rate/date",
                "no process exists to reconcile the applied FX rate against the contract clause",
            ],
            "investigation_questions": [
                "What does the contract specify as the governing FX basis, if anything?",
                "What rate and date was actually applied to the conversion?",
            ],
            "recovery_playbook": [
                "confirm the contract's FX-basis clause, if any",
                "confirm the rate/date actually applied",
                "quantify the gap against the contractual basis",
                "approve billing/collection correction where a genuine contractual gap exists",
                "collect or credit the difference as appropriate",
                "record realized value",
                "finance verification",
                "verified-value ledger posting",
            ],
            "closure_evidence": ["reconciliation record against the contractual FX basis"],
            "value_basis": {
                "category": "REVENUE_RECOVERY",
                "notes": (
                    "Normal FX movement is not leakage. Exposure exists only where the contract "
                    "specifies an FX basis and the actual conversion is inconsistent with it "
                    "beyond any agreed tolerance."
                ),
            },
            "limitations": [
                "only applicable where the contract specifies an FX basis; without one, this "
                "pattern cannot distinguish leakage from ordinary currency movement",
            ],
            "related_defect_codes": ["currency_mismatch"],
            "family": "F",
            "validation_tier": "tier_2_reference_specified",
            "validation_status": "reference_specified",
            "source_systems": ["CLM/MSA", "ERP billing", "contractual FX source", "payment/bank"],
            "correlation_fields": [
                "contract currency",
                "invoice currency",
                "invoice-date FX",
                "payment-date FX",
                "contractual FX clause",
            ],
            "validation_plan": {
                "status": "validation_planned",
                "required_systems": [
                    "CLM/MSA",
                    "ERP billing",
                    "contractual FX source",
                    "payment/bank",
                ],
                "required_fields": [
                    "contract currency",
                    "invoice currency",
                    "invoice-date FX",
                    "payment-date FX",
                    "contractual FX clause",
                ],
                "scenario_concept": (
                    "FX movement between invoice and payment dates "
                    "deviates from the contractual FX methodology."
                ),
                "clean_case_concept": (
                    "Applied FX rate matches the contract's specified FX source/timing."
                ),
                "positive_case_concept": (
                    "Applied FX rate deviates from the contractual source beyond a tolerance."
                ),
                "exclusion_case_concept": (
                    "Deviation is within normal contractual FX-source rounding."
                ),
                "ambiguity_case_concept": (
                    "Contract does not specify an authoritative FX source at all."
                ),
                "blocker_to_promotion": (
                    "requires an explicit contractual FX-clause fixture "
                    "and an authoritative rate source before executable "
                    "validation is possible -- normal FX movement "
                    "must never be treated as leakage by default"
                ),
                "readiness": "BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
                "next_validation_action": "requires an explicit FX-basis clause and rate source",
            },
        },
    },
)


PATTERN_FAMILIES: dict[str, str] = {
    "A": "Revenue Capture & Field Ticketing",
    "B": "Material & Asset",
    "C": "Third-Party & Logistics",
    "D": "Commercial & Contract",
    "E": "Field Operations",
    "F": "E-Invoicing & Cash",
}


# P3.13 normalization pass: every candidate concept the work order raised, mapped to its
# disposition. INCLUDED candidates appear in PATTERNS under final_pattern_key. MERGED
# candidates were folded into an existing pattern's content rather than duplicated as a
# separate pattern. DEFERRED candidates were consciously left out of v1.0/v1.1 scope to keep
# the portfolio at a defensible, non-duplicative 30-35 patterns rather than padding for count.
class NormalizationEntry(TypedDict):
    candidate: str
    final_pattern_key: str | None
    family: str | None
    tier: str | None
    disposition: str
    notes: str | None


NORMALIZATION_MATRIX: tuple[NormalizationEntry, ...] = (
    {
        "candidate": "COMPLETED_JOB_NOT_INVOICED",
        "final_pattern_key": "J2C-OFS-01",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "FIELD_TICKET_NOT_INVOICED",
        "final_pattern_key": "J2C-OFS-02",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "BILLABLE_LABOR_OMITTED",
        "final_pattern_key": "J2C-OFS-03",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "BILLABLE_EQUIPMENT_OMITTED",
        "final_pattern_key": "J2C-OFS-04",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "BILLABLE_MATERIAL_OMITTED",
        "final_pattern_key": "J2C-OFS-05",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "BILLABLE_STANDBY_OMITTED",
        "final_pattern_key": "J2C-OFS-06",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "MOB_DEMOB_CHARGE_OMITTED",
        "final_pattern_key": "J2C-OFS-07",
        "family": "C",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "CONTRACT_RATE_MISMATCH",
        "final_pattern_key": "J2C-OFS-08",
        "family": "D",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "UNAUTHORIZED_DISCOUNT_OR_CREDIT",
        "final_pattern_key": "J2C-OFS-09",
        "family": "D",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "INVOICE_DELAY_AFTER_COMPLETION",
        "final_pattern_key": "J2C-OFS-10",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12.",
    },
    {
        "candidate": "PAYMENT_BLOCKED_BY_DOCUMENTATION",
        "final_pattern_key": "J2C-OFS-11",
        "family": "F",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12 (originally 'Payment Delay -- Documentation Blocker').",
    },
    {
        "candidate": "JOB_MARGIN_EROSION",
        "final_pattern_key": "J2C-OFS-12",
        "family": "D",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Preserved from P3.12; composite commercial-economics pattern.",
    },
    {
        "candidate": "OUT_OF_SCOPE_ORAL_WORK",
        "final_pattern_key": "J2C-OFS-13",
        "family": "A",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "UNAUTHORIZED_TICKET_SIGNOFF",
        "final_pattern_key": "J2C-OFS-29",
        "family": "E",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Placed once, under Field Operations only, per the work order's explicit "
        "instruction not to duplicate it under Revenue Capture.",
    },
    {
        "candidate": "CUSTOMER_APPROVAL_NOT_CAPTURED",
        "final_pattern_key": "J2C-OFS-01",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "MERGED",
        "notes": "Already covered by Completed Job Not Invoiced's required_evidence/exclusions "
        "(customer approval/signature evidence); a standalone pattern would duplicate it.",
    },
    {
        "candidate": "MINIMUM_CHARGE_NOT_APPLIED",
        "final_pattern_key": "J2C-OFS-14",
        "family": "A",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Canonical home for this concept; MINIMUM_HOUR_MINIMUM_CHARGE_LEAKAGE (raised "
        "under Family D) is the same underlying leakage and was merged here.",
    },
    {
        "candidate": "MINIMUM_HOUR_MINIMUM_CHARGE_LEAKAGE",
        "final_pattern_key": "J2C-OFS-14",
        "family": "A",
        "tier": "tier_2_reference_specified",
        "disposition": "MERGED",
        "notes": "Same concept as MINIMUM_CHARGE_NOT_APPLIED; not duplicated as a separate "
        "pattern.",
    },
    {
        "candidate": "PARTIAL_TICKET_BILLING",
        "final_pattern_key": "J2C-OFS-15",
        "family": "A",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "JOB_REOPENED_AFTER_BILLING_MISMATCH",
        "final_pattern_key": None,
        "family": "A",
        "tier": None,
        "disposition": "DEFERRED",
        "notes": "Lower-frequency edge case relative to the other Family A gaps; deferred to "
        "keep the portfolio within the 30-35 target without padding.",
    },
    {
        "candidate": "LOSS_IN_HOLE_TOOL_DAMAGE",
        "final_pattern_key": "J2C-OFS-16",
        "family": "B",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Kept Tier 2: recoverability depends on a contract-specific liability "
        "determination that cannot be made deterministic without fabricating contractual "
        "certainty.",
    },
    {
        "candidate": "BULK_MATERIAL_SHRINKAGE_AND_TRANSFERS",
        "final_pattern_key": "J2C-OFS-17",
        "family": "B",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "EXTENDED_IDLE_ASSET_RENTAL",
        "final_pattern_key": "J2C-OFS-18",
        "family": "B",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "CUSTOMER_CHARGEABLE_TOOL_REPAIR_NOT_RECOVERED",
        "final_pattern_key": "J2C-OFS-19",
        "family": "B",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Distinct from usage-based equipment billing: this is repair-cost recovery, "
        "not usage/rate billing.",
    },
    {
        "candidate": "EQUIPMENT_USAGE_UNDER_BILLED",
        "final_pattern_key": "J2C-OFS-04",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "MERGED",
        "notes": "Same concept as the existing Billable Equipment Omitted pattern.",
    },
    {
        "candidate": "CONSUMABLE_USAGE_UNDER_BILLED",
        "final_pattern_key": "J2C-OFS-05",
        "family": "A",
        "tier": "tier_1_validated",
        "disposition": "MERGED",
        "notes": "Same concept as the existing Billable Material Omitted pattern.",
    },
    {
        "candidate": "THIRD_PARTY_PASS_THROUGH_RE_RENTAL",
        "final_pattern_key": "J2C-OFS-20",
        "family": "C",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Promoted to Tier 1: vendor-cost/PO/markup/customer-invoice-line correlation "
        "supports credible deterministic validation.",
    },
    {
        "candidate": "VENDOR_COST_CUSTOMER_PASS_THROUGH_MISSING",
        "final_pattern_key": "J2C-OFS-20",
        "family": "C",
        "tier": "tier_1_validated",
        "disposition": "MERGED",
        "notes": "Same underlying concept as THIRD_PARTY_PASS_THROUGH_RE_RENTAL.",
    },
    {
        "candidate": "TRAVEL_MOB_CAMP_ALLOWANCES",
        "final_pattern_key": "J2C-OFS-21",
        "family": "C",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "UNBILLED_DEMOB_DELAY",
        "final_pattern_key": "J2C-OFS-22",
        "family": "C",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Distinct from MOB_DEMOB_CHARGE_OMITTED (an omission at billing time): this is "
        "a delay-driven standby/extended-demob concept.",
    },
    {
        "candidate": "FREIGHT_HOTSHOT_CHARGE_OMITTED",
        "final_pattern_key": "J2C-OFS-23",
        "family": "C",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "NPT_VS_STANDBY_MISCLASSIFICATION",
        "final_pattern_key": "J2C-OFS-24",
        "family": "D",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Promoted to Tier 1: DDR root-cause code + contract standby trigger + "
        "threshold supports credible deterministic validation.",
    },
    {
        "candidate": "PREMATURE_TIERED_DISCOUNTING",
        "final_pattern_key": "J2C-OFS-25",
        "family": "D",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "CONTRACTUAL_INDEXING_ESCALATION_MISSED",
        "final_pattern_key": "J2C-OFS-26",
        "family": "D",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "EXPIRED_MSA_PRICING_SCHEDULE",
        "final_pattern_key": "J2C-OFS-08",
        "family": "D",
        "tier": "tier_1_validated",
        "disposition": "MERGED",
        "notes": "Treated as a specific causal variant of Contract Rate Mismatch rather than "
        "a separate pattern.",
    },
    {
        "candidate": "CHANGE_ORDER_AFE_SCOPE_LEAKAGE",
        "final_pattern_key": "J2C-OFS-27",
        "family": "D",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Canonical home for scope-creep-without-formal-change-order; "
        "OUT_OF_SCOPE_WORK_WITHOUT_CHANGE_ORDER was merged here.",
    },
    {
        "candidate": "OUT_OF_SCOPE_WORK_WITHOUT_CHANGE_ORDER",
        "final_pattern_key": "J2C-OFS-27",
        "family": "D",
        "tier": "tier_2_reference_specified",
        "disposition": "MERGED",
        "notes": "Same underlying concept as CHANGE_ORDER_AFE_SCOPE_LEAKAGE.",
    },
    {
        "candidate": "SIMOPS_ACCESS_STANDDOWN",
        "final_pattern_key": "J2C-OFS-28",
        "family": "E",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "EINVOICING_PORTAL_REJECTION",
        "final_pattern_key": "J2C-OFS-30",
        "family": "F",
        "tier": "tier_1_validated",
        "disposition": "INCLUDED",
        "notes": "Promoted to Tier 1: portal rejection-code/PO/document correlation supports "
        "credible deterministic validation.",
    },
    {
        "candidate": "UNEARNED_EARLY_PAYMENT_DISCOUNT",
        "final_pattern_key": "J2C-OFS-31",
        "family": "F",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "LINE_ITEM_SHORT_PAY",
        "final_pattern_key": "J2C-OFS-32",
        "family": "F",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "AGED_UNRESOLVED_DEDUCTION was merged here as its aging/escalation dimension.",
    },
    {
        "candidate": "AGED_UNRESOLVED_DEDUCTION",
        "final_pattern_key": "J2C-OFS-32",
        "family": "F",
        "tier": "tier_2_reference_specified",
        "disposition": "MERGED",
        "notes": "Same underlying concept as LINE_ITEM_SHORT_PAY.",
    },
    {
        "candidate": "UNJUSTIFIED_WRITE_OFF",
        "final_pattern_key": "J2C-OFS-33",
        "family": "F",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "SALES_USE_TAX_MISAPPLICATION",
        "final_pattern_key": "J2C-OFS-34",
        "family": "F",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": "Investigation/reference flag only; encodes no tax advice or determination.",
    },
    {
        "candidate": "CROSS_BORDER_FX_GAP",
        "final_pattern_key": "J2C-OFS-35",
        "family": "F",
        "tier": "tier_2_reference_specified",
        "disposition": "INCLUDED",
        "notes": None,
    },
    {
        "candidate": "PO_CAP_OR_PO_EXHAUSTION",
        "final_pattern_key": None,
        "family": "F",
        "tier": None,
        "disposition": "DEFERRED",
        "notes": "Already represented as a correlation field/rejection cause within "
        "E-Invoicing Portal Rejection; deferred as a standalone pattern to avoid overlap.",
    },
    {
        "candidate": "UNAPPLIED_CASH_CASH_APPLICATION_MISMATCH",
        "final_pattern_key": None,
        "family": "F",
        "tier": None,
        "disposition": "DEFERRED",
        "notes": "Lower-priority AR-operations concern relative to the other Family F gaps; "
        "deferred to keep the portfolio within the 30-35 target without padding.",
    },
)


# Representative cross-system correlation flows for a subset of patterns, declared as pack
# content (not a graph engine). Each entry documents which systems must be correlated, through
# which keys, to investigate the named pattern.
class CrossSystemFlow(TypedDict):
    pattern_key: str
    flow: tuple[str, ...]
    keys: tuple[str, ...]


CROSS_SYSTEM_INTELLIGENCE_MAP: tuple[CrossSystemFlow, ...] = (
    {
        "pattern_key": "J2C-OFS-24",
        "flow": ("DDR / Morning Report", "Field Ticket", "MSA", "Invoice"),
        "keys": (
            "job/well",
            "timestamp",
            "cause code",
            "standby hours",
            "contract trigger",
        ),
    },
    {
        "pattern_key": "J2C-OFS-20",
        "flow": ("AP", "PO", "Vendor Ticket", "MSA", "AR Invoice"),
        "keys": ("job", "PO", "vendor invoice", "markup %", "customer invoice line"),
    },
    {
        "pattern_key": "J2C-OFS-16",
        "flow": ("Field Ticket", "EAM", "Incident/DDR", "MSA", "Invoice"),
        "keys": ("asset", "job/well", "incident", "contract clause", "recovery value"),
    },
    {
        "pattern_key": "J2C-OFS-30",
        "flow": ("ERP AR", "Customer Portal", "PO", "Ticket/Evidence"),
        "keys": ("invoice ID", "rejection code", "PO", "supporting document"),
    },
)


def pattern_by_key(pattern_key: str) -> PatternDefinition:
    for pattern in PATTERNS:
        if pattern["pattern_key"] == pattern_key:
            return pattern
    raise KeyError(pattern_key)
