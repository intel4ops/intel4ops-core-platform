from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial import (
    Entitlement,
    IndustryPackAssignment,
    IndustryPackDefinition,
    UsageEvent,
)
from app.models.entities import Finding, FindingEvidence, Organization
from app.models.industry_packs import IndustryPackAssignmentState, IndustryPackVersion
from app.models.signatures import (
    OperationalFeatureDefinition,
    OperationalFeatureVersion,
    OperationalSignatureDefinition,
    OperationalSignatureDeployment,
    OperationalSignatureExecution,
    OperationalSignatureExecutionEvidence,
    OperationalSignatureLifecycleEvent,
    OperationalSignatureValidation,
    OperationalSignatureVersion,
)
from app.schemas.signatures import (
    SignatureDeploymentCreate,
    SignatureExecutionCreate,
    SignatureTransition,
)
from app.signatures.engine import SignatureEvaluator


class SignatureServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


CANONICAL_STATUS = {
    "hypothesis": "draft",
    "candidate": "draft",
    "observed": "under_review",
    "validated": "under_review",
    "approved": "approved",
    "production": "active",
    "suspended": "suspended",
    "deprecated": "deprecated",
    "retired": "retired",
}

TRANSITIONS: dict[str, frozenset[str]] = {
    "hypothesis": frozenset({"candidate"}),
    "candidate": frozenset({"hypothesis", "observed"}),
    "observed": frozenset({"candidate", "validated"}),
    "validated": frozenset({"observed", "approved"}),
    "approved": frozenset({"production"}),
    "production": frozenset({"suspended", "deprecated"}),
    "suspended": frozenset({"production", "retired"}),
    "deprecated": frozenset({"retired"}),
    "retired": frozenset(),
}


