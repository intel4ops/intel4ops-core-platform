from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import Finding
from app.schemas.findings import (
    EvidenceItemCreate,
    EvidenceType,
    FindingSeverity,
    FindingType,
    FindingValueType,
)
from app.services.canonical_evidence_completeness import CanonicalEvidenceCompletenessResult
from app.services.governed_cross_dataset_rate import RateDatasetFields, resolve_applicable_rate
from app.services.governed_finding_publisher import (
    ContributingDataset,
    GovernedFindingRequest,
    StableFindingIdentityReference,
    governed_finding_publisher,
)

RULE_CODE = "CONTRACT-RATE-COMPLIANCE"


@dataclass(frozen=True)
class AppliedRateDatasetFields:
    """Governed fields on one subject-attributable dataset.

    ``actual_rate_field`` is populated only from the distinct
    ``actual_applied_rate`` canonical concept. A contract/reference rate,
    invoice total, bare amount, or unresolved ``unit_price`` never enters
    that slot.
    """

    dataset_id: UUID
    dataset_label: str
    dataframe: pd.DataFrame
    trust_assessment_id: UUID | None
    subject_id_field: str | None
    actual_rate_field: str | None
    contract_id_field: str | None
    unit_field: str | None
    currency_field: str | None
    event_timestamp_field: str | None = None
    quantity_field: str | None = None
    canonical_evidence_completeness: CanonicalEvidenceCompletenessResult | None = None


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


