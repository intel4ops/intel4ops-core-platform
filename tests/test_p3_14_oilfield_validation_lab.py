"""P3.14 — Oilfield Services Validation Laboratory Integration.

Certifies the governed validation bridge (tests/oilfield_validation_lab.py)
that connects the P3.12/P3.13 Oilfield Services Job-to-Cash Knowledge Pack
to a bounded, deterministic scoring engine, and proves the static
validation_evidence/validation_plan content embedded on each pattern
(app/knowledge/oilfield_services_job_to_cash.py) has not drifted from what
the lab actually computes.
"""

from __future__ import annotations

from oilfield_j2c_golden_dataset import DETECTORS, GOLDEN_CASES
from oilfield_validation_lab import (
    ALL_EVIDENCE,
    TIER2_VALIDATION_PLANS,
    TIER_1_PATTERN_IDS,
    UNMAPPED_PATTERN_IDS,
    VALIDATION_COVERAGE_MATRIX,
    VALIDATION_THRESHOLDS,
    TruthClass,
    case_pattern_number,
    certify_pattern,
    score_pattern,
    truth_class_for,
)

from app.knowledge.oilfield_services_job_to_cash import PATTERNS

_PATTERN_BY_KEY = {p["pattern_key"]: p for p in PATTERNS}
_TIER1_KEYS = frozenset(TIER_1_PATTERN_IDS)
_TIER2_KEYS = frozenset(TIER2_VALIDATION_PLANS)


def test_coverage_matrix_contains_all_35_patterns() -> None:
    assert len(PATTERNS) == 35
    assert set(VALIDATION_COVERAGE_MATRIX) == set(_PATTERN_BY_KEY)
    assert len(VALIDATION_COVERAGE_MATRIX) == 35


def test_all_15_tier1_patterns_mapped_to_scenarios() -> None:
    assert len(_TIER1_KEYS) == 15
    for pattern_id in _TIER1_KEYS:
        row = VALIDATION_COVERAGE_MATRIX[pattern_id]
        assert row.tier == "tier_1_validated"
        assert len(row.scenario_ids) >= 1


def test_all_20_tier2_patterns_have_validation_plans() -> None:
    assert len(_TIER2_KEYS) == 20
    for pattern_id in _TIER2_KEYS:
        plan = TIER2_VALIDATION_PLANS[pattern_id]
        assert plan.required_systems
        assert plan.required_fields
        assert plan.scenario_concept
        assert plan.clean_case_concept
        assert plan.positive_case_concept
        assert plan.exclusion_case_concept
        assert plan.ambiguity_case_concept
        assert plan.blocker_to_promotion


def test_no_unmapped_patterns() -> None:
    assert UNMAPPED_PATTERN_IDS == ()


def test_tier2_never_reports_validated() -> None:
    for pattern_id in _TIER2_KEYS:
        row = VALIDATION_COVERAGE_MATRIX[pattern_id]
        assert row.validation_status == "validation_planned"
        assert row.last_certification_result is None
        content = _PATTERN_BY_KEY[pattern_id]["content"]
        plan = content["validation_plan"]
        assert plan["status"] == "validation_planned"
        false_claim_phrases = (
            "is validated",
            "production validated",
            "customer proven",
            "validated pattern",
        )
        for value in plan.values():
            if isinstance(value, str):
                lowered = value.lower()
                for phrase in false_claim_phrases:
                    assert phrase not in lowered, f"{pattern_id}: found false claim {phrase!r}"
                assert "production" not in lowered
                assert "precision" not in lowered
                assert "recall" not in value.lower()


def test_hidden_truth_separate_from_observed_data() -> None:
    for case in GOLDEN_CASES:
        assert "case_type" not in case.observed
        assert "expected_patterns" not in case.observed
        assert "truth_class" not in case.observed


def test_clean_cases_do_not_trigger_unexpectedly() -> None:
    clean_cases = [c for c in GOLDEN_CASES if c.case_type == "clean"]
    assert clean_cases
    for case in clean_cases:
        for pattern_id, detector in DETECTORS.items():
            assert not detector(case.observed), f"{pattern_id} misfired on {case.case_id}"


