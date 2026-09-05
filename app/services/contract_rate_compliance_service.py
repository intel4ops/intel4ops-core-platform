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
from app.services.governed_cross_dataset_rate import (
    GovernedRateEvidence,
    RateDatasetFields,
    resolve_applicable_rate,
)
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
    # P3.xxI.5A-R: optional inputs for the independent derived-rate path.
    # The orchestration layer supplies these only after normal governed
    # semantic resolution.  This service never infers a role from a filename,
    # customer, industry, or raw column spelling.
    invoice_amount_field: str | None = None
    component_unit_price_field: str | None = None
    implicit_quantity_unit: str | None = None
    is_rate_card_shaped: bool = False


@dataclass(frozen=True)
class DerivedAppliedRateEvidence:
    """One provenance-complete rate derived from governed amount evidence."""

    primary_dataset: AppliedRateDatasetFields
    subject_key: str
    contract_key: str
    observed_at: pd.Timestamp | None
    actual_rate: Decimal
    target_amount: Decimal
    quantity: Decimal
    unit: str
    currency: str
    row_reference: str
    evidence: tuple[EvidenceItemCreate, ...]
    contributing_dataset_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class _DerivedInputLine:
    dataset: AppliedRateDatasetFields
    row_reference: str
    value: Decimal
    currency: str | None = None
    unit: str | None = None
    observed_at: pd.Timestamp | None = None
    component_amount: Decimal | None = None


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


