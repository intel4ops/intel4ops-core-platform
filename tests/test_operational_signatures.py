from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commercial import (
    Entitlement,
    IndustryPackAssignment,
    IndustryPackDefinition,
    Plan,
    PlanVersion,
    Subscription,
    UsageEvent,
    UsageMeterDefinition,
)
from app.models.entities import Finding, Organization
from app.models.gateway import ApplicationClient
from app.models.industry_packs import IndustryPackAssignmentState, IndustryPackVersion
from app.models.raw_lineage import LineageNode
from app.models.signatures import (
    OperationalSignatureDefinition,
    OperationalSignatureExecution,
    OperationalSignatureLifecycleEvent,
    OperationalSignatureValidation,
    OperationalSignatureVersion,
)
from app.schemas.signatures import (
    SignatureDeploymentCreate,
    SignatureEvidenceInput,
    SignatureExecutionCreate,
    SignatureTransition,
)
from app.services.signature_service import (
    SignatureServiceError,
    signature_catalog_service,
    tenant_signature_service,
)
from app.signatures.catalog import SIGNATURE_CATALOG
from app.signatures.engine import SignatureEvaluator
from app.signatures.sdk import SignatureDefinitionError, validate_extension


def _foundation(
    db: Session,
    *,
    code: str = "J2C.SIGNATURE.OILFIELD.BILLING_LEAKAGE",
    entitlement: bool = True,
) -> tuple[Organization, OperationalSignatureDefinition, OperationalSignatureVersion, UUID]:
    actor = uuid4()
    organization = Organization(
        name=f"Signature Tenant {uuid4()}",
        slug=f"signature-{uuid4()}",
        country_code="US",
        default_currency="USD",
        timezone="UTC",
        status="active",
        is_demo=True,
    )
    db.add(organization)
    plan = Plan(
        code=f"SIG-{uuid4()}", name="Signature Plan", plan_type="enterprise", status="active"
    )
    db.add(plan)
    db.flush()
    plan_version = PlanVersion(
        plan_id=plan.id,
        version=1,
        effective_date=date(2026, 1, 1),
        migration_policy="explicit",
        terms={},
    )
    db.add(plan_version)
    db.flush()
    now = datetime.now(UTC)
    subscription = Subscription(
        organization_id=organization.id,
        plan_version_id=plan_version.id,
        idempotency_key=f"subscription:{organization.id}",
        status="active",
        starts_at=now - timedelta(days=1),
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=30),
        created_by_user_id=actor,
    )
    db.add(subscription)
    meter = db.scalar(
        select(UsageMeterDefinition).where(UsageMeterDefinition.code == "signature_executions")
    )
    if meter is None:
        db.add(
            UsageMeterDefinition(
                code="signature_executions",
                product="Intelligence",
                meter_kind="event",
                unit="executions",
                aggregation="sum",
                currency_behavior="not_applicable",
            )
        )
    db.flush()
    if entitlement:
        db.add(
            Entitlement(
                organization_id=organization.id,
                subscription_id=subscription.id,
                entitlement_type="feature",
                entitlement_key="intelligence.operational_signatures",
                enabled=True,
                source="plan",
                effective_at=now - timedelta(days=1),
                idempotency_key=f"signature-entitlement:{organization.id}",
                granted_by_user_id=actor,
            )
        )
    definition = SIGNATURE_CATALOG[code]
    pack_code = str(definition["applicable_pack_versions"][0]).split("@", 1)[0]
    pack = IndustryPackDefinition(
        code=pack_code,
        name=pack_code,
        entitlement_key=f"industry.{pack_code.lower()}",
        status="active",
    )
    db.add(pack)
    db.flush()
    pack_version = IndustryPackVersion(
        pack_id=pack.id,
        semantic_version="1.0.0",
        lifecycle_status="published",
        manifest_json={},
        minimum_platform_revision="20260727_0020",
        published_at=now,
    )
    db.add(pack_version)
    db.flush()
    assignment = IndustryPackAssignment(
        organization_id=organization.id,
        pack_id=pack.id,
        status="active",
        effective_at=now,
        assigned_by_user_id=actor,
    )
    db.add(assignment)
    db.flush()
    db.add(
        IndustryPackAssignmentState(
            organization_id=organization.id,
            assignment_id=assignment.id,
            pack_version_id=pack_version.id,
            status="active",
            configuration_overrides={},
            entitlement_snapshot={},
            activated_at=now,
        )
    )
    signature = OperationalSignatureDefinition(
        code=code,
        name=str(definition["name"]),
        description=str(definition["description"]),
        signature_type=str(definition["signature_type"]),
        industry=str(definition["industry"]),
        lifecycle_status="production",
        canonical_governance_status="active",
        owner=str(definition["owner"]),
        tags=[],
        documentation_reference="docs/operational-signatures.md",
    )
    db.add(signature)
    db.flush()
    version = OperationalSignatureVersion(
        signature_id=signature.id,
        semantic_version="1.0.0",
        applicable_pack_versions=definition["applicable_pack_versions"],
        required_canonical_objects=definition["required_canonical_objects"],
        required_features=definition["required_features"],
        required_events=definition["required_events"],
        required_conditions=definition["required_conditions"],
        exclusion_conditions=definition["exclusion_conditions"],
        evidence_requirements=definition["evidence_requirements"],
        confidence_model=definition["confidence_model"],
        economic_impact_policy=definition["economic_impact_policy"],
        expected_outcome=definition["expected_outcome"],
        supporting_algorithms=definition["supporting_algorithms"],
        supporting_rules=definition["supporting_rules"],
        supporting_models=definition["supporting_models"],
        dependencies=definition["dependencies"],
        monitoring_policy=definition["monitoring_policy"],
        known_limitations=definition["known_limitations"],
        definition_hash=str(definition["definition_hash"]),
        approved_at=now,
    )
    db.add(version)
    db.flush()
    db.add(
        OperationalSignatureValidation(
            signature_version_id=version.id,
            status="passed",
            metrics={"deterministic_replay": True},
            false_positive_count=0,
            false_negative_count=0,
            evidence_references=[{"scenario": definition["scenario_code"]}],
            limitations=definition["known_limitations"],
            approved=True,
        )
    )
    db.commit()
    return organization, signature, version, actor


