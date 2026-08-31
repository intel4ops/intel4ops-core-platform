from __future__ import annotations

import re
from uuid import UUID

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex, MeasureCapability
from app.intelligence_packs.confidence_distribution import ConfidenceDistribution
from app.models.analysis_case import AnalysisCaseEntityLink, EntityLinkStatus
from app.models.entities_canonical import CanonicalCaseEntity, CanonicalCaseRelationship
from app.models.process_canonical import (
    CanonicalOperationalProcess,
    CanonicalProcessActivity,
    CanonicalProcessEdge,
)
from app.semantic.candidate import InterpretationDecision
from app.semantic.concept_registry import CanonicalConceptRegistry, CanonicalConceptType

# ---------------------------------------------------------------------------
# P3.xxE.5: the one DB-touching file in the capability-index surface --
# mirrors app/entities/intelligence_contract.py's own "single file that
# necessarily imports SQLAlchemy" role. Builds ONE CaseCapabilityIndex per
# run from E.3's CanonicalCaseEntity/CanonicalCaseRelationship, E.4's
# CanonicalProcessActivity/CanonicalProcessEdge, and the legacy
# domain/field/entity-link/trust signals already resolved earlier in
# analysis_case_orchestration_service.py's execute() -- never re-derives
# or rewrites any of them (Invariant: canonical entity/relationship/process
# identity is read-only here, matching E.4's own intelligence_contract.py
# precedent).
# ---------------------------------------------------------------------------

_MEASURE_CONCEPT_TYPES = frozenset(
    {CanonicalConceptType.QUANTITY.value, CanonicalConceptType.MONETARY_AMOUNT.value}
)
_CURRENCY_COLUMN_PATTERN = re.compile(r"currency", re.IGNORECASE)
_UNIT_COLUMN_PATTERN = re.compile(r"unit(_of_measure)?$|^uom$", re.IGNORECASE)


def _distribution(values: list[float]) -> ConfidenceDistribution:
    return ConfidenceDistribution(values=tuple(values))


def _legacy_resolved_entity_types(
    db: Session, organization_id: UUID, analysis_case_id: UUID
) -> frozenset[str]:
    rows = db.scalars(
        select(AnalysisCaseEntityLink.entity_type).where(
            AnalysisCaseEntityLink.organization_id == organization_id,
            AnalysisCaseEntityLink.analysis_case_id == analysis_case_id,
            AnalysisCaseEntityLink.status == EntityLinkStatus.MATCHED.value,
        )
    ).all()
    return frozenset(rows)


def _canonical_entity_signals(
    db: Session, organization_id: UUID, run_id: UUID
) -> tuple[frozenset[str], dict[str, ConfidenceDistribution]]:
    rows = db.execute(
        select(
            CanonicalCaseEntity.entity_type, CanonicalCaseEntity.entity_identity_confidence
        ).where(
            CanonicalCaseEntity.organization_id == organization_id,
            CanonicalCaseEntity.run_id == run_id,
        )
    ).all()
    by_type: dict[str, list[float]] = {}
    for entity_type, confidence in rows:
        by_type.setdefault(entity_type, []).append(confidence)
    return frozenset(by_type), {k: _distribution(v) for k, v in by_type.items()}


def _canonical_relationship_signals(
    db: Session, organization_id: UUID, run_id: UUID
) -> tuple[frozenset[str], dict[str, ConfidenceDistribution]]:
    rows = db.execute(
        select(
            CanonicalCaseRelationship.relationship_type,
            CanonicalCaseRelationship.relationship_confidence,
        ).where(
            CanonicalCaseRelationship.organization_id == organization_id,
            CanonicalCaseRelationship.run_id == run_id,
        )
    ).all()
    by_type: dict[str, list[float]] = {}
    for relationship_type, confidence in rows:
        by_type.setdefault(relationship_type, []).append(confidence)
    return frozenset(by_type), {k: _distribution(v) for k, v in by_type.items()}


