from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from oilfield_j2c_golden_dataset import GOLDEN_CASES, detect
from sqlalchemy.orm import Session
from test_decision_intelligence_foundation import make_org

from app.knowledge.oilfield_services_job_to_cash import (
    PACK_DESCRIPTION,
    PACK_DOMAIN,
    PACK_INDUSTRY,
    PACK_NAME,
    PACK_SCOPE,
    PACK_SLUG,
    PATTERNS,
)

_FORBIDDEN_CERTAINTY_WORDS = (
    "proven root cause",
    "guaranteed",
    "production validated",
    "production-validated",
    "client proven",
    "client-proven",
)
_AUTOMATIC_EXECUTION_WORDS = (
    "automatically charge",
    "automatically bill",
    "auto-execute",
    "without approval",
)


def _pack_path(organization_id: UUID, suffix: str = "") -> str:
    return f"/api/v1/organizations/{organization_id}/knowledge-packs{suffix}"


def _seed_pack(client: TestClient, organization_id: UUID) -> dict[str, Any]:
    response = client.post(
        _pack_path(organization_id),
        json={
            "name": PACK_NAME,
            "slug": PACK_SLUG,
            "description": PACK_DESCRIPTION,
            "industry": PACK_INDUSTRY,
            "domain": PACK_DOMAIN,
            "scope": PACK_SCOPE,
            "change_summary": "Initial v1.0 reference pattern library.",
        },
    )
    assert response.status_code == 201, response.text
    pack = cast(dict[str, Any], response.json())
    version_id = pack["latest_draft_version"]["id"]
    for pattern in PATTERNS:
        add_response = client.post(
            _pack_path(organization_id, f"/{pack['id']}/versions/{version_id}/patterns"),
            json={
                "pattern_key": pattern["pattern_key"],
                "name": pattern["name"],
                "process_stage": pattern["process_stage"],
                "description": pattern["description"],
                "provenance_type": pattern["provenance_type"],
                "content": pattern["content"],
            },
        )
        assert add_response.status_code == 201, add_response.text
    get_response = client.get(_pack_path(organization_id, f"/{pack['id']}"))
    assert get_response.status_code == 200, get_response.text
    return cast(dict[str, Any], get_response.json())