def _unit(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    normalized = text.lower()
    aliases = {
        "hours": "hour",
        "hrs": "hour",
        "hr": "hour",
        "h": "hour",
        "days": "day",
        "units": "unit",
        "each": "unit",
        "ea": "unit",
    }
    return aliases.get(normalized, normalized.rstrip("s"))


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


def derive_actual_applied_rates(
    datasets: list[AppliedRateDatasetFields],
    eligible_subject_keys: set[str],
    *,
    subject_entity_type: str = "work_order",
) -> list[DerivedAppliedRateEvidence]:
    """Derive actual rates only from complete, uniquely attributable inputs.

    The supported generic shape is one billed total, one target-quantity
    population, and at most one non-target component population whose rows
    each carry quantity and unit price.  Multiple quantity datasets may only
    corroborate the same total and UOM; disagreement abstains.  This is
    intentionally not an invoice-allocation engine.
    """

    contract_by_subject = _subject_contract_map(datasets)
    billings: dict[str, list[_DerivedInputLine]] = {}
    quantities: dict[str, dict[UUID, list[_DerivedInputLine]]] = {}
    components: dict[str, dict[UUID, list[_DerivedInputLine]]] = {}
    invalid_subjects: set[str] = set()

    for dataset in datasets:
        if dataset.is_rate_card_shaped:
            continue
        frame = dataset.dataframe
        subject_field = dataset.subject_id_field
        if subject_field is None or subject_field not in frame.columns:
            continue
        billed_field = dataset.invoice_amount_field
        quantity_field = dataset.quantity_field
        component_rate_field = dataset.component_unit_price_field
        has_billing = billed_field is not None and billed_field in frame.columns
        has_component = component_rate_field is not None and component_rate_field in frame.columns
        has_target_quantity = (
            quantity_field is not None
            and quantity_field in frame.columns
            and not has_component
            and dataset.actual_rate_field is None
        )
        if not (has_billing or has_component or has_target_quantity):
            continue

        for row_index, row in frame.iterrows():
            subject_key = _text(row[subject_field])
            if subject_key is None or subject_key not in eligible_subject_keys:
                continue
            if (
                dataset.canonical_evidence_completeness is not None
                and not dataset.canonical_evidence_completeness.satisfied
            ):
                invalid_subjects.add(subject_key)
                continue

            row_reference = str(row_index)
            currency = (
                _currency(row[dataset.currency_field])
                if dataset.currency_field is not None and dataset.currency_field in frame.columns
                else None
            )
            observed_at = (
                _timestamp(row[dataset.event_timestamp_field])
                if dataset.event_timestamp_field is not None
                and dataset.event_timestamp_field in frame.columns
                else None
            )

            if has_billing and billed_field is not None:
                billed_amount = _decimal(row[billed_field])
                if billed_amount is None or billed_amount < 0 or currency is None:
                    invalid_subjects.add(subject_key)
                else:
                    billings.setdefault(subject_key, []).append(
                        _DerivedInputLine(
                            dataset,
                            row_reference,
                            billed_amount,
                            currency=currency,
                            observed_at=observed_at,
                        )
                    )

            if has_component and component_rate_field is not None:
                if quantity_field is None or quantity_field not in frame.columns:
                    invalid_subjects.add(subject_key)
                    continue
                component_quantity = _decimal(row[quantity_field])
                component_rate = _decimal(row[component_rate_field])
                if (
                    component_quantity is None
                    or component_quantity < 0
                    or component_rate is None
                    or component_rate < 0
                    or currency is None
                ):
                    invalid_subjects.add(subject_key)
                else:
                    components.setdefault(subject_key, {}).setdefault(
                        dataset.dataset_id, []
                    ).append(
                        _DerivedInputLine(
                            dataset,
                            row_reference,
                            component_quantity,
                            currency=currency,
                            component_amount=component_quantity * component_rate,
                        )
                    )

            if has_target_quantity and quantity_field is not None:
                quantity = _decimal(row[quantity_field])
                unit = (
                    _unit(row[dataset.unit_field])
                    if dataset.unit_field is not None and dataset.unit_field in frame.columns
                    else _unit(dataset.implicit_quantity_unit)
                )
                if quantity is None or quantity < 0 or unit is None:
                    invalid_subjects.add(subject_key)
                else:
                    quantities.setdefault(subject_key, {}).setdefault(
                        dataset.dataset_id, []
                    ).append(
                        _DerivedInputLine(
                            dataset,
                            row_reference,
                            quantity,
                            unit=unit,
                            observed_at=observed_at,
                        )
                    )

    derived: list[DerivedAppliedRateEvidence] = []
    for subject_key in sorted(eligible_subject_keys):
        if subject_key in invalid_subjects:
            continue
        billing_lines = billings.get(subject_key, [])
        quantity_groups = quantities.get(subject_key, {})
        component_groups = components.get(subject_key, {})
        if len(billing_lines) != 1 or not quantity_groups or len(component_groups) > 1:
            continue

        quantity_summaries: list[tuple[Decimal, str, list[_DerivedInputLine]]] = []
        quantity_invalid = False
        for lines in quantity_groups.values():
            units = {line.unit for line in lines if line.unit is not None}
            if len(units) != 1:
                quantity_invalid = True
                break
            quantity_total = sum((line.value for line in lines), Decimal("0"))
            quantity_summaries.append((quantity_total, units.pop(), lines))
        if quantity_invalid or not quantity_summaries:
            continue
        quantity_totals = {(total, unit) for total, unit, _ in quantity_summaries}
        if len(quantity_totals) != 1:
            continue
        quantity, unit = next(iter(quantity_totals))
        if quantity <= 0:
            continue

        billing = billing_lines[0]
        component_lines = next(iter(component_groups.values()), [])
        currencies = {billing.currency} | {line.currency for line in component_lines}
        if None in currencies or len(currencies) != 1:
            continue
        currency = next(iter(currencies))
        assert currency is not None
        component_amount = sum((line.component_amount or Decimal("0")) for line in component_lines)
        target_amount = billing.value - component_amount
        if target_amount < 0:
            continue

        contract_key = (
            subject_key
            if subject_entity_type == "contract"
            else contract_by_subject.get(subject_key)
        )
        if contract_key is None:
            continue
        actual_rate = target_amount / quantity
        quantity_lines = [line for _, _, lines in quantity_summaries for line in lines]
        evidence: list[EvidenceItemCreate] = [
            EvidenceItemCreate(
                evidence_type=EvidenceType.CALCULATION_TRACE,
                reference_type="derived_rate_billed_amount_source",
                reference_id=f"{billing.dataset.dataset_label}:{billing.row_reference}",
                dataset_id=billing.dataset.dataset_id,
                label="Attributed billed amount",
                description=(
                    f"Billed amount {billing.value} {currency} from "
                    f"{billing.dataset.dataset_label} row {billing.row_reference}."
                ),
                comparison_value=billing.value,
                comparison_currency=currency,
            )
        ]
        for line in quantity_lines:
            evidence.append(
                EvidenceItemCreate(
                    evidence_type=EvidenceType.CALCULATION_TRACE,
                    reference_type="derived_rate_quantity_source",
                    reference_id=f"{line.dataset.dataset_label}:{line.row_reference}",
                    dataset_id=line.dataset.dataset_id,
                    label="Governed target quantity",
                    description=(
                        f"Target quantity {line.value} {unit} from "
                        f"{line.dataset.dataset_label} row {line.row_reference}."
                    ),
                    comparison_value=line.value,
                    comparison_unit=unit,
                )
            )
        for line in component_lines:
            evidence.append(
                EvidenceItemCreate(
                    evidence_type=EvidenceType.CALCULATION_TRACE,
                    reference_type="derived_rate_non_target_component",
                    reference_id=f"{line.dataset.dataset_label}:{line.row_reference}",
                    dataset_id=line.dataset.dataset_id,
                    label="Governed non-target component",
                    description=(
                        f"Non-target component amount {line.component_amount} {currency} from "
                        f"{line.dataset.dataset_label} row {line.row_reference}."
                    ),
                    comparison_value=line.component_amount,
                    comparison_currency=currency,
                )
            )
        evidence.extend(
            [
                EvidenceItemCreate(
                    evidence_type=EvidenceType.CALCULATION_TRACE,
                    reference_type="derived_rate_target_amount",
                    reference_id=f"{subject_key}:derived-target-amount",
                    dataset_id=billing.dataset.dataset_id,
                    label="Derived target billed amount",
                    description=(
                        f"Billed amount {billing.value} minus governed non-target components "
                        f"{component_amount} equals target amount {target_amount} {currency}."
                    ),
                    comparison_value=target_amount,
                    comparison_currency=currency,
                ),
                EvidenceItemCreate(
                    evidence_type=EvidenceType.CALCULATION_TRACE,
                    reference_type="derived_actual_applied_rate",
                    reference_id=f"{subject_key}:derived-actual-rate",
                    dataset_id=billing.dataset.dataset_id,
                    label="Derived actual applied rate",
                    description=(
                        f"Target amount {target_amount} {currency} divided by governed quantity "
                        f"{quantity} {unit} equals {actual_rate} {currency}/{unit}."
                    ),
                    comparison_value=actual_rate,
                    comparison_unit=unit,
                    comparison_currency=currency,
                    metadata={"derivation": "billed_minus_non_target_divided_by_quantity"},
                ),
            ]
        )
        dataset_ids = {
            billing.dataset.dataset_id,
            *(line.dataset.dataset_id for line in quantity_lines),
            *(line.dataset.dataset_id for line in component_lines),
        }
        derived.append(
            DerivedAppliedRateEvidence(
                primary_dataset=billing.dataset,
                subject_key=subject_key,
                contract_key=contract_key,
                observed_at=billing.observed_at,
                actual_rate=actual_rate,
                target_amount=target_amount,
                quantity=quantity,
                unit=unit,
                currency=currency,
                row_reference=f"derived:{billing.row_reference}",
                evidence=tuple(evidence),
                contributing_dataset_ids=tuple(
                    sorted(
                        (
                            dataset_id
                            for dataset_id in dataset_ids
                            if dataset_id != billing.dataset.dataset_id
                        ),
                        key=str,
                    )
                ),
            )
        )
    return derived


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
    *,
    include_actual_rate_source: bool = True,
) -> list[EvidenceItemCreate]:
    start, end = applicability or (None, None)
    items: list[EvidenceItemCreate] = []
    if include_actual_rate_source:
        items.append(
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
            )
        )
    items.extend(
        [
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
    )
    return items


def _publish_derived_rate_comparison(
    db: Session,
    organization_id: UUID,
    actor_user_id: UUID,
    subject_entity_type: str,
    derived: DerivedAppliedRateEvidence,
    contract_rate: GovernedRateEvidence,
) -> Finding | None:
    rate_variance = derived.actual_rate - contract_rate.amount
    if rate_variance == 0:
        return None
    absolute_variance = abs(rate_variance)
    relative_variance = (
        absolute_variance / contract_rate.amount if contract_rate.amount != 0 else None
    )
    exposure = absolute_variance * derived.quantity
    condition = "actual_rate_above_contract" if rate_variance > 0 else "actual_rate_below_contract"
    material_reference = (
        f"{derived.primary_dataset.dataset_id}:{derived.row_reference}:"
        f"{contract_rate.dataset_id}:{contract_rate.row_reference}:"
        f"{derived.actual_rate}:{contract_rate.amount}:{contract_rate.unit}:"
        f"{contract_rate.currency}:derived"
    )
    supporting_evidence = list(derived.evidence)
    supporting_evidence.extend(
        _evidence(
            derived.primary_dataset,
            derived.row_reference,
            derived.actual_rate,
            contract_rate.unit or derived.unit,
            contract_rate.currency or derived.currency,
            contract_rate.amount,
            contract_rate.dataset_id,
            contract_rate.dataset_label,
            contract_rate.row_reference,
            contract_rate.rate_basis or "",
            contract_rate.temporal_applicability,
            derived.observed_at,
            absolute_variance,
            relative_variance,
            include_actual_rate_source=False,
        )
    )
    supporting_evidence.append(
        EvidenceItemCreate(
            evidence_type=EvidenceType.CALCULATION_TRACE,
            reference_type="rate_variance_exposure",
            reference_id=(f"{derived.primary_dataset.dataset_label}:{derived.row_reference}"),
            dataset_id=derived.primary_dataset.dataset_id,
            label="Rate variance economic exposure",
            description=(
                f"Absolute rate variance {absolute_variance} multiplied by governed "
                f"quantity {derived.quantity} produced exposure {exposure} "
                f"{contract_rate.currency}."
            ),
            comparison_value=exposure,
            comparison_currency=contract_rate.currency,
            metadata={"calculation": "absolute_rate_variance_x_quantity"},
        )
    )
    contributing_ids = {
        contract_rate.dataset_id,
        *derived.contributing_dataset_ids,
    }
    subject_label = subject_entity_type.replace("_", " ")
    return (
        governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=derived.primary_dataset.dataset_id,
                trust_assessment_id=derived.primary_dataset.trust_assessment_id,
                definition_code=RULE_CODE,
                definition_version="1.1",
                rule_condition_code=condition,
                affected_record_count=1,
                title=(
                    f"{subject_label.capitalize()} {derived.subject_key} applied rate differs "
                    "from the applicable contract rate"
                ),
                summary=(
                    f"Derived actual applied rate {derived.actual_rate} "
                    f"{contract_rate.currency}/{contract_rate.unit}; applicable contract rate "
                    f"{contract_rate.amount} {contract_rate.currency}/{contract_rate.unit}; "
                    f"signed rate variance {rate_variance}."
                ),
                domain_code="cross_domain",
                severity=FindingSeverity.MEDIUM,
                finding_type=FindingType.RECONCILIATION,
                actor_user_id=actor_user_id,
                contributing_datasets=[
                    ContributingDataset(dataset_id=dataset_id)
                    for dataset_id in sorted(contributing_ids, key=str)
                ],
                entities=[
                    {
                        "entity_type": subject_entity_type,
                        "canonical_key": derived.subject_key,
                    },
                    {"entity_type": "contract", "canonical_key": derived.contract_key},
                ],
                identity_references=[
                    StableFindingIdentityReference(
                        identity_role="subject",
                        reference_type=subject_entity_type,
                        canonical_reference=derived.subject_key,
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
                exposure_value_type=FindingValueType.CURRENCY,
                exposure_currency=contract_rate.currency,
                supporting_evidence=supporting_evidence,
                canonical_evidence_completeness=(
                    derived.primary_dataset.canonical_evidence_completeness
                ),
                limitations=[
                    "Actual applied rate was derived from attributable billed amount, "
                    "governed non-target components, and governed target quantity.",
                    "Rate-compliance identity is distinct from any related total-amount "
                    "variance; portfolio recovery must not double-count overlapping exposure.",
                ],
            ),
        )
        if derived.primary_dataset.trust_assessment_id is not None
        else None
    )


def run_contract_rate_compliance(
    db: Session,
    organization_id: UUID,
    datasets: list[AppliedRateDatasetFields],
    eligible_subject_keys: set[str],
    actor_user_id: UUID,
    rate_datasets: list[RateDatasetFields],
    subject_entity_type: str = "work_order",
) -> list[Finding]:
    """Compare explicit or safely derived applied rates with contract rates.

    Every unsafe state is an abstention: missing or ambiguous subject/contract
    linkage, missing actual rate, missing rate basis, incompatible UOM,
    missing/incompatible currency, and unresolved temporal applicability.
    Missing evidence is never converted to zero. A billed total is used only
    by ``derive_actual_applied_rates`` after attribution, component,
    quantity, UOM, currency, and ambiguity gates all pass.
    """

    if not datasets or not eligible_subject_keys or not rate_datasets:
        return []

    contract_by_subject = _subject_contract_map(datasets)
    published: list[Finding] = []
    explicit_subjects: set[str] = set()
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

            # A valid explicit actual rate is authoritative for this subject.
            # The derived path must never create a second competing finding.
            explicit_subjects.add(subject_key)

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

    for derived in derive_actual_applied_rates(
        datasets,
        eligible_subject_keys,
        subject_entity_type=subject_entity_type,
    ):
        if derived.subject_key in explicit_subjects:
            continue
        contract_rate = resolve_applicable_rate(
            rate_datasets,
            derived.contract_key,
            derived.observed_at,
            derived.unit,
            derived.currency,
        )
        if (
            contract_rate is None
            or contract_rate.currency is None
            or contract_rate.unit is None
            or contract_rate.rate_basis is None
        ):
            continue
        finding = _publish_derived_rate_comparison(
            db,
            organization_id,
            actor_user_id,
            subject_entity_type,
            derived,
            contract_rate,
        )
        if finding is not None:
            published.append(finding)

    return published
