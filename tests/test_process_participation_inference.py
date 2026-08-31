"""P3.xxE.4 section 14: participation role is never inferred solely from
entity_type -- concept_code/dataset_role/primary-entity context are all
required corroborating inputs."""

from app.process.activity_type import ParticipationRole
from app.process.participation_inference import infer_participation_role


def test_primary_entity_is_always_subject_regardless_of_type() -> None:
    role, confidence, _ = infer_participation_role(
        entity_type="CUSTOMER",
        concept_code="customer_id",
        dataset_role="invoice",
        is_primary_entity=True,
    )
    assert role == ParticipationRole.SUBJECT.value
    assert confidence > 0.0


def test_person_in_labor_context_is_actor() -> None:
    role, _, _ = infer_participation_role(
        entity_type="PERSON",
        concept_code="technician_id",
        dataset_role="labor",
        is_primary_entity=False,
    )
    assert role == ParticipationRole.ACTOR.value


def test_person_alone_without_labor_context_does_not_default_to_actor() -> None:
    """entity_type alone is never sufficient -- same PERSON type, different
    context, must not force the same role."""
    role, confidence, _ = infer_participation_role(
        entity_type="PERSON",
        concept_code="reference_id",
        dataset_role="invoice",
        is_primary_entity=False,
    )
    assert role != ParticipationRole.ACTOR.value or confidence == 0.0


def test_part_in_inventory_context_is_resource() -> None:
    role, _, _ = infer_participation_role(
        entity_type="PART",
        concept_code="part_id",
        dataset_role="inventory",
        is_primary_entity=False,
    )
    assert role == ParticipationRole.RESOURCE.value


def test_unmatched_context_falls_back_to_unknown_at_zero_confidence() -> None:
    role, confidence, _ = infer_participation_role(
        entity_type="OTHER",
        concept_code="whatever",
        dataset_role="unknown",
        is_primary_entity=False,
    )
    assert role == ParticipationRole.UNKNOWN.value
    assert confidence == 0.0
