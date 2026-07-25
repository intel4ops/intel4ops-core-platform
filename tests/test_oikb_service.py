from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.definitions.resolution import OIKBFirstDefinitionResolver
from app.models.oikb import OIKBChangeLog, OIKBDefinition, OIKBDefinitionVersion
from app.schemas.contracts import OrganizationCreate
from app.schemas.intelligence import ExecutionType
from app.schemas.oikb import (
    AnalyticalLevel,
    DefinitionCreate,
    DefinitionVersionCreate,
    FormulaExpression,
    GovernanceAction,
    InputRequirementCreate,
    KnowledgeClass,
    LifecycleStatus,
    ResolveRequest,
    ScopeType,
    SourceCreate,
    SourceLinkCreate,
    ValidationCaseCreate,
)
from app.services.oikb_service import (
    OIKBConflictError,
    OIKBError,
    OIKBImmutableError,
    OIKBUnsupportedError,
    definition_registry_service,
    execution_package_export_service,
    governance_service,
    knowledge_resolution_service,
    knowledge_validation_service,
    source_citation_service,
)
from app.services.organization_service import OrganizationService


def definition_payload(
    code: str,
    *,
    organization_id: UUID | None = None,
    industry: str | None = None,
    region: str | None = None,
    level: AnalyticalLevel = AnalyticalLevel.ARITHMETIC,
) -> DefinitionCreate:
    scope = ScopeType.SHARED_CORE
    if organization_id:
        scope = ScopeType.ORGANIZATION
    elif region:
        scope = ScopeType.REGIONAL
    elif industry:
        scope = ScopeType.INDUSTRY
    return DefinitionCreate(
        stable_code=code,
        name=code.replace(".", " ").title(),
        description="Synthetic governed definition for isolated tests.",
        knowledge_class=KnowledgeClass.KPI,
        analytical_level=level,
        domain="operations",
        owner_organization_id=organization_id,
        industry_pack_code=industry,
        region_code=region,
        scope_type=scope,
        is_system_definition=organization_id is None,
    )


def version_payload(
    version: str = "1.0.0",
    *,
    operation: str = "sum",
    unit: str = "USD",
    currency: str | None = "USD",
) -> DefinitionVersionCreate:
    return DefinitionVersionCreate(
        semantic_version=version,
        quality_level="provisional",
        expression_schema=FormulaExpression(operation=operation, inputs=["amount"]),
        output_type="currency" if currency else "decimal",
        output_unit=unit,
        currency_code=currency,
        trust_requirement={"minimum_status": "completed"},
        readiness_requirement={"analytical_level": "arithmetic"},
        input_requirements=[
            InputRequirementCreate(
                input_code="amount",
                canonical_entity="transaction",
                canonical_field="amount",
                expected_type="currency" if currency else "decimal",
                expected_unit=unit,
                currency_code=currency,
                minimum_record_count=1,
            )
        ],
        evidence_requirements=[
            {
                "evidence_type": "calculation_trace",
                "requirement_code": "CALCULATION_TRACE",
                "description": "Bounded calculation trace.",
                "retention_class": "governed_reference",
            }
        ],
    )


def create_version(
    db: Session,
    code: str,
    *,
    organization_id: UUID | None = None,
    industry: str | None = None,
    region: str | None = None,
    version: str = "1.0.0",
    level: AnalyticalLevel = AnalyticalLevel.ARITHMETIC,
) -> tuple[OIKBDefinition, OIKBDefinitionVersion, UUID]:
    actor = uuid4()
    definition = definition_registry_service.create(
        db,
        definition_payload(
            code,
            organization_id=organization_id,
            industry=industry,
            region=region,
            level=level,
        ),
        actor,
    )
    definition_version = definition_registry_service.create_version(
        db,
        definition.id,
        organization_id,
        version_payload(version),
        actor,
    )
    return definition, definition_version, actor


