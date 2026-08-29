from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------
# Deterministic, scalable dataset profiling -- section 3. Never sends a
# dataset (or any row-level content) to an AI provider; this module has no
# network dependency at all. Pattern detection is regex/dtype-based only,
# generic across industries (currency-like, identifier-like, url/email/
# phone-like -- never a client-specific column name).
# ---------------------------------------------------------------------------

_MAX_SAMPLE_VALUES = 5
_CATEGORICAL_MAX_DISTINCT_RATIO = 0.2
_IDENTIFIER_MIN_UNIQUENESS_RATIO = 0.95

_CURRENCY_PATTERN = re.compile(r"^[$€£¥]?\s?-?\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{1,4})?\s?[A-Z]{0,3}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"^\+?[\d\s().-]{7,20}$")
_UNIT_SUFFIX_PATTERN = re.compile(
    r"(hours?|hrs?|kg|lbs?|km|miles?|liters?|gallons?|units?|pcs|%|percent)$", re.IGNORECASE
)
_ISO_CURRENCY_CODES = frozenset(
    {"USD", "EUR", "GBP", "XOF", "CAD", "AUD", "JPY", "CNY", "INR", "BRL", "MXN", "NGN", "ZAR"}
)


@dataclass(frozen=True)
class FieldProfile:
    source_field: str
    physical_type: str
    null_count: int
    row_count: int
    null_rate: float
    distinct_count: int
    uniqueness_ratio: float
    sample_values: list[str] = field(default_factory=list)
    value_patterns: list[str] = field(default_factory=list)
    min_value: str | None = None
    max_value: str | None = None
    is_date_like: bool = False
    is_numeric_like: bool = False
    is_candidate_identifier: bool = False
    is_candidate_categorical: bool = False
    is_currency_like: bool = False
    is_unit_like: bool = False
    is_email_like: bool = False
    is_url_like: bool = False
    is_phone_like: bool = False
    detected_currency_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DatasetProfile:
    dataset_label: str
    row_count: int
    column_count: int
    fields: list[FieldProfile]
    candidate_grain: list[str]
    candidate_primary_keys: list[str]
    candidate_foreign_keys: list[str]
    is_append_or_event_like: bool
    is_snapshot_like: bool
    is_master_or_reference_like: bool
    is_transaction_like: bool
    is_ledger_like: bool
    is_measurement_like: bool


def _sample_values(series: pd.Series) -> list[str]:
    non_null = series.dropna()
    if non_null.empty:
        return []
    values = non_null.astype(str).unique()[:_MAX_SAMPLE_VALUES]
    return [str(v) for v in values]


def _value_patterns(series: pd.Series) -> list[str]:
    """A handful of generic shape signatures -- never a specific client
    format string. E.g. "digits", "alpha_dash_digits", "iso_date"."""
    non_null = series.dropna().astype(str)
    if non_null.empty:
        return []
    patterns: set[str] = set()
    for value in non_null.head(50):
        if value.isdigit():
            patterns.add("digits")
        elif re.fullmatch(r"[A-Za-z]+-?\d+", value):
            patterns.add("alpha_dash_digits")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ].*)?", value):
            patterns.add("iso_date")
        elif re.fullmatch(r"-?\d+\.\d+", value):
            patterns.add("decimal")
        elif value.isupper():
            patterns.add("upper_alpha")
        else:
            patterns.add("free_text")
    return sorted(patterns)


def _detect_currency_codes(series: pd.Series) -> list[str]:
    non_null = series.dropna().astype(str)
    found = {
        v.strip().upper() for v in non_null.unique() if v.strip().upper() in _ISO_CURRENCY_CODES
    }
    return sorted(found)


def _is_date_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    non_null = series.dropna().astype(str).head(20)
    if non_null.empty:
        return False
    try:
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return False
    return bool(parsed.notna().mean() >= 0.8)