def test_positive_cases_detect_intended_leakage() -> None:
    leakage_cases = [c for c in GOLDEN_CASES if c.case_type == "leakage"]
    assert leakage_cases
    for case in leakage_cases:
        for pattern_id in case.expected_patterns:
            assert DETECTORS[pattern_id](case.observed), (
                f"{pattern_id} failed to detect {case.case_id}"
            )


def test_exclusions_suppress_false_positives() -> None:
    edge_cases = [c for c in GOLDEN_CASES if c.case_type == "edge"]
    assert edge_cases
    for case in edge_cases:
        owner = case_pattern_number(case)
        if owner is None or owner not in DETECTORS:
            continue
        assert not DETECTORS[owner](case.observed), (
            f"{owner} false-positived on exclusion case {case.case_id}"
        )


def test_ambiguous_cases_do_not_produce_unjustified_certainty() -> None:
    ambiguous_cases = [c for c in GOLDEN_CASES if c.case_type == "ambiguous"]
    assert ambiguous_cases
    for case in ambiguous_cases:
        owner = case_pattern_number(case)
        if owner is None or owner not in DETECTORS:
            continue
        assert not DETECTORS[owner](case.observed), (
            f"{owner} produced unjustified certainty on ambiguous case {case.case_id}"
        )


def test_contamination_handling() -> None:
    contaminated = [c for c in GOLDEN_CASES if c.case_type == "contaminated"]
    assert len(contaminated) == 15
    for case in contaminated:
        owner = case_pattern_number(case)
        assert owner in DETECTORS
        fired = DETECTORS[owner](case.observed)
        truth = truth_class_for(case, owner)
        expected_fire = truth is TruthClass.TRUE_LEAKAGE
        assert fired == expected_fire, (
            f"{owner} contamination case {case.case_id}: fired={fired}, expected={expected_fire}"
        )
        assert case.observed.get("data_quality_defect") is not None


def test_adversarial_lookalike_handling() -> None:
    """Edge cases ARE the adversarial-lookalike dimension: each satisfies an
    exclusion while otherwise resembling a positive case for its pattern."""
    edge_cases_by_pattern: dict[str, int] = {}
    for case in GOLDEN_CASES:
        if case.case_type != "edge":
            continue
        owner = case_pattern_number(case)
        if owner:
            edge_cases_by_pattern[owner] = edge_cases_by_pattern.get(owner, 0) + 1
    assert set(edge_cases_by_pattern) <= _TIER1_KEYS
    assert len(edge_cases_by_pattern) >= 12


def test_deterministic_replay() -> None:
    for pattern_id in _TIER1_KEYS:
        metrics_a = score_pattern(pattern_id)
        metrics_b = score_pattern(pattern_id)
        assert metrics_a == metrics_b
        assert metrics_a.replay_consistent
        evidence_a = certify_pattern(pattern_id)
        evidence_b = certify_pattern(pattern_id)
        assert evidence_a.evidence_hash == evidence_b.evidence_hash


def test_tp_fp_tn_fn_correctness() -> None:
    for pattern_id in _TIER1_KEYS:
        metrics = score_pattern(pattern_id)
        total = (
            metrics.true_positive
            + metrics.false_positive
            + metrics.true_negative
            + metrics.false_negative
        )
        assert total == len(GOLDEN_CASES)


def test_precision_calculation() -> None:
    for pattern_id in _TIER1_KEYS:
        metrics = score_pattern(pattern_id)
        assert metrics.precision >= VALIDATION_THRESHOLDS["precision_min"]


def test_recall_calculation() -> None:
    for pattern_id in _TIER1_KEYS:
        metrics = score_pattern(pattern_id)
        assert metrics.recall >= VALIDATION_THRESHOLDS["recall_min"]


def test_exclusion_correctness() -> None:
    for pattern_id in _TIER1_KEYS:
        metrics = score_pattern(pattern_id)
        assert metrics.exclusion_correctness >= VALIDATION_THRESHOLDS["exclusion_correctness_min"]


def test_evidence_completeness() -> None:
    for pattern_id in _TIER1_KEYS:
        metrics = score_pattern(pattern_id)
        assert 0.0 < metrics.evidence_completeness <= 1.0


def test_validation_provenance_is_simulation_reference() -> None:
    for pattern_id in _TIER1_KEYS:
        evidence = ALL_EVIDENCE[pattern_id]
        assert evidence.provenance == "simulation"
        content_evidence = _PATTERN_BY_KEY[pattern_id]["content"]["validation_evidence"]
        assert content_evidence["provenance"] == "simulation"


