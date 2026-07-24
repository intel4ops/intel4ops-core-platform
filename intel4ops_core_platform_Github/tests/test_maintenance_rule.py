import pandas as pd

from app.rules.maintenance_rules import detect_repeated_asset_failures


def test_repeated_failures_create_finding():
    frame = pd.DataFrame([
        {"asset_id": "BUS-1", "failure_code": "BRAKE", "downtime_hours": 4, "repair_cost": 200},
        {"asset_id": "BUS-1", "failure_code": "BRAKE", "downtime_hours": 5, "repair_cost": 250},
        {"asset_id": "BUS-1", "failure_code": "BRAKE", "downtime_hours": 6, "repair_cost": 300},
    ])
    findings = detect_repeated_asset_failures(frame)
    assert len(findings) == 1
    assert findings[0].confidence_score > 0.5
    assert findings[0].exposure_high > findings[0].exposure_low
