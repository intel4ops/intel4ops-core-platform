from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import Finding
from app.schemas.findings import FindingSeverity, FindingType
from app.services.governed_finding_publisher import (
    ContributingDataset,
    GovernedFindingRequest,
    governed_finding_publisher,
)


@dataclass(frozen=True)
class MatchContract:
    """Every cross-domain rule declares this explicitly (Section 8) --
    cross-domain intelligence must never infer leakage merely because two
    datasets fail to join. required_time_fields/acceptable_window are
    validated before any matching is attempted."""

    required_entities: frozenset[str]
    primary_match_key: str
    fallback_match_keys: tuple[str, ...]
    required_time_fields: tuple[str, ...]
    acceptable_window: timedelta | None


RULE_A_CONTRACT = MatchContract(
    required_entities=frozenset({"asset"}),
    primary_match_key="asset_id",
    fallback_match_keys=(),
    required_time_fields=("event_date",),
    acceptable_window=None,  # window is the downtime duration itself, computed per row
)
RULE_B_CONTRACT = MatchContract(
    required_entities=frozenset({"operational_event"}),
    primary_match_key="operational_event_id",
    fallback_match_keys=("route_id", "event_date"),
    required_time_fields=("event_date",),
    acceptable_window=timedelta(days=0),
)


def run_asset_failure_to_lost_activity(
    db: Session,
    organization_id: UUID,
    maintenance_dataset_id: UUID,
    maintenance_df: pd.DataFrame,
    operations_dataset_id: UUID,
    operations_df: pd.DataFrame,
    trust_assessment_id: UUID,
    matched_asset_keys: set[str],
    actor_user_id: UUID,
) -> list[Finding]:
    """Rule A: ASSET_FAILURE_TO_LOST_ACTIVITY instance. Fires only for
    assets the entity resolver actually matched across both datasets, and
    only when both sides carry the required time field -- never a fabricated
    overlap."""
    required = {"asset_id", "downtime_hours"}
    if not required <= set(maintenance_df.columns):
        return []
    if "event_date" not in maintenance_df.columns or "event_date" not in operations_df.columns:
        return []  # BLOCKED by missing required time field -- readiness layer already reports this

    published: list[Finding] = []
    maint = maintenance_df.copy()
    maint["event_date"] = pd.to_datetime(maint["event_date"], errors="coerce")
    ops = operations_df.copy()
    ops["event_date"] = pd.to_datetime(ops["event_date"], errors="coerce")

    for asset_id in sorted(matched_asset_keys):
        asset_events = maint[maint["asset_id"].astype(str) == asset_id]
        asset_ops = (
            ops[ops["asset_id"].astype(str) == asset_id]
            if "asset_id" in ops.columns
            else ops.iloc[0:0]
        )
        if asset_events.empty or asset_ops.empty:
            continue
        affected_operational_event_ids: set[str] = set()
        for _, event in asset_events.iterrows():
            if pd.isna(event["event_date"]):
                continue
            downtime_hours = float(event.get("downtime_hours") or 0)
            window_start = event["event_date"]
            window_end = window_start + timedelta(hours=downtime_hours)
            overlapping = asset_ops[
                (asset_ops["event_date"] >= window_start) & (asset_ops["event_date"] <= window_end)
            ]
            if "operational_event_id" in overlapping.columns:
                affected_operational_event_ids.update(
                    str(value) for value in overlapping["operational_event_id"]
                )
        if not affected_operational_event_ids:
            continue
        finding = governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=maintenance_dataset_id,
                trust_assessment_id=trust_assessment_id,
                definition_code="XDOM-A-ASSET-FAILURE-LOST-ACTIVITY",
                definition_version="1.0",
                rule_condition_code="downtime_window_overlaps_operational_event",
                affected_record_count=len(affected_operational_event_ids),
                title=f"Asset {asset_id} failure downtime overlapped scheduled activity",
                summary=(
                    f"{len(affected_operational_event_ids)} operational event(s) for asset "
                    f"{asset_id} fall within a recorded maintenance downtime window."
                ),
                domain_code="cross_domain",
                severity=FindingSeverity.HIGH,
                finding_type=FindingType.EXCEPTION,
                actor_user_id=actor_user_id,
                contributing_datasets=[ContributingDataset(dataset_id=operations_dataset_id)],
                entities=[{"entity_type": "asset", "canonical_key": asset_id}],
                domains=["maintenance", "operations"],
                economic_status="governed_pending",
                limitations=["Observed operational impact only -- no economic value estimated."],
            ),
        )
        if finding is not None:
            published.append(finding)
    return published


