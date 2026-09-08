from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from app.intelligence_packs.registry import default_intelligence_pack_registry


@dataclass(frozen=True)
class FieldSemantic:
    source_field: str
    canonical_concept: str | None
    confidence: float
    evidence: str


@dataclass(frozen=True)
class DatasetSemanticProfile:
    dataset_name: str
    inferred_domains: tuple[str, ...]
    fields: tuple[FieldSemantic, ...]
    warnings: tuple[str, ...]

    @property
    def available_concepts(self) -> set[str]:
        return {
            field.canonical_concept
            for field in self.fields
            if field.canonical_concept is not None and field.confidence >= 0.70
        }


@dataclass(frozen=True)
class DatasetRelationship:
    left_dataset: str
    right_dataset: str
    canonical_concept: str
    left_field: str
    right_field: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class CapabilityRoutingDecision:
    pack_code: str
    rule_code: str
    version: str
    status: str
    required_domains: tuple[str, ...]
    required_canonical_fields: tuple[str, ...]
    matched_domains: tuple[str, ...]
    matched_canonical_fields: tuple[str, ...]
    missing_domains: tuple[str, ...]
    missing_canonical_fields: tuple[str, ...]
    confidence: float


# General operational vocabulary only. These aliases intentionally describe
# common customer-native business language and are not tied to simulations,
# record ids, hidden truth, scenario names, or expected findings.
_CONCEPT_ALIASES: dict[str, frozenset[str]] = {
    "asset_id": frozenset({"asset_id", "equipment_id", "unit_id", "machine_id", "equipment_number"}),
    "work_order_id": frozenset({"work_order_id", "workorder_id", "wo_id", "service_order_id", "service_order_number"}),
    "job_id": frozenset({"job_id", "project_id", "engagement_id", "job_number"}),
    "invoice_id": frozenset({"invoice_id", "invoice_number", "bill_id", "billing_document_id"}),
    "employee_id": frozenset({"employee_id", "technician_id", "worker_id", "crew_member_id"}),
    "operational_event_id": frozenset({"operational_event_id", "event_id", "service_event_id", "activity_id"}),
    "failure_code": frozenset({"failure_code", "fault_code", "issue_code", "defect_code"}),
    "activity_category": frozenset({"activity_category", "activity_type", "event_type", "work_type", "service_type"}),
    "operational_event_status": frozenset({"operational_event_status", "event_status", "activity_status", "work_status", "status"}),
    "scheduled_timestamp": frozenset({"scheduled_timestamp", "scheduled_date", "scheduled_at", "planned_date", "planned_at"}),
    "completed_timestamp": frozenset({"completed_timestamp", "completed_date", "completed_at", "finish_date", "finished_at", "closed_at"}),
    "event_timestamp": frozenset({"event_timestamp", "event_date", "occurred_at", "activity_date"}),
    "labor_hours": frozenset({"labor_hours", "worked_hours", "work_hours", "time_hours", "billable_hours", "hours"}),
    "downtime_hours": frozenset({"downtime_hours", "outage_hours", "down_hours", "offline_hours"}),
    "quantity": frozenset({"quantity", "qty", "units", "unit_quantity"}),
    "rate": frozenset({"rate", "hourly_rate", "labor_rate", "unit_rate", "billing_rate"}),
    "transaction_amount": frozenset({"transaction_amount", "invoice_amount", "billed_amount", "billing_amount", "revenue_amount", "amount"}),
    "repair_cost": frozenset({"repair_cost", "maintenance_cost", "service_cost", "repair_amount"}),
    "currency": frozenset({"currency", "currency_code", "iso_currency"}),
}

_IDENTIFIER_CONCEPTS = frozenset(
    {"asset_id", "work_order_id", "job_id", "invoice_id", "employee_id", "operational_event_id"}
)


def _normalize_name(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value.strip())
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return re.sub(r"_+", "_", text)


def _token_set(value: str) -> set[str]:
    return {part for part in _normalize_name(value).split("_") if part}