def _process_signals(
    db: Session, organization_id: UUID, run_id: UUID
) -> tuple[
    frozenset[str],
    dict[str, ConfidenceDistribution],
    frozenset[tuple[str, str]],
    dict[tuple[str, str], ConfidenceDistribution],
    frozenset[str],
    dict[str, ConfidenceDistribution],
]:
    # process_id alone isn't run-scoped, so resolve this run's process ids
    # from CanonicalOperationalProcess first.
    run_process_ids = set(
        db.scalars(
            select(CanonicalOperationalProcess.id).where(
                CanonicalOperationalProcess.organization_id == organization_id,
                CanonicalOperationalProcess.run_id == run_id,
            )
        ).all()
    )
    if not run_process_ids:
        return frozenset(), {}, frozenset(), {}, frozenset(), {}

    activity_rows = db.execute(
        select(
            CanonicalProcessActivity.id,
            CanonicalProcessActivity.activity_type,
            CanonicalProcessActivity.activity_type_confidence,
            CanonicalProcessActivity.state_value,
            CanonicalProcessActivity.state_meaning_confidence,
        ).where(
            CanonicalProcessActivity.organization_id == organization_id,
            CanonicalProcessActivity.process_id.in_(run_process_ids),
        )
    ).all()

    activity_type_by_id: dict[UUID, str] = {}
    activity_confidence_by_type: dict[str, list[float]] = {}
    state_confidence_by_state: dict[str, list[float]] = {}
    for (
        activity_id,
        activity_type,
        type_confidence,
        state_value,
        state_meaning_confidence,
    ) in activity_rows:
        activity_type_by_id[activity_id] = activity_type
        activity_confidence_by_type.setdefault(activity_type, []).append(type_confidence)
        if state_value is not None:
            state_confidence_by_state.setdefault(state_value, []).append(state_meaning_confidence)

    edge_rows = db.execute(
        select(
            CanonicalProcessEdge.from_activity_id,
            CanonicalProcessEdge.to_activity_id,
            CanonicalProcessEdge.edge_type,
            CanonicalProcessEdge.precedence_confidence,
        ).where(
            CanonicalProcessEdge.organization_id == organization_id,
            CanonicalProcessEdge.process_id.in_(run_process_ids),
            CanonicalProcessEdge.edge_type == "PRECEDES",
        )
    ).all()
    precedes_confidence_by_pair: dict[tuple[str, str], list[float]] = {}
    for from_id, to_id, _edge_type, precedence_confidence in edge_rows:
        from_type = activity_type_by_id.get(from_id)
        to_type = activity_type_by_id.get(to_id)
        if from_type is None or to_type is None:
            continue
        precedes_confidence_by_pair.setdefault((from_type, to_type), []).append(
            precedence_confidence
        )

    return (
        frozenset(activity_confidence_by_type),
        {k: _distribution(v) for k, v in activity_confidence_by_type.items()},
        frozenset(precedes_confidence_by_pair),
        {k: _distribution(v) for k, v in precedes_confidence_by_pair.items()},
        frozenset(state_confidence_by_state),
        {k: _distribution(v) for k, v in state_confidence_by_state.items()},
    )


