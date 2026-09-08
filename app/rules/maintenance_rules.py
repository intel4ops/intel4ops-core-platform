from __future__ import annotations

import pandas as pd

from app.schemas.contracts import EvidenceCreate, FindingCreate

RULE_ID = "MAINT-001-REPEATED-FAILURE"


def detect_repeated_asset_failures(
    events: pd.DataFrame,
    *,
    currency: str,
) -> list[FindingCreate]:
    required = {"asset_id", "failure_code", "downtime_hours", "repair_cost"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing required maintenance columns: {sorted(missing)}")

    normalized_currency = currency.strip().upper()
    if len(normalized_currency) != 3 or not normalized_currency.isascii() or not normalized_currency.isalpha():
        raise ValueError("currency must be a three-letter ASCII currency code")

    findings: list[FindingCreate] = []
    grouped = events.groupby(["asset_id", "failure_code"], dropna=False)
    for (asset_id, failure_code), group in grouped:
        if len(group) < 3:
            continue

        repair_cost = float(group["repair_cost"].fillna(0).sum())
        downtime = float(group["downtime_hours"].fillna(0).sum())
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
                exposure_low=round(repair_cost, 2),
                exposure_high=round(repair_cost, 2),
                currency=normalized_currency,
                confidence_score=round(confidence, 2),
                ontology_concept_ids=[
                    "Asset",
                    "Failure",
                    "MaintenanceEvent",
                    "Downtime",
                    "ValueExposure",
                ],
                causal_chain_id="ASSET-FAILURE-DOWNTIME-VALUE",
                evidence=evidence,
            )
        )
    return findings
