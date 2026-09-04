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
from app.services.canonical_revenue_variance_evidence import (
    COMPARABLE_CURRENCY_STATES,
    CurrencyComparability,
    classify_currency_comparability,
)
from app.services.governed_cross_dataset_rate import (
    RateDatasetFields,
    resolve_applicable_rate,
)
from app.services.governed_finding_publisher import (
    ContributingDataset,
    GovernedFindingRequest,
    StableFindingIdentityReference,
    governed_finding_publisher,
)

# ---------------------------------------------------------------------------
# P3.xxI.2: REVENUE-AMOUNT-VARIANCE. Additive sibling to XDOM-B, never a
# modification of it. XDOM-B answers "does a linked revenue record exist at
# all" (existence); this rule answers "is the actual billed amount
# consistent with the expected amount computed from governed consumption/
# rate evidence" (amount). See docs/p3xxi2-revenue-amount-billing-variance-report.md
# Section C for the full capability contract.
# ---------------------------------------------------------------------------

RULE_CODE = "REVENUE-AMOUNT-VARIANCE"

# P3.xxI.2 Section 11: smallest generic deterministic materiality policy --
# "greater of an absolute floor or a relative percentage", a standard
# financial-reconciliation pattern, not tuned to any specific simulation.
# Not hidden inside the rule body: both numbers are named constants so a
# future governed-config migration has an obvious, single place to read
# from, mirroring Trust's own numeric_range_validity config shape.
DEFAULT_RELATIVE_TOLERANCE = Decimal("0.02")
DEFAULT_ABSOLUTE_TOLERANCE = Decimal("1.00")


@dataclass(frozen=True)
class DatasetConceptFields:
    """Which column (if any) on ONE dataset's canonical_frames dataframe
    carries governed evidence for each concept this capability needs --
    resolved once per dataset by the orchestration layer (mirroring
    XDOM-A/B's own field/entity-resolution split) and passed in here as
    plain data. This module never touches SemanticInterpretationDecision
    or the DB directly -- framework-light except for the pandas dataframe
    itself, matching cross_domain_intelligence_service.py's own shape."""

    dataset_id: UUID
    dataset_label: str
    dataframe: pd.DataFrame
    trust_assessment_id: UUID | None
    # P3.xxI.2C: the column (if any) on this dataset carrying the case's
    # governed billable subject identity -- direct when the subject's own
    # concept resolves here (e.g. work_order_id), or already translated by
    # the orchestration layer through a governed one-hop identifier bridge
    # when it doesn't (e.g. a dispatch/service-event id bridged to its
    # contract). Either way this module treats it as one flat key; it
    # never knows or cares which case applied.
    subject_id_field: str | None
    quantity_field: str | None
    unit_price_field: str | None
    invoice_amount_field: str | None
    cost_amount_field: str | None
    currency_field: str | None
    contract_id_field: str | None = None
    event_timestamp_field: str | None = None
    unit_field: str | None = None
    implicit_quantity_unit: str | None = None
    # P3.xxV.2D's existing correction path (see governed_finding_publisher.py):
    # when this dataset's raw-field Trust check is blocked (e.g. Trust's
    # early RawFieldCompletenessRule requires literal domain-registry
    # fields like asset_id/failure_code this dataset never carries) but
    # THIS capability's own governed concept evidence is independently
    # complete, publication may still proceed. Computed once per dataset
    # by the orchestration layer from the same semantic decisions
    # DatasetConceptFields itself was resolved from.
    canonical_evidence_completeness: CanonicalEvidenceCompletenessResult | None = None
    # P3.xxI.3: True when the orchestration layer already determined this
    # dataset is rate-card-shaped (a contract reference plus an explicit
    # rate -- the same governed reference row that ALSO feeds
    # rate_dataset_fields for this pass, never a per-row transactional
    # one). Suppresses ONLY this module's own "no quantity/invoice/cost
    # present, so read unit_price as a flat billed amount" fallback for
    # this specific dataset -- that fallback exists for a genuinely
    # different shape (an ambiguous bare "amount" column with no rate
    # role at all) and was never meant to also re-read a governed RATE
    # value a second time as an unrelated actual-billing total. A
    # rate-card-shaped dataset that separately ALSO resolves a real
    # invoice_amount or cost_amount concept is unaffected -- those paths
    # do not depend on this flag.
    is_rate_card_shaped: bool = False


