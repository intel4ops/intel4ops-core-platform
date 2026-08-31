from __future__ import annotations

from app.process.activity_type import ParticipationRole

# ---------------------------------------------------------------------------
# P3.xxE.4 section 14: entity participation. Role is NEVER inferred solely
# from entity_type -- every rule below also requires the concept_code
# and/or dataset_role and/or primary-entity relationship as corroborating
# context (a PERSON could be ACTOR/CUSTOMER/APPROVER/OWNER depending on
# evidence, never assumed from PERSON alone).
# ---------------------------------------------------------------------------


def infer_participation_role(
    *,
    entity_type: str,
    concept_code: str,
    dataset_role: str,
    is_primary_entity: bool,
) -> tuple[str, float, str]:
    """Returns (role, role_confidence, evidence). is_primary_entity means
    this entity is the activity's own primary_entity_id (the SUBJECT of
    the activity, structurally, regardless of type)."""
    if is_primary_entity:
        return (
            ParticipationRole.SUBJECT.value,
            0.8,
            f"{entity_type} is the activity's primary entity in a {dataset_role!r}-role dataset",
        )

    if entity_type == "PERSON" and dataset_role in {"work_order", "labor"}:
        return (
            ParticipationRole.ACTOR.value,
            0.7,
            f"PERSON co-occurs via {concept_code!r} in a {dataset_role!r}-role dataset",
        )

    if entity_type == "PART" and dataset_role in {"work_order", "inventory"}:
        return (
            ParticipationRole.RESOURCE.value,
            0.6,
            f"PART co-occurs via {concept_code!r} in a {dataset_role!r}-role dataset",
        )

    if entity_type == "ASSET" and dataset_role in {"work_order", "event"}:
        return (
            ParticipationRole.RESOURCE.value,
            0.6,
            f"ASSET co-occurs via {concept_code!r} in a {dataset_role!r}-role dataset, "
            "not the activity's own primary entity",
        )

    if entity_type == "INVOICE" and dataset_role == "invoice":
        return (
            ParticipationRole.OUTPUT.value,
            0.55,
            f"INVOICE co-occurs via {concept_code!r} in an {dataset_role!r}-role dataset",
        )

    if entity_type == "CUSTOMER":
        return (
            ParticipationRole.REFERENCE.value,
            0.5,
            f"CUSTOMER co-occurs via {concept_code!r}, treated as contextual reference "
            "absent stronger evidence",
        )

    if entity_type == "LOCATION":
        return (
            ParticipationRole.LOCATION.value,
            0.5,
            f"LOCATION co-occurs via {concept_code!r}",
        )

    return (
        ParticipationRole.UNKNOWN.value,
        0.0,
        f"no participation-role rule matched for {entity_type} via {concept_code!r} "
        f"in a {dataset_role!r}-role dataset",
    )
