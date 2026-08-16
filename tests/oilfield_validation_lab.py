"""Oilfield Services validation-laboratory bridge (P3.14).

Connects the governed Oilfield Services Job-to-Cash Knowledge Pack (P3.12/
P3.13) to a bounded, deterministic scoring engine so Tier 1 patterns can be
systematically challenged, scored, and certified -- and Tier 2 patterns have
an explicit, honest validation plan instead of a fabricated status.

This module is test-only infrastructure, mirroring the doctrine already
established for tests/oilfield_j2c_golden_dataset.py: pure predicates and
deterministic scoring over synthetic data, never wired into any API,
service, or production code path. It must never be imported from app/.

Layering (the P3.14 "governed validation bridge"):

    Knowledge Pack Pattern
        -> Validation Scenario      (ValidationScenario, one per Tier 1 pattern)
        -> Observed Inputs          (GoldenCase.observed, from the P3.12/13 dataset)
        -> Hidden Truth             (GoldenCase.case_type/expected_patterns -> TruthClass)
        -> Detection Result         (DETECTORS[pattern_id](observed))
        -> Scoring                  (score_pattern -> PatternMetrics)
        -> Certification Evidence   (certify_pattern -> CertificationEvidence)
        -> Pattern Validation Status (validation_status on PatternMetrics/evidence)

No existing precision/recall/TP-FP-FN scoring formula exists anywhere in the
platform (app/validation/suites.py's CertificationSuites are structural/
schema oracles -- tenant isolation, idempotency, resilience -- not per-record
detection scoring), so SCORING_WEIGHTS and VALIDATION_THRESHOLDS below are
the one new, authoritative policy location for this pack. Evidence hashing
reuses app.validation.certification.evidence_hash() rather than reinventing
it.

Doctrine (must not be blurred anywhere in this module or its outputs):
    Simulation != Production
    Hidden Truth != Observed Input
    Reference Pattern != Validated Pattern
    Validated in Simulation != Production Validated
    Detection != Root Cause Proof
    Precision/Recall != Business Value
    Pass != Universal Truth
    Certification Run != Customer Deployment
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from oilfield_j2c_golden_dataset import DETECTORS, GOLDEN_CASES, GoldenCase

from app.validation.certification import evidence_hash

DATASET_VERSION = "p3.15-oilfield-golden-v2"

TIER_1_PATTERN_IDS: tuple[str, ...] = tuple(sorted(DETECTORS))


class TruthClass(StrEnum):
    TRUE_LEAKAGE = "true_leakage"
    CLEAN = "clean"
    AMBIGUOUS = "ambiguous"
    EXCLUDED = "excluded"


_CASE_TYPE_TO_TRUTH_CLASS: dict[str, TruthClass] = {
    "leakage": TruthClass.TRUE_LEAKAGE,
    "clean": TruthClass.CLEAN,
    "edge": TruthClass.EXCLUDED,
    "ambiguous": TruthClass.AMBIGUOUS,
}


def truth_class_for(case: GoldenCase, pattern_id: str) -> TruthClass:
    """Hidden-truth classification for one case, from one pattern's point of view.

    Never derived from the case's `observed` dict -- always from case_type/
    expected_patterns, which a detector is never given.

    A "leakage" or "contaminated" case is only TRUE_LEAKAGE for the specific
    pattern(s) named in its expected_patterns -- e.g. LEAK-02-A is a positive
    case for J2C-OFS-02, but a legitimate negative (CLEAN) case when scoring
    every other pattern's detector, since CLEAN_BASE keeps their precondition
    fields quiescent.
    """
    if case.case_type in ("leakage", "contaminated"):
        is_leakage = pattern_id in case.expected_patterns
        return TruthClass.TRUE_LEAKAGE if is_leakage else TruthClass.CLEAN
    return _CASE_TYPE_TO_TRUTH_CLASS[case.case_type]


def case_pattern_number(case: GoldenCase) -> str | None:
    """The two-digit pattern number a scenario-specific case (edge/ambiguous/
    contaminated) was authored against, per the repository's own
    `{PREFIX}-{NN}-{LETTER}` case_id convention. Returns None for cases that
    are not associated with one specific pattern (the generic CLEAN-* cases).
    """
    prefix = case.case_id.split("-")[0]
    if prefix not in {"EDGE", "AMBIG", "CONTAM", "LEAK"}:
        return None
    number = case.case_id.split("-")[1]
    if not number.isdigit():
        # generic cross-pattern edge case (e.g. EDGE-ZERO-001, EDGE-BUNDLE-001),
        # not authored against one specific pattern
        return None
    return f"J2C-OFS-{number}"


@dataclass(frozen=True)
class PatternMetrics:
    pattern_id: str
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    exclusion_correct: int
    exclusion_total: int
    ambiguous_correct: int
    ambiguous_total: int
    contamination_correct: int
    contamination_total: int
    replay_consistent: bool

    @property
    def precision(self) -> float:
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom else 1.0

    @property
    def specificity(self) -> float:
        denom = self.true_negative + self.false_positive
        return self.true_negative / denom if denom else 1.0

    @property
    def false_positive_rate(self) -> float:
        return 1.0 - self.specificity

    @property
    def false_negative_rate(self) -> float:
        return 1.0 - self.recall

    @property
    def exclusion_correctness(self) -> float:
        return self.exclusion_correct / self.exclusion_total if self.exclusion_total else 1.0

    @property
    def ambiguity_handling_rate(self) -> float:
        return self.ambiguous_correct / self.ambiguous_total if self.ambiguous_total else 1.0

    @property
    def contamination_robustness(self) -> float:
        if not self.contamination_total:
            return 1.0
        return self.contamination_correct / self.contamination_total

    @property
    def evidence_completeness(self) -> float:
        """Fraction of the six case dimensions this pattern exercises at least once."""
        dimensions_present = sum(
            [
                self.true_positive + self.false_negative > 0,  # positive coverage
                self.true_negative > 0,  # clean coverage
                self.exclusion_total > 0,  # exclusion/edge coverage
                self.ambiguous_total > 0,  # ambiguity coverage
                self.contamination_total > 0,  # contamination coverage
                self.replay_consistent,  # deterministic replay
            ]
        )
        return dimensions_present / 6.0


def _score_case(detector: Any, case: GoldenCase, pattern_id: str) -> tuple[bool, TruthClass]:
    fired = bool(detector(case.observed))
    truth = truth_class_for(case, pattern_id)
    return fired, truth


def score_pattern(pattern_id: str) -> PatternMetrics:
    """Deterministically score one Tier 1 pattern's detector against the full
    golden dataset (all 74 cases -- other patterns' cases are legitimate
    true-negative opportunities, since each detector only reacts to its own
    precondition fields)."""
    detector = DETECTORS[pattern_id]
    tp = fp = tn = fn = 0
    excl_correct = excl_total = 0
    amb_correct = amb_total = 0
    contam_correct = contam_total = 0

    for case in GOLDEN_CASES:
        fired, truth = _score_case(detector, case, pattern_id)
        is_positive = truth is TruthClass.TRUE_LEAKAGE
        if fired and is_positive:
            tp += 1
        elif fired and not is_positive:
            fp += 1
        elif not fired and is_positive:
            fn += 1
        else:
            tn += 1

        owner = case_pattern_number(case)
        if owner != pattern_id:
            continue
        if case.case_type == "edge":
            excl_total += 1
            if not fired:
                excl_correct += 1
        elif case.case_type == "ambiguous":
            amb_total += 1
            if not fired:
                amb_correct += 1
        elif case.case_type == "contaminated":
            contam_total += 1
            if fired == is_positive:
                contam_correct += 1

    replay = all(
        bool(detector(case.observed)) == _score_case(detector, case, pattern_id)[0]
        for case in GOLDEN_CASES
    )

    return PatternMetrics(
        pattern_id=pattern_id,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        exclusion_correct=excl_correct,
        exclusion_total=excl_total,
        ambiguous_correct=amb_correct,
        ambiguous_total=amb_total,
        contamination_correct=contam_correct,
        contamination_total=contam_total,
        replay_consistent=replay,
    )


ALL_METRICS: dict[str, PatternMetrics] = {
    pattern_id: score_pattern(pattern_id) for pattern_id in TIER_1_PATTERN_IDS
}


# --------------------------------------------------------------------------
# Certification policy -- one authoritative location. No existing platform
# scoring formula was found to reuse (see module docstring), so this is a
# new, explicit, bounded policy rather than a second/conflicting score.
# --------------------------------------------------------------------------

SCORING_WEIGHTS: dict[str, float] = {
    "detection_accuracy": 0.30,
    "false_positive_control": 0.25,
    "false_negative_control": 0.20,
    "evidence_completeness": 0.10,
    "ambiguity_handling": 0.10,
    "deterministic_replay": 0.05,
}
assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-9

VALIDATION_THRESHOLDS: dict[str, float] = {
    "precision_min": 0.85,
    "recall_min": 0.85,
    "exclusion_correctness_min": 1.0,  # CRITICAL: no systematic false positive on exclusions
    "false_negative_on_required_positives": 0,  # CRITICAL: no missed leakage in positive cases
    "replay_consistency_required": 1.0,
    "hidden_truth_integrity_required": 1.0,
}


def certification_score(metrics: PatternMetrics) -> float:
    return (
        SCORING_WEIGHTS["detection_accuracy"] * metrics.recall
        + SCORING_WEIGHTS["false_positive_control"] * (1.0 - metrics.false_positive_rate)
        + SCORING_WEIGHTS["false_negative_control"] * (1.0 - metrics.false_negative_rate)
        + SCORING_WEIGHTS["evidence_completeness"] * metrics.evidence_completeness
        + SCORING_WEIGHTS["ambiguity_handling"] * metrics.ambiguity_handling_rate
        + SCORING_WEIGHTS["deterministic_replay"] * (1.0 if metrics.replay_consistent else 0.0)
    )


def pattern_passes(metrics: PatternMetrics) -> tuple[bool, tuple[str, ...]]:
    """Explicit pass/fail against VALIDATION_THRESHOLDS. Returns (passed, failed_reasons)."""
    reasons: list[str] = []
    if metrics.precision < VALIDATION_THRESHOLDS["precision_min"]:
        reasons.append(f"precision {metrics.precision:.3f} below threshold")
    if metrics.recall < VALIDATION_THRESHOLDS["recall_min"]:
        reasons.append(f"recall {metrics.recall:.3f} below threshold")
    if metrics.exclusion_correctness < VALIDATION_THRESHOLDS["exclusion_correctness_min"]:
        reasons.append("exclusion correctness below 100%: systematic false positive risk")
    if metrics.false_negative > VALIDATION_THRESHOLDS["false_negative_on_required_positives"]:
        reasons.append(f"{metrics.false_negative} false negative(s) on required positive cases")
    if not metrics.replay_consistent:
        reasons.append("deterministic replay inconsistent")
    return (not reasons, tuple(reasons))


@dataclass(frozen=True)
class ValidationScenario:
    scenario_id: str
    name: str
    industry: str
    domain: str
    service_family: str
    description: str
    pattern_ids: tuple[str, ...]
    scenario_version: str
    dataset_version: str
    contamination_profile: tuple[str, ...]
    provenance: str
    related_platform_scenario: str


def _scenario_for(pattern_id: str, case_count: int) -> ValidationScenario:
    contam_defects = tuple(
        sorted(
            {
                str(case.observed.get("data_quality_defect"))
                for case in GOLDEN_CASES
                if case.case_type == "contaminated" and case_pattern_number(case) == pattern_id
            }
        )
    )
    return ValidationScenario(
        scenario_id=f"{pattern_id}-VALIDATION-001",
        name=f"{pattern_id} synthetic validation scenario",
        industry="oilfield_services",
        domain="job_to_cash",
        service_family="oilfield_leakage_intelligence",
        description=(
            f"Deterministic clean/positive/exclusion/ambiguous/contaminated case set "
            f"for {pattern_id}, drawn from the shared P3.12/P3.13/P3.14 golden dataset "
            f"({case_count} cases exercise this pattern's detector)."
        ),
        pattern_ids=(pattern_id,),
        scenario_version="1.0.0",
        dataset_version=DATASET_VERSION,
        contamination_profile=contam_defects,
        provenance="simulation",
        related_platform_scenario="J2C-OILFIELD-001",
    )


VALIDATION_SCENARIOS: dict[str, ValidationScenario] = {
    pattern_id: _scenario_for(
        pattern_id,
        sum(1 for case in GOLDEN_CASES if case_pattern_number(case) == pattern_id)
        + sum(
            1
            for case in GOLDEN_CASES
            if case.case_type == "leakage" and pattern_id in case.expected_patterns
        ),
    )
    for pattern_id in TIER_1_PATTERN_IDS
}


@dataclass(frozen=True)
class CertificationEvidence:
    certification_run_id: str
    scenario_id: str
    scenario_version: str
    dataset_version: str
    pattern_id: str
    provenance: str
    metrics_summary: dict[str, float]
    score: float
    passed: bool
    failed_reasons: tuple[str, ...]
    case_counts: dict[str, int]
    replay_consistent: bool
    evidence_hash: str


def certify_pattern(pattern_id: str) -> CertificationEvidence:
    metrics = ALL_METRICS[pattern_id]
    passed, reasons = pattern_passes(metrics)
    scenario = VALIDATION_SCENARIOS[pattern_id]
    metrics_summary = {
        "precision": round(metrics.precision, 4),
        "recall": round(metrics.recall, 4),
        "specificity": round(metrics.specificity, 4),
        "false_positive_rate": round(metrics.false_positive_rate, 4),
        "false_negative_rate": round(metrics.false_negative_rate, 4),
        "exclusion_correctness": round(metrics.exclusion_correctness, 4),
        "ambiguity_handling_rate": round(metrics.ambiguity_handling_rate, 4),
        "contamination_robustness": round(metrics.contamination_robustness, 4),
    }
    case_counts = {
        "true_positive": metrics.true_positive,
        "false_positive": metrics.false_positive,
        "true_negative": metrics.true_negative,
        "false_negative": metrics.false_negative,
        "exclusion_cases": metrics.exclusion_total,
        "ambiguous_cases": metrics.ambiguous_total,
        "contaminated_cases": metrics.contamination_total,
    }
    payload = {
        "scenario_id": scenario.scenario_id,
        "dataset_version": scenario.dataset_version,
        "pattern_id": pattern_id,
        "metrics_summary": metrics_summary,
        "case_counts": case_counts,
    }
    return CertificationEvidence(
        certification_run_id=f"{pattern_id}-CERT-{DATASET_VERSION}",
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        dataset_version=scenario.dataset_version,
        pattern_id=pattern_id,
        provenance="simulation",
        metrics_summary=metrics_summary,
        score=round(certification_score(metrics), 4),
        passed=passed,
        failed_reasons=reasons,
        case_counts=case_counts,
        replay_consistent=metrics.replay_consistent,
        evidence_hash=evidence_hash(payload),
    )


ALL_EVIDENCE: dict[str, CertificationEvidence] = {
    pattern_id: certify_pattern(pattern_id) for pattern_id in TIER_1_PATTERN_IDS
}


# --------------------------------------------------------------------------
# Tier 2 validation plans -- 20 patterns, no executable coverage yet.
# Blockers are explicit and truthful; nothing here claims validated status.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Tier2ValidationPlan:
    pattern_id: str
    required_systems: tuple[str, ...]
    required_fields: tuple[str, ...]
    scenario_concept: str
    clean_case_concept: str
    positive_case_concept: str
    exclusion_case_concept: str
    ambiguity_case_concept: str
    blocker_to_promotion: str
    readiness: str = "DEFERRED"
    next_validation_action: str = ""


@dataclass(frozen=True)
class ReadinessAssessment:
    pattern_id: str
    readiness: str
    assessment: str


TIER2_READINESS_ASSESSMENT: dict[str, ReadinessAssessment] = {
    "J2C-OFS-13": ReadinessAssessment(
        pattern_id="J2C-OFS-13",
        readiness="BLOCKED_UNSAFE_TO_AUTOMATE",
        assessment="requires free-text crew-log interpretation; no structured source.",
    ),
    "J2C-OFS-14": ReadinessAssessment(
        pattern_id="J2C-OFS-14",
        readiness="READY_NOW",
        assessment="promoted to Tier 1 in P3.15.",
    ),
    "J2C-OFS-15": ReadinessAssessment(
        pattern_id="J2C-OFS-15",
        readiness="READY_NOW",
        assessment="promoted to Tier 1 in P3.15.",
    ),
    "J2C-OFS-16": ReadinessAssessment(
        pattern_id="J2C-OFS-16",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="promoted to Tier 1 in P3.15; detector never reads asset value alone.",
    ),
    "J2C-OFS-17": ReadinessAssessment(
        pattern_id="J2C-OFS-17",
        readiness="DEFERRED",
        assessment="needs a dedicated transfer/return fixture family; high FP risk.",
    ),
    "J2C-OFS-18": ReadinessAssessment(
        pattern_id="J2C-OFS-18",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="promoted to Tier 1 in P3.15, with an unreliable-telemetry abstention path.",
    ),
    "J2C-OFS-19": ReadinessAssessment(
        pattern_id="J2C-OFS-19",
        readiness="DEFERRED",
        assessment="near-duplicate of J2C-OFS-16; revisit once it matures further.",
    ),
    "J2C-OFS-21": ReadinessAssessment(
        pattern_id="J2C-OFS-21",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="needs a billable-travel-radius/zone fixture, not a boolean flag.",
    ),
    "J2C-OFS-22": ReadinessAssessment(
        pattern_id="J2C-OFS-22",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="promoted to Tier 1 in P3.15.",
    ),
    "J2C-OFS-23": ReadinessAssessment(
        pattern_id="J2C-OFS-23",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="detector feasible; deprioritized this round vs. higher-value ones.",
    ),
    "J2C-OFS-25": ReadinessAssessment(
        pattern_id="J2C-OFS-25",
        readiness="READY_NOW",
        assessment="promoted to Tier 1 in P3.15.",
    ),
    "J2C-OFS-26": ReadinessAssessment(
        pattern_id="J2C-OFS-26",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="needs an index-source/fallback fixture so fallback isn't flagged.",
    ),
    "J2C-OFS-27": ReadinessAssessment(
        pattern_id="J2C-OFS-27",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="needs an explicit scope-materiality-threshold fixture first.",
    ),
    "J2C-OFS-28": ReadinessAssessment(
        pattern_id="J2C-OFS-28",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="promoted to Tier 1 in P3.15.",
    ),
    "J2C-OFS-29": ReadinessAssessment(
        pattern_id="J2C-OFS-29",
        readiness="READY_NOW",
        assessment="single clean boolean check; deprioritized this round, no fixture.",
    ),
    "J2C-OFS-31": ReadinessAssessment(
        pattern_id="J2C-OFS-31",
        readiness="READY_NOW",
        assessment="needs a postmark-vs-bank-received-date fixture for its ambiguity.",
    ),
    "J2C-OFS-32": ReadinessAssessment(
        pattern_id="J2C-OFS-32",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="promoted to Tier 1 in P3.15.",
    ),
    "J2C-OFS-33": ReadinessAssessment(
        pattern_id="J2C-OFS-33",
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        assessment="needs an authorization-matrix fixture (amount tier -> approver).",
    ),
    "J2C-OFS-34": ReadinessAssessment(
        pattern_id="J2C-OFS-34",
        readiness="BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
        assessment="requires a governed tax-jurisdiction rule source; no invented tax.",
    ),
    "J2C-OFS-35": ReadinessAssessment(
        pattern_id="J2C-OFS-35",
        readiness="BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
        assessment="requires an explicit contract FX-basis clause and rate source.",
    ),
}


TIER2_VALIDATION_PLANS: dict[str, Tier2ValidationPlan] = {
    "J2C-OFS-13": Tier2ValidationPlan(
        pattern_id="J2C-OFS-13",
        required_systems=("dispatch/crew log", "field ticketing", "change order/CLM"),
        required_fields=("job/service order ID", "crew log entry", "change order ID"),
        scenario_concept="Verbally-authorized field work with no ticket ever opened.",
        clean_case_concept="Crew log entry exists and a matching ticket was opened same-shift.",
        positive_case_concept="Crew log shows hours worked; no ticket exists for that window.",
        exclusion_case_concept="Work was pre-work (setup) time explicitly excluded from billing.",
        ambiguity_case_concept="Crew log entry lacks a clear job/service order reference.",
        blocker_to_promotion=(
            "requires a synthetic crew-log/dispatch data source distinct from the existing "
            "field-ticket-centric golden dataset before a credible detector can be written"
        ),
        readiness="BLOCKED_UNSAFE_TO_AUTOMATE",
        next_validation_action="requires free-text crew-log interpretation; no structured source.",
    ),
    "J2C-OFS-17": Tier2ValidationPlan(
        pattern_id="J2C-OFS-17",
        required_systems=("inventory/ERP", "field ticketing", "warehouse transfer log"),
        required_fields=(
            "SKU",
            "job/well ID",
            "issued qty",
            "transferred qty",
            "consumed qty",
            "billed qty",
        ),
        scenario_concept=(
            "Bulk material issued/transferred quantities do not reconcile to billed quantities."
        ),
        clean_case_concept=(
            "Issued, transferred, consumed, and billed quantities reconcile within tolerance."
        ),
        positive_case_concept=(
            "Consumed quantity exceeds billed quantity beyond the customer-billable threshold."
        ),
        exclusion_case_concept=(
            "Variance is within normal operational shrinkage tolerance for the material class."
        ),
        ambiguity_case_concept=(
            "Transfer log has gaps that prevent a clean issued-to-consumed reconciliation."
        ),
        blocker_to_promotion=(
            "requires a clear, contract-sourced distinction between operational shrinkage "
            "tolerance and customer-billable quantity, not yet represented as a fixture"
        ),
        readiness="DEFERRED",
        next_validation_action="needs a dedicated transfer/return fixture family; high FP risk.",
    ),
    "J2C-OFS-19": Tier2ValidationPlan(
        pattern_id="J2C-OFS-19",
        required_systems=(
            "EAM / asset management",
            "repair shop work order",
            "CLM/MSA",
            "ERP billing",
        ),
        required_fields=("asset ID", "repair work order ID", "job/well ID", "damage cause code"),
        scenario_concept=(
            "Customer-caused tool damage generates a repair work order not billed to the customer."
        ),
        clean_case_concept=(
            "Repair work order exists, damage cause is company-caused; correctly not billed."
        ),
        positive_case_concept=(
            "Repair work order exists, damage cause is customer-attributable; not billed."
        ),
        exclusion_case_concept="Damage is within normal wear-and-tear, contractually non-billable.",
        ambiguity_case_concept="Damage cause code is missing or unresolved.",
        blocker_to_promotion=(
            "requires an authoritative damage-cause-code taxonomy shared with Loss-in-Hole "
            "(J2C-OFS-16) before both can be validated without cross-pattern ambiguity"
        ),
        readiness="DEFERRED",
        next_validation_action="near-duplicate of J2C-OFS-16; revisit once it matures further.",
    ),
    "J2C-OFS-21": Tier2ValidationPlan(
        pattern_id="J2C-OFS-21",
        required_systems=("fleet/GPS", "expense management", "crew roster", "CLM/MSA"),
        required_fields=(
            "job/well ID",
            "employee/crew ID",
            "mileage",
            "travel dates",
            "per-diem rate",
        ),
        scenario_concept=(
            "Contractually billable travel/camp/per-diem allowances not reflected on the invoice."
        ),
        clean_case_concept=(
            "Travel/camp days billed matches crew roster and contractual per-diem rate."
        ),
        positive_case_concept=(
            "Crew roster shows travel/camp days not reflected on any invoice line."
        ),
        exclusion_case_concept="Travel policy caps per-diem below what was informally claimed.",
        ambiguity_case_concept="Crew roster and expense system disagree on travel-day count.",
        blocker_to_promotion=(
            "requires expense-management and crew-roster fixtures, systems not yet "
            "represented anywhere in the current golden dataset"
        ),
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        next_validation_action="needs a billable-travel-radius/zone fixture, not a boolean flag.",
    ),
    "J2C-OFS-23": Tier2ValidationPlan(
        pattern_id="J2C-OFS-23",
        required_systems=("AP", "dispatch/logistics", "CLM/MSA", "ERP billing"),
        required_fields=("freight/hotshot record ID", "job ID", "vendor invoice ID"),
        scenario_concept=(
            "Freight/hotshot delivery cost incurred for a job but never invoiced to the customer."
        ),
        clean_case_concept="Freight cost incurred and correctly passed through per contract terms.",
        positive_case_concept="Freight cost incurred, contract permits pass-through, not invoiced.",
        exclusion_case_concept=(
            "Contract treats freight as a servicer-absorbed cost of doing business."
        ),
        ambiguity_case_concept="Freight/hotshot record cannot be tied to a specific job.",
        blocker_to_promotion=(
            "shares its pass-through-eligibility shape with the already-Tier-1 Third-Party "
            "Pass-Through pattern (J2C-OFS-20); promotion should reuse that detector's "
            "structure once a freight-specific fixture exists"
        ),
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        next_validation_action="detector feasible; deprioritized this round vs. higher-value ones.",
    ),
    "J2C-OFS-26": Tier2ValidationPlan(
        pattern_id="J2C-OFS-26",
        required_systems=("CLM/MSA", "rate book", "contract-specified index source", "ERP billing"),
        required_fields=(
            "contract ID",
            "base rate",
            "index clause",
            "effective date",
            "invoice date",
            "applied rate",
        ),
        scenario_concept=(
            "A contract's index/escalation clause should have "
            "raised the rate but the old rate persisted."
        ),
        clean_case_concept=(
            "Applied rate reflects the contractually specified index as of the invoice date."
        ),
        positive_case_concept=(
            "Index clause is due to apply; invoice still reflects the prior, lower rate."
        ),
        exclusion_case_concept="Contract has no indexing/escalation clause for this rate line.",
        ambiguity_case_concept="Index source data is unavailable for the relevant effective date.",
        blocker_to_promotion=(
            "requires an authoritative contractual index-source fixture -- explicitly, "
            "per pack doctrine, this must never assume a generic CPI/fuel index without "
            "contract support, so no generic fixture can substitute for a real clause"
        ),
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        next_validation_action="needs an index-source/fallback fixture so fallback isn't flagged.",
    ),
    "J2C-OFS-27": Tier2ValidationPlan(
        pattern_id="J2C-OFS-27",
        required_systems=("AFE/change order system", "field ticketing", "ERP billing"),
        required_fields=("AFE/job order ID", "change order ID", "job/service order ID"),
        scenario_concept=(
            "Job scope grew beyond the original AFE/order without a formal change order."
        ),
        clean_case_concept="Scope change captured via an approved change order before billing.",
        positive_case_concept="Field evidence shows expanded scope; no change order exists.",
        exclusion_case_concept="Scope variance is within the AFE's approved contingency allowance.",
        ambiguity_case_concept=(
            "Whether the additional work was in- or out-of-original-scope is disputed."
        ),
        blocker_to_promotion=(
            "requires an AFE/change-order fixture distinct from the field-ticket-only "
            "shape the golden dataset currently models"
        ),
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        next_validation_action="needs an explicit scope-materiality-threshold fixture first.",
    ),
    "J2C-OFS-29": Tier2ValidationPlan(
        pattern_id="J2C-OFS-29",
        required_systems=("signature/approval log", "CRM/customer contacts", "field ticketing"),
        required_fields=(
            "approver ID/email",
            "customer/company",
            "authorization threshold",
            "ticket ID",
        ),
        scenario_concept=(
            "A ticket is signed off by someone without authority to approve billable work."
        ),
        clean_case_concept="Signer matches an authorized approver on file for the customer.",
        positive_case_concept="Signer is not on the customer's authorized-approver list.",
        exclusion_case_concept="Verbal/emergency-authorization exception applies per contract.",
        ambiguity_case_concept="Customer's authorized-approver list is stale or unavailable.",
        blocker_to_promotion=(
            "requires a customer authorized-approver-list fixture, not modeled in the "
            "current golden dataset's per-job shape"
        ),
        readiness="READY_NOW",
        next_validation_action="single clean boolean check; deprioritized this round, no fixture.",
    ),
    "J2C-OFS-31": Tier2ValidationPlan(
        pattern_id="J2C-OFS-31",
        required_systems=("ERP AR", "bank/remittance", "CLM customer terms"),
        required_fields=("invoice date", "payment date", "discount window", "discount taken"),
        scenario_concept=(
            "Customer takes an early-payment discount without paying inside the discount window."
        ),
        clean_case_concept=(
            "Discount taken only when payment date falls inside the contractual window."
        ),
        positive_case_concept="Discount taken despite payment landing after the window closed.",
        exclusion_case_concept="Contract grants a grace period beyond the nominal discount window.",
        ambiguity_case_concept=(
            "Payment date in the remittance feed conflicts with the bank-posted date."
        ),
        blocker_to_promotion=(
            "requires a bank/remittance fixture with reconciled payment-posting dates, "
            "a data source not yet represented in the golden dataset"
        ),
        readiness="READY_NOW",
        next_validation_action="needs a postmark-vs-bank-received-date fixture for its ambiguity.",
    ),
    "J2C-OFS-33": Tier2ValidationPlan(
        pattern_id="J2C-OFS-33",
        required_systems=("AR adjustments", "credit memo", "GL", "approval workflow"),
        required_fields=(
            "invoice",
            "adjustment ID",
            "write-off GL code",
            "approval authority",
            "reason code",
        ),
        scenario_concept="An AR write-off is posted without approval commensurate with its amount.",
        clean_case_concept="Write-off amount is within the posting approver's delegated authority.",
        positive_case_concept=(
            "Write-off amount exceeds the posting approver's delegated authority."
        ),
        exclusion_case_concept="Write-off is a contractually pre-approved standing adjustment.",
        ambiguity_case_concept=(
            "Approval-authority table does not cover the posting approver's role."
        ),
        blocker_to_promotion=(
            "requires a delegation-of-authority fixture (amount thresholds per role), "
            "not modeled anywhere in the current dataset"
        ),
        readiness="READY_WITH_BOUNDED_FIXTURE_EXPANSION",
        next_validation_action="needs an authorization-matrix fixture (amount tier -> approver).",
    ),
    "J2C-OFS-34": Tier2ValidationPlan(
        pattern_id="J2C-OFS-34",
        required_systems=(
            "tax engine",
            "ERP AR",
            "customer exemption certificates",
            "site/job location",
        ),
        required_fields=("jurisdiction", "taxability flag", "exemption status", "invoice date"),
        scenario_concept=(
            "Sales/use tax applied does not match the job "
            "location's jurisdiction and exemption status."
        ),
        clean_case_concept=(
            "Tax applied matches jurisdiction rules and any valid exemption certificate."
        ),
        positive_case_concept=(
            "Exemption certificate is on file and valid, but tax was charged anyway."
        ),
        exclusion_case_concept="Exemption certificate is expired as of the invoice date.",
        ambiguity_case_concept=(
            "Job location spans a jurisdiction boundary with unclear tax authority."
        ),
        blocker_to_promotion=(
            "requires authoritative tax-jurisdiction/rule fixture before executable "
            "validation is possible -- this pattern must remain investigation/reference "
            "only and must never encode tax advice"
        ),
        readiness="BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
        next_validation_action="requires a governed tax-jurisdiction rule source; no invented tax.",
    ),
    "J2C-OFS-35": Tier2ValidationPlan(
        pattern_id="J2C-OFS-35",
        required_systems=("CLM/MSA", "ERP billing", "contractual FX source", "payment/bank"),
        required_fields=(
            "contract currency",
            "invoice currency",
            "invoice-date FX",
            "payment-date FX",
            "contractual FX clause",
        ),
        scenario_concept=(
            "FX movement between invoice and payment dates "
            "deviates from the contractual FX methodology."
        ),
        clean_case_concept="Applied FX rate matches the contract's specified FX source/timing.",
        positive_case_concept=(
            "Applied FX rate deviates from the contractual source beyond a tolerance."
        ),
        exclusion_case_concept="Deviation is within normal contractual FX-source rounding.",
        ambiguity_case_concept="Contract does not specify an authoritative FX source at all.",
        blocker_to_promotion=(
            "requires an explicit contractual FX-clause fixture and an authoritative rate "
            "source before executable validation is possible -- normal FX movement must "
            "never be treated as leakage by default"
        ),
        readiness="BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
        next_validation_action="requires an explicit contract FX-basis clause and rate source.",
    ),
}


# --------------------------------------------------------------------------
# Coverage matrix -- all 35 patterns, derivable/renderable without a graph
# engine. Built from ALL_EVIDENCE (Tier 1) and TIER2_VALIDATION_PLANS
# (Tier 2); intentionally does not require importing app.knowledge to avoid
# a test-module -> app-module -> content coupling beyond what's needed.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageRow:
    pattern_id: str
    tier: str
    scenario_ids: tuple[str, ...]
    clean_cases: int
    positive_cases: int
    exclusion_cases: int
    ambiguous_cases: int
    contamination_cases: int
    validation_status: str
    last_certification_result: str | None


def _tier1_coverage_row(pattern_id: str) -> CoverageRow:
    evidence = ALL_EVIDENCE[pattern_id]
    scenario = VALIDATION_SCENARIOS[pattern_id]
    return CoverageRow(
        pattern_id=pattern_id,
        tier="tier_1_validated",
        scenario_ids=(scenario.scenario_id,),
        clean_cases=evidence.case_counts["true_negative"],
        positive_cases=evidence.case_counts["true_positive"]
        + evidence.case_counts["false_negative"],
        exclusion_cases=evidence.case_counts["exclusion_cases"],
        ambiguous_cases=evidence.case_counts["ambiguous_cases"],
        contamination_cases=evidence.case_counts["contaminated_cases"],
        validation_status="validated" if evidence.passed else "validation_failed",
        last_certification_result="pass" if evidence.passed else "fail",
    )


def _tier2_coverage_row(pattern_id: str) -> CoverageRow:
    return CoverageRow(
        pattern_id=pattern_id,
        tier="tier_2_reference_specified",
        scenario_ids=(),
        clean_cases=0,
        positive_cases=0,
        exclusion_cases=0,
        ambiguous_cases=0,
        contamination_cases=0,
        validation_status="validation_planned",
        last_certification_result=None,
    )


VALIDATION_COVERAGE_MATRIX: dict[str, CoverageRow] = {
    **{pattern_id: _tier1_coverage_row(pattern_id) for pattern_id in TIER_1_PATTERN_IDS},
    **{pattern_id: _tier2_coverage_row(pattern_id) for pattern_id in TIER2_VALIDATION_PLANS},
}

UNMAPPED_PATTERN_IDS: tuple[str, ...] = tuple(
    f"J2C-OFS-{n:02d}" for n in range(1, 36) if f"J2C-OFS-{n:02d}" not in VALIDATION_COVERAGE_MATRIX
)