def test_no_production_validation_claim_anywhere() -> None:
    for pattern in PATTERNS:
        content = pattern["content"]
        for key in ("validation_evidence", "validation_plan"):
            payload = content.get(key)
            if payload is None:
                continue
            serialized = str(payload).lower()
            assert "production validated" not in serialized
            assert "customer proven" not in serialized
            assert "guaranteed" not in serialized


def test_scenario_and_version_traceability() -> None:
    for pattern_id in _TIER1_KEYS:
        evidence = _PATTERN_BY_KEY[pattern_id]["content"]["validation_evidence"]
        assert evidence["scenario_id"] == f"{pattern_id}-VALIDATION-001"
        assert evidence["scenario_version"]
        assert evidence["related_platform_scenario"] == "J2C-OILFIELD-001"


def test_dataset_version_traceability() -> None:
    versions = {
        _PATTERN_BY_KEY[pattern_id]["content"]["validation_evidence"]["dataset_version"]
        for pattern_id in _TIER1_KEYS
    }
    assert len(versions) == 1


def test_lih_adversarial_semantics() -> None:
    plan = TIER2_VALIDATION_PLANS["J2C-OFS-16"]
    text = (plan.scenario_concept + plan.blocker_to_promotion).lower()
    assert "asset value" in text or "liability" in text
    content = _PATTERN_BY_KEY["J2C-OFS-16"]["content"]
    assert "recover" in str(content["value_basis"]).lower()


def test_npt_standby_adversarial_semantics() -> None:
    npt_cases = [
        c for c in GOLDEN_CASES if case_pattern_number(c) == "J2C-OFS-24" and c.case_type == "edge"
    ]
    assert npt_cases
    for case in npt_cases:
        assert not DETECTORS["J2C-OFS-24"](case.observed)


def test_third_party_pass_through_adversarial_semantics() -> None:
    edge_cases = [
        c for c in GOLDEN_CASES if case_pattern_number(c) == "J2C-OFS-20" and c.case_type == "edge"
    ]
    assert edge_cases
    for case in edge_cases:
        assert not DETECTORS["J2C-OFS-20"](case.observed)


def test_portal_rejection_adversarial_semantics() -> None:
    edge_cases = [
        c for c in GOLDEN_CASES if case_pattern_number(c) == "J2C-OFS-30" and c.case_type == "edge"
    ]
    assert edge_cases
    for case in edge_cases:
        assert not DETECTORS["J2C-OFS-30"](case.observed)


def test_bundled_rate_exclusions() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "CLEAN-004")
    assert case.observed["rate_override_approved"] is True
    assert not DETECTORS["J2C-OFS-08"](case.observed)


def test_authorized_discount_exclusions() -> None:
    credit_reversal_cases = [
        c
        for c in GOLDEN_CASES
        if c.observed.get("credit_is_reversal_of_error") is True and c.case_type == "edge"
    ]
    for case in credit_reversal_cases:
        assert not DETECTORS["J2C-OFS-09"](case.observed)


def test_billing_grace_period_exclusions() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "EDGE-01-A")
    assert not DETECTORS["J2C-OFS-01"](case.observed)


def test_p3_13_regression_35_pattern_portfolio_unchanged() -> None:
    assert len(PATTERNS) == 35
    tier1 = [p for p in PATTERNS if p["content"]["validation_tier"] == "tier_1_validated"]
    tier2 = [p for p in PATTERNS if p["content"]["validation_tier"] != "tier_1_validated"]
    assert len(tier1) == 15
    assert len(tier2) == 20
    families = {p["content"]["family"] for p in PATTERNS}
    assert families == {"A", "B", "C", "D", "E", "F"}


def test_p3_12_regression_original_12_patterns_present() -> None:
    original_keys = {f"J2C-OFS-{n:02d}" for n in range(1, 13)}
    assert original_keys <= set(_PATTERN_BY_KEY)


def test_golden_dataset_remains_deterministic() -> None:
    from oilfield_j2c_golden_dataset import detect

    for case in GOLDEN_CASES:
        first = detect(case.observed)
        second = detect(case.observed)
        assert first == second
        assert first == frozenset(case.expected_patterns)