@dataclass(frozen=True)
class _AmountLine:
    dataset_id: UUID
    dataset_label: str
    trust_assessment_id: UUID | None
    canonical_evidence_completeness: CanonicalEvidenceCompletenessResult | None
    row_reference: str
    amount: Decimal
    currency: str | None
    basis: str
    additional_dataset_ids: tuple[UUID, ...] = ()


def _to_decimal(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric):
        return None
    try:
        return Decimal(str(numeric))
    except InvalidOperation:
        return None


def _row_currency(row: pd.Series, currency_field: str | None) -> str | None:
    if currency_field is None or currency_field not in row.index:
        return None
    value = row[currency_field]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper()
    return text if len(text) == 3 and text.isalpha() else None


def _side_currency(lines: list[_AmountLine]) -> tuple[str | None, bool]:
    """The side's own currency, and whether the side is internally
    consistent enough to sum at all. >1 distinct known currency on one
    side is never cross-summed -- that side is reported unusable, never
    coerced to one of them."""
    currencies = {line.currency for line in lines if line.currency is not None}
    if len(currencies) > 1:
        return None, False
    if len(currencies) == 1:
        return next(iter(currencies)), True
    return None, True


@dataclass(frozen=True)
class _CollectedLines:
    """P3.xxI.2A: carries not just the per-work-order line dicts but
    whether EITHER side ever had a dataset in this case declare governed
    evidence for its amount concept AT ALL -- the case-wide
    NO_GOVERNED_EVIDENCE signal (Section 3). A work order absent from
    `expected`/`actual` because its side never governed-resolved anywhere
    in the case is categorically different from one absent because a
    governed, resolved dataset simply has no matching row for it
    (CONFIRMED_ZERO) -- see run_revenue_amount_variance's use of these two
    flags before treating any empty side as zero."""

    expected: dict[str, list[_AmountLine]]
    actual: dict[str, list[_AmountLine]]
    expected_side_has_governed_source: bool
    actual_side_has_governed_source: bool


