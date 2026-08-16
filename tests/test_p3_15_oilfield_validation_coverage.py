"""P3.15: Oilfield Services Validation Coverage Expansion.

Certifies the evidence-gated Tier 2 -> Tier 1 promotions, the expanded
Failure Lab (contamination + matching-key adversarial cases), and the
readiness matrix covering all 20 original Tier 2 patterns. Reuses the
P3.14 validation-lab scoring/threshold policy verbatim -- no second
scoring formula.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from oilfield_j2c_golden_dataset import DETECTORS, GOLDEN_CASES  # noqa: E402
from oilfield_validation_lab import (  # noqa: E402
    ALL_EVIDENCE,
    TIER2_READINESS_ASSESSMENT,
    TIER2_VALIDATION_PLANS,
    TIER_1_PATTERN_IDS,
    VALIDATION_COVERAGE_MATRIX,
    case_pattern_number,
    pattern_passes,
    score_pattern,
)

from app.knowledge.oilfield_services_job_to_cash import PATTERNS

_PATTERN_BY_KEY = {p["pattern_key"]: p for p in PATTERNS}
_ORIGINAL_TWELVE = {f"J2C-OFS-{n:02d}" for n in range(1, 13)}
_P313_PROMOTED = {"J2C-OFS-20", "J2C-OFS-24", "J2C-OFS-30"}
_P315_PROMOTED = {
    "J2C-OFS-14",
    "J2C-OFS-15",
    "J2C-OFS-16",
    "J2C-OFS-18",
    "J2C-OFS-22",
    "J2C-OFS-25",
    "J2C-OFS-28",
    "J2C-OFS-32",
}
_ORIGINAL_TWENTY_TIER2 = {f"J2C-OFS-{n:02d}" for n in range(13, 36)} - _P313_PROMOTED
_VALID_READINESS = {
    "READY_NOW",
    "READY_WITH_BOUNDED_FIXTURE_EXPANSION",
    "BLOCKED_AUTHORITATIVE_RULE_REQUIRED",
    "BLOCKED_UNSAFE_TO_AUTOMATE",
    "DEFERRED",
}


def test_all_35_patterns_remain_represented() -> None:
    assert len(PATTERNS) == 35
    assert set(_PATTERN_BY_KEY) == {f"J2C-OFS-{n:02d}" for n in range(1, 36)}


def test_original_15_tier1_are_reevaluated() -> None:
    original_fifteen = _ORIGINAL_TWELVE | _P313_PROMOTED
    for pattern_id in original_fifteen:
        metrics = score_pattern(pattern_id)
        passed, reasons = pattern_passes(metrics)
        assert passed, (pattern_id, reasons, "existing Tier 1 pattern regressed under P3.15")


def test_readiness_matrix_covers_all_20_original_tier2_patterns() -> None:
    assert set(TIER2_READINESS_ASSESSMENT) == _ORIGINAL_TWENTY_TIER2
    for pattern_id, assessment in TIER2_READINESS_ASSESSMENT.items():
        assert assessment.readiness in _VALID_READINESS, pattern_id
        assert assessment.assessment, pattern_id


def test_only_evidence_supported_patterns_were_promoted() -> None:
    for pattern_id in _P315_PROMOTED:
        assert pattern_id in TIER_1_PATTERN_IDS
        assert pattern_id in DETECTORS
        metrics = score_pattern(pattern_id)
        passed, reasons = pattern_passes(metrics)
        assert passed, (pattern_id, reasons)
        # every promoted pattern's readiness record is READY_*, never BLOCKED/DEFERRED
        assessment = TIER2_READINESS_ASSESSMENT[pattern_id]
        assert assessment.readiness in {"READY_NOW", "READY_WITH_BOUNDED_FIXTURE_EXPANSION"}


def test_promotions_have_multiple_case_classes() -> None:
    for pattern_id in _P315_PROMOTED:
        cases_for_pattern = [c for c in GOLDEN_CASES if case_pattern_number(c) == pattern_id]
        case_types = {c.case_type for c in cases_for_pattern}
        # every promotion has at least clean(implicit)+leakage+edge+ambiguous+contaminated
        assert {"leakage", "edge", "ambiguous", "contaminated"} <= case_types, pattern_id
        leakage_count = sum(1 for c in cases_for_pattern if c.case_type == "leakage")
        assert leakage_count >= 1, pattern_id


def test_clean_case_correctness_for_promotions() -> None:
    clean_cases = [c for c in GOLDEN_CASES if c.case_type == "clean"]
    for pattern_id in _P315_PROMOTED:
        for case in clean_cases:
            assert not DETECTORS[pattern_id](case.observed), (pattern_id, case.case_id)


def test_positive_case_correctness_for_promotions() -> None:
    for pattern_id in _P315_PROMOTED:
        positives = [
            c
            for c in GOLDEN_CASES
            if c.case_type == "leakage" and pattern_id in c.expected_patterns
        ]
        assert positives, pattern_id
        for case in positives:
            assert DETECTORS[pattern_id](case.observed), (pattern_id, case.case_id)


def test_exclusion_correctness_for_promotions() -> None:
    for pattern_id in _P315_PROMOTED:
        exclusions = [
            c
            for c in GOLDEN_CASES
            if case_pattern_number(c) == pattern_id and c.case_type == "edge"
        ]
        assert exclusions, pattern_id
        for case in exclusions:
            assert not DETECTORS[pattern_id](case.observed), (pattern_id, case.case_id)


def test_ambiguity_handling_for_promotions() -> None:
    for pattern_id in _P315_PROMOTED:
        ambiguous = [
            c
            for c in GOLDEN_CASES
            if case_pattern_number(c) == pattern_id and c.case_type == "ambiguous"
        ]
        assert ambiguous, pattern_id
        for case in ambiguous:
            assert not DETECTORS[pattern_id](case.observed), (
                pattern_id,
                case.case_id,
                "ambiguous case produced unjustified certainty",
            )


def test_contamination_handling_for_promotions() -> None:
    for pattern_id in _P315_PROMOTED:
        contaminated = [
            c
            for c in GOLDEN_CASES
            if case_pattern_number(c) == pattern_id and c.case_type == "contaminated"
        ]
        assert contaminated, pattern_id
        for case in contaminated:
            expected_fire = pattern_id in case.expected_patterns
            assert DETECTORS[pattern_id](case.observed) == expected_fire, (pattern_id, case.case_id)


def test_matching_key_adversarial_cases_exist_and_are_handled() -> None:
    adv_key_cases = [c for c in GOLDEN_CASES if c.case_id.startswith("ADV-KEY-")]
    assert len(adv_key_cases) >= 4
    for case in adv_key_cases:
        assert case.case_type == "edge"
        assert case.expected_patterns == ()
        assert "data_quality_defect" in case.observed
        # no detector should fire on a pure matching-key artifact layered onto
        # otherwise-clean/correctly-billed data
        for pattern_id, detector in DETECTORS.items():
            assert not detector(case.observed), (pattern_id, case.case_id)


def test_duplicate_key_behavior() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "ADV-KEY-01-A")
    assert case.observed["data_quality_defect"] == "duplicate_po_reused_across_jobs"
    assert not DETECTORS["J2C-OFS-01"](case.observed)


def test_wrong_key_mapping_behavior() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "ADV-KEY-04-A")
    assert case.observed["data_quality_defect"] == "asset_alias_mid_job"
    assert not DETECTORS["J2C-OFS-04"](case.observed)


def test_stale_superseded_key_behavior() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "ADV-KEY-20-A")
    assert case.observed["data_quality_defect"] == "superseded_po_version_reference"
    assert not DETECTORS["J2C-OFS-20"](case.observed)


def test_cross_system_matching_customer_alias() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "ADV-KEY-08-A")
    assert case.observed["data_quality_defect"] == "customer_alias_merged_account"
    assert not DETECTORS["J2C-OFS-08"](case.observed)


def test_deterministic_replay_for_all_tier1() -> None:
    for pattern_id in TIER_1_PATTERN_IDS:
        assert score_pattern(pattern_id).replay_consistent, pattern_id


def test_scoring_correctness_matches_p314_policy() -> None:
    # No competing/second scoring formula: every certification's metrics_summary
    # must come from the same PatternMetrics computed by score_pattern().
    for pattern_id in TIER_1_PATTERN_IDS:
        evidence = ALL_EVIDENCE[pattern_id]
        metrics = score_pattern(pattern_id)
        assert evidence.metrics_summary["precision"] == round(metrics.precision, 4)
        assert evidence.metrics_summary["recall"] == round(metrics.recall, 4)


def test_evidence_completeness_for_promotions() -> None:
    for pattern_id in _P315_PROMOTED:
        metrics = score_pattern(pattern_id)
        assert metrics.evidence_completeness == 1.0, pattern_id


def test_precision_recall_fp_fn_rates_are_bounded() -> None:
    for pattern_id in TIER_1_PATTERN_IDS:
        metrics = score_pattern(pattern_id)
        assert 0.0 <= metrics.precision <= 1.0
        assert 0.0 <= metrics.recall <= 1.0
        assert 0.0 <= metrics.false_positive_rate <= 1.0
        assert 0.0 <= metrics.false_negative_rate <= 1.0


def test_existing_tier1_failure_lab_regression() -> None:
    # The original 15 Tier 1 patterns must survive the P3.15-expanded Failure
    # Lab (new contamination + matching-key adversarial cases added on top of
    # the existing dataset), not just their original P3.14 case set.
    original_fifteen = _ORIGINAL_TWELVE | _P313_PROMOTED
    regressions = [pid for pid in original_fifteen if not pattern_passes(score_pattern(pid))[0]]
    assert regressions == [], f"validation regression(s) found: {regressions}"


def test_honest_validation_regression_would_be_reported_not_hidden() -> None:
    # No pattern's certification evidence is hand-overridden to force `passed`
    # True independent of its actual computed metrics -- evidence always
    # equals what score_pattern()/pattern_passes() compute.
    for pattern_id in TIER_1_PATTERN_IDS:
        evidence = ALL_EVIDENCE[pattern_id]
        metrics = score_pattern(pattern_id)
        passed, _ = pattern_passes(metrics)
        assert evidence.passed == passed, pattern_id


def test_remaining_tier2_blockers_are_actionable() -> None:
    assert set(TIER2_VALIDATION_PLANS) == (_ORIGINAL_TWENTY_TIER2 - _P315_PROMOTED)
    for pattern_id, plan in TIER2_VALIDATION_PLANS.items():
        assert plan.readiness in _VALID_READINESS, pattern_id
        assert plan.next_validation_action, pattern_id
        assert plan.blocker_to_promotion, pattern_id


def test_remaining_tier2_never_claims_validated() -> None:
    for pattern_id in TIER2_VALIDATION_PLANS:
        content = _PATTERN_BY_KEY[pattern_id]["content"]
        assert content["validation_status"] == "reference_specified", pattern_id
        assert content["validation_tier"] == "tier_2_reference_specified", pattern_id
        assert "validation_evidence" not in content, pattern_id


def test_coverage_matrix_reflects_current_split() -> None:
    tier1_rows = [r for r in VALIDATION_COVERAGE_MATRIX.values() if r.tier == "tier_1_validated"]
    tier2_rows = [
        r for r in VALIDATION_COVERAGE_MATRIX.values() if r.tier == "tier_2_reference_specified"
    ]
    assert len(tier1_rows) == 23
    assert len(tier2_rows) == 12
    assert len(VALIDATION_COVERAGE_MATRIX) == 35


def test_no_production_validation_claims_anywhere() -> None:
    forbidden = ("production validated", "customer proven", "production-proven")
    for pattern in PATTERNS:
        content = pattern["content"]
        haystacks = [
            str(content.get("validation_evidence", {})),
            str(content.get("validation_plan", {})),
        ]
        for haystack in haystacks:
            lowered = haystack.lower()
            for phrase in forbidden:
                assert phrase not in lowered, (pattern["pattern_key"], phrase)


def test_dataset_version_bumped_and_consistent() -> None:
    versions = {
        _PATTERN_BY_KEY[pid]["content"]["validation_evidence"]["dataset_version"]
        for pid in TIER_1_PATTERN_IDS
    }
    assert versions == {"p3.15-oilfield-golden-v2"}


def test_coverage_scale_increased_meaningfully() -> None:
    # 74 (P3.14) -> materially more, without becoming a padded/repetitive set.
    assert len(GOLDEN_CASES) > 74
    case_ids = [c.case_id for c in GOLDEN_CASES]
    assert len(case_ids) == len(set(case_ids))


def test_no_perfect_score_gaming_via_case_diversity() -> None:
    # Every promoted pattern's case set spans at least 4 distinct dimensions
    # (positive/exclusion/ambiguous/contaminated) rather than one trivial
    # positive fixture engineered to trivially score 1.0.
    for pattern_id in _P315_PROMOTED:
        metrics = score_pattern(pattern_id)
        assert metrics.true_positive >= 1
        assert metrics.exclusion_total >= 2
        assert metrics.ambiguous_total >= 1
        assert metrics.contamination_total >= 1


def test_lih_promotion_never_reads_asset_value_field() -> None:
    import inspect

    from oilfield_j2c_golden_dataset import detect_loss_in_hole_tool_damage

    source = inspect.getsource(detect_loss_in_hole_tool_damage)
    assert "asset_value" not in source
    assert "book_value" not in source
    assert "replacement_value" not in source


def test_idle_asset_rental_abstains_on_unreliable_telemetry() -> None:
    case = next(c for c in GOLDEN_CASES if c.case_id == "AMBIG-18-A")
    assert case.observed["asset_telemetry_unreliable"] is True
    assert not DETECTORS["J2C-OFS-18"](case.observed)


def test_p3_14_regression() -> None:
    for pattern_id in {"J2C-OFS-20", "J2C-OFS-24", "J2C-OFS-30"}:
        assert pattern_id in TIER_1_PATTERN_IDS
        assert pattern_passes(score_pattern(pattern_id))[0]


def test_p3_13_regression_family_taxonomy_unchanged() -> None:
    families = {p["content"]["family"] for p in PATTERNS}
    assert families == {"A", "B", "C", "D", "E", "F"}


def test_p3_12_regression_original_twelve_present() -> None:
    assert _ORIGINAL_TWELVE <= set(_PATTERN_BY_KEY)


def test_p3_11_regression_knowledge_pack_module_importable() -> None:
    from app.services.knowledge_pack_service import knowledge_pack_service

    assert knowledge_pack_service is not None


def test_p3_10_regression_operational_learning_module_importable() -> None:
    from app.models.learning import PROVENANCE_TYPES

    assert PROVENANCE_TYPES == ("production", "simulation", "manual", "mixed")


def test_p3_09_08_07_regression_value_semantics_vocabulary_reused() -> None:
    valid_categories = {
        "REVENUE_RECOVERY",
        "COST_REDUCTION",
        "CASH_ACCELERATION",
        "MARGIN_PROTECTION",
    }
    for pattern in PATTERNS:
        assert pattern["content"]["value_basis"]["category"] in valid_categories


_SERVICE_FAMILY_TAXONOMY = {
    "equipment_rental",
    "pressure_pumping",
    "wireline_coiled_tubing",
    "field_maintenance",
    "artificial_lift",
}


def test_service_family_coverage_declared_for_all_tier1_patterns() -> None:
    for pattern_id in TIER_1_PATTERN_IDS:
        families = _PATTERN_BY_KEY[pattern_id]["content"]["service_families"]
        assert families, pattern_id
        assert set(families) <= _SERVICE_FAMILY_TAXONOMY, pattern_id


def test_service_family_coverage_spans_at_least_three_contexts() -> None:
    represented = {
        family
        for pattern_id in TIER_1_PATTERN_IDS
        for family in _PATTERN_BY_KEY[pattern_id]["content"]["service_families"]
    }
    assert len(represented) >= 3


def test_remaining_tier2_validation_plans_carry_readiness_in_pack_content() -> None:
    # The readiness classification is visible in the actual Knowledge Pack
    # content (not just the test-only validation lab), so the frontend/API
    # can render it.
    for pattern_id in TIER2_VALIDATION_PLANS:
        plan = _PATTERN_BY_KEY[pattern_id]["content"]["validation_plan"]
        assert plan["readiness"] in _VALID_READINESS, pattern_id
        assert plan["next_validation_action"], pattern_id