def _execution_payload(key: str = "signature:one") -> SignatureExecutionCreate:
    evidence_types = (
        "contract",
        "field_ticket",
        "expected_billing_trace",
        "invoice",
    )
    return SignatureExecutionCreate(
        idempotency_key=key,
        observations={
            "billing_variance": "1250.00",
            "documentation_complete": False,
            "job_cancelled": False,
        },
        evidence=[
            SignatureEvidenceInput(
                evidence_type=item,
                source_type="canonical_record",
                source_identifier=f"{item}:001",
                integrity_fingerprint=f"fingerprint-{item}-001",
            )
            for item in evidence_types
        ],
    )


def test_evaluator_is_deterministic_explainable_and_exclusion_safe() -> None:
    definition = SIGNATURE_CATALOG["J2C.SIGNATURE.OILFIELD.BILLING_LEAKAGE"]
    evaluator = SignatureEvaluator()
    payload = {
        "billing_variance": "50",
        "documentation_complete": False,
        "job_cancelled": False,
    }
    evidence = set(definition["evidence_requirements"])
    first = evaluator.evaluate(definition, payload, evidence)
    assert first == evaluator.evaluate(definition, payload, evidence)
    assert first.matched and first.confidence > 0
    excluded = evaluator.evaluate(definition, {**payload, "job_cancelled": True}, evidence)
    assert not excluded.matched
    assert excluded.confidence <= Decimal("0.49")


def test_deploy_execute_publish_meter_and_retry_idempotently(db: Session) -> None:
    organization, _signature, version, actor = _foundation(db)
    deployment = tenant_signature_service.deploy(
        db,
        organization.id,
        SignatureDeploymentCreate(signature_version_id=version.id),
        actor,
    )
    payload = _execution_payload()
    execution = tenant_signature_service.execute(db, organization.id, deployment.id, payload, actor)
    replay = tenant_signature_service.execute(db, organization.id, deployment.id, payload, actor)
    assert execution.id == replay.id
    assert execution.matched is True
    finding = db.scalar(
        select(Finding).where(
            Finding.id == execution.finding_id,
            Finding.organization_id == organization.id,
            Finding.signature_version_id == version.id,
        )
    )
    assert finding is not None
    assert finding.signature_execution_id == execution.id
    assert db.scalar(select(func.count()).select_from(OperationalSignatureExecution)) == 1
    assert db.scalar(select(func.count()).select_from(UsageEvent)) == 1


