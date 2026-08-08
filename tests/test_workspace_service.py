from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_ingestion_service import batch_payload
from test_ingestion_service import foundation as ingestion_foundation

from app.models.entities import MembershipRole, MembershipStatus, Organization
from app.models.trust import AnalyticalReadinessDecision, ReadinessStatus, TrustAssessment
from app.models.workspace import OrganizationChallenge, OrganizationObjective, OrganizationSystem
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate
from app.schemas.memberships import MembershipCreate
from app.schemas.workspace import OrganizationSystemSelection
from app.services.ingestion_service import DatasetService, IngestionBatchService
from app.services.membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService
from app.services.workspace_service import (
    WorkspaceServiceError,
    get_team_summary,
    get_workspace_summary,
    list_challenges,
    list_objectives,
    list_systems,
    persona_for_role,
    replace_challenges,
    replace_objectives,
    replace_systems,
)


def create_organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )


def test_new_organization_has_incomplete_workspace_summary(db: Session) -> None:
    organization = create_organization(db, "workspace-new")
    creator = uuid4()
    OrganizationMembershipService().create(
        db,
        organization.id,
        MembershipCreate(
            user_id=creator,
            role=MembershipRole.ORGANIZATION_ADMIN,
            status=MembershipStatus.ACTIVE,
        ),
        invited_by_user_id=creator,
    )

    summary = get_workspace_summary(db, organization.id, creator)

    assert summary.setup_progress.percent < 100
    assert "industry" in summary.setup_progress.missing_required
    assert "objectives" in summary.setup_progress.missing_required
    assert summary.data_readiness == "NOT_STARTED"
    assert summary.ai_readiness == "NOT_READY"
    assert summary.handoff_state == "SETUP_IN_PROGRESS"
    assert summary.current_user_persona == "Admin"


def test_replace_objectives_add_and_remove(db: Session) -> None:
    organization = create_organization(db, "workspace-objectives")
    actor = uuid4()

    first = replace_objectives(db, organization.id, ["increase_revenue"], actor)
    assert [item.objective_code for item in first] == ["increase_revenue"]

    second = replace_objectives(db, organization.id, ["increase_revenue", "reduce_downtime"], actor)
    assert {item.objective_code for item in second} == {"increase_revenue", "reduce_downtime"}

    third = replace_objectives(db, organization.id, ["reduce_downtime"], actor)
    assert [item.objective_code for item in third] == ["reduce_downtime"]
    assert list_objectives(db, organization.id) == third


def test_replace_objectives_rejects_invalid_code(db: Session) -> None:
    organization = create_organization(db, "workspace-objectives-invalid")
    with pytest.raises(WorkspaceServiceError) as excinfo:
        replace_objectives(db, organization.id, ["not_a_real_objective"], uuid4())
    assert excinfo.value.code == "invalid_registry_code"
    assert excinfo.value.status == 400


def test_replace_challenges_add_and_remove(db: Session) -> None:
    organization = create_organization(db, "workspace-challenges")
    actor = uuid4()

    replace_challenges(db, organization.id, ["downtime", "fuel_loss"], actor)
    remaining = replace_challenges(db, organization.id, ["fuel_loss"], actor)
    assert [item.challenge_code for item in remaining] == ["fuel_loss"]
    assert list_challenges(db, organization.id) == remaining


def test_replace_challenges_rejects_invalid_code(db: Session) -> None:
    organization = create_organization(db, "workspace-challenges-invalid")
    with pytest.raises(WorkspaceServiceError) as excinfo:
        replace_challenges(db, organization.id, ["not_a_real_challenge"], uuid4())
    assert excinfo.value.code == "invalid_registry_code"


def test_replace_systems_add_and_remove_with_custom_label(db: Session) -> None:
    organization = create_organization(db, "workspace-systems")
    actor = uuid4()

    selections = [
        OrganizationSystemSelection(system_code="sap"),
        OrganizationSystemSelection(system_code="other", custom_label="Homegrown planner"),
    ]
    created = replace_systems(db, organization.id, selections, actor)
    assert {(item.system_code, item.custom_label) for item in created} == {
        ("sap", None),
        ("other", "Homegrown planner"),
    }

    remaining = replace_systems(
        db, organization.id, [OrganizationSystemSelection(system_code="sap")], actor
    )
    assert [(item.system_code, item.custom_label) for item in remaining] == [("sap", None)]
    assert list_systems(db, organization.id) == remaining


