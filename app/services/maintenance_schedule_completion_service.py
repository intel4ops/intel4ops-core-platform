from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

# ---------------------------------------------------------------------------
# P3.xxI.6 (GAP-007): MAINTENANCE-SCHEDULE-COMPLETION-GAP. A scheduled
# maintenance event with no completed timestamp is a governed, structural
# signal on its own -- it never depends on an invented "materially late"
# day-count threshold or on any specific activity-category label
# (e.g. "PM"). Corrective-maintenance-shaped rows in this platform's real
# Wave 1 corpus never carry a scheduled timestamp at all, so this rule
# naturally never fires on them without needing to name them. This rule
# reports an observed scheduling gap only -- it never asserts a policy
# violation and never estimates an incremental corrective-cost exposure,
# since no governed cost-impact evidence for a maintenance event that never
# happened exists in customer-visible data.
# ---------------------------------------------------------------------------

RULE_CODE = "MAINTENANCE-SCHEDULE-COMPLETION-GAP"


@dataclass(frozen=True)
class ScheduledMaintenanceDatasetFields:
    dataset_id: UUID
    dataset_label: str
    dataframe: pd.DataFrame
    trust_assessment_id: UUID
    subject_id_field: str
    event_id_field: str
    scheduled_timestamp_field: str
    completed_timestamp_field: str
    canonical_evidence_completeness: CanonicalEvidenceCompletenessResult | None = None


@dataclass(frozen=True)
class ScheduleGapEvidence:
    dataset: ScheduledMaintenanceDatasetFields
    row_reference: str
    subject_key: str
    event_key: str
    scheduled_at: datetime


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
    return parsed.to_pydatetime()


