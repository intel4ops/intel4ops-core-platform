"""P3.13: Oilfield Services Leakage Intelligence expansion.

Focused tests for the P3.13-specific additions on top of the P3.12 pack:
family/tier classification, the normalization matrix, the cross-system
intelligence map, and the pattern-specific economic semantic safeguards the
work order called out by name (LIH, material shrinkage, NPT/standby,
third-party pass-through, portal rejection, short-pay/write-off, tax, FX).

P3.11/P3.10/P3.09/P3.08/P3.07 regressions and the original P3.12 12-pattern
regressions are certified by running their own existing test files
(tests/test_p3_11_knowledge_packs.py, tests/test_p3_10_operational_learning.py,
tests/test_p3_09_recovery_portfolio.py, tests/test_p3_08_recovery_workspace.py,
tests/test_p3_07a_decision_workspace.py, tests/test_p3_12_oilfield_pack.py),
not duplicated here.
"""

from oilfield_j2c_golden_dataset import GOLDEN_CASES, detect

from app.knowledge.oilfield_services_job_to_cash import (
    CROSS_SYSTEM_INTELLIGENCE_MAP,
    NORMALIZATION_MATRIX,
    PATTERN_FAMILIES,
    PATTERNS,
    PatternContent,
    pattern_by_key,
)

_VALID_FAMILIES = set(PATTERN_FAMILIES)
_VALID_TIERS = {"tier_1_validated", "tier_2_reference_specified"}
_VALID_STATUSES = {"validated", "reference_specified"}
_FORBIDDEN_CERTAINTY_WORDS = (
    "proven root cause",
    "guaranteed",
    "production validated",
    "production-validated",
    "client proven",
    "client-proven",
)


def _content(pattern_key: str) -> PatternContent:
    return pattern_by_key(pattern_key)["content"]


def test_final_pattern_count_is_within_thirty_to_thirty_five() -> None:
    assert 30 <= len(PATTERNS) <= 35


def test_pattern_ids_are_stable_and_unique() -> None:
    keys = [p["pattern_key"] for p in PATTERNS]
    assert len(keys) == len(set(keys))
    for key in keys:
        assert key.startswith("J2C-OFS-")


def test_family_classification_is_valid_and_every_family_represented() -> None:
    families_seen: set[str] = set()
    for pattern in PATTERNS:
        family = pattern["content"]["family"]
        assert family in _VALID_FAMILIES, pattern["pattern_key"]
        families_seen.add(family)
    assert families_seen == _VALID_FAMILIES


def test_tier_classification_is_valid() -> None:
    for pattern in PATTERNS:
        assert pattern["content"]["validation_tier"] in _VALID_TIERS, pattern["pattern_key"]


def test_validation_status_classification_is_valid() -> None:
    for pattern in PATTERNS:
        assert pattern["content"]["validation_status"] in _VALID_STATUSES, pattern["pattern_key"]


def test_tier_1_patterns_are_appropriately_validated() -> None:
    tier_1 = [p for p in PATTERNS if p["content"]["validation_tier"] == "tier_1_validated"]
    # 12 original (P3.12) + up to 3 (P3.13) + up to 8 more (P3.15), each evidence-gated.
    assert 12 <= len(tier_1) <= 23
    tier_1_keys = {p["pattern_key"] for p in tier_1}
    golden_covered_keys = {
        key
        for case in GOLDEN_CASES
        for key in case.expected_patterns
        if case.case_type == "leakage"
    }
    for pattern in tier_1:
        assert pattern["content"]["validation_status"] == "validated", pattern["pattern_key"]
        assert pattern["pattern_key"] in golden_covered_keys, (
            pattern["pattern_key"],
            "every Tier 1 pattern must have at least one golden leakage case",
        )
    # The original 12 P3.12 patterns remain Tier 1 unless inspection gave a strong reason
    # otherwise (none did); P3.13 promoted at most 3 additional, P3.15 promoted at most 8 more,
    # each gated on real validation evidence, never on quota.
    original_twelve = {f"J2C-OFS-{n:02d}" for n in range(1, 13)}
    assert original_twelve <= tier_1_keys
    assert len(tier_1_keys - original_twelve) <= 11


