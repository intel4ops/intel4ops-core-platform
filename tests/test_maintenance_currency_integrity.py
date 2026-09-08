import pandas as pd
import pytest

from app.rules.maintenance_rules import detect_repeated_asset_failures


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "BUS-014",
                "failure_code": "BATTERY",
                "downtime_hours": 18.6,
                "repair_cost": 127125.0,
            },
            {
                "asset_id": "BUS-014",
                "failure_code": "BATTERY",
                "downtime_hours": 17.6,
                "repair_cost": 90919.0,
            },
            {
                "asset_id": "BUS-014",
                "failure_code": "BATTERY",
                "downtime_hours": 3.9,
                "repair_cost": 47099.0,
            },
        ]
    )


def test_maint_001_uses_governed_currency_without_unpriced_downtime_uplift() -> None:
    findings = detect_repeated_asset_failures(_events(), currency="XOF")

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "MAINT-001-REPEATED-FAILURE"
    assert finding.currency == "XOF"
    assert finding.exposure_low == 265143.0
    assert finding.exposure_high == 265143.0
    assert "40.1 downtime hours" in finding.summary


def test_maint_001_normalizes_currency_code() -> None:
    finding = detect_repeated_asset_failures(_events(), currency="xof")[0]
    assert finding.currency == "XOF"


def test_maint_001_rejects_invalid_currency_code() -> None:
    with pytest.raises(ValueError, match="three-letter ASCII currency code"):
        detect_repeated_asset_failures(_events(), currency="US$")
