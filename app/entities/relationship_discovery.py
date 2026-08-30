from __future__ import annotations

from dataclasses import replace
from itertools import combinations

import pandas as pd

from app.entities.confidence_decomposition import (
    compose_relationship_confidence,
    derive_relationship_status,
)
from app.entities.entity_candidate import EntityCandidate
from app.entities.identifier_normalization import normalize_identifier
from app.entities.relationship_candidate import RelationshipCandidate
from app.entities.relationship_type import Cardinality, RelationshipStatus, RelationshipType

# ---------------------------------------------------------------------------
# P3.xxE.3 sections 16/17/19: relationship discovery, order-independent by
# construction (all entity candidates and raw dataframes are gathered into
# flat, unordered collections before any pairwise logic runs -- same
# structural argument already proven for CaseSemanticContext/
# CaseEntityContext).
#
# Relationship semantics are evidence-gated, never type-pair-asserted
# (plan review correction 2) -- see relationship_type.py's module
# docstring. Every RelationshipType this module can produce
# (REFERENCES/BELONGS_TO/ASSOCIATED_WITH) is derived from the ACTUAL shape
# of co-occurrence/cardinality evidence in the data, never from a
# (left_entity_type, right_entity_type) lookup table.
#
# Pairing is ROW-LEVEL, not a cross-product of every entity of type A
# against every entity of type B that merely share a dataset -- a
# relationship candidate is only ever emitted for an (entity_a, entity_b)
# pair that was actually observed together in at least one real row.
# ---------------------------------------------------------------------------

_MIN_CO_OCCURRING_ROWS_FOR_CARDINALITY = 3
_STRUCTURAL_CORROBORATION_STEP = 0.15


def _entity_type_field_by_dataset(
    entity_candidates: list[EntityCandidate],
) -> dict[str, dict[str, str]]:
    """dataset_id -> {entity_type: source_field} -- picks the first
    observed field per (dataset, entity_type); used only to locate which
    raw dataframe column to inspect, not for identity."""
    result: dict[str, dict[str, str]] = {}
    for candidate in entity_candidates:
        for obs in candidate.observations:
            by_type = result.setdefault(obs.analysis_case_dataset_id, {})
            by_type.setdefault(obs.entity_type, obs.source_field)
    return result


def _normalized_pairs(df: pd.DataFrame, field_a: str, field_b: str) -> pd.DataFrame | None:
    if field_a not in df.columns or field_b not in df.columns:
        return None
    subset = df[[field_a, field_b]].dropna()
    if subset.empty:
        return None
    normalized = pd.DataFrame(
        {
            "a": subset[field_a].astype(str).map(normalize_identifier),
            "b": subset[field_b].astype(str).map(normalize_identifier),
        }
    )
    normalized = normalized[(normalized["a"] != "") & (normalized["b"] != "")]
    return normalized if not normalized.empty else None


def _cardinality_shape(normalized: pd.DataFrame) -> tuple[str, str] | None:
    """Returns (cardinality, direction) for a normalized (a, b) pair
    dataframe, or None if there isn't enough co-occurring data to say
    anything. direction is "a_belongs_to_b", "b_belongs_to_a", or
    "associated"."""
    if len(normalized) < _MIN_CO_OCCURRING_ROWS_FOR_CARDINALITY:
        return None
    a_to_b_clean = bool((normalized.groupby("a")["b"].nunique() == 1).all())
    b_to_a_clean = bool((normalized.groupby("b")["a"].nunique() == 1).all())
    a_repeats = normalized["a"].duplicated().any()
    b_repeats = normalized["b"].duplicated().any()

    if a_to_b_clean and b_to_a_clean:
        return (Cardinality.ONE_TO_ONE.value, "associated")
    if a_to_b_clean and b_repeats:
        return (Cardinality.MANY_TO_ONE.value, "a_belongs_to_b")
    if b_to_a_clean and a_repeats:
        return (Cardinality.MANY_TO_ONE.value, "b_belongs_to_a")
    return (Cardinality.MANY_TO_MANY.value, "associated")


def _has_temporal_signal(df: pd.DataFrame) -> bool:
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            return True
        lowered = str(column).lower()
        if "date" in lowered or "time" in lowered:
            return True
    return False