def test_pack_exists_with_correct_identity_and_lifecycle(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p312-identity")
    pack = _seed_pack(client, organization_id)
    assert pack["name"] == PACK_NAME
    assert pack["industry"] == "oilfield_services"
    assert pack["domain"] == "job_to_cash"
    assert pack["scope"] == PACK_SCOPE
    draft = pack["latest_draft_version"]
    assert draft["version_number"] == 1
    assert draft["lifecycle_status"] == "draft"


def test_pack_provenance_is_truthful_and_not_fabricated_production(
    client: TestClient, db: Session
) -> None:
    organization_id, _ = make_org(db, "p312-provenance")
    pack = _seed_pack(client, organization_id)
    draft = pack["latest_draft_version"]
    for pattern in draft["patterns"]:
        assert pattern["provenance_type"] in {"simulation", "manual"}
        assert pattern["provenance_type"] != "production"
    # A pack with zero Learning members and only reference patterns must not claim a
    # production-derived provenance summary anywhere in its lifecycle.
    assert draft["provenance_summary"] in (None, "simulation", "manual", "mixed")
    assert draft["provenance_summary"] != "production"


_ORIGINAL_P3_12_PATTERN_KEYS = frozenset(f"J2C-OFS-{n:02d}" for n in range(1, 13))


def test_pattern_keys_are_unique_and_original_twelve_remain_present() -> None:
    # P3.13 legitimately expanded the portfolio beyond the original P3.12 8-12 pattern bound
    # (see tests/test_p3_13_oilfield_leakage_intelligence.py for the current portfolio-size
    # invariant). This P3.12 regression only guards that keys stay unique and none of the
    # original 12 P3.12 patterns were renamed, removed, or duplicated by that expansion.
    keys = [p["pattern_key"] for p in PATTERNS]
    assert len(keys) == len(set(keys))
    assert _ORIGINAL_P3_12_PATTERN_KEYS <= set(keys)


def test_pattern_metadata_is_structurally_valid(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p312-pattern-metadata")
    pack = _seed_pack(client, organization_id)
    draft = pack["latest_draft_version"]
    assert len(draft["patterns"]) == len(PATTERNS)
    required_keys = {
        "required_evidence",
        "detection_preconditions",
        "exclusions",
        "ambiguity_conditions",
        "false_positive_risks",
        "causal_hypotheses",
        "investigation_questions",
        "recovery_playbook",
        "closure_evidence",
        "value_basis",
        "limitations",
        "related_defect_codes",
    }
    for pattern in draft["patterns"]:
        assert required_keys <= set(pattern["content_json"].keys())
        assert pattern["process_stage"] in {
            "job_creation",
            "field_execution",
            "evidence_capture",
            "resource_validation",
            "contract_rate_validation",
            "invoicing",
            "payment",
            "recovery",
        }


def test_pattern_required_evidence_and_exclusions_present() -> None:
    for pattern in PATTERNS:
        content = pattern["content"]
        assert len(content["required_evidence"]) > 0, pattern["pattern_key"]
        assert len(content["exclusions"]) > 0, pattern["pattern_key"]
        assert len(content["detection_preconditions"]) > 0, pattern["pattern_key"]


def test_causal_content_remains_hypothesis_not_proven_claim() -> None:
    for pattern in PATTERNS:
        content = pattern["content"]
        assert len(content["causal_hypotheses"]) > 0, pattern["pattern_key"]
        joined = " ".join(content["causal_hypotheses"]).lower()
        for forbidden in _FORBIDDEN_CERTAINTY_WORDS:
            assert forbidden not in joined, (pattern["pattern_key"], forbidden)


def test_recovery_playbooks_are_declarative_and_human_governed() -> None:
    for pattern in PATTERNS:
        playbook = pattern["content"]["recovery_playbook"]
        assert isinstance(playbook, list)
        assert len(playbook) >= 3, pattern["pattern_key"]
        joined = " ".join(playbook).lower()
        for forbidden in _AUTOMATIC_EXECUTION_WORDS:
            assert forbidden not in joined, (pattern["pattern_key"], forbidden)
        assert any("approve" in step.lower() for step in playbook), pattern["pattern_key"]


def test_value_semantics_keep_exposure_expected_realized_verified_distinct() -> None:
    valid_categories = {
        "REVENUE_RECOVERY",
        "COST_REDUCTION",
        "CASH_ACCELERATION",
        "MARGIN_PROTECTION",
    }
    for pattern in PATTERNS:
        value_basis = pattern["content"]["value_basis"]
        assert value_basis["category"] in valid_categories, pattern["pattern_key"]
        notes = value_basis["notes"].lower()
        # No pattern may assert that exposure equals a later-stage value directly.
        assert "exposure is realized" not in notes
        assert "exposure is verified" not in notes
        assert "expected recovery is verified" not in notes


def test_golden_dataset_loads_within_bounds() -> None:
    assert 40 <= len(GOLDEN_CASES) <= 100
    case_ids = [case.case_id for case in GOLDEN_CASES]
    assert len(case_ids) == len(set(case_ids))


def test_golden_dataset_clean_cases_produce_no_detections() -> None:
    clean_cases = [case for case in GOLDEN_CASES if case.case_type == "clean"]
    assert len(clean_cases) >= 4
    for case in clean_cases:
        assert detect(case.observed) == frozenset(), case.case_id


def test_golden_dataset_leakage_cases_trigger_intended_patterns() -> None:
    # Golden-dataset coverage is scoped to Tier 1 (validated) patterns only, by design --
    # Tier 2 (reference-specified) patterns are governed content that has not been exercised
    # through the synthetic validation framework and must not claim validated status.
    tier_1_patterns = [p for p in PATTERNS if p["content"]["validation_tier"] == "tier_1_validated"]
    leakage_cases = [case for case in GOLDEN_CASES if case.case_type == "leakage"]
    assert len(leakage_cases) >= len(tier_1_patterns)
    for case in leakage_cases:
        assert detect(case.observed) == frozenset(case.expected_patterns), case.case_id


def test_golden_dataset_ambiguous_cases_do_not_produce_unjustified_certainty() -> None:
    ambiguous_cases = [case for case in GOLDEN_CASES if case.case_type == "ambiguous"]
    assert len(ambiguous_cases) >= 1
    for case in ambiguous_cases:
        assert detect(case.observed) == frozenset(), case.case_id


def test_golden_dataset_edge_cases_are_excluded_false_positive_controls() -> None:
    edge_cases = [case for case in GOLDEN_CASES if case.case_type == "edge"]
    assert len(edge_cases) >= 8
    for case in edge_cases:
        assert detect(case.observed) == frozenset(case.expected_patterns), case.case_id


def test_golden_dataset_deterministic_replay_is_stable() -> None:
    for case in GOLDEN_CASES:
        first = detect(case.observed)
        second = detect(dict(case.observed))
        assert first == second, case.case_id


def test_golden_dataset_hidden_truth_is_not_present_in_observed_view() -> None:
    hidden_only_keys = {"case_id", "case_type", "expected_patterns", "notes"}
    for case in GOLDEN_CASES:
        assert hidden_only_keys.isdisjoint(case.observed.keys()), case.case_id


def test_pattern_authoring_remains_tenant_scoped(client: TestClient, db: Session) -> None:
    first_id, _ = make_org(db, "p312-tenant-first")
    second_id, _ = make_org(db, "p312-tenant-second")
    first_pack = _seed_pack(client, first_id)
    second_response = client.post(
        _pack_path(second_id),
        json={
            "name": PACK_NAME,
            "slug": PACK_SLUG,
            "description": PACK_DESCRIPTION,
            "industry": PACK_INDUSTRY,
            "domain": PACK_DOMAIN,
            "scope": PACK_SCOPE,
            "change_summary": "Second tenant pack, independent content.",
        },
    )
    assert second_response.status_code == 201, second_response.text
    second_pack = cast(dict[str, Any], second_response.json())
    cross_tenant = client.post(
        _pack_path(
            second_id,
            f"/{first_pack['id']}/versions/{first_pack['latest_draft_version']['id']}/patterns",
        ),
        json={
            "pattern_key": "CROSS-TENANT-01",
            "name": "Should not be reachable",
            "process_stage": "invoicing",
            "description": "Cross-tenant pattern injection attempt.",
            "provenance_type": "manual",
            "content": {"required_evidence": ["x"]},
        },
    )
    assert cross_tenant.status_code == 404
    assert second_pack["latest_draft_version"]["patterns"] == []


def test_pattern_key_uniqueness_enforced_per_version(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p312-key-uniqueness")
    pack = _seed_pack(client, organization_id)
    version_id = pack["latest_draft_version"]["id"]
    duplicate = client.post(
        _pack_path(organization_id, f"/{pack['id']}/versions/{version_id}/patterns"),
        json={
            "pattern_key": PATTERNS[0]["pattern_key"],
            "name": "Duplicate key attempt",
            "process_stage": "invoicing",
            "description": "Should be rejected as a duplicate pattern key.",
            "provenance_type": "manual",
            "content": {"required_evidence": ["x"]},
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "PATTERN_KEY_ALREADY_USED"


def test_pack_with_only_patterns_and_zero_learning_can_be_approved(
    client: TestClient, db: Session
) -> None:
    organization_id, _ = make_org(db, "p312-zero-learning-approve")
    pack = _seed_pack(client, organization_id)
    version_id = pack["latest_draft_version"]["id"]
    assert pack["latest_draft_version"]["members"] == []
    assert len(pack["latest_draft_version"]["patterns"]) == len(PATTERNS)
    submitted = client.post(
        _pack_path(organization_id, f"/{pack['id']}/versions/{version_id}/submit"),
        json={"rationale": "Reference content is bounded and ready for review."},
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        _pack_path(organization_id, f"/{pack['id']}/versions/{version_id}/approve"),
        json={"rationale": "Reference pack approved for v1.0 publication."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["current_approved_version"]["lifecycle_status"] == "approved"


def test_removing_all_patterns_and_learning_blocks_submission(
    client: TestClient, db: Session
) -> None:
    organization_id, _ = make_org(db, "p312-empty-blocks-submit")
    pack = _seed_pack(client, organization_id)
    version_id = pack["latest_draft_version"]["id"]
    for pattern in PATTERNS:
        removed = client.delete(
            _pack_path(
                organization_id,
                f"/{pack['id']}/versions/{version_id}/patterns/{pattern['pattern_key']}",
            )
        )
        assert removed.status_code == 204, removed.text
    blocked = client.post(
        _pack_path(organization_id, f"/{pack['id']}/versions/{version_id}/submit"),
        json={"rationale": "Must not pass with no members and no patterns."},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "PACK_MEMBERSHIP_REQUIRED"