class SignatureCatalogService:
    def features(self, db: Session) -> list[OperationalFeatureDefinition]:
        return list(
            db.scalars(
                select(OperationalFeatureDefinition).order_by(OperationalFeatureDefinition.code)
            )
        )

    def feature_versions(self, db: Session, feature_id: UUID) -> list[OperationalFeatureVersion]:
        return list(
            db.scalars(
                select(OperationalFeatureVersion)
                .where(OperationalFeatureVersion.feature_id == feature_id)
                .order_by(OperationalFeatureVersion.semantic_version)
            )
        )

    def signatures(self, db: Session) -> list[OperationalSignatureDefinition]:
        return list(
            db.scalars(
                select(OperationalSignatureDefinition).order_by(OperationalSignatureDefinition.code)
            )
        )

    def versions(self, db: Session, signature_id: UUID) -> list[OperationalSignatureVersion]:
        return list(
            db.scalars(
                select(OperationalSignatureVersion)
                .where(OperationalSignatureVersion.signature_id == signature_id)
                .order_by(OperationalSignatureVersion.semantic_version)
            )
        )

    def transition(
        self,
        db: Session,
        signature_id: UUID,
        payload: SignatureTransition,
        actor: UUID,
        actor_role: str,
    ) -> OperationalSignatureDefinition:
        signature = db.get(OperationalSignatureDefinition, signature_id)
        if signature is None:
            raise SignatureServiceError("SIGNATURE_NOT_FOUND", "Signature not found", 404)
        prior_event = db.scalar(
            select(OperationalSignatureLifecycleEvent).where(
                OperationalSignatureLifecycleEvent.signature_id == signature_id,
                OperationalSignatureLifecycleEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if prior_event:
            return signature
        if payload.target_status not in TRANSITIONS.get(signature.lifecycle_status, frozenset()):
            raise SignatureServiceError(
                "INVALID_SIGNATURE_TRANSITION",
                f"Cannot transition {signature.lifecycle_status} to {payload.target_status}",
                409,
            )
        if payload.target_status in {"approved", "production"}:
            versions = self.versions(db, signature_id)
            if not versions or not all(self._validated(db, item.id) for item in versions):
                raise SignatureServiceError(
                    "SIGNATURE_VALIDATION_REQUIRED",
                    "Approved validation is required before approval or production",
                    409,
                )
        prior = signature.lifecycle_status
        signature.lifecycle_status = payload.target_status
        signature.canonical_governance_status = CANONICAL_STATUS[payload.target_status]
        signature.updated_at = datetime.now(UTC)
        if payload.target_status == "retired":
            signature.retired_at = datetime.now(UTC)
        db.add(
            OperationalSignatureLifecycleEvent(
                signature_id=signature.id,
                prior_status=prior,
                new_status=payload.target_status,
                actor_user_id=actor,
                actor_role=actor_role,
                reason=payload.reason,
                approval_reference=payload.approval_reference,
                idempotency_key=payload.idempotency_key,
            )
        )
        db.commit()
        db.refresh(signature)
        return signature

    @staticmethod
    def _validated(db: Session, version_id: UUID) -> bool:
        return (
            db.scalar(
                select(OperationalSignatureValidation.id).where(
                    OperationalSignatureValidation.signature_version_id == version_id,
                    OperationalSignatureValidation.approved.is_(True),
                    OperationalSignatureValidation.status == "passed",
                )
            )
            is not None
        )


class TenantSignatureService:
    def __init__(self, evaluator: SignatureEvaluator | None = None) -> None:
        self.evaluator = evaluator or SignatureEvaluator()

    def deployments(
        self, db: Session, organization_id: UUID
    ) -> list[OperationalSignatureDeployment]:
        return list(
            db.scalars(
                select(OperationalSignatureDeployment)
                .where(OperationalSignatureDeployment.organization_id == organization_id)
                .order_by(OperationalSignatureDeployment.deployed_at.desc())
            )
        )

    def deploy(
        self,
        db: Session,
        organization_id: UUID,
        payload: SignatureDeploymentCreate,
        actor: UUID,
    ) -> OperationalSignatureDeployment:
        prior = db.scalar(
            select(OperationalSignatureDeployment).where(
                OperationalSignatureDeployment.organization_id == organization_id,
                OperationalSignatureDeployment.signature_version_id == payload.signature_version_id,
                OperationalSignatureDeployment.environment == payload.environment,
            )
        )
        if prior:
            return prior
        version, signature = self._production_version(db, payload.signature_version_id)
        entitlement = self._entitlement(db, organization_id)
        self._applicable_pack(db, organization_id, version.applicable_pack_versions)
        deployment = OperationalSignatureDeployment(
            organization_id=organization_id,
            signature_version_id=version.id,
            environment=payload.environment,
            status="active",
            calibration=payload.calibration,
            entitlement_snapshot={
                "key": entitlement.entitlement_key,
                "source": entitlement.source,
                "effective_at": entitlement.effective_at.isoformat(),
            },
            deployed_by_user_id=actor,
        )
        db.add(deployment)
        db.commit()
        db.refresh(deployment)
        return deployment

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        deployment_id: UUID,
        payload: SignatureExecutionCreate,
        actor: UUID,
    ) -> OperationalSignatureExecution:
        prior = db.scalar(
            select(OperationalSignatureExecution).where(
                OperationalSignatureExecution.organization_id == organization_id,
                OperationalSignatureExecution.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        deployment = db.scalar(
            select(OperationalSignatureDeployment).where(
                OperationalSignatureDeployment.id == deployment_id,
                OperationalSignatureDeployment.organization_id == organization_id,
            )
        )
        if deployment is None:
            raise SignatureServiceError("DEPLOYMENT_NOT_FOUND", "Deployment not found", 404)
        if deployment.status != "active":
            raise SignatureServiceError(
                "SIGNATURE_DEPLOYMENT_INACTIVE", "Signature deployment is not active", 409
            )
        version, signature = self._production_version(db, deployment.signature_version_id)
        self._entitlement(db, organization_id)
        evaluation = self.evaluator.evaluate(
            {
                "required_conditions": version.required_conditions,
                "exclusion_conditions": version.exclusion_conditions,
                "evidence_requirements": version.evidence_requirements,
                "confidence_model": version.confidence_model,
                "known_limitations": version.known_limitations,
            },
            payload.observations,
            {item.evidence_type for item in payload.evidence},
        )
        execution = OperationalSignatureExecution(
            organization_id=organization_id,
            deployment_id=deployment.id,
            signature_version_id=version.id,
            idempotency_key=payload.idempotency_key,
            input_fingerprint=evaluation.input_fingerprint,
            status="completed",
            matched=evaluation.matched,
            confidence=evaluation.confidence,
            result_json=evaluation.model_dump(mode="json"),
            explanation={
                "signature_code": signature.code,
                "signature_version": version.semantic_version,
                "matched_conditions": evaluation.matched_conditions,
                "failed_conditions": evaluation.failed_conditions,
                "limitations": evaluation.limitations,
            },
            completed_at=datetime.now(UTC),
        )
        db.add(execution)
        db.flush()
        for item in payload.evidence:
            db.add(
                OperationalSignatureExecutionEvidence(
                    organization_id=organization_id,
                    execution_id=execution.id,
                    evidence_type=item.evidence_type,
                    source_type=item.source_type,
                    source_identifier=item.source_identifier,
                    lineage_node_id=item.lineage_node_id,
                    observed_at=item.observed_at,
                    integrity_fingerprint=item.integrity_fingerprint,
                    metadata_json=item.metadata,
                )
            )
        if evaluation.matched:
            finding = self._finding(
                db, organization_id, execution, signature, version, payload, actor
            )
            execution.finding_id = finding.id
        db.add(
            UsageEvent(
                organization_id=organization_id,
                meter_code="signature_executions",
                idempotency_key=f"signature:{payload.idempotency_key}",
                quantity=Decimal(1),
                source_type="operational_signature_execution",
                source_id=str(execution.id),
                occurred_at=datetime.now(UTC),
                metadata_json={
                    "signature_code": signature.code,
                    "matched": evaluation.matched,
                },
            )
        )
        db.commit()
        db.refresh(execution)
        return execution

    def executions(
        self, db: Session, organization_id: UUID, deployment_id: UUID
    ) -> list[OperationalSignatureExecution]:
        return list(
            db.scalars(
                select(OperationalSignatureExecution)
                .where(
                    OperationalSignatureExecution.organization_id == organization_id,
                    OperationalSignatureExecution.deployment_id == deployment_id,
                )
                .order_by(OperationalSignatureExecution.started_at.desc())
            )
        )

    def _finding(
        self,
        db: Session,
        organization_id: UUID,
        execution: OperationalSignatureExecution,
        signature: OperationalSignatureDefinition,
        version: OperationalSignatureVersion,
        payload: SignatureExecutionCreate,
        actor: UUID,
    ) -> Finding:
        organization = db.get(Organization, organization_id)
        currency = organization.default_currency if organization else "USD"
        exposure = Decimal(str(payload.observations.get("billing_variance", 0)))
        finding = Finding(
            organization_id=organization_id,
            rule_id=signature.code,
            title=signature.name,
            summary=signature.description,
            domain=signature.industry,
            severity="medium",
            priority=3,
            exposure_low=float(exposure),
            exposure_high=float(exposure),
            currency=currency,
            confidence_score=execution.confidence or Decimal("0"),
            status="open",
            ontology_concept_ids=["operational.signature"],
            finding_code=signature.code,
            finding_type="operational_signature",
            description=signature.description,
            domain_code=signature.industry,
            confidence_level="high" if (execution.confidence or 0) >= Decimal("0.8") else "medium",
            confidence_method_code="operational_signature",
            confidence_method_version=version.semantic_version,
            confidence_components={"signature_execution_id": str(execution.id)},
            confidence_limitations=version.known_limitations,
            exposure_value=exposure,
            exposure_value_type="estimated",
            exposure_currency=currency,
            affected_record_count=1,
            detected_at=datetime.now(UTC),
            published_at=datetime.now(UTC),
            definition_code=signature.code,
            definition_version=version.semantic_version,
            signature_version_id=version.id,
            signature_execution_id=execution.id,
            deduplication_key=sha256(
                f"{organization_id}:{version.id}:{payload.idempotency_key}".encode()
            ).hexdigest(),
            created_by_user_id=actor,
        )
        db.add(finding)
        db.flush()
        first = payload.evidence[0]
        db.add(
            FindingEvidence(
                organization_id=organization_id,
                finding_id=finding.id,
                source_system=first.source_type,
                source_record_id=first.source_identifier,
                evidence_type="operational_signature_evidence",
                payload={
                    "signature_version_id": str(version.id),
                    "signature_execution_id": str(execution.id),
                    "integrity_fingerprint": first.integrity_fingerprint,
                },
            )
        )
        return finding

    @staticmethod
    def _production_version(
        db: Session, version_id: UUID
    ) -> tuple[OperationalSignatureVersion, OperationalSignatureDefinition]:
        version = db.get(OperationalSignatureVersion, version_id)
        if version is None:
            raise SignatureServiceError(
                "SIGNATURE_VERSION_NOT_FOUND", "Signature version not found", 404
            )
        signature = db.get(OperationalSignatureDefinition, version.signature_id)
        if signature is None or signature.lifecycle_status != "production":
            raise SignatureServiceError(
                "SIGNATURE_NOT_PRODUCTION",
                "Only production signatures may be deployed or executed",
                409,
            )
        if not SignatureCatalogService._validated(db, version.id):
            raise SignatureServiceError(
                "SIGNATURE_VALIDATION_REQUIRED", "Approved validation is required", 409
            )
        return version, signature

    @staticmethod
    def _entitlement(db: Session, organization_id: UUID) -> Entitlement:
        now = datetime.now(UTC)
        entitlement = db.scalar(
            select(Entitlement)
            .where(
                Entitlement.organization_id == organization_id,
                Entitlement.entitlement_key == "intelligence.operational_signatures",
                Entitlement.enabled.is_(True),
                Entitlement.effective_at <= now,
                Entitlement.expires_at.is_(None) | (Entitlement.expires_at > now),
            )
            .order_by(Entitlement.created_at.desc())
        )
        if entitlement is None:
            raise SignatureServiceError(
                "SIGNATURE_ENTITLEMENT_REQUIRED",
                "Operational Signature Intelligence entitlement is required",
                403,
            )
        return entitlement

    @staticmethod
    def _applicable_pack(
        db: Session, organization_id: UUID, applicable_versions: list[str]
    ) -> None:
        rows = db.execute(
            select(IndustryPackDefinition.code, IndustryPackVersion.semantic_version)
            .join(
                IndustryPackAssignment,
                IndustryPackAssignment.pack_id == IndustryPackDefinition.id,
            )
            .join(
                IndustryPackAssignmentState,
                IndustryPackAssignmentState.assignment_id == IndustryPackAssignment.id,
            )
            .join(
                IndustryPackVersion,
                IndustryPackVersion.id == IndustryPackAssignmentState.pack_version_id,
            )
            .where(
                IndustryPackAssignment.organization_id == organization_id,
                IndustryPackAssignment.status == "active",
                IndustryPackAssignmentState.status == "active",
            )
        ).all()
        effective = {f"{code}@{version}" for code, version in rows}
        if not effective.intersection(applicable_versions):
            raise SignatureServiceError(
                "SIGNATURE_PACK_NOT_APPLICABLE",
                "No active applicable industry-pack version is assigned",
                403,
            )


signature_catalog_service = SignatureCatalogService()
tenant_signature_service = TenantSignatureService()