def _collect_lines(
    datasets: list[DatasetConceptFields],
    eligible_subject_keys: set[str],
    rate_datasets: list[RateDatasetFields] | None = None,
) -> _CollectedLines:
    expected: dict[str, list[_AmountLine]] = {}
    actual: dict[str, list[_AmountLine]] = {}
    expected_side_has_governed_source = False
    actual_side_has_governed_source = False
    rate_datasets = rate_datasets or []
    contracts_by_subject: dict[str, set[str]] = {}
    for relationship_ds in datasets:
        relationship_subject_field = relationship_ds.subject_id_field
        relationship_contract_field = relationship_ds.contract_id_field
        if (
            relationship_subject_field is not None
            and relationship_contract_field is not None
            and relationship_subject_field in relationship_ds.dataframe.columns
            and relationship_contract_field in relationship_ds.dataframe.columns
        ):
            for _, relationship_row in relationship_ds.dataframe.iterrows():
                subject = relationship_row[relationship_subject_field]
                contract = relationship_row[relationship_contract_field]
                if pd.notna(subject) and pd.notna(contract):
                    contracts_by_subject.setdefault(str(subject), set()).add(str(contract))
    contract_by_subject = {
        subject: next(iter(contracts))
        for subject, contracts in contracts_by_subject.items()
        if len(contracts) == 1
    }
    for ds in datasets:
        subject_field = ds.subject_id_field
        if subject_field is None or subject_field not in ds.dataframe.columns:
            continue
        df = ds.dataframe
        quantity_field = ds.quantity_field if ds.quantity_field in df.columns else None
        unit_price_field = ds.unit_price_field if ds.unit_price_field in df.columns else None
        invoice_amount_field = (
            ds.invoice_amount_field if ds.invoice_amount_field in df.columns else None
        )
        cost_amount_field = ds.cost_amount_field if ds.cost_amount_field in df.columns else None
        # Form A: same-row quantity x unit_price -- inherently unit-safe,
        # the rate is by construction "price per this row's own unit"; no
        # cross-record unit-of-measure assumption is ever made.
        has_quantity_rate = quantity_field is not None and unit_price_field is not None
        # Form B: a direct reference amount on the same row (e.g. an
        # approved/agreed cost figure) -- distinct concept (cost_amount)
        # from the actual/billed side's invoice_amount, so the same
        # dataset can never simultaneously supply both sides of one
        # comparison.
        has_cost_reference = cost_amount_field is not None
        has_invoice_amount = invoice_amount_field is not None
        # unit_price/invoice_amount/cost_amount deliberately share the raw
        # alias "amount" (app/semantic/concept_registry.py's own
        # documented ambiguity) -- a bare "amount" column on an
        # invoice-shaped dataset can resolve to any of the three
        # depending on which sibling concept happens to also be present
        # elsewhere in the case. When unit_price resolves on a dataset
        # that carries NO co-located quantity (so it cannot possibly be
        # participating in Form A's same-row multiplication) and no
        # invoice_amount/cost_amount evidence exists on that same
        # dataset, its value is treated as a flat billed amount, not a
        # per-unit rate -- the only interpretation left once "a rate
        # multiplying some quantity" is structurally ruled out.
        # P3.xxI.3: a dataset the orchestration layer already identified
        # as rate-card-shaped is excluded from this fallback -- its
        # unit_price is a governed RATE (already feeding rate_datasets
        # for this same pass), never re-read a second time as an
        # unrelated flat billed total.
        has_unit_price_as_flat_amount = (
            not has_invoice_amount
            and not has_cost_reference
            and unit_price_field is not None
            and quantity_field is None
            and not ds.is_rate_card_shaped
        )
        has_cross_dataset_rate_source = quantity_field is not None and bool(rate_datasets)
        if not (
            has_quantity_rate
            or has_cost_reference
            or has_invoice_amount
            or has_unit_price_as_flat_amount
            or has_cross_dataset_rate_source
        ):
            continue
        # P3.xxI.2A Section 3/5/6: this dataset structurally resolved
        # governed evidence for this side's amount concept -- recorded
        # regardless of whether any row also happens to match an eligible
        # work order below. This is what lets an empty expected/actual
        # dict later be told apart from a side that never had governed
        # evidence anywhere in the case at all.
        if has_quantity_rate or has_cost_reference or has_cross_dataset_rate_source:
            expected_side_has_governed_source = True
        if has_invoice_amount or has_unit_price_as_flat_amount:
            actual_side_has_governed_source = True
        for row_index, row in df.iterrows():
            raw_key = row[subject_field]
            if raw_key is None or (isinstance(raw_key, float) and pd.isna(raw_key)):
                continue
            subject_key = str(raw_key)
            if subject_key not in eligible_subject_keys:
                continue
            currency = _row_currency(row, ds.currency_field)
            if quantity_field is not None and unit_price_field is not None:
                qty = _to_decimal(row[quantity_field])
                price = _to_decimal(row[unit_price_field])
                if qty is not None and price is not None:
                    expected.setdefault(subject_key, []).append(
                        _AmountLine(
                            ds.dataset_id,
                            ds.dataset_label,
                            ds.trust_assessment_id,
                            ds.canonical_evidence_completeness,
                            str(row_index),
                            qty * price,
                            currency,
                            "quantity_x_unit_price",
                        )
                    )
            elif quantity_field is not None and rate_datasets:
                qty = _to_decimal(row[quantity_field])
                contract_field = ds.contract_id_field
                timestamp_field = ds.event_timestamp_field
                row_unit_field = ds.unit_field
                # P3.xxI.2C: when this row carries no separate contract
                # reference and no governed subject->contract bridge
                # exists, the subject key ITSELF is tried as the contract
                # key -- always correct when the case's chosen subject IS
                # the contract (subject_key already equals the value
                # rate_datasets are keyed by), and harmless otherwise: a
                # work-order-shaped subject_key simply never matches any
                # real contract_id row below, so resolve_applicable_rate
                # still correctly returns None rather than a false match.
                contract_key = (
                    str(row[contract_field])
                    if contract_field is not None
                    and contract_field in df.columns
                    and pd.notna(row[contract_field])
                    else contract_by_subject.get(subject_key, subject_key)
                )
                event_at = (
                    pd.to_datetime(str(row[timestamp_field]), errors="coerce", utc=True)
                    if timestamp_field is not None and timestamp_field in df.columns
                    else None
                )
                if event_at is not None and pd.isna(event_at):
                    event_at = None
                rate = (
                    resolve_applicable_rate(
                        rate_datasets,
                        contract_key,
                        event_at,
                        ds.implicit_quantity_unit
                        or (
                            str(row[row_unit_field])
                            if row_unit_field is not None
                            and row_unit_field in df.columns
                            and pd.notna(row[row_unit_field])
                            else None
                        ),
                        currency,
                    )
                    if qty is not None and contract_key is not None
                    else None
                )
                if qty is not None and rate is not None:
                    expected.setdefault(subject_key, []).append(
                        _AmountLine(
                            ds.dataset_id,
                            f"{ds.dataset_label} + {rate.dataset_label}",
                            ds.trust_assessment_id,
                            ds.canonical_evidence_completeness,
                            f"{row_index}->{rate.row_reference}",
                            qty * rate.amount,
                            rate.currency or currency,
                            "quantity_x_cross_dataset_rate",
                            (rate.dataset_id,),
                        )
                    )
            if cost_amount_field is not None:
                cost = _to_decimal(row[cost_amount_field])
                if cost is not None:
                    expected.setdefault(subject_key, []).append(
                        _AmountLine(
                            ds.dataset_id,
                            ds.dataset_label,
                            ds.trust_assessment_id,
                            ds.canonical_evidence_completeness,
                            str(row_index),
                            cost,
                            currency,
                            "reference_cost_amount",
                        )
                    )
            if invoice_amount_field is not None:
                billed = _to_decimal(row[invoice_amount_field])
                if billed is not None:
                    actual.setdefault(subject_key, []).append(
                        _AmountLine(
                            ds.dataset_id,
                            ds.dataset_label,
                            ds.trust_assessment_id,
                            ds.canonical_evidence_completeness,
                            str(row_index),
                            billed,
                            currency,
                            "invoice_amount",
                        )
                    )
            elif has_unit_price_as_flat_amount and unit_price_field is not None:
                billed = _to_decimal(row[unit_price_field])
                if billed is not None:
                    actual.setdefault(subject_key, []).append(
                        _AmountLine(
                            ds.dataset_id,
                            ds.dataset_label,
                            ds.trust_assessment_id,
                            ds.canonical_evidence_completeness,
                            str(row_index),
                            billed,
                            currency,
                            "unit_price_as_flat_amount",
                        )
                    )
    return _CollectedLines(
        expected=expected,
        actual=actual,
        expected_side_has_governed_source=expected_side_has_governed_source,
        actual_side_has_governed_source=actual_side_has_governed_source,
    )