def _name_score(source_field: str, alias: str) -> float:
    source = _normalize_name(source_field)
    candidate = _normalize_name(alias)
    if source == candidate:
        return 1.0
    left = _token_set(source)
    right = _token_set(candidate)
    if not left or not right:
        return 0.0
    overlap = len(left & right) / len(left | right)
    if candidate in source or source in candidate:
        overlap = max(overlap, 0.82)
    return overlap


def _infer_field(source_field: str) -> FieldSemantic:
    scored: list[tuple[float, str, str]] = []
    for concept, aliases in _CONCEPT_ALIASES.items():
        for alias in aliases:
            scored.append((_name_score(source_field, alias), concept, alias))
    scored.sort(reverse=True)
    best_score, best_concept, best_alias = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 0.58:
        return FieldSemantic(source_field, None, round(best_score, 4), "no sufficiently strong semantic name match")
    if best_score - second_score < 0.08 and best_score < 0.95:
        return FieldSemantic(source_field, None, round(best_score, 4), "ambiguous semantic name match")
    confidence = 0.98 if best_score == 1.0 else min(0.94, 0.55 + (0.45 * best_score))
    return FieldSemantic(
        source_field=source_field,
        canonical_concept=best_concept,
        confidence=round(confidence, 4),
        evidence=f"field name matched general alias '{best_alias}'",
    )


def _infer_domains(concepts: set[str]) -> set[str]:
    domains: set[str] = set()
    if "invoice_id" in concepts or "transaction_amount" in concepts:
        domains.add("revenue")
    if concepts & {"work_order_id", "job_id", "operational_event_id", "activity_category", "operational_event_status"}:
        domains.add("operations")
    if "asset_id" in concepts and concepts & {
        "failure_code",
        "downtime_hours",
        "repair_cost",
        "scheduled_timestamp",
        "completed_timestamp",
        "activity_category",
    }:
        domains.add("maintenance")
    return domains


def infer_dataset_semantics(dataset_name: str, frame: pd.DataFrame) -> DatasetSemanticProfile:
    fields = tuple(_infer_field(str(column)) for column in frame.columns)
    concepts = {
        field.canonical_concept
        for field in fields
        if field.canonical_concept is not None and field.confidence >= 0.70
    }
    warnings: list[str] = []
    if not concepts:
        warnings.append("NO_HIGH_CONFIDENCE_CANONICAL_CONCEPTS")
    domains = _infer_domains(concepts)
    if not domains:
        warnings.append("NO_HIGH_CONFIDENCE_OPERATIONAL_DOMAIN")
    return DatasetSemanticProfile(
        dataset_name=dataset_name,
        inferred_domains=tuple(sorted(domains)),
        fields=fields,
        warnings=tuple(warnings),
    )


def _series_values(frame: pd.DataFrame, field_name: str) -> set[str]:
    if field_name not in frame.columns:
        return set()
    values: set[str] = set()
    for value in frame[field_name].dropna().head(500).tolist():
        text = str(value).strip()
        if text:
            values.add(text.casefold())
    return values


def infer_relationships(
    datasets: list[tuple[str, pd.DataFrame, DatasetSemanticProfile]],
) -> list[DatasetRelationship]:
    relationships: list[DatasetRelationship] = []
    for left_index, (left_name, left_frame, left_profile) in enumerate(datasets):
        for right_name, right_frame, right_profile in datasets[left_index + 1 :]:
            left_fields = {
                field.canonical_concept: field
                for field in left_profile.fields
                if field.canonical_concept in _IDENTIFIER_CONCEPTS and field.confidence >= 0.70
            }
            right_fields = {
                field.canonical_concept: field
                for field in right_profile.fields
                if field.canonical_concept in _IDENTIFIER_CONCEPTS and field.confidence >= 0.70
            }
            for concept in sorted(set(left_fields) & set(right_fields)):
                left_field = left_fields[concept]
                right_field = right_fields[concept]
                left_values = _series_values(left_frame, left_field.source_field)
                right_values = _series_values(right_frame, right_field.source_field)
                if not left_values or not right_values:
                    continue
                overlap = left_values & right_values
                denominator = min(len(left_values), len(right_values))
                overlap_ratio = len(overlap) / denominator if denominator else 0.0
                if overlap_ratio < 0.10:
                    continue
                confidence = min(
                    left_field.confidence,
                    right_field.confidence,
                    0.65 + min(0.34, overlap_ratio * 0.34),
                )
                relationships.append(
                    DatasetRelationship(
                        left_dataset=left_name,
                        right_dataset=right_name,
                        canonical_concept=concept,
                        left_field=left_field.source_field,
                        right_field=right_field.source_field,
                        confidence=round(confidence, 4),
                        evidence=f"shared {concept} values overlap at {overlap_ratio:.1%}",
                    )
                )
    return relationships