def _relationship_shape_for_type_pair(
    shape_rows: list[tuple[str, str]],
) -> tuple[str, str, str, bool]:
    """Given every dataset's (cardinality, direction) assessment for one
    (type_a, type_b) pair, returns (relationship_type, cardinality,
    left/right hint direction, has_conflict). Evidence-gated: derived
    purely from the shape of the evidence, never from the type pair
    itself (plan review correction 2)."""
    cardinalities = {r[0] for r in shape_rows}
    directions = {r[1] for r in shape_rows}
    non_unknown = cardinalities - set()

    has_conflict = len(directions - {"associated"}) > 1 or (
        len(non_unknown) > 1
        and Cardinality.MANY_TO_MANY.value in non_unknown
        and any(c != Cardinality.MANY_TO_MANY.value for c in non_unknown)
    )

    if "a_belongs_to_b" in directions and "b_belongs_to_a" not in directions:
        return (
            RelationshipType.BELONGS_TO.value,
            Cardinality.MANY_TO_ONE.value,
            "a_belongs_to_b",
            has_conflict,
        )
    if "b_belongs_to_a" in directions and "a_belongs_to_b" not in directions:
        return (
            RelationshipType.BELONGS_TO.value,
            Cardinality.MANY_TO_ONE.value,
            "b_belongs_to_a",
            has_conflict,
        )
    if Cardinality.ONE_TO_ONE.value in cardinalities and len(cardinalities) == 1:
        return (
            RelationshipType.REFERENCES.value,
            Cardinality.ONE_TO_ONE.value,
            "associated",
            has_conflict,
        )
    cardinality = (
        Cardinality.MANY_TO_MANY.value
        if Cardinality.MANY_TO_MANY.value in cardinalities
        else Cardinality.UNKNOWN.value
    )
    return RelationshipType.ASSOCIATED_WITH.value, cardinality, "associated", has_conflict


def discover_relationships_for_case(
    entity_candidates: list[EntityCandidate],
    raw_dataframes: dict[str, pd.DataFrame],
) -> list[RelationshipCandidate]:
    candidates_by_key: dict[tuple[str, str], EntityCandidate] = {
        (c.entity_type, c.normalized_key): c for c in entity_candidates
    }
    fields_by_dataset = _entity_type_field_by_dataset(entity_candidates)

    # Real, row-level observed pairs -- never a cross-product of every
    # entity of type A against every entity of type B that merely share a
    # dataset. Keyed by (type_a, type_b, key_a, key_b) -> [(dataset_id, has_temporal), ...]
    pair_occurrences: dict[tuple[str, str, str, str], list[tuple[str, bool]]] = {}
    # Aggregate cardinality/direction shape per (type_a, type_b), used to
    # decide relationship_type/cardinality once per type pair (a
    # case-level structural judgment) and re-applied to every real pair
    # of that type -- not re-derived per pair, and never derived from the
    # type pair's identity alone.
    type_pair_shape: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for dataset_id, type_fields in fields_by_dataset.items():
        types_here = sorted(type_fields)
        if len(types_here) < 2:
            continue
        df = raw_dataframes.get(dataset_id)
        if df is None:
            continue
        temporal = _has_temporal_signal(df)
        for type_a, type_b in combinations(types_here, 2):
            normalized = _normalized_pairs(df, type_fields[type_a], type_fields[type_b])
            if normalized is None:
                continue

            shape = _cardinality_shape(normalized)
            if shape is not None:
                type_pair_shape.setdefault((type_a, type_b), []).append(shape)

            for key_a, key_b in normalized.drop_duplicates().itertuples(index=False, name=None):
                pair_occurrences.setdefault((type_a, type_b, key_a, key_b), []).append(
                    (dataset_id, temporal)
                )

    relationship_candidates: list[RelationshipCandidate] = []
    for (type_a, type_b, key_a, key_b), occurrences in pair_occurrences.items():
        left_candidate = candidates_by_key.get((type_a, key_a))
        right_candidate = candidates_by_key.get((type_b, key_b))
        if left_candidate is None or right_candidate is None:
            continue

        shape_rows = type_pair_shape.get((type_a, type_b), [])
        relationship_type, cardinality, direction_hint, has_conflict = (
            _relationship_shape_for_type_pair(shape_rows)
            if shape_rows
            else (
                RelationshipType.ASSOCIATED_WITH.value,
                Cardinality.UNKNOWN.value,
                "associated",
                False,
            )
        )
        if direction_hint == "b_belongs_to_a":
            left_candidate, right_candidate = right_candidate, left_candidate

        dataset_ids = {o[0] for o in occurrences}
        has_temporal = any(o[1] for o in occurrences)
        structural_evidence_confidence = min(
            0.4
            + _STRUCTURAL_CORROBORATION_STEP * (len(dataset_ids) - 1)
            + (0.1 if has_temporal else 0.0),
            0.95,
        )

        confidence = compose_relationship_confidence(
            left_entity_identity_confidence=left_candidate.entity_identity_confidence,
            right_entity_identity_confidence=right_candidate.entity_identity_confidence,
            structural_evidence_confidence=structural_evidence_confidence,
        )
        status = derive_relationship_status(
            relationship_confidence=confidence.relationship_confidence,
            has_cardinality_conflict=has_conflict,
        )

        evidence_summary = [
            f"observed together in {len(dataset_ids)} dataset(s); "
            f"type-pair cardinality signal(s): {sorted({s[0] for s in shape_rows})}",
        ]
        if has_temporal:
            evidence_summary.append(
                "temporal columns present in contributing dataset(s) -- coarse plausibility only"
            )
        conflict_reason = None
        if has_conflict:
            conflict_reason = (
                f"cardinality/direction evidence disagrees across datasets for "
                f"{type_a}/{type_b}: {shape_rows}"
            )

        relationship_candidates.append(
            RelationshipCandidate(
                left_entity_type=left_candidate.entity_type,
                left_normalized_key=left_candidate.normalized_key,
                right_entity_type=right_candidate.entity_type,
                right_normalized_key=right_candidate.normalized_key,
                relationship_type=relationship_type,
                cardinality=cardinality,
                confidence=confidence,
                status=status,
                evidence_summary=evidence_summary,
                conflict_reason=conflict_reason,
            )
        )

    return _flag_contradictory_many_to_one_pairs(relationship_candidates)