def _line_evidence(role: str, lines: list[_AmountLine]) -> list[EvidenceItemCreate]:
    items = []
    for line in lines[:20]:
        items.append(
            EvidenceItemCreate(
                evidence_type=EvidenceType.CALCULATION_TRACE,
                reference_type=f"{role}_amount_line",
                reference_id=f"{line.dataset_label}:{line.row_reference}",
                dataset_id=line.dataset_id,
                label=f"{role.title()} amount line ({line.basis})",
                description=(
                    f"{line.basis} = {line.amount} "
                    f"{line.currency or '(currency not confirmed)'} "
                    f"from {line.dataset_label} row {line.row_reference}"
                ),
                comparison_value=line.amount,
                comparison_currency=line.currency,
                metadata={"basis": line.basis},
            )
        )
    return items


def run_revenue_amount_variance(
    db: Session,
    organization_id: UUID,
    datasets: list[DatasetConceptFields],
    eligible_subject_keys: set[str],
    actor_user_id: UUID,
    rate_datasets: list[RateDatasetFields] | None = None,
    subject_entity_type: str = "work_order",
) -> list[Finding]:
    """Rule: REVENUE-AMOUNT-VARIANCE. For each governed BILLABLE OPERATIONAL
    SUBJECT entity (P3.xxE.3, same identity-confidence contract XDOM-A/
    MAINT-001 already use -- P3.xxI.2C generalized the concrete entity type
    beyond WORK_ORDER-only; see app/intelligence_packs/registry.py's
    alternative_canonical_entity_sets), compares an expected amount
    (governed consumption/rate or reference-cost evidence) against an
    actual amount (governed invoice evidence) linked by the same subject
    key. Never invents an FX rate, never multiplies across an unverified
    unit basis, never cross-sums incompatible currencies. XDOM-B is not
    read, called, or modified by this function.

    subject_entity_type names the CONCRETE entity type this call's
    `datasets`/`eligible_subject_keys` were resolved against (e.g.
    "work_order" or "contract") -- carried through verbatim into every
    finding's title, entity reference, and stable identity below (Fix #7:
    a finding against one subject type must never collapse into another's
    identity key). This module itself never chooses or infers the type; it
    only reflects whatever the orchestration layer already resolved.

    Unlike XDOM-A/B (one anchor dataset, one trust_assessment_id per call),
    this rule aggregates evidence across potentially many datasets in one
    call -- each finding uses the trust_assessment_id AND
    canonical_evidence_completeness of the dataset that supplied its own
    primary (first) expected-amount line, since that is the dataset
    governed_finding_publisher.publish() judges readiness against for
    that specific finding (the same P3.xxV.2D correction path XDOM-A/B
    already use, applied per contributing dataset instead of once).

    P3.xxI.2A safety gate: if EITHER side never had any dataset in this
    case resolve governed evidence for its amount concept at all, this
    function returns [] immediately -- no per-subject comparison is
    ever attempted. This is the fix for the defect where an empty
    per-subject line list (because the side's concept never resolved
    anywhere, not because a resolved dataset genuinely lacks a row) was
    silently summed to Decimal("0") and treated as a confirmed zero
    amount. A CONFIRMED_ZERO per subject (a resolved, governed dataset
    that simply has no matching row for this specific subject) remains
    valid and is still handled per-subject below -- only the case-wide
    "this side never resolved at all" state is now a hard stop."""
    if not datasets or not eligible_subject_keys:
        return []
    collected = _collect_lines(datasets, eligible_subject_keys, rate_datasets)
    if not collected.expected_side_has_governed_source:
        return []  # NO_GOVERNED_EVIDENCE (expected side) -- never inferred as zero
    if not collected.actual_side_has_governed_source:
        return []  # NO_GOVERNED_EVIDENCE (actual side) -- never inferred as zero
    expected_by_subject, actual_by_subject = collected.expected, collected.actual
    subject_label = subject_entity_type.replace("_", " ")

    published: list[Finding] = []
    for subject_key in sorted(expected_by_subject.keys()):
        expected_lines = expected_by_subject[subject_key]
        actual_lines = actual_by_subject.get(subject_key, [])

        expected_currency, expected_ok = _side_currency(expected_lines)
        actual_currency, actual_ok = _side_currency(actual_lines)
        if not expected_ok or not actual_ok:
            continue  # internally mixed currency on one side -- unsafe

        # P3.xxI.2A: this CONFIRMED_ZERO branch is only reached once the
        # case-wide safety gate above has already established that some
        # dataset in this case genuinely resolved governed actual-billing
        # evidence -- so an empty actual_lines here means that governed,
        # resolved dataset has no row for THIS specific work order, a
        # legitimate zero, never a stand-in for "we don't understand
        # billing in this case at all." The sum over an empty set is
        # trivially 0, in ANY currency, so it can never conflict with a
        # known expected-side currency -- distinct from a genuinely
        # observed-but-uncertain currency (Section 6's mixed_known_unknown
        # case), which stays blocked.
        if not actual_lines:
            comparability = (
                CurrencyComparability.SAME_KNOWN
                if expected_currency
                else (CurrencyComparability.UNKNOWN_BOTH)
            )
        else:
            comparability = classify_currency_comparability(expected_currency, actual_currency)
        if comparability not in COMPARABLE_CURRENCY_STATES:
            continue  # different known currencies, or one known/one unknown -- never bridged

        expected_amount = sum((line.amount for line in expected_lines), Decimal("0"))
        actual_amount = sum((line.amount for line in actual_lines), Decimal("0"))
        if expected_amount <= 0:
            continue

        tolerance = max(DEFAULT_ABSOLUTE_TOLERANCE, expected_amount * DEFAULT_RELATIVE_TOLERANCE)
        variance = expected_amount - actual_amount
        if variance <= tolerance:
            continue  # actual >= expected, or within materiality tolerance

        shortfall_type = (
            "full_billing_shortfall" if actual_amount == 0 else "partial_billing_shortfall"
        )
        currency_known = comparability == CurrencyComparability.SAME_KNOWN
        variance_ratio = variance / expected_amount if expected_amount else Decimal("1")
        severity = (
            FindingSeverity.HIGH
            if shortfall_type == "full_billing_shortfall" or variance_ratio >= Decimal("0.5")
            else FindingSeverity.MEDIUM
        )

        limitations = [
            "Estimated shortfall based on governed canonical consumption/rate and invoice "
            "evidence -- not a verified or recovered value.",
        ]
        if not currency_known:
            limitations.append(
                "Currency was not confirmed in the source data on either side; the amounts "
                "below are compared as same-unit magnitudes only, never assumed to be USD."
            )

        supporting_evidence = _line_evidence("expected", expected_lines) + _line_evidence(
            "actual", actual_lines
        )
        primary_dataset_id = expected_lines[0].dataset_id
        primary_trust_assessment_id = expected_lines[0].trust_assessment_id
        primary_canonical_evidence_completeness = expected_lines[0].canonical_evidence_completeness
        if primary_trust_assessment_id is None:
            continue
        contributing = {
            dataset_id
            for line in (*expected_lines, *actual_lines)
            for dataset_id in (line.dataset_id, *line.additional_dataset_ids)
        } - {primary_dataset_id}

        finding = governed_finding_publisher.publish(
            db,
            GovernedFindingRequest(
                organization_id=organization_id,
                primary_dataset_id=primary_dataset_id,
                trust_assessment_id=primary_trust_assessment_id,
                definition_code=RULE_CODE,
                definition_version="1.0",
                rule_condition_code=shortfall_type,
                affected_record_count=len(expected_lines) + len(actual_lines),
                title=f"{subject_label.capitalize()} {subject_key} billed amount is below "
                "the expected amount",
                summary=(
                    f"Expected {expected_amount} "
                    f"{expected_currency or '(currency not confirmed)'} from "
                    f"{len(expected_lines)} consumption/reference record(s); actual billed "
                    f"amount is {actual_amount} "
                    f"{actual_currency or '(currency not confirmed)'} from "
                    f"{len(actual_lines)} invoice record(s) -- a shortfall of {variance}."
                ),
                domain_code="cross_domain",
                severity=severity,
                finding_type=FindingType.LEAKAGE,
                actor_user_id=actor_user_id,
                contributing_datasets=[ContributingDataset(dataset_id=d) for d in contributing],
                entities=[{"entity_type": subject_entity_type, "canonical_key": subject_key}],
                identity_references=[
                    StableFindingIdentityReference(
                        identity_role="subject",
                        reference_type=subject_entity_type,
                        canonical_reference=subject_key,
                        canonical_entity=subject_entity_type,
                    )
                ],
                domains=["revenue"],
                economic_status="governed_pending",
                exposure_value=variance,
                exposure_value_type=(
                    FindingValueType.CURRENCY if currency_known else FindingValueType.DECIMAL
                ),
                exposure_currency=expected_currency if currency_known else None,
                supporting_evidence=supporting_evidence,
                canonical_evidence_completeness=primary_canonical_evidence_completeness,
                limitations=limitations,
            ),
        )
        if finding is not None:
            published.append(finding)
    return published