def test_entitlement_pack_and_tenant_boundaries_fail_closed(db: Session) -> None:
    organization, _signature, version, actor = _foundation(db, entitlement=False)
    with pytest.raises(SignatureServiceError, match="entitlement is required"):
        tenant_signature_service.deploy(
            db,
            organization.id,
            SignatureDeploymentCreate(signature_version_id=version.id),
            actor,
        )

    entitled, _second_signature, second_version, second_actor = _foundation(
        db,
        code="MFG.SIGNATURE.SERVO.DEGRADATION",
    )
    deployment = tenant_signature_service.deploy(
        db,
        entitled.id,
        SignatureDeploymentCreate(signature_version_id=second_version.id),
        second_actor,
    )
    with pytest.raises(SignatureServiceError, match="Deployment not found"):
        tenant_signature_service.execute(
            db,
            organization.id,
            deployment.id,
            _execution_payload("cross-tenant"),
            actor,
        )


def test_lifecycle_requires_validation_and_is_audited(db: Session) -> None:
    actor = uuid4()
    signature = OperationalSignatureDefinition(
        code=f"TEST.SIGNATURE.{uuid4()}",
        name="Lifecycle Test",
        description="Lifecycle transition validation.",
        signature_type="failure",
        industry="shared",
        lifecycle_status="hypothesis",
        canonical_governance_status="draft",
        owner="test-owner",
        tags=[],
        documentation_reference="test",
    )
    db.add(signature)
    db.commit()
    transitioned = signature_catalog_service.transition(
        db,
        signature.id,
        SignatureTransition(
            target_status="candidate",
            reason="Candidate evidence collection started.",
            idempotency_key="candidate:one",
        ),
        actor,
        "platform_admin",
    )
    assert transitioned.lifecycle_status == "candidate"
    replay = signature_catalog_service.transition(
        db,
        signature.id,
        SignatureTransition(
            target_status="candidate",
            reason="Candidate evidence collection started.",
            idempotency_key="candidate:one",
        ),
        actor,
        "platform_admin",
    )
    assert replay.lifecycle_status == "candidate"
    assert db.scalar(select(func.count()).select_from(OperationalSignatureLifecycleEvent)) == 1
    with pytest.raises(SignatureServiceError, match="Cannot transition"):
        signature_catalog_service.transition(
            db,
            signature.id,
            SignatureTransition(
                target_status="production",
                reason="Attempt to skip required governance.",
                idempotency_key="invalid:one",
            ),
            actor,
            "platform_admin",
        )


def test_signature_sdk_validates_extension_contract() -> None:
    definition = dict(SIGNATURE_CATALOG["J2C.SIGNATURE.OILFIELD.BILLING_LEAKAGE"])

    class Extension:
        code = "J2C.SIGNATURE.TEST.EXTENSION"
        semantic_version = "1.0.0"

        def definition(self) -> dict[str, object]:
            return definition

    validated = validate_extension(Extension())
    assert len(str(validated["definition_hash"])) == 64
    Extension.code = "not namespaced"
    with pytest.raises(SignatureDefinitionError, match="namespaced uppercase"):
        validate_extension(Extension())


def test_signature_api_catalog_deployment_and_execution(
    client: TestClient,
    db: Session,
) -> None:
    organization, signature, version, _actor = _foundation(db)
    db.add(
        ApplicationClient(
            client_code="intel4ops-web",
            name="Intel4Ops Web",
            client_type="first_party",
            status="active",
        )
    )
    db.commit()

    catalog = client.get("/api/v1/operational-intelligence/signatures")
    assert catalog.status_code == 200, catalog.text
    assert [item["code"] for item in catalog.json()] == [signature.code]

    deployed = client.post(
        f"/api/v1/organizations/{organization.id}/operational-signatures/deployments",
        json={"signature_version_id": str(version.id), "environment": "production"},
    )
    assert deployed.status_code == 201, deployed.text
    execution = client.post(
        f"/api/v1/organizations/{organization.id}/operational-signatures/deployments/"
        f"{deployed.json()['id']}/executions",
        json=_execution_payload("api:one").model_dump(mode="json"),
    )
    assert execution.status_code == 201, execution.text
    assert execution.json()["matched"] is True
    assert execution.json()["finding_id"] is not None


