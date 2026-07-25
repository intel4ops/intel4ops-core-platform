from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

import pandas as pd

from app.models.trust import (
    AnalyticalLevel,
    ReadinessStatus,
    TrustDimension,
    TrustResultStatus,
    TrustRuleSeverity,
)
from app.schemas.contracts import TrustIssue, TrustReport

Record = dict[str, object]
RuleConfig = dict[str, object]
MAX_EVIDENCE_PER_RULE = 25


@dataclass(frozen=True)
class TrustEvidenceItem:
    record_identifier: str | None = None
    field_name: str | None = None
    observed_value: object | None = None
    expected_condition: str | None = None
    evidence_type: str = "record"
    source_reference: str | None = None


@dataclass(frozen=True)
class TrustRuleOutcome:
    status: TrustResultStatus
    checked_count: int
    affected_count: int
    score: float | None
    message: str
    observed_value: dict[str, object] | None = None
    evidence: tuple[TrustEvidenceItem, ...] = ()


class TrustRule(Protocol):
    code: str
    name: str
    version: str
    dimension: TrustDimension
    severity: TrustRuleSeverity
    description: str
    supported_dataset_types: frozenset[str]
    required_config_fields: frozenset[str]
    threshold_definition: dict[str, object]

    @property
    def remediation_guidance(self) -> str | None: ...

    def is_applicable(self, dataset_type: str, config: RuleConfig) -> bool: ...

    def execute(
        self, records: list[Record], config: RuleConfig, now: datetime
    ) -> TrustRuleOutcome: ...


class BaseTrustRule:
    code = ""
    name = ""
    version = "1.0"
    dimension = TrustDimension.VALIDITY
    severity = TrustRuleSeverity.ERROR
    description = ""
    supported_dataset_types = frozenset({"*"})
    required_config_fields: frozenset[str] = frozenset()
    threshold_definition: dict[str, object] = {"maximum_affected_percentage": 0.0}
    remediation_guidance: str | None = None

    def is_applicable(self, dataset_type: str, config: RuleConfig) -> bool:
        supports_type = "*" in self.supported_dataset_types or dataset_type in (
            self.supported_dataset_types
        )
        return supports_type and self.required_config_fields <= config.keys()

    def _outcome(
        self,
        records: list[Record],
        affected: list[TrustEvidenceItem],
        *,
        message: str,
        observed: dict[str, object] | None = None,
        threshold: float | None = None,
    ) -> TrustRuleOutcome:
        checked = len(records)
        affected_count = len(affected)
        percentage = 0.0 if checked == 0 else affected_count * 100 / checked
        maximum = (
            _as_float(self.threshold_definition["maximum_affected_percentage"])
            if threshold is None
            else threshold
        )
        score = round(max(0.0, 100.0 - percentage), 2)
        if affected_count == 0:
            status = TrustResultStatus.PASSED
        elif percentage <= maximum:
            status = TrustResultStatus.WARNING
        else:
            status = TrustResultStatus.FAILED
        return TrustRuleOutcome(
            status=status,
            checked_count=checked,
            affected_count=affected_count,
            score=score,
            message=message,
            observed_value=observed or {"affected_percentage": round(percentage, 2)},
            evidence=tuple(affected[:MAX_EVIDENCE_PER_RULE]),
        )


def _identifier(record: Record, index: int, config: RuleConfig) -> str:
    identifier_field = str(config.get("identifier_field", "id"))
    value = record.get(identifier_field)
    return str(value) if value is not None else str(index + 1)


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Rule configuration value must be a list")
    return value


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Rule configuration value must be an object")
    return {str(key): nested for key, nested in value.items()}


