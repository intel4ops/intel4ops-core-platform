from datetime import UTC, datetime, timedelta

import pytest

from app.engines.trust_engine import (
    CurrencyCodeValidityRule,
    DateTimestampValidityRule,
    DuplicateBusinessEventRule,
    DuplicateTrustRuleError,
    LineageCompletenessRule,
    NumericRangeValidityRule,
    PrimaryIdentifierUniquenessRule,
    ProgressiveReadinessPolicy,
    RecordFreshnessRule,
    ReferentialIntegrityRule,
    RequiredFieldCompletenessRule,
    SchemaConformanceRule,
    TrustRule,
    TrustRuleOutcome,
    TrustRuleRegistry,
    calculate_scores,
    default_rule_registry,
)
from app.models.trust import (
    AnalyticalLevel,
    ReadinessStatus,
    TrustResultStatus,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("rule", "records", "config"),
    [
        (
            RequiredFieldCompletenessRule(),
            [{"id": "1", "amount": ""}],
            {"required_fields": ["amount"], "identifier_field": "id"},
        ),
        (
            PrimaryIdentifierUniquenessRule(),
            [{"id": "1"}, {"id": "1"}],
            {"identifier_field": "id"},
        ),
        (
            ReferentialIntegrityRule(),
            [{"id": "1", "parent_id": "missing"}],
            {
                "reference_field": "parent_id",
                "valid_references": ["known"],
                "identifier_field": "id",
            },
        ),
        (
            DateTimestampValidityRule(),
            [{"id": "1", "occurred_at": "not-a-date"}],
            {"date_fields": ["occurred_at"], "identifier_field": "id"},
        ),
        (
            NumericRangeValidityRule(),
            [{"id": "1", "amount": 101}],
            {
                "numeric_ranges": {"amount": {"minimum": 0, "maximum": 100}},
                "identifier_field": "id",
            },
        ),
        (
            CurrencyCodeValidityRule(),
            [{"id": "1", "currency": "XYZ"}],
            {"currency_fields": ["currency"], "identifier_field": "id"},
        ),
        (
            RecordFreshnessRule(),
            [{"id": "1", "updated_at": (NOW - timedelta(days=40)).isoformat()}],
            {
                "timestamp_field": "updated_at",
                "maximum_age_days": 30,
                "identifier_field": "id",
            },
        ),
        (
            LineageCompletenessRule(),
            [{"id": "1", "source_id": None}],
            {"lineage_fields": ["source_id"], "identifier_field": "id"},
        ),
        (
            DuplicateBusinessEventRule(),
            [
                {"id": "1", "asset": "A", "event": "X"},
                {"id": "2", "asset": "A", "event": "X"},
            ],
            {
                "composite_key_fields": ["asset", "event"],
                "identifier_field": "id",
            },
        ),
        (
            SchemaConformanceRule(),
            [{"id": "1", "amount": "not-number"}],
            {
                "expected_schema": {"id": "string", "amount": "number"},
                "identifier_field": "id",
            },
        ),
    ],
)
def test_reference_rule_detects_deterministic_failure(
    rule: object,
    records: list[dict[str, object]],
    config: dict[str, object],
) -> None:
    outcome = rule.execute(records, config, NOW)  # type: ignore[attr-defined]
    assert outcome.status == TrustResultStatus.FAILED
    assert outcome.affected_count >= 1
    assert outcome.score is not None and 0 <= outcome.score < 100
    assert outcome.evidence


def test_rules_pass_for_valid_records() -> None:
    records = [
        {
            "id": "1",
            "parent_id": "P1",
            "amount": 10,
            "currency": "USD",
            "occurred_at": NOW.isoformat(),
            "source_id": "source",
            "event": "created",
        }
    ]
    configurations: dict[str, dict[str, object]] = {
        "required_field_completeness": {"required_fields": ["id", "amount"]},
        "primary_identifier_uniqueness": {"identifier_field": "id"},
        "referential_integrity": {
            "reference_field": "parent_id",
            "valid_references": ["P1"],
        },
        "date_timestamp_validity": {"date_fields": ["occurred_at"]},
        "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0, "maximum": 100}}},
        "currency_code_validity": {"currency_fields": ["currency"]},
        "record_freshness": {
            "timestamp_field": "occurred_at",
            "maximum_age_days": 30,
        },
        "lineage_completeness": {"lineage_fields": ["source_id"]},
        "duplicate_business_event": {"composite_key_fields": ["id", "event"]},
        "schema_conformance": {"expected_schema": {"id": "string", "amount": "number"}},
    }
    applicable = default_rule_registry().applicable("transactional", configurations)
    assert len(applicable) == 10
    assert all(
        rule.execute(records, config, NOW).status == TrustResultStatus.PASSED
        for rule, config in applicable
    )