def test_execution_rejects_cross_tenant_evidence_lineage(db: Session) -> None:
    organization, _signature, version, actor = _foundation(db)
    deployment = tenant_signature_service.deploy(
        db,
        organization.id,
        SignatureDeploymentCreate(signature_version_id=version.id),
        actor,
    )
    other = Organization(
        name="Other Signature Tenant",
        slug=f"other-signature-{uuid4()}",
        country_code="US",
        default_currency="USD",
        timezone="UTC",
        status="active",
        is_demo=True,
    )
    db.add(other)
    db.flush()
    foreign_node = LineageNode(
        organization_id=other.id,
        node_type="dataset",
        entity_id=uuid4(),
        status="active",
    )
    db.add(foreign_node)
    db.commit()
    payload = _execution_payload("cross-tenant-lineage")
    payload.evidence[0] = payload.evidence[0].model_copy(
        update={"lineage_node_id": foreign_node.id}
    )

    with pytest.raises(
        SignatureServiceError,
        match="lineage node must belong to the organization",
    ) as error:
        tenant_signature_service.execute(
            db,
            organization.id,
            deployment.id,
            payload,
            actor,
        )
    assert error.value.status == 403
    assert error.value.code == "EVIDENCE_LINEAGE_TENANT_MISMATCH"


def test_execution_rechecks_active_applicable_pack(db: Session) -> None:
    organization, _signature, version, actor = _foundation(db)
    deployment = tenant_signature_service.deploy(
        db,
        organization.id,
        SignatureDeploymentCreate(signature_version_id=version.id),
        actor,
    )
    assignment_state = db.scalar(
        select(IndustryPackAssignmentState).where(
            IndustryPackAssignmentState.organization_id == organization.id
        )
    )
    assert assignment_state is not None
    assignment_state.status = "suspended"
    db.commit()

    with pytest.raises(SignatureServiceError, match="No active applicable") as error:
        tenant_signature_service.execute(
            db,
            organization.id,
            deployment.id,
            _execution_payload("revoked-pack"),
            actor,
        )
    assert error.value.status == 403
    assert error.value.code == "SIGNATURE_PACK_NOT_APPLICABLE"


def test_execution_idempotency_rejects_changed_request_or_deployment(db: Session) -> None:
    organization, _signature, version, actor = _foundation(db)
    production = tenant_signature_service.deploy(
        db,
        organization.id,
        SignatureDeploymentCreate(signature_version_id=version.id),
        actor,
    )
    pilot = tenant_signature_service.deploy(
        db,
        organization.id,
        SignatureDeploymentCreate(
            signature_version_id=version.id,
            environment="pilot",
        ),
        actor,
    )
    initial = _execution_payload("idempotency-conflict")
    created = tenant_signature_service.execute(
        db,
        organization.id,
        production.id,
        initial,
        actor,
    )
    created.input_fingerprint = str(created.result_json["input_fingerprint"])
    db.commit()
    replay = tenant_signature_service.execute(
        db,
        organization.id,
        production.id,
        initial,
        actor,
    )
    assert replay.id == created.id

    changed = initial.model_copy(
        update={
            "observations": {
                **initial.observations,
                "billing_variance": "1500.00",
            }
        }
    )
    with pytest.raises(SignatureServiceError) as changed_error:
        tenant_signature_service.execute(
            db,
            organization.id,
            production.id,
            changed,
            actor,
        )
    assert changed_error.value.status == 409
    assert changed_error.value.code == "SIGNATURE_IDEMPOTENCY_CONFLICT"

    with pytest.raises(SignatureServiceError) as deployment_error:
        tenant_signature_service.execute(
            db,
            organization.id,
            pilot.id,
            initial,
            actor,
        )
    assert deployment_error.value.status == 409
    assert deployment_error.value.code == "SIGNATURE_IDEMPOTENCY_CONFLICT"