def test_tier_2_patterns_never_report_validated() -> None:
    tier_2 = [
        p for p in PATTERNS if p["content"]["validation_tier"] == "tier_2_reference_specified"
    ]
    assert 12 <= len(tier_2) <= 20
    for pattern in tier_2:
        content = pattern["content"]
        assert content["validation_status"] != "validated", pattern["pattern_key"]
        assert content["validation_status"] == "reference_specified", pattern["pattern_key"]
        assert pattern["provenance_type"] != "production", pattern["pattern_key"]


def test_source_system_metadata_present() -> None:
    for pattern in PATTERNS:
        systems = pattern["content"]["source_systems"]
        assert isinstance(systems, list)
        assert len(systems) > 0, pattern["pattern_key"]


def test_correlation_fields_present() -> None:
    for pattern in PATTERNS:
        keys = pattern["content"]["correlation_fields"]
        assert isinstance(keys, list)
        assert len(keys) > 0, pattern["pattern_key"]


def test_required_evidence_present() -> None:
    for pattern in PATTERNS:
        assert len(pattern["content"]["required_evidence"]) > 0, pattern["pattern_key"]


def test_detection_concept_present() -> None:
    # detection_preconditions is this pack's detection-concept field (see the P3.13 content
    # module docstring for the explicit mapping); it must be non-empty for every pattern.
    for pattern in PATTERNS:
        assert len(pattern["content"]["detection_preconditions"]) > 0, pattern["pattern_key"]


def test_exclusions_represented() -> None:
    for pattern in PATTERNS:
        assert len(pattern["content"]["exclusions"]) > 0, pattern["pattern_key"]


def test_ambiguity_controls_represented() -> None:
    for pattern in PATTERNS:
        assert len(pattern["content"]["ambiguity_conditions"]) > 0, pattern["pattern_key"]


def test_false_positive_risks_represented() -> None:
    for pattern in PATTERNS:
        assert len(pattern["content"]["false_positive_risks"]) > 0, pattern["pattern_key"]


def test_causal_hypotheses_remain_hypotheses() -> None:
    for pattern in PATTERNS:
        hypotheses = pattern["content"]["causal_hypotheses"]
        assert len(hypotheses) > 0, pattern["pattern_key"]
        joined = " ".join(hypotheses).lower()
        for forbidden in _FORBIDDEN_CERTAINTY_WORDS:
            assert forbidden not in joined, (pattern["pattern_key"], forbidden)


def test_investigation_questions_present() -> None:
    for pattern in PATTERNS:
        assert len(pattern["content"]["investigation_questions"]) > 0, pattern["pattern_key"]


def test_recovery_playbooks_remain_declarative() -> None:
    forbidden_execution_words = (
        "automatically charge",
        "automatically bill",
        "auto-execute",
        "without approval",
    )
    for pattern in PATTERNS:
        playbook = pattern["content"]["recovery_playbook"]
        assert len(playbook) >= 3, pattern["pattern_key"]
        joined = " ".join(playbook).lower()
        for forbidden in forbidden_execution_words:
            assert forbidden not in joined, (pattern["pattern_key"], forbidden)
        assert any("approve" in step.lower() for step in playbook), pattern["pattern_key"]


def test_economic_interpretation_present() -> None:
    valid_categories = {
        "REVENUE_RECOVERY",
        "COST_REDUCTION",
        "CASH_ACCELERATION",
        "MARGIN_PROTECTION",
    }
    for pattern in PATTERNS:
        value_basis = pattern["content"]["value_basis"]
        assert value_basis["category"] in valid_categories, pattern["pattern_key"]
        assert value_basis["notes"], pattern["pattern_key"]


def test_provenance_is_truthful_across_full_portfolio() -> None:
    for pattern in PATTERNS:
        assert pattern["provenance_type"] in {"simulation", "manual"}, pattern["pattern_key"]


def test_limitations_present() -> None:
    for pattern in PATTERNS:
        assert len(pattern["content"]["limitations"]) > 0, pattern["pattern_key"]


def test_cross_system_intelligence_map_represented() -> None:
    assert len(CROSS_SYSTEM_INTELLIGENCE_MAP) >= 4
    known_keys = {p["pattern_key"] for p in PATTERNS}
    for flow in CROSS_SYSTEM_INTELLIGENCE_MAP:
        assert flow["pattern_key"] in known_keys
        assert len(flow["flow"]) >= 2
        assert len(flow["keys"]) >= 2