def test_registry_duplicate_and_applicability_behavior() -> None:
    rule = RequiredFieldCompletenessRule()
    registry = TrustRuleRegistry([rule])
    registry.register(rule)
    with pytest.raises(DuplicateTrustRuleError):
        registry.register(RequiredFieldCompletenessRule())
    assert registry.applicable("transactional", {}) == []
    assert (
        len(
            registry.applicable(
                "transactional",
                {"required_field_completeness": {"required_fields": ["id"]}},
            )
        )
        == 1
    )


def test_score_calculation_ignores_skipped_rules() -> None:
    rule = RequiredFieldCompletenessRule()
    dimensions, overall = calculate_scores(
        [
            (
                rule,
                TrustRuleOutcome(
                    status=TrustResultStatus.PASSED,
                    checked_count=1,
                    affected_count=0,
                    score=80,
                    message="passed",
                ),
            ),
            (
                rule,
                TrustRuleOutcome(
                    status=TrustResultStatus.SKIPPED,
                    checked_count=0,
                    affected_count=0,
                    score=100,
                    message="skipped",
                ),
            ),
        ]
    )
    assert dimensions[rule.dimension] == 80
    assert overall == 80


def test_critical_failure_blocks_high_average_and_sample_size_is_distinct() -> None:
    completeness = RequiredFieldCompletenessRule()
    validity = NumericRangeValidityRule()
    outcomes: list[tuple[TrustRule, TrustRuleOutcome]] = [
        (
            completeness,
            TrustRuleOutcome(
                status=TrustResultStatus.FAILED,
                checked_count=40,
                affected_count=1,
                score=97.5,
                message="critical",
            ),
        ),
        (
            validity,
            TrustRuleOutcome(
                status=TrustResultStatus.PASSED,
                checked_count=40,
                affected_count=0,
                score=100,
                message="passed",
            ),
        ),
    ]
    dimensions, _ = calculate_scores(outcomes)
    decisions = ProgressiveReadinessPolicy().decide(40, dimensions, outcomes)
    arithmetic = next(item for item in decisions if item.level == AnalyticalLevel.ARITHMETIC)
    predictive = next(item for item in decisions if item.level == AnalyticalLevel.PREDICTIVE)
    assert arithmetic.status == ReadinessStatus.BLOCKED
    assert completeness.code in arithmetic.blocking_codes
    assert predictive.status == ReadinessStatus.BLOCKED

    clean_outcomes: list[tuple[TrustRule, TrustRuleOutcome]] = [
        (
            completeness,
            TrustRuleOutcome(
                status=TrustResultStatus.PASSED,
                checked_count=10,
                affected_count=0,
                score=100,
                message="passed",
            ),
        )
    ]
    clean_dimensions, _ = calculate_scores(clean_outcomes)
    predictive_small_sample = next(
        item
        for item in ProgressiveReadinessPolicy().decide(10, clean_dimensions, clean_outcomes)
        if item.level == AnalyticalLevel.PREDICTIVE
    )
    assert predictive_small_sample.status == ReadinessStatus.INSUFFICIENT_DATA


def test_evidence_is_capped_per_rule() -> None:
    records: list[dict[str, object]] = [
        {"id": str(index), "required": None} for index in range(100)
    ]
    outcome = RequiredFieldCompletenessRule().execute(
        records, {"required_fields": ["required"], "identifier_field": "id"}, NOW
    )
    assert outcome.affected_count == 100
    assert len(outcome.evidence) == 25
