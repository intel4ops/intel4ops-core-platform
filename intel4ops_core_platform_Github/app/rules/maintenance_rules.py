from __future__ import annotations

import pandas as pd

from app.schemas.contracts import EvidenceCreate, FindingCreate


RULE_ID = "MAINT-001-REPEATED-FAILURE"


def detect_repeated_asset_failures(events: pd.DataFrame) -> list[FindingCreate]:
    required = {"asset_id", "failure_code", "downtime_hours", "repair_cost"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing required maintenance columns: {sorted(missing)}")

    findings: list[FindingCreate] = []
    grouped = events.groupby(["asset_id", "failure_code"], dropna=False)
    for (asset_id, failure_code), group in grouped:
        if len(group) < 3:
            continue

        repair_cost = float(group["repair_cost"].fillna(0).sum())
        downtime = float(group["downtime_hours"].fillna(0).sum())
        exposure_low = repair_cost + downtime * 100
        exposure_high = repair_cost + downtime * 250
        confidence = min(0.95, 0.55 + (len(group) * 0.07))

        evidence = [
            EvidenceCreate(
                source_system="maintenance_upload",
                source_record_id=str(index),
                evidence_type="maintenance_event",
                payload=row.dropna().to_dict(),
            )
            for index, row in group.iterrows()
        ]

        findings.append(
            FindingCreate(
                rule_id=RULE_ID,
                title=f"Repeated {failure_code} failure on asset {asset_id}",
                summary=(
                    f"Asset {asset_id} recorded {len(group)} repeated {failure_code} failures "
                    f"causing {downtime:.1f} downtime hours."
                ),
                domain="maintenance",
                severity="high" if downtime >= 24 else "medium",
                priority=1 if downtime >= 24 else 2,
                exposure_low=round(exposure_low, 2),
                exposure_high=round(exposure_high, 2),
                currency="USD",
                confidence_score=round(confidence, 2),
                ontology_concept_ids=["Asset", "Failure", "MaintenanceEvent", "Downtime", "ValueExposure"],
                causal_chain_id="ASSET-FAILURE-DOWNTIME-VALUE",
                evidence=evidence,
            )
        )
    return findings