def create_organization(db: Session, slug: str) -> UUID:
    return (
        OrganizationService()
        .create(
            db,
            OrganizationCreate(
                name=slug,
                slug=slug,
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        .id
    )


def activate(
    db: Session,
    definition_version: OIKBDefinitionVersion,
    actor: UUID,
    organization_id: UUID | None = None,
) -> None:
    version_id = definition_version.id
    knowledge_validation_service.create_case(
        db,
        definition_version,
        ValidationCaseCreate(
            case_code="NORMAL_CASE",
            description="Normal sum case.",
            input_payload={"values": [1, 2]},
            expected_output="3",
            tolerance="0",
        ),
    )
    knowledge_validation_service.run(db, definition_version, actor)
    governance_service.transition(
        db,
        version_id,
        organization_id,
        LifecycleStatus.IN_REVIEW,
        GovernanceAction(reason="review requested"),
        actor,
    )
    governance_service.mark_validated(db, version_id, organization_id, actor)
    governance_service.transition(
        db,
        version_id,
        organization_id,
        LifecycleStatus.APPROVED,
        GovernanceAction(reason="approved"),
        actor,
    )
    governance_service.transition(
        db,
        version_id,
        organization_id,
        LifecycleStatus.ACTIVE,
        GovernanceAction(reason="activated"),
        actor,
    )


def test_registry_scope_uniqueness_specialization_and_tenant_isolation(db: Session) -> None:
    first, _, _ = create_version(db, "SHARED.OPERATIONS.TEST_SCOPE")
    with pytest.raises(OIKBConflictError):
        definition_registry_service.create(
            db, definition_payload("SHARED.OPERATIONS.TEST_SCOPE"), uuid4()
        )
    organization_a = create_organization(db, "oikb-scope-a")
    organization_b = create_organization(db, "oikb-scope-b")
    specialized, _, _ = create_version(
        db, "SHARED.OPERATIONS.TEST_SCOPE", organization_id=organization_a
    )
    own, own_total = definition_registry_service.list_definitions(
        db, organization_a, page=1, page_size=10
    )
    other, other_total = definition_registry_service.list_definitions(
        db, organization_b, page=1, page_size=10
    )
    assert {item.id for item in own} == {first.id, specialized.id}
    assert own_total == 2
    assert [item.id for item in other] == [first.id]
    assert other_total == 1


def test_semantic_version_order_and_duplicate_content(db: Session) -> None:
    definition, _, actor = create_version(db, "SHARED.OPERATIONS.VERSIONING")
    with pytest.raises(OIKBError):
        definition_registry_service.create_version(
            db, definition.id, None, version_payload("0.9.0"), actor
        )
    second = definition_registry_service.create_version(
        db, definition.id, None, version_payload("1.1.0"), actor
    )
    assert second.semantic_version == "1.1.0"
    with pytest.raises(OIKBConflictError):
        definition_registry_service.create_version(
            db, definition.id, None, version_payload("1.1.0"), actor
        )
    with pytest.raises(ValidationError):
        version_payload("1.01.0")


def test_formula_validation_rejects_unsupported_units_currency_and_inputs(db: Session) -> None:
    definition = definition_registry_service.create(
        db, definition_payload("SHARED.OPERATIONS.FORMULA_VALIDATION"), uuid4()
    )
    unsupported = version_payload().model_copy(
        update={"expression_schema": FormulaExpression(operation="median", inputs=["amount"])}
    )
    with pytest.raises(OIKBUnsupportedError):
        definition_registry_service.create_version(db, definition.id, None, unsupported, uuid4())
    bad_unit = version_payload().model_copy(update={"output_unit": "EUR"})
    with pytest.raises(OIKBError, match="units"):
        definition_registry_service.create_version(db, definition.id, None, bad_unit, uuid4())
    bad_currency = version_payload().model_copy(update={"currency_code": "EUR"})
    with pytest.raises(OIKBError, match="currency"):
        definition_registry_service.create_version(db, definition.id, None, bad_currency, uuid4())
    missing = version_payload().model_copy(
        update={"expression_schema": FormulaExpression(operation="sum", inputs=["missing"])}
    )
    with pytest.raises(OIKBError, match="undeclared"):
        definition_registry_service.create_version(db, definition.id, None, missing, uuid4())


def test_fingerprint_is_deterministic_and_active_version_is_immutable(db: Session) -> None:
    _, version, actor = create_version(db, "SHARED.OPERATIONS.FINGERPRINT")
    expected = version.fingerprint
    activate(db, version, actor)
    assert version.fingerprint == expected
    with pytest.raises(OIKBImmutableError):
        knowledge_validation_service.create_case(
            db,
            version,
            ValidationCaseCreate(
                case_code="LATE_CASE",
                description="Must be rejected.",
                input_payload={"values": []},
                expected_output="0",
            ),
        )


def test_lifecycle_requires_validation_approval_and_records_audit(db: Session) -> None:
    definition, version, actor = create_version(db, "SHARED.OPERATIONS.LIFECYCLE")
    with pytest.raises(OIKBConflictError):
        governance_service.transition(
            db,
            version.id,
            None,
            LifecycleStatus.ACTIVE,
            GovernanceAction(reason="invalid shortcut"),
            actor,
        )
    governance_service.transition(
        db,
        version.id,
        None,
        LifecycleStatus.IN_REVIEW,
        GovernanceAction(reason="review"),
        actor,
    )
    with pytest.raises(OIKBConflictError, match="validation"):
        governance_service.mark_validated(db, version.id, None, actor)
    audit = list(
        db.scalars(select(OIKBChangeLog).where(OIKBChangeLog.definition_id == definition.id))
    )
    assert [item.action for item in audit] == [
        "definition_created",
        "version_created",
        "lifecycle_in_review",
    ]


def test_resolution_precedence_effective_dates_and_fallback(db: Session) -> None:
    organization_id = create_organization(db, "oikb-resolution")
    shared, shared_version, shared_actor = create_version(db, "SHARED.OPERATIONS.RESOLUTION")
    activate(db, shared_version, shared_actor)
    regional, regional_version, regional_actor = create_version(
        db, "SHARED.OPERATIONS.RESOLUTION", region="US"
    )
    activate(db, regional_version, regional_actor)
    org, org_version, org_actor = create_version(
        db, "SHARED.OPERATIONS.RESOLUTION", organization_id=organization_id
    )
    activate(db, org_version, org_actor, organization_id)
    resolved = knowledge_resolution_service.resolve(
        db,
        ResolveRequest(
            organization_id=organization_id,
            stable_code="SHARED.OPERATIONS.RESOLUTION",
            region_code="US",
        ),
    )
    assert resolved is not None
    assert resolved.definition.id == org.id
    assert resolved.trace.scope_selected == "organization"
    assert shared.id != regional.id
    org_version.effective_from = datetime.now(UTC) + timedelta(days=1)
    db.commit()
    fallback = knowledge_resolution_service.resolve(
        db,
        ResolveRequest(
            organization_id=organization_id,
            stable_code="SHARED.OPERATIONS.RESOLUTION",
            region_code="US",
        ),
    )
    assert fallback is not None
    assert fallback.definition.id == regional.id


def test_source_provenance_execution_package_and_unsupported_level(db: Session) -> None:
    definition, version, actor = create_version(db, "SHARED.OPERATIONS.PACKAGE")
    source = source_citation_service.create(
        db,
        SourceCreate(
            source_type="internal_governance",
            title="Test provenance",
            publisher="Intel4Ops",
            citation="Synthetic test source.",
            authority_level="intel4ops_proprietary",
        ),
        None,
    )
    source_citation_service.link(
        db,
        version,
        SourceLinkCreate(
            source_id=source.id, relationship_type="governance_provenance", is_primary=True
        ),
        None,
    )
    activate(db, version, actor)
    package = execution_package_export_service.export(db, version)
    assert package.stable_code == definition.stable_code
    assert package.fingerprint == version.fingerprint
    assert package.evidence_requirements[0]["requirement_code"] == "CALCULATION_TRACE"
    assert package.provenance_references[0]["source_id"] == str(source.id)

    advanced, advanced_version, advanced_actor = create_version(
        db, "SHARED.OPERATIONS.STATISTICAL", level=AnalyticalLevel.STATISTICAL
    )
    activate(db, advanced_version, advanced_actor)
    statistical_package = execution_package_export_service.export(db, advanced_version)
    assert statistical_package.analytical_level == "statistical"
    assert advanced.analytical_level == "statistical"


def test_governed_resolver_and_explicit_legacy_fallback(db: Session) -> None:
    organization_id = uuid4()
    _, version, actor = create_version(db, "SHARED.OPERATIONS.GOVERNED")
    activate(db, version, actor)
    resolver = OIKBFirstDefinitionResolver()
    governed = resolver.resolve(
        "SHARED.OPERATIONS.GOVERNED",
        "1.0.0",
        ExecutionType.CALCULATION,
        db=db,
        organization_id=organization_id,
    )
    assert governed.scope_metadata["legacy_fallback"] is False
    legacy = resolver.resolve(
        "sum",
        "1.0",
        ExecutionType.CALCULATION,
        db=db,
        organization_id=organization_id,
    )
    assert legacy.scope_metadata["legacy_fallback"] is True
    assert legacy.scope_metadata["compatibility_warning"] == "LEGACY_CODE_BACKED_DEFINITION"