def find_incomplete_scheduled_maintenance(
    datasets: list[ScheduledMaintenanceDatasetFields], eligible_subject_keys: set[str]
) -> list[ScheduleGapEvidence]:
    """A scheduled maintenance event never becomes eligible unless its own
    dataset independently resolves BOTH a governed scheduled and a governed
    completed timestamp concept -- resolving only one of the two never lets
    a missing VALUE be confused with a missing CONCEPT (the same
    NO_GOVERNED_EVIDENCE-vs-CONFIRMED_ZERO discipline
    revenue_variance_intelligence_service.py already applies). Once both
    concepts are governed for a dataset, an individual row's genuinely
    empty completed-timestamp value is legitimate, structural evidence
    that the scheduled event never completed -- never inferred, never
    threshold-derived.

    Conflicting representations of the same event (different datasets
    disagreeing on its scheduled timestamp or completion state) abstain,
    exactly like build_repeat_visit_pairs's own duplicate-representation
    rule -- their state cannot be governed deterministically."""

    representations: dict[tuple[str, str], list[tuple[ScheduleGapEvidence, bool]]] = {}
    for dataset in datasets:
        required_fields = {
            dataset.subject_id_field,
            dataset.event_id_field,
            dataset.scheduled_timestamp_field,
            dataset.completed_timestamp_field,
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
            event_key = _text(row[dataset.event_id_field])
            scheduled_at = _timestamp(row[dataset.scheduled_timestamp_field])
            completed_at = _timestamp(row[dataset.completed_timestamp_field])
            if subject_key is None or subject_key not in eligible_subject_keys:
                continue
            if event_key is None or scheduled_at is None:
                continue
            evidence = ScheduleGapEvidence(
                dataset=dataset,
                row_reference=str(row_index),
                subject_key=subject_key,
                event_key=event_key,
                scheduled_at=scheduled_at,
            )
            representations.setdefault((subject_key, event_key), []).append(
                (evidence, completed_at is None)
            )

    gaps: list[ScheduleGapEvidence] = []
    for event_representations in representations.values():
        signatures = {
            (item.subject_key, item.scheduled_at, incomplete)
            for item, incomplete in event_representations
        }
        if len(signatures) != 1:
            continue
        _, incomplete = event_representations[0]
        if not incomplete:
            continue
        best = min(
            (item for item, _ in event_representations),
            key=lambda item: (
                item.dataset.dataset_label.casefold(),
                str(item.dataset.dataset_id),
                item.row_reference,
            ),
        )
        gaps.append(best)

    return sorted(
        gaps,
        key=lambda g: (g.subject_key.casefold(), g.scheduled_at, g.event_key.casefold()),
    )


def run_maintenance_schedule_completion(
    db: Session,
    organization_id: UUID,
    datasets: list[ScheduledMaintenanceDatasetFields],
    eligible_subject_keys: set[str],
    actor_user_id: UUID,
) -> list[Finding]:
    """Publish an observed scheduled-maintenance completion gap. Never
    asserts a policy violation and never estimates a corrective-cost
    exposure -- no governed cost-impact evidence for maintenance that
    never happened exists in customer-visible data."""

    published: list[Finding] = []
    for gap in find_incomplete_scheduled_maintenance(datasets, eligible_subject_keys):
        finding = governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=gap.dataset.dataset_id,
                trust_assessment_id=gap.dataset.trust_assessment_id,
                definition_code=RULE_CODE,
                definition_version="1.0",
                rule_condition_code="scheduled_maintenance_not_completed",
                affected_record_count=1,
                title=f"Scheduled maintenance not completed for asset {gap.subject_key}",
                summary=(
                    f"Asset {gap.subject_key} has maintenance event {gap.event_key} "
                    f"scheduled for {gap.scheduled_at.isoformat()} with no governed "
                    f"completion timestamp on file."
                ),
                domain_code="maintenance",
                severity=FindingSeverity.MEDIUM,
                finding_type=FindingType.RISK,
                actor_user_id=actor_user_id,
                contributing_datasets=[ContributingDataset(dataset_id=gap.dataset.dataset_id)],
                entities=[
                    {"entity_type": "asset", "canonical_key": gap.subject_key},
                    {
                        "entity_type": "maintenance_event",
                        "canonical_key": gap.event_key,
                        "role": "incomplete_scheduled_event",
                    },
                ],
                identity_references=[
                    StableFindingIdentityReference(
                        identity_role="subject",
                        reference_type="asset",
                        canonical_reference=gap.subject_key,
                        canonical_entity="asset",
                    ),
                    StableFindingIdentityReference(
                        identity_role="material_condition",
                        reference_type="scheduled_event_identity",
                        canonical_reference=gap.event_key,
                        canonical_entity="maintenance_event",
                    ),
                ],
                domains=["maintenance"],
                economic_status="governed_pending",
                limitations=[
                    "Observed scheduling gap only -- no governed cost-impact evidence "
                    "for maintenance that never occurred exists in customer-visible "
                    "data, so no corrective-cost exposure is estimated.",
                    "This finding does not assert that the maintenance was skipped "
                    "for cause, only that no completion timestamp is on file as of "
                    "this run.",
                ],
                supporting_evidence=[
                    EvidenceItemCreate(
                        evidence_type=EvidenceType.AFFECTED_RECORD,
                        reference_type="scheduled_event",
                        reference_id=gap.event_key,
                        dataset_id=gap.dataset.dataset_id,
                        canonical_entity="maintenance_event",
                        canonical_record_reference=gap.event_key,
                        label="Scheduled maintenance event",
                        description=(
                            f"Event {gap.event_key} on asset {gap.subject_key} was "
                            f"scheduled for {gap.scheduled_at.isoformat()}; the "
                            f"governed completion timestamp field is empty for this row."
                        ),
                        metadata={
                            "row_reference": gap.row_reference,
                            "scheduled_at": gap.scheduled_at.isoformat(),
                            "policy_violation_asserted": False,
                        },
                    ),
                ],
                canonical_evidence_completeness=gap.dataset.canonical_evidence_completeness,
            ),
        )
        if finding is not None:
            published.append(finding)
    return published