def _flag_contradictory_many_to_one_pairs(
    candidates: list[RelationshipCandidate],
) -> list[RelationshipCandidate]:
    """Type-pair-level shape agreement (e.g. "many_to_one, work_order
    belongs_to asset" in every contributing dataset) is not enough to
    catch a real contradiction: two datasets can agree on the SHAPE while
    disagreeing on which specific entity a given "many"-side entity
    belongs to (e.g. WO-1 belongs_to A-1 in one dataset, WO-1 belongs_to
    A-2 in another). This pass catches exactly that -- any BELONGS_TO/
    MANY_TO_ONE candidate whose left (the "many" side) entity has more
    than one distinct right-side partner across the whole case is
    reclassified CONFLICTED, regardless of its per-pair confidence."""
    fan_out: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for candidate in candidates:
        if candidate.relationship_type != RelationshipType.BELONGS_TO.value:
            continue
        left_key = (candidate.left_entity_type, candidate.left_normalized_key)
        fan_out.setdefault(left_key, set()).add(
            (candidate.right_entity_type, candidate.right_normalized_key)
        )

    contradictory_left_keys = {key for key, partners in fan_out.items() if len(partners) > 1}
    if not contradictory_left_keys:
        return candidates

    flagged: list[RelationshipCandidate] = []
    for candidate in candidates:
        left_key = (candidate.left_entity_type, candidate.left_normalized_key)
        if (
            candidate.relationship_type == RelationshipType.BELONGS_TO.value
            and left_key in contradictory_left_keys
        ):
            partners = fan_out[left_key]
            flagged.append(
                replace(
                    candidate,
                    status=RelationshipStatus.CONFLICTED.value,
                    conflict_reason=(
                        f"{left_key[0]} {left_key[1]!r} belongs_to more than one distinct "
                        f"{candidate.right_entity_type} across contributing datasets: "
                        f"{sorted(partners)}"
                    ),
                )
            )
        else:
            flagged.append(candidate)
    return flagged