def test_replace_systems_rejects_invalid_code(db: Session) -> None:
    organization = create_organization(db, "workspace-systems-invalid")
    with pytest.raises(WorkspaceServiceError) as excinfo:
        replace_systems(
            db, organization.id, [OrganizationSystemSelection(system_code="ghost_erp")], uuid4()
        )
    assert excinfo.value.code == "invalid_registry_code"


def test_replace_systems_requires_custom_label_for_custom_code(db: Session) -> None:
    organization = create_organization(db, "workspace-systems-custom-required")
    with pytest.raises(WorkspaceServiceError) as excinfo:
        replace_systems(
            db, organization.id, [OrganizationSystemSelection(system_code="other")], uuid4()
        )
    assert excinfo.value.code == "invalid_system_selection"


def test_replace_systems_rejects_custom_label_for_known_code(db: Session) -> None:
    organization = create_organization(db, "workspace-systems-label-not-allowed")
    with pytest.raises(WorkspaceServiceError) as excinfo:
        replace_systems(
            db,
            organization.id,
            [OrganizationSystemSelection(system_code="sap", custom_label="My SAP")],
            uuid4(),
        )
    assert excinfo.value.code == "invalid_system_selection"


def test_replace_systems_rejects_duplicate_known_code(db: Session) -> None:
    organization = create_organization(db, "workspace-systems-duplicate")
    with pytest.raises(WorkspaceServiceError) as excinfo:
        replace_systems(
            db,
            organization.id,
            [
                OrganizationSystemSelection(system_code="sap"),
                OrganizationSystemSelection(system_code="sap"),
            ],
            uuid4(),
        )
    assert excinfo.value.code == "invalid_system_selection"


def test_team_summary_reflects_membership_and_invitations(db: Session) -> None:
    organization = create_organization(db, "workspace-team")
    membership_service = OrganizationMembershipService()
    admin_id = uuid4()
    membership_service.create(
        db,
        organization.id,
        MembershipCreate(
            user_id=admin_id, role=MembershipRole.ORGANIZATION_ADMIN, status=MembershipStatus.ACTIVE
        ),
        invited_by_user_id=admin_id,
    )
    membership_service.create(
        db,
        organization.id,
        MembershipCreate(
            user_id=uuid4(), role=MembershipRole.OPERATOR, status=MembershipStatus.ACTIVE
        ),
        invited_by_user_id=admin_id,
    )
    membership_service.create(
        db,
        organization.id,
        MembershipCreate(
            user_id=uuid4(), role=MembershipRole.VIEWER, status=MembershipStatus.INVITED
        ),
        invited_by_user_id=admin_id,
    )

    summary = get_team_summary(db, organization.id)

    assert summary.active_member_count == 2
    assert summary.counts_by_role["organization_admin"] == 1
    assert summary.counts_by_role["operator"] == 1
    assert summary.counts_by_persona["Admin"] == 1
    assert summary.counts_by_persona["Operations"] == 1


def test_persona_mapping() -> None:
    assert persona_for_role(MembershipRole.ORGANIZATION_ADMIN.value) == "Admin"
    assert persona_for_role(MembershipRole.OPERATOR.value) == "Operations"
    assert persona_for_role(MembershipRole.RECOVERY_MANAGER.value) == "Finance"
    assert persona_for_role(MembershipRole.ANALYST.value) == "Analyst"
    assert persona_for_role(MembershipRole.VIEWER.value) == "Viewer"


def test_setup_progress_reaches_full_when_all_components_satisfied(db: Session) -> None:
    organization = create_organization(db, "workspace-full-setup")
    organization.industry = "manufacturing"
    db.commit()
    creator = uuid4()
    membership_service = OrganizationMembershipService()
    membership_service.create(
        db,
        organization.id,
        MembershipCreate(
            user_id=creator, role=MembershipRole.ORGANIZATION_ADMIN, status=MembershipStatus.ACTIVE
        ),
        invited_by_user_id=creator,
    )
    membership_service.create(
        db,
        organization.id,
        MembershipCreate(
            user_id=uuid4(), role=MembershipRole.OPERATOR, status=MembershipStatus.ACTIVE
        ),
        invited_by_user_id=creator,
    )
    replace_objectives(db, organization.id, ["increase_revenue"], creator)
    replace_challenges(db, organization.id, ["downtime"], creator)
    replace_systems(db, organization.id, [OrganizationSystemSelection(system_code="sap")], creator)

    summary = get_workspace_summary(db, organization.id, creator)

    assert summary.setup_progress.percent == 100
    assert summary.setup_progress.missing_required == []
    assert summary.handoff_state == "DATA_PENDING"