def _currency(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    normalized = text.upper()
    valid = len(normalized) == 3 and normalized.isascii() and normalized.isalpha()
    return normalized if valid else None


def _timestamp(value: object) -> pd.Timestamp | None:
    text = _text(value)
    if text is None:
        return None
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed


def _subject_contract_map(datasets: list[AppliedRateDatasetFields]) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for dataset in datasets:
        subject_field = dataset.subject_id_field
        contract_field = dataset.contract_id_field
        frame = dataset.dataframe
        if (
            subject_field is None
            or contract_field is None
            or subject_field not in frame.columns
            or contract_field not in frame.columns
        ):
            continue
        for _, row in frame.iterrows():
            subject = _text(row[subject_field])
            contract = _text(row[contract_field])
            if subject is not None and contract is not None:
                candidates.setdefault(subject, set()).add(contract)
    return {
        subject: next(iter(contracts))
        for subject, contracts in candidates.items()
        if len(contracts) == 1
    }


def _evidence(
    dataset: AppliedRateDatasetFields,
    row_reference: str,
    actual_rate: Decimal,
    unit: str,
    currency: str,
    contract_rate: Decimal,
    contract_dataset_id: UUID,
    contract_dataset_label: str,
    contract_row_reference: str,
    rate_basis: str,
    applicability: tuple[pd.Timestamp | None, pd.Timestamp | None] | None,
    observed_at: pd.Timestamp | None,
    absolute_variance: Decimal,
    relative_variance: Decimal | None,
) -> list[EvidenceItemCreate]:
    start, end = applicability or (None, None)
    return [
        EvidenceItemCreate(
            evidence_type=EvidenceType.CALCULATION_TRACE,
            reference_type="actual_applied_rate_line",
            reference_id=f"{dataset.dataset_label}:{row_reference}",
            dataset_id=dataset.dataset_id,
            label="Governed actual applied rate",
            description=(
                f"Actual applied rate {actual_rate} {currency}/{unit} from "
                f"{dataset.dataset_label} row {row_reference}."
            ),
            comparison_value=actual_rate,
            comparison_unit=unit,
            comparison_currency=currency,
            metadata={
                "rate_role": "actual_applied",
                "observed_at": observed_at.isoformat() if observed_at is not None else None,
            },
        ),
        EvidenceItemCreate(
            evidence_type=EvidenceType.CALCULATION_TRACE,
            reference_type="applicable_contract_rate_line",
            reference_id=f"{contract_dataset_label}:{contract_row_reference}",
            dataset_id=contract_dataset_id,
            label="Governed applicable contract rate",
            description=(
                f"Applicable contract rate {contract_rate} {currency}/{unit} from "
                f"{contract_dataset_label} row {contract_row_reference}."
            ),
            comparison_value=contract_rate,
            comparison_unit=unit,
            comparison_currency=currency,
            metadata={
                "rate_role": "applicable_contract",
                "rate_basis": rate_basis,
                "effective_from": start.isoformat() if start is not None else None,
                "effective_to": end.isoformat() if end is not None else None,
            },
        ),
        EvidenceItemCreate(
            evidence_type=EvidenceType.CALCULATION_TRACE,
            reference_type="rate_comparison",
            reference_id=(
                f"{dataset.dataset_id}:{row_reference}:"
                f"{contract_dataset_id}:{contract_row_reference}"
            ),
            dataset_id=dataset.dataset_id,
            label="Contract rate comparison",
            description=(
                f"Absolute rate variance is {absolute_variance} {currency}/{unit}; "
                + (
                    f"relative variance is {relative_variance}."
                    if relative_variance is not None
                    else "relative variance is unavailable because the contract rate is zero."
                )
            ),
            comparison_value=absolute_variance,
            comparison_unit=unit,
            comparison_currency=currency,
            metadata={
                "comparison": "exact_decimal_inequality",
                "relative_variance": (
                    str(relative_variance) if relative_variance is not None else None
                ),
            },
        ),
    ]


def run_contract_rate_compliance(
    db: Session,
    organization_id: UUID,
    datasets: list[AppliedRateDatasetFields],
    eligible_subject_keys: set[str],
    actor_user_id: UUID,
    rate_datasets: list[RateDatasetFields],
    subject_entity_type: str = "work_order",
) -> list[Finding]:
    """Compare explicit actual applied rates with governed applicable rates.

    Every unsafe state is an abstention: missing or ambiguous subject/contract
    linkage, missing actual rate, missing rate basis, incompatible UOM,
    missing/incompatible currency, and unresolved temporal applicability.
    Missing evidence is never converted to zero. No total billed amount is
    divided to manufacture an actual rate.
    """

    if not datasets or not eligible_subject_keys or not rate_datasets:
        return []

    contract_by_subject = _subject_contract_map(datasets)
    published: list[Finding] = []
    subject_label = subject_entity_type.replace("_", " ")

    for dataset in datasets:
        frame = dataset.dataframe
        subject_field = dataset.subject_id_field
        actual_rate_field = dataset.actual_rate_field
        unit_field = dataset.unit_field
        currency_field = dataset.currency_field
        if (
            subject_field is None
            or actual_rate_field is None
            or unit_field is None
            or currency_field is None
            or subject_field not in frame.columns
            or actual_rate_field not in frame.columns
            or unit_field not in frame.columns
            or currency_field not in frame.columns
        ):
            continue

        for row_index, row in frame.iterrows():
            subject_key = _text(row[subject_field])
            if subject_key is None or subject_key not in eligible_subject_keys:
                continue
            actual_rate = _decimal(row[actual_rate_field])
            actual_unit = _text(row[unit_field])
            actual_currency = _currency(row[currency_field])
            if (
                actual_rate is None
                or actual_rate < 0
                or actual_unit is None
                or actual_currency is None
            ):
                continue

            contract_key = None
            contract_field = dataset.contract_id_field
            if contract_field is not None and contract_field in frame.columns:
                contract_key = _text(row[contract_field])
            if contract_key is None:
                contract_key = (
                    subject_key
                    if subject_entity_type == "contract"
                    else contract_by_subject.get(subject_key)
                )
            if contract_key is None:
                continue

            observed_at = None
            timestamp_field = dataset.event_timestamp_field
            if timestamp_field is not None and timestamp_field in frame.columns:
                observed_at = _timestamp(row[timestamp_field])

            contract_rate = resolve_applicable_rate(
                rate_datasets,
                contract_key,
                observed_at,
                actual_unit,
                actual_currency,
            )
            if (
                contract_rate is None
                or contract_rate.currency is None
                or contract_rate.unit is None
            ):
                continue
            if contract_rate.rate_basis is None:
                continue

            rate_variance = actual_rate - contract_rate.amount
            if rate_variance == 0:
                continue
            absolute_variance = abs(rate_variance)
            relative_variance = (
                absolute_variance / contract_rate.amount if contract_rate.amount != 0 else None
            )

            exposure = None
            quantity_field = dataset.quantity_field
            if quantity_field is not None and quantity_field in frame.columns:
                quantity = _decimal(row[quantity_field])
                if quantity is not None and quantity > 0:
                    exposure = absolute_variance * quantity

            row_reference = str(row_index)
            condition = (
                "actual_rate_above_contract" if rate_variance > 0 else "actual_rate_below_contract"
            )
            material_reference = (
                f"{dataset.dataset_id}:{row_reference}:"
                f"{contract_rate.dataset_id}:{contract_rate.row_reference}:"
                f"{actual_rate}:{contract_rate.amount}:{contract_rate.unit}:"
                f"{contract_rate.currency}"
            )
            supporting_evidence = _evidence(
                dataset,
                row_reference,
                actual_rate,
                contract_rate.unit,
                contract_rate.currency,
                contract_rate.amount,
                contract_rate.dataset_id,
                contract_rate.dataset_label,
                contract_rate.row_reference,
                contract_rate.rate_basis,
                contract_rate.temporal_applicability,
                observed_at,
                absolute_variance,
                relative_variance,
            )
            if exposure is not None:
                supporting_evidence.append(
                    EvidenceItemCreate(
                        evidence_type=EvidenceType.CALCULATION_TRACE,
                        reference_type="rate_variance_exposure",
                        reference_id=f"{dataset.dataset_label}:{row_reference}",
                        dataset_id=dataset.dataset_id,
                        label="Rate variance economic exposure",
                        description=(
                            f"Absolute rate variance {absolute_variance} multiplied by governed "
                            f"quantity produced exposure {exposure} {contract_rate.currency}."
                        ),
                        comparison_value=exposure,
                        comparison_currency=contract_rate.currency,
                        metadata={"calculation": "absolute_rate_variance_x_quantity"},
                    )
                )

            finding = (
                governed_finding_publisher.publish(
                    db,
                    GovernedFindingRequest(
                        organization_id=organization_id,
                        primary_dataset_id=dataset.dataset_id,
                        trust_assessment_id=dataset.trust_assessment_id,
                        definition_code=RULE_CODE,
                        definition_version="1.0",
                        rule_condition_code=condition,
                        affected_record_count=1,
                        title=(
                            f"{subject_label.capitalize()} {subject_key} applied rate differs "
                            "from the applicable contract rate"
                        ),
                        summary=(
                            f"Actual applied rate {actual_rate} {contract_rate.currency}/"
                            f"{contract_rate.unit}; applicable contract rate "
                            f"{contract_rate.amount} {contract_rate.currency}/"
                            f"{contract_rate.unit}; signed rate variance {rate_variance}."
                        ),
                        domain_code="cross_domain",
                        severity=FindingSeverity.MEDIUM,
                        finding_type=FindingType.RECONCILIATION,
                        actor_user_id=actor_user_id,
                        contributing_datasets=[
                            ContributingDataset(dataset_id=contract_rate.dataset_id)
                        ],
                        entities=[
                            {"entity_type": subject_entity_type, "canonical_key": subject_key},
                            {"entity_type": "contract", "canonical_key": contract_key},
                        ],
                        identity_references=[
                            StableFindingIdentityReference(
                                identity_role="subject",
                                reference_type=subject_entity_type,
                                canonical_reference=subject_key,
                                canonical_entity=subject_entity_type,
                            ),
                            StableFindingIdentityReference(
                                identity_role="material_condition",
                                reference_type="contract_rate_comparison",
                                canonical_reference=material_reference,
                                canonical_entity="contract",
                            ),
                        ],
                        domains=["revenue", "contract"],
                        economic_status="governed_pending",
                        exposure_value=exposure,
                        exposure_value_type=(
                            None if exposure is None else FindingValueType.CURRENCY
                        ),
                        exposure_currency=(
                            contract_rate.currency if exposure is not None else None
                        ),
                        supporting_evidence=supporting_evidence,
                        canonical_evidence_completeness=dataset.canonical_evidence_completeness,
                        limitations=[
                            "Rate-compliance identity is distinct from any related total-amount "
                            "variance; portfolio recovery must not double-count overlapping "
                            "exposure."
                        ],
                    ),
                )
                if dataset.trust_assessment_id is not None
                else None
            )
            if finding is not None:
                published.append(finding)

    return published
