from uuid import uuid4

import pandas as pd

from app.services.governed_cross_dataset_rate import (
    RATE_BASIS_EXPLICIT_UNIT_COLUMN,
    RATE_BASIS_IMPLICIT_UNIT_CONCEPT,
    GovernedRateEvidence,
    RateDatasetFields,
    resolve_applicable_rate,
)


def _rates(rows: list[dict[str, object]], *, implicit_unit: str | None = None) -> RateDatasetFields:
    return RateDatasetFields(
        dataset_id=uuid4(),
        dataset_label="governed-rate-reference",
        dataframe=pd.DataFrame(rows),
        contract_id_field="agreement",
        rate_field="price",
        effective_from_field="valid_from",
        effective_to_field="valid_to",
        unit_field=None if implicit_unit else "basis",
        currency_field="currency",
        implicit_unit=implicit_unit,
    )


def _resolve(datasets: list[RateDatasetFields], **overrides: object) -> GovernedRateEvidence | None:
    arguments: dict[str, object] = {
        "contract_key": "C-1",
        "at": pd.Timestamp("2026-06-01", tz="UTC"),
        "quantity_unit": "hour",
        "quantity_currency": "USD",
    }
    arguments.update(overrides)
    return resolve_applicable_rate(datasets, **arguments)  # type: ignore[arg-type]


def test_b_cross_dataset_quantity_and_applicable_rate_resolves() -> None:
    rate = _resolve(
        [
            _rates(
                [
                    {
                        "agreement": "C-1",
                        "price": 125,
                        "valid_from": "2026-01-01",
                        "valid_to": "2026-12-31",
                        "basis": "hours",
                        "currency": "USD",
                    }
                ]
            )
        ]
    )
    assert rate is not None
    assert rate.amount == 125
    # P3.xxI.4 positive test E: full lineage preserved -- WHICH governed
    # source supplied the denominator, and the exact effective-date window
    # this specific row declared, both survive on the returned evidence
    # rather than requiring the caller to re-derive them from the raw
    # dataframe.
    assert rate.rate_basis == RATE_BASIS_EXPLICIT_UNIT_COLUMN
    assert rate.temporal_applicability == (
        pd.Timestamp("2026-01-01", tz="UTC"),
        pd.Timestamp("2026-12-31", tz="UTC"),
    )
    assert rate.dataset_id is not None
    assert rate.row_reference == "0"


def test_rate_basis_implicit_unit_concept_recorded_as_such() -> None:
    # P3.xxI.4 positive test C: a strongly-governed concept whose own name
    # inherently encodes the denominator (the orchestration layer's
    # hourly_rate -> "hour" wiring) is recorded as IMPLICIT_UNIT_CONCEPT,
    # never silently indistinguishable from an explicit column.
    row = {"agreement": "C-1", "price": 125, "currency": "USD"}
    rate = _resolve([_rates([row], implicit_unit="hour")])
    assert rate is not None
    assert rate.rate_basis == RATE_BASIS_IMPLICIT_UNIT_CONCEPT
    assert rate.temporal_applicability is None


def test_no_unit_anywhere_abstains_with_no_rate_basis() -> None:
    # P3.xxI.4 negative test A: a bare rate with no UOM evidence anywhere
    # (no explicit column value, no implicit_unit) never resolves.
    dataset = RateDatasetFields(
        dataset_id=uuid4(),
        dataset_label="bare-rate-reference",
        dataframe=pd.DataFrame([{"agreement": "C-1", "price": 125, "currency": "USD"}]),
        contract_id_field="agreement",
        rate_field="price",
    )
    assert _resolve([dataset]) is None


def test_c_multiple_equally_applicable_rates_abstain() -> None:
    row = {
        "agreement": "C-1",
        "price": 125,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "basis": "hour",
        "currency": "USD",
    }
    assert _resolve([_rates([row, {**row, "price": 130}])]) is None


def test_d_wrong_relationship_key_does_not_match() -> None:
    assert (
        _resolve(
            [
                _rates(
                    [
                        {
                            "agreement": "C-2",
                            "price": 125,
                            "basis": "hour",
                            "currency": "USD",
                        }
                    ]
                )
            ]
        )
        is None
    )


def test_e_expired_and_future_rates_do_not_match() -> None:
    rows = [
        {
            "agreement": "C-1",
            "price": 125,
            "valid_from": "2025-01-01",
            "valid_to": "2025-12-31",
            "basis": "hour",
            "currency": "USD",
        },
        {
            "agreement": "C-1",
            "price": 130,
            "valid_from": "2027-01-01",
            "valid_to": "2027-12-31",
            "basis": "hour",
            "currency": "USD",
        },
    ]
    assert _resolve([_rates(rows)]) is None


def test_f_uom_mismatch_abstains() -> None:
    row = {"agreement": "C-1", "price": 125, "basis": "day", "currency": "USD"}
    assert _resolve([_rates([row])]) is None


def test_g_currency_mismatch_without_fx_abstains() -> None:
    row = {"agreement": "C-1", "price": 125, "basis": "hour", "currency": "EUR"}
    assert _resolve([_rates([row])]) is None


def test_one_known_and_one_unknown_currency_abstains() -> None:
    row = {"agreement": "C-1", "price": 125, "basis": "hour", "currency": None}
    assert _resolve([_rates([row])]) is None


def test_h_missing_governed_rate_dataset_abstains() -> None:
    assert _resolve([]) is None


def test_i_missing_quantity_unit_authority_abstains() -> None:
    row = {"agreement": "C-1", "price": 125, "basis": "hour", "currency": "USD"}
    assert _resolve([_rates([row])], quantity_unit=None) is None


def test_j_non_labor_schema_with_same_invariant_works() -> None:
    row = {"agreement": "C-1", "price": 9.5, "basis": "unit", "currency": "USD"}
    rate = _resolve([_rates([row])], quantity_unit="each")
    assert rate is not None
    assert rate.unit == "unit"


def test_explicit_hourly_concept_can_supply_governed_implicit_basis() -> None:
    row = {"agreement": "C-1", "price": 125, "currency": "USD"}
    assert _resolve([_rates([row], implicit_unit="hour")]) is not None


def test_unresolved_temporal_authority_abstains() -> None:
    dataset = _rates([{"agreement": "C-1", "price": 125, "basis": "hour", "currency": "USD"}])
    unresolved = RateDatasetFields(
        **{
            **dataset.__dict__,
            "temporal_authority_unresolved": True,
        }
    )
    assert _resolve([unresolved]) is None
