from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.entities import MembershipRole, MembershipStatus
from app.models.raw_lineage import LineageNodeType
from app.models.source_system import SourceSystemStatus
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate, DatasetVersionCreate, IngestionBatchCreate
from app.schemas.memberships import MembershipCreate
from app.schemas.raw_lineage import RawStorageObjectCreate
from app.schemas.source_systems import SourceSystemCreate, SourceSystemUpdate
from app.schemas.trust import TrustAssessmentCreate
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
)
from app.services.membership_service import OrganizationMembershipService
from app.services.organization_service import OrganizationService
from app.services.raw_lineage_service import RawStorageObjectService
from app.services.source_system_service import SourceSystemService
from app.services.trust_service import TrustAssessmentService


def test_default_foundation_path_preserves_governance_and_inline_trust_boundary(
    db: Session,
) -> None:
    actor = uuid4()
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Foundation Integration",
            slug="foundation-integration",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    membership = OrganizationMembershipService().create(
        db,
        organization.id,
        MembershipCreate(
            user_id=actor,
            role=MembershipRole.ORGANIZATION_ADMIN,
            status=MembershipStatus.ACTIVE,
        ),
        invited_by_user_id=uuid4(),
    )
    assert (
        OrganizationMembershipService().require_active_member(db, organization.id, actor).id
        == membership.id
    )

    sources = SourceSystemService()
    source = sources.create(
        db,
        organization.id,
        SourceSystemCreate(
            name="Foundation ERP",
            code="foundation-erp",
            system_type="erp",
            integration_method="file_upload",
        ),
        actor,
    )
    sources.update(
        db,
        organization.id,
        source.id,
        SourceSystemUpdate(status=SourceSystemStatus.CONFIGURED),
        actor,
    )
    sources.update(
        db,
        organization.id,
        source.id,
        SourceSystemUpdate(status=SourceSystemStatus.VALIDATING),
        actor,
    )
    sources.record_connection_success(db, organization.id, source.id, actor)

    batch = IngestionBatchService().create(
        db,
        organization.id,
        IngestionBatchCreate(
            source_system_id=source.id,
            batch_number="foundation-batch",
            ingestion_method="file_upload",
            trigger_type="manual",
        ),
        actor,
    )
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Foundation records",
            code="foundation-records",
            domain="operations",
            dataset_type="transactional",
        ),
        actor,
    )
    version = DatasetVersionService().create(
        db,
        organization.id,
        dataset.id,
        DatasetVersionCreate(ingestion_batch_id=batch.id),
    )
    raw_service = RawStorageObjectService()
    raw = raw_service.register(
        db,
        organization.id,
        RawStorageObjectCreate(
            source_system_id=source.id,
            ingestion_batch_id=batch.id,
            dataset_version_id=version.id,
            object_number="foundation-raw",
            object_type="file",
            storage_provider="s3",
            storage_reference="s3://opaque/foundation.csv",
            content_checksum_algorithm="sha256",
            content_checksum="a" * 64,
            size_bytes=100,
            received_at=datetime.now(UTC),
        ),
        actor,
    )
    raw_node = raw_service.lineage.node_for_entity(
        db,
        organization.id,
        LineageNodeType.RAW_STORAGE_OBJECT,
        raw.id,
    )
    graph = raw_service.lineage.graph(
        db,
        organization.id,
        raw_node.id,
        direction="upstream",
    )
    assert {node.node_type for node in graph.nodes} >= {
        "source_system",
        "ingestion_batch",
        "dataset",
        "dataset_version",
        "raw_storage_object",
    }

    # FR-015 is intentionally not implemented: Trust consumes bounded inline
    # records here and does not claim that the raw object supplied the records.
    trust = TrustAssessmentService()
    assessment = trust.create_and_execute(
        db,
        organization.id,
        dataset.id,
        TrustAssessmentCreate(
            ingestion_batch_id=batch.id,
            idempotency_key="foundation-trust",
            records=[{"id": "1", "source_id": "foundation"}],
            rule_configurations={
                "required_field_completeness": {"required_fields": ["id"]},
                "lineage_completeness": {"lineage_fields": ["source_id"]},
            },
        ),
    )
    assert assessment.assessed_row_count == 1
    assert len(trust.readiness(db, organization.id, assessment.id)) == 7
