from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

import pandas as pd


@dataclass(frozen=True)
class RateDatasetFields:
    """Governed fields on one rate/reference dataset.

    Field names arrive only after semantic authority resolution.  This
    module therefore contains no filename, customer, or raw-schema branch.
    """

    dataset_id: UUID
    dataset_label: str
    dataframe: pd.DataFrame
    contract_id_field: str
    rate_field: str
    effective_from_field: str | None = None
    effective_to_field: str | None = None
    unit_field: str | None = None
    currency_field: str | None = None
    implicit_unit: str | None = None
    temporal_authority_unresolved: bool = False


@dataclass(frozen=True)
class ApplicableRate:
    dataset_id: UUID
    dataset_label: str
    row_reference: str
    amount: Decimal
    unit: str | None
    currency: str | None
    contract_key: str


def _decimal(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(numeric):
            return None
        return Decimal(str(numeric))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _timestamp(value: object) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parsed = pd.to_datetime(str(value), errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed


def _normalized_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    aliases = {
        "hours": "hour",
        "hrs": "hour",
        "hr": "hour",
        "h": "hour",
        "units": "unit",
        "each": "unit",
        "ea": "unit",
        "days": "day",
    }
    return aliases.get(normalized, normalized.rstrip("s"))


def resolve_applicable_rate(
    rate_datasets: list[RateDatasetFields],
    contract_key: str,
    at: pd.Timestamp | None,
    quantity_unit: str | None,
    quantity_currency: str | None,
) -> ApplicableRate | None:
    """Return exactly one safe applicable rate, otherwise abstain.

    Missing temporal evidence is allowed only when the rate row declares no
    temporal boundary.  Multiple equally applicable rows, unknown/mismatched
    units, and known currency mismatch all abstain.
    """

    matches: list[ApplicableRate] = []
    expected_unit = _normalized_unit(quantity_unit)
    for dataset in rate_datasets:
        if dataset.temporal_authority_unresolved:
            continue
        frame = dataset.dataframe
        required = {dataset.contract_id_field, dataset.rate_field}
        if not required <= set(frame.columns):
            continue
        for index, row in frame.iterrows():
            row_contract = _text(row[dataset.contract_id_field])
            if row_contract != contract_key:
                continue
            from_field = dataset.effective_from_field
            to_field = dataset.effective_to_field
            unit_field = dataset.unit_field
            currency_field = dataset.currency_field
            start = (
                _timestamp(row[from_field])
                if from_field is not None and from_field in frame.columns
                else None
            )
            end = (
                _timestamp(row[to_field])
                if to_field is not None and to_field in frame.columns
                else None
            )
            if (start is not None or end is not None) and at is None:
                continue
            if at is not None and (
                (start is not None and at < start) or (end is not None and at > end)
            ):
                continue
            rate_unit = _normalized_unit(
                _text(row[unit_field])
                if unit_field is not None and unit_field in frame.columns
                else dataset.implicit_unit
            )
            if expected_unit is None or rate_unit is None or expected_unit != rate_unit:
                continue
            raw_currency = (
                _text(row[currency_field])
                if currency_field is not None and currency_field in frame.columns
                else None
            )
            rate_currency = raw_currency.upper() if raw_currency is not None else None
            if (quantity_currency is None) != (rate_currency is None):
                continue
            if (
                quantity_currency is not None
                and rate_currency is not None
                and quantity_currency.upper() != rate_currency
            ):
                continue
            amount = _decimal(row[dataset.rate_field])
            if amount is None or amount < 0:
                continue
            matches.append(
                ApplicableRate(
                    dataset.dataset_id,
                    dataset.dataset_label,
                    str(index),
                    amount,
                    rate_unit,
                    rate_currency,
                    contract_key,
                )
            )
    return matches[0] if len(matches) == 1 else None
