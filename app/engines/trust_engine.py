from __future__ import annotations

import pandas as pd

from app.schemas.contracts import TrustIssue, TrustReport


class TrustEngine:
    """Deterministic dataset trust profiling for Phase 2."""

    def profile(self, dataframe: pd.DataFrame, dataset_name: str) -> TrustReport:
        issues: list[TrustIssue] = []
        rows = len(dataframe)
        cells = max(rows * max(len(dataframe.columns), 1), 1)
        missing = int(dataframe.isna().sum().sum())
        completeness = max(0.0, 1 - missing / cells)

        duplicate_rows = int(dataframe.duplicated().sum()) if rows else 0
        duplicate_score = 1.0 if rows == 0 else max(0.0, 1 - duplicate_rows / rows)

        for column in dataframe.columns:
            null_count = int(dataframe[column].isna().sum())
            if null_count:
                issues.append(
                    TrustIssue(
                        field=str(column),
                        issue_type="missing_values",
                        message=f"{null_count} missing values detected",
                    )
                )

        if duplicate_rows:
            issues.append(
                TrustIssue(
                    issue_type="duplicate_rows",
                    message=f"{duplicate_rows} fully duplicated rows detected",
                )
            )

        validity = 1.0
        overall = round((completeness * 0.45) + (duplicate_score * 0.25) + (validity * 0.30), 4)
        return TrustReport(
            dataset_name=dataset_name,
            row_count=rows,
            completeness_score=round(completeness, 4),
            duplicate_score=round(duplicate_score, 4),
            validity_score=validity,
            overall_trust_score=overall,
            issues=issues,
        )
