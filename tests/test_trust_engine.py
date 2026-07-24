import pandas as pd

from app.engines.trust_engine import TrustEngine


def test_trust_engine_detects_missing_and_duplicates() -> None:
    frame = pd.DataFrame(
        [
            {"asset_id": "A1", "status": "up"},
            {"asset_id": "A1", "status": "up"},
            {"asset_id": None, "status": "down"},
        ]
    )
    report = TrustEngine().profile(frame, "assets")
    assert report.row_count == 3
    assert report.overall_trust_score < 1
    assert any(issue.issue_type == "duplicate_rows" for issue in report.issues)
