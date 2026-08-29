from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Section 11/29: deterministic representative sampling. Produces a small,
# bounded sample suitable for a semantic AI proposal (never the full
# dataset) -- covers head/tail, rare and common categories, null vs.
# non-null, and numeric/date range extremes so the sample is genuinely
# representative rather than just "the first N rows."
# ---------------------------------------------------------------------------

_DEFAULT_SAMPLE_SIZE = 12


def representative_sample(series: pd.Series, sample_size: int = _DEFAULT_SAMPLE_SIZE) -> list[str]:
    non_null = series.dropna()
    if non_null.empty:
        return []

    parts: list[pd.Series] = []
    remaining = sample_size

    head_n = min(2, remaining, len(non_null))
    parts.append(non_null.head(head_n))
    remaining -= head_n

    tail_n = min(2, remaining, len(non_null))
    if tail_n:
        parts.append(non_null.tail(tail_n))
        remaining -= tail_n

    if pd.api.types.is_numeric_dtype(non_null) and remaining:
        extremes = pd.Series([non_null.min(), non_null.max()])
        take = min(2, remaining, len(extremes))
        parts.append(extremes.head(take))
        remaining -= take

    if remaining:
        value_counts = non_null.astype(str).value_counts()
        if not value_counts.empty:
            rare_n = min(remaining // 2 or 1, len(value_counts))
            rare_values = value_counts.tail(rare_n).index.tolist()
            parts.append(pd.Series(rare_values))
            remaining -= len(rare_values)

    if remaining:
        value_counts = non_null.astype(str).value_counts()
        if not value_counts.empty:
            common_n = min(remaining, len(value_counts))
            common_values = value_counts.head(common_n).index.tolist()
            parts.append(pd.Series(common_values))

    combined = pd.concat(parts) if parts else pd.Series([], dtype=object)
    seen: list[str] = []
    for value in combined.astype(str):
        if value not in seen:
            seen.append(value)
        if len(seen) >= sample_size:
            break
    return seen


def has_null_and_non_null(series: pd.Series) -> tuple[bool, bool]:
    return bool(series.isna().any()), bool(series.notna().any())
