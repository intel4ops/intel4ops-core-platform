from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import Finding
from app.schemas.findings import EvidenceItemCreate, EvidenceType, FindingSeverity, FindingType
from app.services.canonical_evidence_completeness import CanonicalEvidenceCompletenessResult
from app.services.governed_finding_publisher import (
    ContributingDataset,
    GovernedFindingRequest,
    StableFindingIdentityReference,
    governed_finding_publisher,
)

RULE_CODE = "MAINTENANCE-REPEAT-VISIT"


@dataclass(frozen=True)
class InterventionDatasetFields:
    dataset_id: UUID
    dataset_label: str
    dataframe: pd.DataFrame
    trust_assessment_id: UUID
    subject_id_field: str
    intervention_id_field: str
    timestamp_field: str
    activity_category_field: str
    canonical_evidence_completeness: CanonicalEvidenceCompletenessResult | None = None


@dataclass(frozen=True)
class InterventionEvidence:
    dataset: InterventionDatasetFields
    row_reference: str
    subject_key: str
    intervention_key: str
    occurred_at: datetime
    activity_category: str
    normalized_activity_category: str


@dataclass(frozen=True)
class RepeatVisitPair:
    prior: InterventionEvidence
    subsequent: InterventionEvidence
    elapsed_hours: Decimal


def _text(value: object) -> str | None:
    if value is None or pd.isna(value):  # type: ignore[call-overload]
        return None
    normalized = str(value).strip()
    return normalized or None