def test_normalization_matrix_eliminates_duplicates() -> None:
    included = [e for e in NORMALIZATION_MATRIX if e["disposition"] == "INCLUDED"]
    merged = [e for e in NORMALIZATION_MATRIX if e["disposition"] == "MERGED"]
    deferred = [e for e in NORMALIZATION_MATRIX if e["disposition"] == "DEFERRED"]
    assert len(included) + len(merged) + len(deferred) == len(NORMALIZATION_MATRIX)
    included_final_keys = {e["final_pattern_key"] for e in included}
    known_keys = {p["pattern_key"] for p in PATTERNS}
    # Every INCLUDED candidate maps to a real pattern, and every real pattern is the final
    # target of at least one INCLUDED candidate -- i.e. no pattern exists that the
    # normalization pass didn't account for, and no INCLUDED disposition points nowhere.
    assert included_final_keys == known_keys
    for entry in merged:
        assert entry["final_pattern_key"] in known_keys
        assert entry["disposition"] == "MERGED"
    for entry in deferred:
        assert entry["final_pattern_key"] is None


def test_loss_in_hole_semantic_safeguard() -> None:
    content = _content("J2C-OFS-16")
    notes = content["value_basis"]["notes"].lower()
    assert "not exposure" in notes or "not, by itself" in notes or "asset replacement" in notes
    joined_limitations = " ".join(content["limitations"]).lower()
    assert "liability" in joined_limitations or "fault" in joined_limitations


def test_material_shrinkage_semantic_safeguard() -> None:
    content = _content("J2C-OFS-17")
    notes = content["value_basis"]["notes"].lower()
    assert "not, by itself" in notes or "not automatic" in notes or "not billable amount" in notes


def test_npt_vs_standby_semantic_safeguard() -> None:
    content = _content("J2C-OFS-24")
    notes = content["value_basis"]["notes"].lower()
    assert "npt is not standby" in notes
    assert "not automatically billable" in notes
    assert content["validation_tier"] == "tier_1_validated"


def test_third_party_pass_through_semantic_safeguard() -> None:
    content = _content("J2C-OFS-20")
    notes = content["value_basis"]["notes"].lower()
    assert "not customer-billable" in notes or "not, by itself" in notes
    assert content["validation_tier"] == "tier_1_validated"


def test_portal_rejection_semantic_safeguard() -> None:
    content = _content("J2C-OFS-30")
    notes = content["value_basis"]["notes"].lower()
    assert "not realized" in notes or "not verified" in notes or "process blockage" in notes
    assert content["validation_tier"] == "tier_1_validated"


def test_short_pay_and_write_off_remain_distinct_concepts() -> None:
    short_pay = _content("J2C-OFS-32")
    write_off = _content("J2C-OFS-33")
    assert "not automatically" in short_pay["value_basis"]["notes"].lower()
    assert "not automatically" in write_off["value_basis"]["notes"].lower()
    # They must not be the same pattern or share identical economic notes verbatim.
    assert short_pay["value_basis"]["notes"] != write_off["value_basis"]["notes"]


def test_tax_pattern_carries_explicit_caveat() -> None:
    content = _content("J2C-OFS-34")
    joined_limitations = " ".join(content["limitations"]).lower()
    assert "tax advice" in joined_limitations or "tax law" in joined_limitations
    assert "not automatically" in content["value_basis"]["notes"].lower() or (
        "not a tax" in content["value_basis"]["notes"].lower()
    )


def test_fx_pattern_carries_explicit_caveat() -> None:
    content = _content("J2C-OFS-35")
    notes = content["value_basis"]["notes"].lower()
    assert "not leakage" in notes or "not, by itself" in notes


def test_golden_dataset_remains_deterministic_after_expansion() -> None:
    for case in GOLDEN_CASES:
        first = detect(case.observed)
        second = detect(dict(case.observed))
        assert first == second, case.case_id


def test_hidden_truth_remains_separate_after_expansion() -> None:
    hidden_only_keys = {"case_id", "case_type", "expected_patterns", "notes"}
    for case in GOLDEN_CASES:
        assert hidden_only_keys.isdisjoint(case.observed.keys()), case.case_id
