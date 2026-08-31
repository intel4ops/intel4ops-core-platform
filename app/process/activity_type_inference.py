from __future__ import annotations

from app.process.activity_type import ActivityType

# ---------------------------------------------------------------------------
# P3.xxE.4 plan review correction 1: the semantic-evidence eligibility
# hierarchy. accepted_with_flag and review_required are NOT equivalent --
# five distinct tiers, branched explicitly here (never a flat strict/weak
# split):
#
#   HUMAN_CONFIRMED/HUMAN_CORRECTED  -> authoritative, named type, full confidence
#   AUTO_ACCEPTED                    -> authoritative machine evidence, named type, full confidence
#   ACCEPTED_WITH_FLAG               -> supporting evidence; named type ONLY when
#                                        independently corroborated, else GENERIC
#   REVIEW_REQUIRED                  -> hypothesis-generation only; NEVER a named
#                                        type on its own, always GENERIC, capped low
#   UNRESOLVED                       -> no semantic-meaning authority at all
#
# This is TIMESTAMP-concept-specific -- identifier-concept inference for
# entity typing stays exactly as strict as
# app/entities/entity_type_inference.py (that module is untouched by this
# milestone). Do not weaken E.2 semantic thresholds themselves; this file
# only governs how those existing thresholds are CONSUMED for activity
# typing, never lowers them.
# ---------------------------------------------------------------------------

_HUMAN_TIERS = frozenset({"human_confirmed", "human_corrected"})
_ACCEPTED_WITH_FLAG_UNCORROBORATED_DISCOUNT = 0.5
_REVIEW_REQUIRED_TYPE_CONFIDENCE_CAP = 0.35

# Generic, data-driven concept -> candidate named ActivityType mapping.
# event_timestamp's alias set is deliberately broad/ambiguous (includes
# "timestamp"/"date") so it never confidently names a specific activity on
# its own -- OTHER is the honest ceiling for that concept regardless of tier.
_TEMPORAL_CONCEPT_TO_ACTIVITY_TYPE: dict[str, str] = {
    "completed_timestamp": ActivityType.COMPLETE.value,
    "scheduled_timestamp": ActivityType.SCHEDULE.value,
    "event_timestamp": ActivityType.OTHER.value,
}


def candidate_activity_type_for_concept(concept_code: str) -> str:
    return _TEMPORAL_CONCEPT_TO_ACTIVITY_TYPE.get(concept_code, ActivityType.OTHER.value)


def infer_activity_type(
    *,
    machine_status: str,
    concept_code: str,
    machine_confidence: float,
    is_independently_corroborated: bool,
) -> tuple[str, float]:
    """Returns (activity_type, activity_type_confidence). A named type is
    reachable only via HUMAN_CONFIRMED/HUMAN_CORRECTED/AUTO_ACCEPTED, or
    ACCEPTED_WITH_FLAG when independently corroborated by temporal/
    structural/entity evidence beyond the bare temporal observation
    itself. REVIEW_REQUIRED and uncorroborated ACCEPTED_WITH_FLAG both
    stay GENERIC -- existence may be supported, naming may not."""
    candidate_type = candidate_activity_type_for_concept(concept_code)

    if machine_status in _HUMAN_TIERS or machine_status == "auto_accepted":
        return candidate_type, machine_confidence

    if machine_status == "accepted_with_flag":
        if is_independently_corroborated:
            return candidate_type, machine_confidence
        return (
            ActivityType.GENERIC.value,
            round(machine_confidence * _ACCEPTED_WITH_FLAG_UNCORROBORATED_DISCOUNT, 4),
        )

    if machine_status == "review_required":
        return ActivityType.GENERIC.value, min(
            machine_confidence, _REVIEW_REQUIRED_TYPE_CONFIDENCE_CAP
        )

    return ActivityType.GENERIC.value, 0.0