def test_data_readiness_and_ai_readiness_progression(db: Session) -> None:
    organization_id, source_id = ingestion_foundation(db, "workspace-data-readiness")
    creator = uuid4()
    OrganizationMembershipService().create(
        db,
        organization_id,
        MembershipCreate(
            user_id=creator, role=MembershipRole.ORGANIZATION_ADMIN, status=MembershipStatus.ACTIVE
        ),
        invited_by_user_id=creator,
    )
    org = db.get(Organization, organization_id)
    assert org is not None
    org.industry = "manufacturing"
    db.commit()
    replace_objectives(db, organization_id, ["increase_revenue"], creator)

    before = get_workspace_summary(db, organization_id, creator)
    assert before.data_readiness == "NOT_STARTED"
    assert before.ai_readiness == "PENDING_DATA"
    assert before.handoff_state == "DATA_PENDING"

    IngestionBatchService().create(db, organization_id, batch_payload(source_id), creator)

    after_data = get_workspace_summary(db, organization_id, creator)
    assert after_data.data_readiness == "HAS_DATA"
    assert after_data.ai_readiness == "PENDING_TRUST"
    assert after_data.handoff_state == "TRUST_PENDING"

    dataset = DatasetService().create(
        db,
        organization_id,
        DatasetCreate(
            source_system_id=source_id,
            name="Transactions",
            code="transactions",
            domain="operations",
            dataset_type="transactional",
        ),
        creator,
    )
    assessment = TrustAssessment(organization_id=organization_id, dataset_id=dataset.id)
    db.add(assessment)
    db.flush()
    decision = AnalyticalReadinessDecision(
        organization_id=organization_id,
        trust_assessment_id=assessment.id,
        analytical_level="arithmetic",
        readiness_status=ReadinessStatus.READY.value,
        explanation="test evidence",
    )
    db.add(decision)
    db.commit()

    after_trust = get_workspace_summary(db, organization_id, creator)
    assert after_trust.ai_readiness == "READY"
    assert after_trust.handoff_state == "READY_FOR_VALUE_SCAN"


def test_unique_objective_per_organization_enforced_at_db_level(db: Session) -> None:
    organization = create_organization(db, "workspace-objective-unique")
    db.add(
        OrganizationObjective(
            organization_id=organization.id,
            objective_code="increase_revenue",
            selected_by_user_id=uuid4(),
        )
    )
    db.commit()
    db.add(
        OrganizationObjective(
            organization_id=organization.id,
            objective_code="increase_revenue",
            selected_by_user_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unique_system_per_organization_enforced_at_db_level(db: Session) -> None:
    # A non-NULL custom_label pair is used deliberately: SQL treats NULL as
    # distinct from NULL in a UNIQUE constraint, so two NULL-custom_label
    # rows for the same known system_code would NOT collide at the database
    # level -- that gap is covered by replace_systems' service-layer check
    # (see test_replace_systems_rejects_duplicate_known_code), not by this
    # constraint. This test verifies the constraint does its part: it
    # rejects two genuinely identical rows.
    organization = create_organization(db, "workspace-system-unique")
    db.add(
        OrganizationSystem(
            organization_id=organization.id,
            system_code="other",
            custom_label="Homegrown planner",
            selected_by_user_id=uuid4(),
        )
    )
    db.commit()
    db.add(
        OrganizationSystem(
            organization_id=organization.id,
            system_code="other",
            custom_label="Homegrown planner",
            selected_by_user_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unique_challenge_per_organization_enforced_at_db_level(db: Session) -> None:
    organization = create_organization(db, "workspace-challenge-unique")
    db.add(
        OrganizationChallenge(
            organization_id=organization.id,
            challenge_code="downtime",
            selected_by_user_id=uuid4(),
        )
    )
    db.commit()
    db.add(
        OrganizationChallenge(
            organization_id=organization.id,
            challenge_code="downtime",
            selected_by_user_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_cascade_delete_removes_workspace_selections(db: Session) -> None:
    organization = create_organization(db, "workspace-cascade")
    actor = uuid4()
    replace_objectives(db, organization.id, ["increase_revenue"], actor)
    replace_challenges(db, organization.id, ["downtime"], actor)
    replace_systems(db, organization.id, [OrganizationSystemSelection(system_code="sap")], actor)

    db.delete(organization)
    db.commit()

    assert list_objectives(db, organization.id) == []
    assert list_challenges(db, organization.id) == []
    assert list_systems(db, organization.id) == []