def _measure_capabilities(
    decisions_by_dataset: dict[UUID, list[InterpretationDecision]],
    raw_dataframes: dict[UUID, pd.DataFrame],
    concept_registry: CanonicalConceptRegistry,
) -> dict[str, MeasureCapability]:
    """Plan review correction 5: deliberately minimal -- one pass over
    already-computed semantic decisions, classifying a field as a measure
    only via the registered CanonicalConcept.concept_type (QUANTITY/
    MONETARY_AMOUNT), never a domain-specific field-name heuristic.
    Currency/unit columns are detected generically by column-name PATTERN
    (a structural/schema convention check, not a business-domain guess)."""
    by_measure: dict[str, list[tuple[float, frozenset[str], frozenset[str]]]] = {}
    for dataset_id, decisions in decisions_by_dataset.items():
        df = raw_dataframes.get(dataset_id)
        currency_values: frozenset[str] = frozenset()
        unit_values: frozenset[str] = frozenset()
        if df is not None:
            for column in df.columns:
                if _CURRENCY_COLUMN_PATTERN.search(str(column)):
                    currency_values = frozenset(df[column].dropna().astype(str).unique())
                elif _UNIT_COLUMN_PATTERN.search(str(column)):
                    unit_values = frozenset(df[column].dropna().astype(str).unique())
        for decision in decisions:
            if decision.selected_concept is None:
                continue
            concept = concept_registry.get(decision.selected_concept)
            if concept is None or concept.concept_type not in _MEASURE_CONCEPT_TYPES:
                continue
            by_measure.setdefault(decision.selected_concept, []).append(
                (decision.confidence, currency_values, unit_values)
            )

    result: dict[str, MeasureCapability] = {}
    for measure_code, observations in by_measure.items():
        confidences = [c for c, _, _ in observations]
        currencies: set[str] = set()
        units: set[str] = set()
        for _, cur, un in observations:
            currencies |= cur
            units |= un
        result[measure_code] = MeasureCapability(
            measure_code=measure_code,
            count=len(observations),
            # one observation per dataset that carries the concept --
            # always fully "present" where counted
            coverage=1.0,
            currencies_observed=frozenset(currencies),
            units_observed=frozenset(units),
            confidence=_distribution(confidences),
        )
    return result


def build_case_capability_index(
    db: Session,
    organization_id: UUID,
    analysis_case_id: UUID,
    run_id: UUID,
    *,
    available_domains: frozenset[str],
    available_canonical_fields: frozenset[str],
    domains_with_resolved_trust: frozenset[str],
    decisions_by_dataset: dict[UUID, list[InterpretationDecision]],
    raw_dataframes: dict[UUID, pd.DataFrame],
    concept_registry: CanonicalConceptRegistry,
) -> CaseCapabilityIndex:
    resolved_entity_types = _legacy_resolved_entity_types(db, organization_id, analysis_case_id)
    canonical_entity_types, entity_confidence = _canonical_entity_signals(
        db, organization_id, run_id
    )
    canonical_relationship_types, relationship_confidence = _canonical_relationship_signals(
        db, organization_id, run_id
    )
    (
        activity_types,
        activity_confidence,
        precedes_pairs,
        precedes_confidence,
        named_states,
        state_confidence,
    ) = _process_signals(db, organization_id, run_id)
    canonical_measures = _measure_capabilities(
        decisions_by_dataset, raw_dataframes, concept_registry
    )

    distinct_currencies: set[str] = set()
    for measure in canonical_measures.values():
        distinct_currencies |= measure.currencies_observed

    return CaseCapabilityIndex(
        organization_id=str(organization_id),
        analysis_case_id=str(analysis_case_id),
        run_id=str(run_id),
        available_domains=available_domains,
        available_canonical_fields=available_canonical_fields,
        resolved_entity_types=resolved_entity_types,
        currency_unresolved=False,
        domains_with_resolved_trust=domains_with_resolved_trust,
        canonical_entity_types_present=canonical_entity_types,
        canonical_entity_identity_confidence_by_type=entity_confidence,
        canonical_relationship_types_present=canonical_relationship_types,
        canonical_relationship_confidence_by_type=relationship_confidence,
        activity_types_present=activity_types,
        activity_type_confidence_by_type=activity_confidence,
        precedes_pairs_present=precedes_pairs,
        precedes_pair_confidence=precedes_confidence,
        named_states_present=named_states,
        state_meaning_confidence_by_state=state_confidence,
        process_confidence_by_anchor_type={},
        canonical_measures=canonical_measures,
        distinct_currencies_observed=frozenset(distinct_currencies),
        distinct_units_observed_by_measure={
            code: measure.units_observed for code, measure in canonical_measures.items()
        },
    )