def _profile_field(name: str, series: pd.Series, row_count: int) -> FieldProfile:
    null_count = int(series.isna().sum())
    non_null = series.dropna()
    distinct_count = int(non_null.nunique())
    null_rate = (null_count / row_count) if row_count else 0.0
    uniqueness_ratio = (distinct_count / len(non_null)) if len(non_null) else 0.0
    is_numeric = bool(pd.api.types.is_numeric_dtype(series))
    is_date = _is_date_like(series)

    min_value: str | None = None
    max_value: str | None = None
    if is_numeric and len(non_null):
        min_value, max_value = str(non_null.min()), str(non_null.max())
    elif is_date and len(non_null):
        try:
            parsed = pd.to_datetime(non_null.astype(str), errors="coerce", format="mixed")
            if parsed.notna().any():
                min_value, max_value = str(parsed.min()), str(parsed.max())
        except (ValueError, TypeError):
            pass

    text_sample = non_null.astype(str).head(50)
    is_currency = (
        (not is_date)
        and bool(
            text_sample.apply(lambda v: bool(_CURRENCY_PATTERN.match(v.strip()))).mean() >= 0.6
        )
        if len(text_sample)
        else False
    )
    is_unit = (
        (not is_date)
        and bool(
            text_sample.apply(lambda v: bool(_UNIT_SUFFIX_PATTERN.search(v.strip()))).mean() >= 0.3
        )
        if len(text_sample)
        else False
    )
    is_email = (
        bool(text_sample.apply(lambda v: bool(_EMAIL_PATTERN.match(v.strip()))).mean() >= 0.6)
        if len(text_sample)
        else False
    )
    is_url = (
        bool(text_sample.apply(lambda v: bool(_URL_PATTERN.match(v.strip()))).mean() >= 0.6)
        if len(text_sample)
        else False
    )
    is_phone = (
        (not is_numeric)
        and bool(text_sample.apply(lambda v: bool(_PHONE_PATTERN.match(v.strip()))).mean() >= 0.6)
        if len(text_sample)
        else False
    )

    # Uniqueness alone, deliberately -- a candidate identifier is not
    # required to be named "*_id" (an email or SKU can identify a record
    # just as well). normalized_name is computed for future evidence
    # weighting (P3.xxE.2), not used as a gate here.
    is_identifier = uniqueness_ratio >= _IDENTIFIER_MIN_UNIQUENESS_RATIO and distinct_count > 1
    is_categorical = (
        not is_identifier
        and distinct_count > 0
        and (distinct_count / row_count if row_count else 0) <= _CATEGORICAL_MAX_DISTINCT_RATIO
        and distinct_count <= 50
    )

    return FieldProfile(
        source_field=name,
        physical_type=str(series.dtype),
        null_count=null_count,
        row_count=row_count,
        null_rate=null_rate,
        distinct_count=distinct_count,
        uniqueness_ratio=uniqueness_ratio,
        sample_values=_sample_values(series),
        value_patterns=_value_patterns(series),
        min_value=min_value,
        max_value=max_value,
        is_date_like=is_date,
        is_numeric_like=is_numeric,
        is_candidate_identifier=is_identifier,
        is_candidate_categorical=is_categorical,
        is_currency_like=is_currency,
        is_unit_like=is_unit,
        is_email_like=is_email,
        is_url_like=is_url,
        is_phone_like=is_phone,
        detected_currency_codes=_detect_currency_codes(series) if not is_numeric else [],
    )


class DatasetProfiler:
    """Deterministic, no-AI profiling of a single already-parsed tabular
    dataset. Operates purely on the dataframe already produced by the
    existing ArtifactParserRegistry -- never re-parses raw bytes, never
    calls out to any external service."""

    def profile(self, dataset_label: str, dataframe: pd.DataFrame) -> DatasetProfile:
        row_count = len(dataframe)
        fields = [
            _profile_field(str(column), dataframe[column], row_count)
            for column in dataframe.columns
        ]

        identifier_fields = [f.source_field for f in fields if f.is_candidate_identifier]
        # A single highly-unique field is a plausible primary key; several
        # together are a plausible composite grain. Never asserted as
        # certain -- these are candidates for later, evidence-weighted
        # semantic interpretation (P3.xxE.2), not a final decision.
        candidate_primary_keys = [
            f.source_field
            for f in fields
            if f.is_candidate_identifier and f.uniqueness_ratio >= 0.999
        ]
        candidate_foreign_keys = [
            f.source_field
            for f in fields
            if f.is_candidate_identifier
            and f not in candidate_primary_keys
            and f.uniqueness_ratio < 0.999
        ]
        candidate_grain = candidate_primary_keys or identifier_fields[:1]

        date_fields = [f for f in fields if f.is_date_like]
        numeric_fields = [f for f in fields if f.is_numeric_like]
        currency_fields = [f for f in fields if f.is_currency_like or f.detected_currency_codes]
        categorical_fields = [f for f in fields if f.is_candidate_categorical]

        # Whole-dataset, evidence-combining heuristics -- never a single
        # field forcing a characteristic (mirrors the domain-detection
        # generic-field lesson from P3.xxC.2E, generalized).
        has_status_like_field = any(
            "status" in f.source_field.lower() or "state" in f.source_field.lower()
            for f in categorical_fields
        )
        has_multiple_date_fields = len(date_fields) >= 2
        is_high_grain_row_count = row_count > 0 and len(identifier_fields) >= 1

        is_transaction_like = bool(currency_fields and identifier_fields and date_fields)
        is_ledger_like = bool(
            is_transaction_like and any("amount" in f.source_field.lower() for f in currency_fields)
        )
        is_measurement_like = bool(
            numeric_fields and date_fields and not currency_fields and len(numeric_fields) >= 2
        )
        is_master_or_reference = bool(
            candidate_primary_keys and not date_fields and row_count > 0 and row_count < 100_000
        )
        is_append_or_event = bool(
            date_fields and is_high_grain_row_count and not is_master_or_reference
        )
        is_snapshot_like = bool(
            has_multiple_date_fields and has_status_like_field and not is_transaction_like
        )

        return DatasetProfile(
            dataset_label=dataset_label,
            row_count=row_count,
            column_count=len(fields),
            fields=fields,
            candidate_grain=candidate_grain,
            candidate_primary_keys=candidate_primary_keys,
            candidate_foreign_keys=candidate_foreign_keys,
            is_append_or_event_like=is_append_or_event,
            is_snapshot_like=is_snapshot_like,
            is_master_or_reference_like=is_master_or_reference,
            is_transaction_like=is_transaction_like,
            is_ledger_like=is_ledger_like,
            is_measurement_like=is_measurement_like,
        )


dataset_profiler = DatasetProfiler()