def _as_float(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        raise ValueError("Rule configuration value must be numeric")
    return float(value)


def _as_int(value: object) -> int:
    if not isinstance(value, (int, str)):
        raise ValueError("Rule configuration value must be an integer")
    return int(value)


class RequiredFieldCompletenessRule(BaseTrustRule):
    code = "required_field_completeness"
    name = "Required field completeness"
    dimension = TrustDimension.COMPLETENESS
    severity = TrustRuleSeverity.CRITICAL
    description = "Required fields must contain non-blank values."
    required_config_fields = frozenset({"required_fields"})
    remediation_guidance = "Populate required fields or correct the source mapping."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        fields = [str(item) for item in _as_list(config["required_fields"])]
        evidence: list[TrustEvidenceItem] = []
        affected_records: set[int] = set()
        for index, record in enumerate(records):
            for field_name in fields:
                value = record.get(field_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    affected_records.add(index)
                    evidence.append(
                        TrustEvidenceItem(
                            record_identifier=_identifier(record, index, config),
                            field_name=field_name,
                            observed_value=value,
                            expected_condition="non-null and non-blank",
                            evidence_type="field",
                        )
                    )
        outcome = self._outcome(
            records,
            [
                next(
                    item
                    for item in evidence
                    if item.record_identifier == _identifier(records[i], i, config)
                )
                for i in sorted(affected_records)
            ],
            message=f"{len(affected_records)} records have missing required fields",
            observed={"missing_value_count": len(evidence)},
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )
        return TrustRuleOutcome(
            **{**outcome.__dict__, "evidence": tuple(evidence[:MAX_EVIDENCE_PER_RULE])}
        )


class PrimaryIdentifierUniquenessRule(BaseTrustRule):
    code = "primary_identifier_uniqueness"
    name = "Primary identifier uniqueness"
    dimension = TrustDimension.UNIQUENESS
    severity = TrustRuleSeverity.CRITICAL
    description = "Primary identifiers must be unique."
    required_config_fields = frozenset({"identifier_field"})
    remediation_guidance = "Deduplicate records or correct identifier generation."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        field_name = str(config["identifier_field"])
        seen: set[object] = set()
        evidence: list[TrustEvidenceItem] = []
        for index, record in enumerate(records):
            value = record.get(field_name)
            if value is not None and value in seen:
                evidence.append(
                    TrustEvidenceItem(
                        record_identifier=_identifier(record, index, config),
                        field_name=field_name,
                        observed_value=value,
                        expected_condition="unique identifier",
                        evidence_type="duplicate",
                    )
                )
            seen.add(value)
        return self._outcome(
            records,
            evidence,
            message=f"{len(evidence)} duplicate identifiers detected",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )


class ReferentialIntegrityRule(BaseTrustRule):
    code = "referential_integrity"
    name = "Referential integrity"
    dimension = TrustDimension.REFERENTIAL_INTEGRITY
    severity = TrustRuleSeverity.ERROR
    description = "Configured references must exist in the allowed reference set."
    required_config_fields = frozenset({"reference_field", "valid_references"})
    remediation_guidance = "Load missing parents or correct invalid references."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        field_name = str(config["reference_field"])
        valid = set(_as_list(config["valid_references"]))
        evidence = [
            TrustEvidenceItem(
                record_identifier=_identifier(record, index, config),
                field_name=field_name,
                observed_value=record.get(field_name),
                expected_condition="reference exists",
                evidence_type="reference",
            )
            for index, record in enumerate(records)
            if record.get(field_name) is not None and record.get(field_name) not in valid
        ]
        return self._outcome(
            records,
            evidence,
            message=f"{len(evidence)} invalid references detected",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class DateTimestampValidityRule(BaseTrustRule):
    code = "date_timestamp_validity"
    name = "Date and timestamp validity"
    dimension = TrustDimension.VALIDITY
    description = "Configured timestamps must be parseable and within bounds."
    required_config_fields = frozenset({"date_fields"})
    remediation_guidance = "Correct timestamp formats and source date boundaries."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        fields = [str(item) for item in _as_list(config["date_fields"])]
        minimum = _parse_datetime(config.get("minimum_date"))
        maximum = _parse_datetime(config.get("maximum_date")) or now
        evidence: list[TrustEvidenceItem] = []
        affected: set[int] = set()
        for index, record in enumerate(records):
            for field_name in fields:
                value = record.get(field_name)
                if value is None:
                    continue
                parsed = _parse_datetime(value)
                if parsed is None or (minimum and parsed < minimum) or parsed > maximum:
                    affected.add(index)
                    evidence.append(
                        TrustEvidenceItem(
                            record_identifier=_identifier(record, index, config),
                            field_name=field_name,
                            observed_value=value,
                            expected_condition="valid in-range ISO timestamp",
                            evidence_type="field",
                        )
                    )
        return self._outcome(
            records,
            [
                TrustEvidenceItem(record_identifier=str(index + 1), evidence_type="field")
                for index in sorted(affected)
            ],
            message=f"{len(affected)} records contain invalid timestamps",
            observed={"invalid_value_count": len(evidence)},
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        ).__class__(
            **{
                **self._outcome(
                    records,
                    [
                        TrustEvidenceItem(
                            record_identifier=_identifier(records[index], index, config)
                        )
                        for index in sorted(affected)
                    ],
                    message=f"{len(affected)} records contain invalid timestamps",
                    observed={"invalid_value_count": len(evidence)},
                    threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
                ).__dict__,
                "evidence": tuple(evidence[:MAX_EVIDENCE_PER_RULE]),
            }
        )


class NumericRangeValidityRule(BaseTrustRule):
    code = "numeric_range_validity"
    name = "Numeric range validity"
    dimension = TrustDimension.VALIDITY
    description = "Configured numeric fields must fall within configured bounds."
    required_config_fields = frozenset({"numeric_ranges"})
    remediation_guidance = "Correct out-of-range values or update governed bounds."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        ranges = _as_dict(config["numeric_ranges"])
        evidence: list[TrustEvidenceItem] = []
        affected: set[int] = set()
        for index, record in enumerate(records):
            for field_name, bounds_value in ranges.items():
                value = record.get(str(field_name))
                if value is None:
                    continue
                bounds = _as_dict(bounds_value)
                try:
                    numeric = Decimal(str(value))
                    invalid = (
                        "minimum" in bounds and numeric < Decimal(str(bounds["minimum"]))
                    ) or ("maximum" in bounds and numeric > Decimal(str(bounds["maximum"])))
                except InvalidOperation:
                    invalid = True
                if invalid:
                    affected.add(index)
                    evidence.append(
                        TrustEvidenceItem(
                            record_identifier=_identifier(record, index, config),
                            field_name=str(field_name),
                            observed_value=value,
                            expected_condition="numeric value within configured range",
                            evidence_type="field",
                        )
                    )
        base = self._outcome(
            records,
            [
                TrustEvidenceItem(record_identifier=_identifier(records[i], i, config))
                for i in sorted(affected)
            ],
            message=f"{len(affected)} records contain invalid numeric values",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )
        return TrustRuleOutcome(
            **{**base.__dict__, "evidence": tuple(evidence[:MAX_EVIDENCE_PER_RULE])}
        )


class CurrencyCodeValidityRule(BaseTrustRule):
    code = "currency_code_validity"
    name = "Currency code validity"
    dimension = TrustDimension.VALIDITY
    description = "Currency values must match the configured ISO-style code set."
    required_config_fields = frozenset({"currency_fields"})
    remediation_guidance = "Normalize currency values to configured three-letter codes."
    default_codes = frozenset(
        {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "CNY", "INR", "MXN", "BRL"}
    )

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        fields = [str(item) for item in _as_list(config["currency_fields"])]
        valid = {
            str(item).upper()
            for item in _as_list(config.get("valid_currency_codes", list(self.default_codes)))
        }
        evidence: list[TrustEvidenceItem] = []
        affected: set[int] = set()
        for index, record in enumerate(records):
            for field_name in fields:
                value = record.get(field_name)
                if value is not None and str(value).upper() not in valid:
                    affected.add(index)
                    evidence.append(
                        TrustEvidenceItem(
                            record_identifier=_identifier(record, index, config),
                            field_name=field_name,
                            observed_value=value,
                            expected_condition="configured three-letter currency code",
                            evidence_type="field",
                        )
                    )
        base = self._outcome(
            records,
            [
                TrustEvidenceItem(record_identifier=_identifier(records[i], i, config))
                for i in sorted(affected)
            ],
            message=f"{len(affected)} records contain invalid currency codes",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )
        return TrustRuleOutcome(
            **{**base.__dict__, "evidence": tuple(evidence[:MAX_EVIDENCE_PER_RULE])}
        )


class RecordFreshnessRule(BaseTrustRule):
    code = "record_freshness"
    name = "Record freshness"
    dimension = TrustDimension.TIMELINESS
    severity = TrustRuleSeverity.WARNING
    description = "Records must be newer than the configured freshness threshold."
    required_config_fields = frozenset({"timestamp_field", "maximum_age_days"})
    remediation_guidance = "Refresh the dataset or investigate delayed ingestion."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        field_name = str(config["timestamp_field"])
        maximum_age_days = _as_int(config["maximum_age_days"])
        cutoff = now - timedelta(days=maximum_age_days)
        evidence = []
        for index, record in enumerate(records):
            parsed = _parse_datetime(record.get(field_name))
            if parsed is None or parsed < cutoff:
                evidence.append(
                    TrustEvidenceItem(
                        record_identifier=_identifier(record, index, config),
                        field_name=field_name,
                        observed_value=record.get(field_name),
                        expected_condition=(f"timestamp no older than {maximum_age_days} days"),
                        evidence_type="field",
                    )
                )
        return self._outcome(
            records,
            evidence,
            message=f"{len(evidence)} stale or invalid records detected",
            threshold=_as_float(config.get("maximum_affected_percentage", 10.0)),
        )


class LineageCompletenessRule(BaseTrustRule):
    code = "lineage_completeness"
    name = "Lineage completeness"
    dimension = TrustDimension.LINEAGE
    severity = TrustRuleSeverity.CRITICAL
    description = "Records must retain configured source and ingestion references."
    required_config_fields = frozenset({"lineage_fields"})
    remediation_guidance = "Restore source, batch, and record lineage references."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        fields = [str(item) for item in _as_list(config["lineage_fields"])]
        evidence = []
        for index, record in enumerate(records):
            missing = [field_name for field_name in fields if not record.get(field_name)]
            if missing:
                evidence.append(
                    TrustEvidenceItem(
                        record_identifier=_identifier(record, index, config),
                        field_name=",".join(missing),
                        expected_condition="all configured lineage references present",
                        evidence_type="lineage",
                    )
                )
        return self._outcome(
            records,
            evidence,
            message=f"{len(evidence)} records have incomplete lineage",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )


class DuplicateBusinessEventRule(BaseTrustRule):
    code = "duplicate_business_event"
    name = "Duplicate business event detection"
    dimension = TrustDimension.UNIQUENESS
    description = "Configured business-event composite keys must be unique."
    required_config_fields = frozenset({"composite_key_fields"})
    remediation_guidance = "Deduplicate events using the governed composite key."

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        fields = [str(item) for item in _as_list(config["composite_key_fields"])]
        seen: set[tuple[object, ...]] = set()
        evidence = []
        for index, record in enumerate(records):
            key = tuple(record.get(field_name) for field_name in fields)
            if key in seen:
                evidence.append(
                    TrustEvidenceItem(
                        record_identifier=_identifier(record, index, config),
                        field_name=",".join(fields),
                        observed_value=list(key),
                        expected_condition="unique composite business-event key",
                        evidence_type="duplicate",
                    )
                )
            seen.add(key)
        return self._outcome(
            records,
            evidence,
            message=f"{len(evidence)} duplicate business events detected",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )


class SchemaConformanceRule(BaseTrustRule):
    code = "schema_conformance"
    name = "Schema conformance"
    dimension = TrustDimension.CONSISTENCY
    severity = TrustRuleSeverity.CRITICAL
    description = "Required fields and configured runtime types must conform."
    required_config_fields = frozenset({"expected_schema"})
    remediation_guidance = "Correct source schema or update the governed schema contract."
    type_map: dict[str, type[object] | tuple[type[object], ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    def execute(self, records: list[Record], config: RuleConfig, now: datetime) -> TrustRuleOutcome:
        del now
        schema = _as_dict(config["expected_schema"])
        evidence: list[TrustEvidenceItem] = []
        affected: set[int] = set()
        for index, record in enumerate(records):
            for field_name, expected_name in schema.items():
                expected = self.type_map.get(str(expected_name))
                value = record.get(str(field_name))
                if expected is None or value is None or not isinstance(value, expected):
                    affected.add(index)
                    evidence.append(
                        TrustEvidenceItem(
                            record_identifier=_identifier(record, index, config),
                            field_name=str(field_name),
                            observed_value=value,
                            expected_condition=f"type {expected_name}",
                            evidence_type="schema",
                        )
                    )
        base = self._outcome(
            records,
            [
                TrustEvidenceItem(record_identifier=_identifier(records[i], i, config))
                for i in sorted(affected)
            ],
            message=f"{len(affected)} records do not conform to schema",
            threshold=_as_float(config.get("maximum_affected_percentage", 0.0)),
        )
        return TrustRuleOutcome(
            **{**base.__dict__, "evidence": tuple(evidence[:MAX_EVIDENCE_PER_RULE])}
        )


class DuplicateTrustRuleError(ValueError):
    pass


class TrustRuleRegistry:
    def __init__(self, rules: list[TrustRule] | None = None) -> None:
        self._rules: dict[tuple[str, str], TrustRule] = {}
        for rule in rules or []:
            self.register(rule)

    def register(self, rule: TrustRule) -> None:
        key = (rule.code, rule.version)
        existing = self._rules.get(key)
        if existing is not None and existing is not rule:
            raise DuplicateTrustRuleError(
                f"Trust rule {rule.code} version {rule.version} is already registered"
            )
        self._rules[key] = rule

    def get(self, code: str, version: str = "1.0") -> TrustRule:
        try:
            return self._rules[(code, version)]
        except KeyError as exc:
            raise KeyError(f"Trust rule {code} version {version} is not registered") from exc

    def applicable(
        self, dataset_type: str, configurations: dict[str, RuleConfig]
    ) -> list[tuple[TrustRule, RuleConfig]]:
        applicable = []
        for key in sorted(self._rules):
            rule = self._rules[key]
            config = configurations.get(rule.code)
            if config is not None and rule.is_applicable(dataset_type, config):
                applicable.append((rule, config))
        return applicable


def default_rule_registry() -> TrustRuleRegistry:
    return TrustRuleRegistry(
        [
            RequiredFieldCompletenessRule(),
            PrimaryIdentifierUniquenessRule(),
            ReferentialIntegrityRule(),
            DateTimestampValidityRule(),
            NumericRangeValidityRule(),
            CurrencyCodeValidityRule(),
            RecordFreshnessRule(),
            LineageCompletenessRule(),
            DuplicateBusinessEventRule(),
            SchemaConformanceRule(),
        ]
    )


DIMENSION_WEIGHTS: dict[TrustDimension, float] = {
    TrustDimension.COMPLETENESS: 0.20,
    TrustDimension.VALIDITY: 0.20,
    TrustDimension.CONSISTENCY: 0.15,
    TrustDimension.UNIQUENESS: 0.15,
    TrustDimension.TIMELINESS: 0.10,
    TrustDimension.LINEAGE: 0.15,
    TrustDimension.REFERENTIAL_INTEGRITY: 0.05,
}


def calculate_scores(
    outcomes: list[tuple[TrustRule, TrustRuleOutcome]],
) -> tuple[dict[TrustDimension, float], float | None]:
    grouped: dict[TrustDimension, list[float]] = {}
    for rule, outcome in outcomes:
        if outcome.status in {TrustResultStatus.SKIPPED, TrustResultStatus.NOT_APPLICABLE}:
            continue
        if outcome.score is not None:
            grouped.setdefault(rule.dimension, []).append(outcome.score)
    dimensions = {
        dimension: round(sum(scores) / len(scores), 2) for dimension, scores in grouped.items()
    }
    weights = {
        dimension: DIMENSION_WEIGHTS[dimension]
        for dimension in dimensions
        if dimension in DIMENSION_WEIGHTS
    }
    weight_total = sum(weights.values())
    overall = (
        round(
            sum(dimensions[dimension] * weight for dimension, weight in weights.items())
            / weight_total,
            2,
        )
        if weight_total
        else None
    )
    return dimensions, overall


@dataclass(frozen=True)
class ReadinessDecision:
    level: AnalyticalLevel
    status: ReadinessStatus
    blocking_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation: str = ""


class ProgressiveReadinessPolicy:
    minimum_rows = {
        AnalyticalLevel.ARITHMETIC: 1,
        AnalyticalLevel.STATISTICAL: 30,
        AnalyticalLevel.FORECASTING: 24,
        AnalyticalLevel.PREDICTIVE: 100,
        AnalyticalLevel.OPTIMIZATION: 20,
        AnalyticalLevel.ECONOMIC_RECOVERY: 1,
    }
    required_dimensions = {
        AnalyticalLevel.ARITHMETIC: {TrustDimension.COMPLETENESS, TrustDimension.VALIDITY},
        AnalyticalLevel.STATISTICAL: {
            TrustDimension.COMPLETENESS,
            TrustDimension.CONSISTENCY,
        },
        AnalyticalLevel.FORECASTING: {
            TrustDimension.COMPLETENESS,
            TrustDimension.CONSISTENCY,
            TrustDimension.TIMELINESS,
            TrustDimension.LINEAGE,
        },
        AnalyticalLevel.PREDICTIVE: {
            TrustDimension.COMPLETENESS,
            TrustDimension.VALIDITY,
            TrustDimension.LINEAGE,
        },
        AnalyticalLevel.OPTIMIZATION: {
            TrustDimension.COMPLETENESS,
            TrustDimension.VALIDITY,
            TrustDimension.CONSISTENCY,
        },
        AnalyticalLevel.ECONOMIC_RECOVERY: {
            TrustDimension.COMPLETENESS,
            TrustDimension.VALIDITY,
            TrustDimension.LINEAGE,
        },
    }
    minimum_score = {
        AnalyticalLevel.ARITHMETIC: 60.0,
        AnalyticalLevel.STATISTICAL: 70.0,
        AnalyticalLevel.FORECASTING: 75.0,
        AnalyticalLevel.PREDICTIVE: 80.0,
        AnalyticalLevel.OPTIMIZATION: 80.0,
        AnalyticalLevel.ECONOMIC_RECOVERY: 85.0,
    }

    def decide(
        self,
        row_count: int,
        dimensions: dict[TrustDimension, float],
        outcomes: list[tuple[TrustRule, TrustRuleOutcome]],
    ) -> list[ReadinessDecision]:
        critical_failures = tuple(
            sorted(
                rule.code
                for rule, outcome in outcomes
                if rule.severity == TrustRuleSeverity.CRITICAL
                and outcome.status == TrustResultStatus.FAILED
            )
        )
        warnings = tuple(
            sorted(
                rule.code
                for rule, outcome in outcomes
                if outcome.status == TrustResultStatus.WARNING
            )
        )
        decisions = []
        for level in AnalyticalLevel:
            if critical_failures:
                decisions.append(
                    ReadinessDecision(
                        level=level,
                        status=ReadinessStatus.BLOCKED,
                        blocking_codes=critical_failures,
                        warning_codes=warnings,
                        explanation="critical trust rules failed",
                    )
                )
                continue
            if row_count < self.minimum_rows[level]:
                decisions.append(
                    ReadinessDecision(
                        level=level,
                        status=ReadinessStatus.INSUFFICIENT_DATA,
                        warning_codes=warnings,
                        explanation=(
                            f"{row_count} rows available; {self.minimum_rows[level]} required"
                        ),
                    )
                )
                continue
            missing = self.required_dimensions[level] - dimensions.keys()
            low_dimensions = {
                dimension
                for dimension in self.required_dimensions[level]
                if dimensions.get(dimension, 0) < self.minimum_score[level]
            }
            if missing or low_dimensions:
                explanation_parts = []
                if missing:
                    explanation_parts.append("required dimensions were not assessed")
                if low_dimensions:
                    explanation_parts.append("required dimension scores are below threshold")
                decisions.append(
                    ReadinessDecision(
                        level=level,
                        status=ReadinessStatus.BLOCKED,
                        warning_codes=warnings,
                        explanation="; ".join(explanation_parts),
                    )
                )
            else:
                decisions.append(
                    ReadinessDecision(
                        level=level,
                        status=(
                            ReadinessStatus.READY_WITH_WARNINGS
                            if warnings
                            else ReadinessStatus.READY
                        ),
                        warning_codes=warnings,
                        explanation="Required trust dimensions and sample size are sufficient",
                    )
                )
        return decisions


class TrustEngine:
    """Compatibility profiler plus deterministic shared Trust Engine entry point."""

    def profile(self, dataframe: pd.DataFrame, dataset_name: str) -> TrustReport:
        issues: list[TrustIssue] = []
        rows = len(dataframe)
        cells = max(rows * max(len(dataframe.columns), 1), 1)
        missing = int(dataframe.isna().sum().sum())
        completeness = max(0.0, 1 - missing / cells)
        duplicate_rows = int(dataframe.duplicated().sum()) if rows else 0
        duplicate_score = 1.0 if rows == 0 else max(0.0, 1 - duplicate_rows / rows)
        for column in dataframe.columns:
            null_count = int(dataframe[column].isna().sum())
            if null_count:
                issues.append(
                    TrustIssue(
                        field=str(column),
                        issue_type="missing_values",
                        message=f"{null_count} missing values detected",
                    )
                )
        if duplicate_rows:
            issues.append(
                TrustIssue(
                    issue_type="duplicate_rows",
                    message=f"{duplicate_rows} fully duplicated rows detected",
                )
            )
        validity = 1.0
        overall = round((completeness * 0.45) + (duplicate_score * 0.25) + (validity * 0.30), 4)
        return TrustReport(
            dataset_name=dataset_name,
            row_count=rows,
            completeness_score=round(completeness, 4),
            duplicate_score=round(duplicate_score, 4),
            validity_score=validity,
            overall_trust_score=overall,
            issues=issues,
        )