def route_capabilities(
    profiles: Iterable[DatasetSemanticProfile],
    relationships: Iterable[DatasetRelationship],
) -> list[CapabilityRoutingDecision]:
    profiles = list(profiles)
    relationships = list(relationships)
    available_domains = {domain for profile in profiles for domain in profile.inferred_domains}
    available_fields = {concept for profile in profiles for concept in profile.available_concepts}
    relationship_concepts = {relationship.canonical_concept for relationship in relationships}
    decisions: list[CapabilityRoutingDecision] = []
    for capability in default_intelligence_pack_registry().all():
        required_domains = set(capability.required_domains)
        required_fields = set(capability.required_canonical_fields)
        matched_domains = required_domains & available_domains
        matched_fields = required_fields & available_fields
        missing_domains = required_domains - available_domains
        missing_fields = required_fields - available_fields
        total_requirements = len(required_domains) + len(required_fields)
        matched_requirements = len(matched_domains) + len(matched_fields)
        coverage = matched_requirements / total_requirements if total_requirements else 1.0
        # Cross-dataset identity overlap strengthens confidence without
        # inventing a relationship type that the canonical entity layer has
        # not actually established yet.
        identity_bonus = 0.05 if relationship_concepts & required_fields else 0.0
        confidence = min(1.0, coverage + identity_bonus)
        if not missing_domains and not missing_fields:
            status = "ELIGIBLE"
        elif coverage >= 0.50:
            status = "PARTIAL"
        else:
            status = "NOT_ELIGIBLE"
        decisions.append(
            CapabilityRoutingDecision(
                pack_code=capability.pack_code,
                rule_code=capability.rule_code,
                version=capability.version,
                status=status,
                required_domains=tuple(sorted(required_domains)),
                required_canonical_fields=tuple(sorted(required_fields)),
                matched_domains=tuple(sorted(matched_domains)),
                matched_canonical_fields=tuple(sorted(matched_fields)),
                missing_domains=tuple(sorted(missing_domains)),
                missing_canonical_fields=tuple(sorted(missing_fields)),
                confidence=round(confidence, 4),
            )
        )
    return decisions


def analyze_customer_native_datasets(
    datasets: list[tuple[str, pd.DataFrame]],
) -> dict[str, object]:
    profiled = [
        (name, frame, infer_dataset_semantics(name, frame))
        for name, frame in datasets
    ]
    relationships = infer_relationships(profiled)
    decisions = route_capabilities(
        [profile for _, _, profile in profiled],
        relationships,
    )
    warnings = [
        {"dataset": profile.dataset_name, "code": warning}
        for _, _, profile in profiled
        for warning in profile.warnings
    ]
    if not any(decision.status == "ELIGIBLE" for decision in decisions):
        warnings.append(
            {
                "dataset": None,
                "code": "NO_EXISTING_INTELLIGENCE_CAPABILITY_FULLY_ELIGIBLE",
            }
        )
    return {
        "datasets": [asdict(profile) for _, _, profile in profiled],
        "relationships": [asdict(relationship) for relationship in relationships],
        "capability_routing": [asdict(decision) for decision in decisions],
        "warnings": warnings,
    }