def run_lost_activity_to_revenue_gap(
    db: Session,
    organization_id: UUID,
    operations_dataset_id: UUID,
    operations_df: pd.DataFrame,
    revenue_dataset_id: UUID,
    revenue_df: pd.DataFrame,
    trust_assessment_id: UUID,
    actor_user_id: UUID,
) -> list[Finding]:
    """Rule B: LOST_ACTIVITY_TO_REVENUE_GAP instance. Distinguishes a
    genuine 'matched, no revenue' finding from a 'could not be reliably
    matched' data-linkage issue (Section 8) -- never conflates the two."""
    if "operational_event_status" not in operations_df.columns:
        return []
    completed = operations_df[
        operations_df["operational_event_status"].astype(str).str.lower() == "completed"
    ]
    if completed.empty:
        return []

    has_direct_key = (
        "operational_event_id" in completed.columns and "operational_event_id" in revenue_df.columns
    )
    has_fallback_key = (
        "route_id" in completed.columns
        and "route_id" in revenue_df.columns
        and "event_date" in completed.columns
        and "event_date" in revenue_df.columns
    )
    if not has_direct_key and not has_fallback_key:
        # No shared identifier at all -- this is a reconciliation/data-
        # semantic issue, never reported as "missing revenue".
        finding = governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=operations_dataset_id,
                trust_assessment_id=trust_assessment_id,
                definition_code="XDOM-DATA-LINKAGE-ISSUE",
                definition_version="1.0",
                rule_condition_code="no_shared_match_key_operations_revenue",
                affected_record_count=len(completed),
                title="Operational activity could not be reliably matched to revenue records",
                summary=(
                    f"{len(completed)} completed operational event(s) share no identifier "
                    "(operational_event_id, or route_id + date) with the revenue dataset -- "
                    "a data/semantic reconciliation issue, not a revenue-integrity finding."
                ),
                domain_code="cross_domain",
                severity=FindingSeverity.LOW,
                finding_type=FindingType.RECONCILIATION,
                actor_user_id=actor_user_id,
                contributing_datasets=[ContributingDataset(dataset_id=revenue_dataset_id)],
                domains=["operations", "revenue"],
                economic_status="governed_pending",
                limitations=["No shared match key -- linkage issue only, not a leakage claim."],
            ),
        )
        return [finding] if finding is not None else []

    if has_direct_key:
        matched_ids = set(revenue_df["operational_event_id"].astype(str))
        unmatched = completed[~completed["operational_event_id"].astype(str).isin(matched_ids)]
    else:
        revenue_keys = set(
            zip(
                revenue_df["route_id"].astype(str),
                pd.to_datetime(revenue_df["event_date"], errors="coerce").dt.date,
            )
        )
        completed = completed.copy()
        completed["_event_date_only"] = pd.to_datetime(
            completed["event_date"], errors="coerce"
        ).dt.date
        unmatched = completed[
            ~completed.apply(
                lambda row: (str(row["route_id"]), row["_event_date_only"]) in revenue_keys, axis=1
            )
        ]

    if unmatched.empty:
        return []

    finding = governed_finding_publisher.publish(
        db,
        GovernedFindingRequest(
            organization_id=organization_id,
            primary_dataset_id=operations_dataset_id,
            trust_assessment_id=trust_assessment_id,
            definition_code="XDOM-B-LOST-ACTIVITY-REVENUE-GAP",
            definition_version="1.0",
            rule_condition_code="completed_event_without_matching_revenue",
            affected_record_count=len(unmatched),
            title="Completed operational activity without linked revenue",
            summary=(
                f"{len(unmatched)} completed operational event(s) have no matching revenue record."
            ),
            domain_code="cross_domain",
            severity=FindingSeverity.MEDIUM,
            finding_type=FindingType.EXCEPTION,
            actor_user_id=actor_user_id,
            contributing_datasets=[ContributingDataset(dataset_id=revenue_dataset_id)],
            domains=["operations", "revenue"],
            economic_status="governed_pending",
            limitations=["Observed activity/revenue-presence gap only -- no amount estimated."],
        ),
    )
    return [finding] if finding is not None else []
