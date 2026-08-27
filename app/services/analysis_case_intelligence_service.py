from __future__ import annotations

from uuid import UUID

import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import Finding
from app.rules.maintenance_rules import detect_repeated_asset_failures
from app.schemas.findings import FindingSeverity, FindingType
from app.services.governed_finding_publisher import (
    GovernedFindingRequest,
    governed_finding_publisher,
)


def run_maintenance_pack(
    db: Session,
    organization_id: UUID,
    dataset_id: UUID,
    trust_assessment_id: UUID,
    canonical_dataframe: pd.DataFrame,
    actor_user_id: UUID,
) -> list[Finding]:
    """Reuses the same MAINT-001 threshold identity (>=3 repeated failures
    for the same asset+failure_code, verified against
    detect_repeated_asset_failures's own validation of required columns
    below) but discards its legacy hard-coded USD exposure computation
    entirely -- only the observed failure_count/downtime facts are carried
    into the governed pipeline (economic_status=governed_pending). The
    standalone legacy endpoint keeps calling detect_repeated_asset_failures
    directly, unmodified, per 'do not change legacy maintenance
    economics'."""
    detect_repeated_asset_failures(canonical_dataframe)  # validates required columns are present
    published: list[Finding] = []
    grouped = canonical_dataframe.groupby(["asset_id", "failure_code"], dropna=False)
    for (asset_id, failure_code), group in grouped:
        if len(group) < 3:
            continue
        downtime = float(group["downtime_hours"].fillna(0).sum())
        finding = governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=dataset_id,
                trust_assessment_id=trust_assessment_id,
                definition_code="MAINT-001-REPEATED-FAILURE",
                definition_version="1.0",
                rule_condition_code="repeated_failure_count_gte_3",
                affected_record_count=len(group),
                title=f"Repeated {failure_code} failure on asset {asset_id}",
                summary=(
                    f"Asset {asset_id} recorded {len(group)} repeated {failure_code} failures "
                    f"causing {downtime:.1f} downtime hours."
                ),
                domain_code="maintenance",
                severity=FindingSeverity.HIGH if downtime >= 24 else FindingSeverity.MEDIUM,
                finding_type=FindingType.EXCEPTION,
                actor_user_id=actor_user_id,
                entities=[{"entity_type": "asset", "canonical_key": str(asset_id)}],
                domains=["maintenance"],
                economic_status="governed_pending",
                limitations=[
                    "Economic exposure not computed -- legacy USD-per-hour assumption is not "
                    "carried into governed Analysis Case findings."
                ],
            ),
        )
        if finding is not None:
            published.append(finding)
    return published