def _timestamp(value: object) -> datetime | None:
    if value is None or pd.isna(value):  # type: ignore[call-overload]
        return None
    parsed = pd.to_datetime(str(value), errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime()
    if isinstance(parsed, datetime):
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def build_repeat_visit_pairs(
    datasets: list[InterventionDatasetFields], eligible_subject_keys: set[str]
) -> list[RepeatVisitPair]:
    """Pair adjacent, exactly related interventions without inventing a policy window.

    Intervention identity is authoritative for duplicate suppression. Conflicting
    representations of one identity and distinct identities tied at one timestamp
    abstain because their sequence cannot be governed deterministically.
    """

    representations: dict[tuple[str, str], list[InterventionEvidence]] = {}
    for dataset in datasets:
        required_fields = {
            dataset.subject_id_field,
            dataset.intervention_id_field,
            dataset.timestamp_field,
            dataset.activity_category_field,
        }
        if not required_fields <= set(dataset.dataframe.columns):
            continue
        if (
            dataset.canonical_evidence_completeness is not None
            and not dataset.canonical_evidence_completeness.satisfied
        ):
            continue
        for row_index, row in dataset.dataframe.iterrows():
            subject_key = _text(row[dataset.subject_id_field])
            intervention_key = _text(row[dataset.intervention_id_field])
            occurred_at = _timestamp(row[dataset.timestamp_field])
            category = _text(row[dataset.activity_category_field])
            if (
                subject_key is None
                or subject_key not in eligible_subject_keys
                or intervention_key is None
                or occurred_at is None
                or category is None
            ):
                continue
            evidence = InterventionEvidence(
                dataset=dataset,
                row_reference=str(row_index),
                subject_key=subject_key,
                intervention_key=intervention_key,
                occurred_at=occurred_at,
                activity_category=category,
                normalized_activity_category=category.casefold(),
            )
            representations.setdefault((subject_key, intervention_key), []).append(evidence)

    deduplicated: list[InterventionEvidence] = []
    for event_representations in representations.values():
        signatures = {
            (
                item.subject_key,
                item.normalized_activity_category,
                item.occurred_at,
            )
            for item in event_representations
        }
        if len(signatures) != 1:
            continue
        deduplicated.append(
            min(
                event_representations,
                key=lambda item: (
                    item.dataset.dataset_label.casefold(),
                    str(item.dataset.dataset_id),
                    item.row_reference,
                ),
            )
        )

    related_groups: dict[tuple[str, str], list[InterventionEvidence]] = {}
    for intervention in deduplicated:
        related_groups.setdefault(
            (intervention.subject_key, intervention.normalized_activity_category), []
        ).append(intervention)

    pairs: list[RepeatVisitPair] = []
    for interventions in related_groups.values():
        timestamp_counts: dict[datetime, int] = {}
        for intervention in interventions:
            timestamp_counts[intervention.occurred_at] = (
                timestamp_counts.get(intervention.occurred_at, 0) + 1
            )
        if any(count > 1 for count in timestamp_counts.values()):
            continue

        ordered = sorted(
            interventions,
            key=lambda item: (item.occurred_at, item.intervention_key.casefold()),
        )
        for prior, subsequent in zip(ordered, ordered[1:], strict=False):
            elapsed_seconds = Decimal(
                str((subsequent.occurred_at - prior.occurred_at).total_seconds())
            )
            if elapsed_seconds <= 0:
                continue
            pairs.append(
                RepeatVisitPair(
                    prior=prior,
                    subsequent=subsequent,
                    elapsed_hours=elapsed_seconds / Decimal("3600"),
                )
            )

    return sorted(
        pairs,
        key=lambda pair: (
            pair.prior.subject_key.casefold(),
            pair.prior.normalized_activity_category,
            pair.prior.occurred_at,
            pair.prior.intervention_key.casefold(),
            pair.subsequent.intervention_key.casefold(),
        ),
    )


def _intervention_evidence(intervention: InterventionEvidence, role: str) -> EvidenceItemCreate:
    return EvidenceItemCreate(
        evidence_type=EvidenceType.AFFECTED_RECORD,
        reference_type=f"{role}_intervention",
        reference_id=intervention.intervention_key,
        dataset_id=intervention.dataset.dataset_id,
        canonical_entity="work_order",
        canonical_record_reference=intervention.intervention_key,
        label=f"{role.title()} related intervention",
        description=(
            f"Intervention {intervention.intervention_key} on subject "
            f"{intervention.subject_key} has governed activity category "
            f"{intervention.activity_category} and timestamp "
            f"{intervention.occurred_at.isoformat()}."
        ),
        metadata={
            "role": role,
            "row_reference": intervention.row_reference,
            "activity_category": intervention.activity_category,
            "occurred_at": intervention.occurred_at.isoformat(),
        },
    )


def run_maintenance_repeat_visit(
    db: Session,
    organization_id: UUID,
    datasets: list[InterventionDatasetFields],
    eligible_subject_keys: set[str],
    actor_user_id: UUID,
) -> list[Finding]:
    """Publish observed related repeat-intervention pairs, never policy violations."""

    published: list[Finding] = []
    for pair in build_repeat_visit_pairs(datasets, eligible_subject_keys):
        prior = pair.prior
        subsequent = pair.subsequent
        contributing = []
        if prior.dataset.dataset_id != subsequent.dataset.dataset_id:
            contributing.append(ContributingDataset(dataset_id=prior.dataset.dataset_id))
        finding = governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=subsequent.dataset.dataset_id,
                trust_assessment_id=subsequent.dataset.trust_assessment_id,
                definition_code=RULE_CODE,
                definition_version="1.0",
                rule_condition_code="related_subsequent_intervention_observed",
                affected_record_count=2,
                title=f"Related repeat intervention observed for asset {prior.subject_key}",
                summary=(
                    f"Asset {prior.subject_key} had intervention {subsequent.intervention_key} "
                    f"after related {prior.activity_category} intervention "
                    f"{prior.intervention_key}; observed recurrence interval is "
                    f"{pair.elapsed_hours} hours."
                ),
                domain_code="maintenance",
                severity=FindingSeverity.INFO,
                finding_type=FindingType.RISK,
                actor_user_id=actor_user_id,
                contributing_datasets=contributing,
                entities=[
                    {"entity_type": "asset", "canonical_key": prior.subject_key},
                    {
                        "entity_type": "work_order",
                        "canonical_key": prior.intervention_key,
                        "role": "prior_intervention",
                    },
                    {
                        "entity_type": "work_order",
                        "canonical_key": subsequent.intervention_key,
                        "role": "subsequent_intervention",
                    },
                ],
                identity_references=[
                    StableFindingIdentityReference(
                        identity_role="subject",
                        reference_type="asset",
                        canonical_reference=prior.subject_key,
                        canonical_entity="asset",
                    ),
                    StableFindingIdentityReference(
                        identity_role="material_condition",
                        reference_type="prior_intervention",
                        canonical_reference=prior.intervention_key,
                        canonical_entity="work_order",
                    ),
                    StableFindingIdentityReference(
                        identity_role="material_condition",
                        reference_type="subsequent_intervention",
                        canonical_reference=subsequent.intervention_key,
                        canonical_entity="work_order",
                    ),
                    StableFindingIdentityReference(
                        identity_role="material_condition",
                        reference_type="activity_category",
                        canonical_reference=prior.normalized_activity_category,
                    ),
                ],
                domains=["maintenance"],
                economic_status="governed_pending",
                limitations=[
                    "Observed related-intervention interval only; no repeat/rework policy "
                    "window was supplied, so this finding does not assert a policy violation.",
                    "Economic exposure is not estimated because no governed rework cost is "
                    "attributable to this pair.",
                ],
                supporting_evidence=[
                    _intervention_evidence(prior, "prior"),
                    _intervention_evidence(subsequent, "subsequent"),
                    EvidenceItemCreate(
                        evidence_type=EvidenceType.CALCULATION_TRACE,
                        reference_type="repeat_interval",
                        reference_id=(f"{prior.intervention_key}->{subsequent.intervention_key}"),
                        dataset_id=subsequent.dataset.dataset_id,
                        label="Observed recurrence interval",
                        description=(
                            f"{subsequent.occurred_at.isoformat()} minus "
                            f"{prior.occurred_at.isoformat()} equals "
                            f"{pair.elapsed_hours} hours."
                        ),
                        comparison_value=pair.elapsed_hours,
                        comparison_unit="hours",
                        metadata={"policy_violation_asserted": False},
                    ),
                ],
                canonical_evidence_completeness=(
                    subsequent.dataset.canonical_evidence_completeness
                ),
            ),
        )
        if finding is not None:
            published.append(finding)
    return published
