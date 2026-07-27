from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.industry_packs.runtime import pack_runtime_registry
from app.models.commercial import (
    CommercialAuditEvent,
    Entitlement,
    IndustryPackAssignment,
    IndustryPackDefinition,
    UsageEvent,
)
from app.models.entities import Finding, FindingEvidence, Organization, RecoveryAction
from app.models.industry_packs import (
    IndustryPackAssignmentState,
    IndustryPackComponent,
    IndustryPackExecution,
    IndustryPackGovernanceEvent,
    IndustryPackValidationResult,
    IndustryPackVersion,
)
from app.schemas.economics import FindingLinkCreate, OpportunityCreate
from app.schemas.industry_packs import (
    PackAssignmentRequest,
    PackComponentWrite,
    PackCreate,
    PackExecutionCreate,
    PackVersionCreate,
)
from app.services.commercial_service import CommercialServiceError, entitlement_service
from app.services.economics_service import economics_service

TRANSITIONS = {
    "draft": {"validated"},
    "validated": {"approved", "draft"},
    "approved": {"published", "draft"},
    "published": {"deprecated"},
    "deprecated": {"retired"},
}
REQUIRED_COMPONENTS = {
    "ontology_mapping",
    "canonical_extension",
    "metric_definition",
    "rule_binding",
    "evidence_policy",
    "economic_mapping",
    "recovery_playbook",
    "command_capability",
    "usage_meter_binding",
}


class IndustryPackGovernanceService:
    def catalog(self, db: Session) -> list[IndustryPackDefinition]:
        return list(
            db.scalars(select(IndustryPackDefinition).order_by(IndustryPackDefinition.code))
        )

    def create_pack(self, db: Session, payload: PackCreate) -> IndustryPackDefinition:
        if db.scalar(
            select(IndustryPackDefinition.id).where(
                (IndustryPackDefinition.code == payload.code)
                | (IndustryPackDefinition.entitlement_key == payload.entitlement_key)
            )
        ):
            raise CommercialServiceError("PACK_CONFLICT", "Pack code or entitlement exists", 409)
        row = IndustryPackDefinition(**payload.model_dump(), status="draft")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def versions(self, db: Session, pack_code: str) -> list[IndustryPackVersion]:
        pack = self._pack(db, pack_code)
        return list(
            db.scalars(
                select(IndustryPackVersion)
                .where(IndustryPackVersion.pack_id == pack.id)
                .order_by(IndustryPackVersion.semantic_version)
            )
        )

    def create_version(
        self, db: Session, pack_code: str, payload: PackVersionCreate, actor: UUID
    ) -> IndustryPackVersion:
        pack = self._pack(db, pack_code)
        if db.scalar(
            select(IndustryPackVersion.id).where(
                IndustryPackVersion.pack_id == pack.id,
                IndustryPackVersion.semantic_version == payload.semantic_version,
            )
        ):
            raise CommercialServiceError(
                "PACK_VERSION_CONFLICT", "Pack version already exists", 409
            )
        row = IndustryPackVersion(
            pack_id=pack.id,
            lifecycle_status="draft",
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        db.flush()
        self._replace_components(db, row)
        self._event(db, row.id, "version_created", actor, "Draft version created")
        db.commit()
        db.refresh(row)
        return row

    def validate(
        self, db: Session, version_id: UUID, actor: UUID, reason: str
    ) -> IndustryPackVersion:
        row = self._version(db, version_id)
        self._require_status(row, "draft")
        errors = self._manifest_errors(row.manifest_json)
        db.add(
            IndustryPackValidationResult(
                pack_version_id=row.id,
                valid=not errors,
                errors_json=errors,
                validator_version="1.0.0",
            )
        )
        if errors:
            db.commit()
            raise CommercialServiceError("PACK_VALIDATION_FAILED", "; ".join(errors))
        row.lifecycle_status = "validated"
        row.validated_at = datetime.now(UTC)
        self._event(db, row.id, "version_validated", actor, reason)
        db.commit()
        db.refresh(row)
        return row

    def transition(
        self, db: Session, version_id: UUID, target: str, actor: UUID, reason: str
    ) -> IndustryPackVersion:
        row = self._version(db, version_id)
        if target not in TRANSITIONS.get(row.lifecycle_status, set()):
            raise CommercialServiceError(
                "INVALID_PACK_TRANSITION",
                f"Cannot transition {row.lifecycle_status} to {target}",
                409,
            )
        if target == "retired" and db.scalar(
            select(IndustryPackAssignmentState.id)
            .where(
                IndustryPackAssignmentState.pack_version_id == row.id,
                IndustryPackAssignmentState.status == "active",
            )
            .limit(1)
        ):
            raise CommercialServiceError(
                "PACK_VERSION_IN_USE", "Active assignments prevent retirement", 409
            )
        row.lifecycle_status = target
        now = datetime.now(UTC)
        if target == "approved":
            row.approved_at, row.approved_by_user_id = now, actor
        elif target == "published":
            row.published_at = now
        self._event(db, row.id, f"version_{target}", actor, reason)
        db.commit()
        db.refresh(row)
        return row

    def components(
        self, db: Session, version_id: UUID, kind: str | None = None
    ) -> list[IndustryPackComponent]:
        query = select(IndustryPackComponent).where(
            IndustryPackComponent.pack_version_id == version_id
        )
        if kind:
            query = query.where(IndustryPackComponent.component_type == kind)
        return list(
            db.scalars(
                query.order_by(IndustryPackComponent.component_type, IndustryPackComponent.code)
            )
        )

    def put_component(
        self,
        db: Session,
        version_id: UUID,
        payload: PackComponentWrite,
        actor: UUID,
    ) -> IndustryPackComponent:
        version = self._version(db, version_id)
        self._require_status(version, "draft")
        row = db.scalar(
            select(IndustryPackComponent).where(
                IndustryPackComponent.pack_version_id == version.id,
                IndustryPackComponent.component_type == payload.component_type,
                IndustryPackComponent.code == payload.code,
            )
        )
        if row is None:
            row = IndustryPackComponent(pack_version_id=version.id, **payload.model_dump())
            db.add(row)
        else:
            row.universal_parent = payload.universal_parent
            row.configuration = payload.configuration
        self._event(db, version.id, "component_updated", actor, f"Component {payload.code} updated")
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _manifest_errors(manifest: dict[str, object]) -> list[str]:
        errors: list[str] = []
        items = manifest.get("components")
        if not isinstance(items, list):
            return ["components must be a list"]
        kinds: set[str] = set()
        keys: set[tuple[object, object]] = set()
        for item in items:
            if not isinstance(item, dict):
                errors.append("component must be an object")
                continue
            kinds.add(str(item.get("type")))
            key = (item.get("type"), item.get("code"))
            if key in keys:
                errors.append(f"duplicate component {key}")
            keys.add(key)
            if not item.get("universal_parent"):
                errors.append(f"component {item.get('code')} lacks universal_parent")
        missing = REQUIRED_COMPONENTS - kinds
        if missing:
            errors.append(f"missing component types: {', '.join(sorted(missing))}")
        return errors

    def _replace_components(self, db: Session, version: IndustryPackVersion) -> None:
        items = version.manifest_json.get("components", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    db.add(
                        IndustryPackComponent(
                            pack_version_id=version.id,
                            component_type=str(item["type"]),
                            code=str(item["code"]),
                            universal_parent=str(item["universal_parent"]),
                            configuration=item.get("config", {}),
                        )
                    )

    @staticmethod
    def _event(db: Session, version_id: UUID, event_type: str, actor: UUID, reason: str) -> None:
        db.add(
            IndustryPackGovernanceEvent(
                pack_version_id=version_id,
                event_type=event_type,
                actor_user_id=actor,
                reason=reason,
            )
        )

    @staticmethod
    def _pack(db: Session, code: str) -> IndustryPackDefinition:
        row = db.scalar(select(IndustryPackDefinition).where(IndustryPackDefinition.code == code))
        if row is None:
            raise CommercialServiceError("PACK_NOT_FOUND", "Industry pack not found", 404)
        return row

    @staticmethod
    def _version(db: Session, version_id: UUID) -> IndustryPackVersion:
        row = db.get(IndustryPackVersion, version_id)
        if row is None:
            raise CommercialServiceError("PACK_VERSION_NOT_FOUND", "Pack version not found", 404)
        return row

    @staticmethod
    def _require_status(row: IndustryPackVersion, expected: str) -> None:
        if row.lifecycle_status != expected:
            raise CommercialServiceError(
                "INVALID_PACK_TRANSITION", f"Expected {expected} version", 409
            )


class TenantIndustryPackService:
    def assignments(self, db: Session, org: UUID) -> list[IndustryPackAssignmentState]:
        return list(
            db.scalars(
                select(IndustryPackAssignmentState).where(
                    IndustryPackAssignmentState.organization_id == org
                )
            )
        )

    def assign(
        self, db: Session, org: UUID, payload: PackAssignmentRequest, actor: UUID
    ) -> IndustryPackAssignmentState:
        pack = governance_service._pack(db, payload.pack_code)
        entitlement = self._require_entitlement(db, org, pack.entitlement_key)
        version = db.scalar(
            select(IndustryPackVersion).where(
                IndustryPackVersion.pack_id == pack.id,
                IndustryPackVersion.semantic_version == payload.semantic_version,
                IndustryPackVersion.lifecycle_status == "published",
            )
        )
        if version is None:
            raise CommercialServiceError(
                "PACK_VERSION_NOT_ASSIGNABLE", "Only published versions may be assigned", 409
            )
        row = db.scalar(
            select(IndustryPackAssignment).where(
                IndustryPackAssignment.organization_id == org,
                IndustryPackAssignment.pack_id == pack.id,
            )
        )
        snapshot: dict[str, object] = {
            "entitlement_key": pack.entitlement_key,
            "entitlement_id": str(entitlement.id),
        }
        if row is None:
            row = IndustryPackAssignment(
                organization_id=org,
                pack_id=pack.id,
                status="assigned",
                assigned_by_user_id=actor,
                effective_at=payload.effective_at,
                expires_at=payload.expires_at,
            )
            db.add(row)
            db.flush()
        else:
            row.status = "assigned"
            row.effective_at, row.expires_at = payload.effective_at, payload.expires_at
        state = db.scalar(
            select(IndustryPackAssignmentState).where(
                IndustryPackAssignmentState.assignment_id == row.id,
                IndustryPackAssignmentState.organization_id == org,
            )
        )
        if state is None:
            state = IndustryPackAssignmentState(
                organization_id=org,
                assignment_id=row.id,
                pack_version_id=version.id,
                status="assigned",
                configuration_overrides=payload.configuration_overrides,
                entitlement_snapshot=snapshot,
            )
            db.add(state)
        else:
            state.pack_version_id = version.id
            state.status = "assigned"
            state.configuration_overrides = payload.configuration_overrides
            state.entitlement_snapshot = snapshot
        db.add(
            CommercialAuditEvent(
                organization_id=org,
                event_type="industry_pack_assigned",
                entity_type="industry_pack_assignment",
                entity_id=str(row.id),
                actor_user_id=actor,
                idempotency_key=f"wp219:assign:{uuid4()}",
                reason=f"{pack.code} {version.semantic_version} assigned",
                event_payload={"pack_code": pack.code, "version": version.semantic_version},
            )
        )
        db.commit()
        db.refresh(state)
        return state

    def set_status(
        self,
        db: Session,
        org: UUID,
        assignment_id: UUID,
        status: str,
        actor: UUID,
        reason: str,
    ) -> IndustryPackAssignmentState:
        row, state = self._assignment(db, org, assignment_id)
        if status not in {"active", "suspended"}:
            raise CommercialServiceError(
                "INVALID_ASSIGNMENT_STATUS", "Unsupported assignment status"
            )
        now = datetime.now(UTC)
        if status == "active" and state.status != "active":
            limit = db.scalar(
                select(Entitlement)
                .where(
                    Entitlement.organization_id == org,
                    Entitlement.entitlement_key == "limits.industry_packs",
                    Entitlement.enabled.is_(True),
                    Entitlement.effective_at <= now,
                    (Entitlement.expires_at.is_(None) | (Entitlement.expires_at > now)),
                )
                .order_by(Entitlement.created_at.desc())
            )
            active_count = db.scalar(
                select(func.count())
                .select_from(IndustryPackAssignmentState)
                .where(
                    IndustryPackAssignmentState.organization_id == org,
                    IndustryPackAssignmentState.status == "active",
                )
            )
            if (
                limit is not None
                and limit.limit_value is not None
                and Decimal(active_count or 0) >= limit.limit_value
            ):
                raise CommercialServiceError(
                    "PACK_LIMIT_EXCEEDED", "Industry-pack activation limit exceeded", 403
                )
        row.status = status
        state.status = status
        if status == "active":
            state.activated_at, state.suspended_at = now, None
        else:
            state.suspended_at = now
        db.add(
            CommercialAuditEvent(
                organization_id=org,
                event_type=f"industry_pack_{status}",
                entity_type="industry_pack_assignment",
                entity_id=str(row.id),
                actor_user_id=actor,
                idempotency_key=f"wp219:status:{uuid4()}",
                reason=reason,
                event_payload={"status": status, "pack_version_id": str(state.pack_version_id)},
            )
        )
        db.commit()
        db.refresh(state)
        return state

    def execute(
        self, db: Session, org: UUID, assignment_id: UUID, payload: PackExecutionCreate, actor: UUID
    ) -> IndustryPackExecution:
        prior = db.scalar(
            select(IndustryPackExecution).where(
                IndustryPackExecution.organization_id == org,
                IndustryPackExecution.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        assignment, state = self._assignment(db, org, assignment_id)
        if assignment.status != "active" or state.status != "active":
            raise CommercialServiceError("PACK_NOT_ACTIVE", "Pack assignment is not active", 409)
        version = governance_service._version(db, state.pack_version_id)
        pack = db.get(IndustryPackDefinition, assignment.pack_id)
        if pack is None or version.lifecycle_status not in {"published", "deprecated"}:
            raise CommercialServiceError(
                "PACK_VERSION_UNAVAILABLE", "Pack version is unavailable", 409
            )
        self._require_entitlement(db, org, pack.entitlement_key)
        rule = db.scalar(
            select(IndustryPackComponent).where(
                IndustryPackComponent.pack_version_id == version.id,
                IndustryPackComponent.component_type == "rule_binding",
                IndustryPackComponent.code == payload.rule_code,
            )
        )
        if rule is None:
            raise CommercialServiceError("PACK_RULE_NOT_FOUND", "Pack rule is not registered", 404)
        runtime = pack_runtime_registry.resolve(pack.code)
        if payload.readiness == "blocked":
            status, result, error = "blocked", {}, "TRUST_READINESS_BLOCKED"
        elif runtime is not None:
            result = runtime(db, org, payload, actor)
            result["rule_code"] = rule.code
            result["recovery_playbook_code"] = (
                f"{rule.code}.RECOVERY" if result.get("finding_count", 0) else None
            )
            recovery_action_ids: list[str] = []
            finding_ids = result.get("finding_ids", [])
            if isinstance(finding_ids, list):
                for finding_id in finding_ids:
                    finding = db.scalar(
                        select(Finding).where(
                            Finding.id == UUID(str(finding_id)),
                            Finding.organization_id == org,
                        )
                    )
                    if finding is None:
                        continue
                    action = RecoveryAction(
                        organization_id=org,
                        finding_id=finding.id,
                        title=f"Execute {rule.code} recovery playbook",
                        owner="unassigned",
                        status="planned",
                        expected_recovery=finding.exposure_high,
                    )
                    db.add(action)
                    db.flush()
                    recovery_action_ids.append(str(action.id))
            result["recovery_action_ids"] = recovery_action_ids
            status, error = "completed", None
        else:
            record = payload.record
            value = Decimal(str(record.get("value", 0)))
            threshold = Decimal(str(record.get("threshold", 0)))
            triggered = value > threshold
            result = {
                "rule_code": rule.code,
                "triggered": triggered,
                "exposure": str(value - threshold if triggered else Decimal(0)),
                "evidence": {
                    key: record.get(key)
                    for key in ("record_id", "observed_at", "value", "threshold")
                },
                "calculation_trace": {
                    "operator": "greater_than",
                    "value": str(value),
                    "threshold": str(threshold),
                },
                "recovery_playbook_code": f"{rule.code}.RECOVERY" if triggered else None,
            }
            status, error = "completed", None
        row = IndustryPackExecution(
            organization_id=org,
            assignment_id=assignment.id,
            pack_version_id=version.id,
            idempotency_key=payload.idempotency_key,
            status=status,
            readiness=payload.readiness,
            input_json=payload.model_dump(mode="json"),
            result_json=result,
            error_code=error,
            created_by_user_id=actor,
            completed_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        if result.get("triggered") is True:
            organization = db.get(Organization, org)
            currency = organization.default_currency if organization else "USD"
            exposure = Decimal(str(result["exposure"]))
            finding = Finding(
                organization_id=org,
                rule_id=rule.code,
                title=f"{rule.code} governed industry-pack finding",
                summary=f"{rule.code} exceeded its governed threshold.",
                domain=str(version.manifest_json.get("industry", "operations")),
                severity="medium",
                priority=3,
                exposure_low=float(exposure),
                exposure_high=float(exposure),
                currency=currency,
                confidence_score=Decimal("1"),
                status="open",
                ontology_concept_ids=[rule.universal_parent],
                finding_code=rule.code,
                finding_type="deterministic_rule",
                industry_pack_code=pack.code,
                measured_value=Decimal(str(payload.record.get("value", 0))),
                measured_value_type="observed",
                exposure_value=exposure,
                exposure_value_type="estimated",
                exposure_currency=currency,
                affected_record_count=1,
                detected_at=datetime.now(UTC),
                published_at=datetime.now(UTC),
                definition_code=rule.code,
                definition_version=version.semantic_version,
                confidence_level="high",
                confidence_method_code="deterministic",
                confidence_method_version="1.0.0",
                deduplication_key=sha256(
                    f"{org}:{payload.idempotency_key}:{rule.code}".encode()
                ).hexdigest(),
                created_by_user_id=actor,
            )
            db.add(finding)
            db.flush()
            db.add(
                FindingEvidence(
                    organization_id=org,
                    finding_id=finding.id,
                    source_system="industry_pack_canonical",
                    source_record_id=str(payload.record.get("record_id", "unknown")),
                    evidence_type="governed_rule_input",
                    payload=result["evidence"],
                )
            )
            result["finding_id"] = str(finding.id)
            opportunity = economics_service.create(
                db,
                org,
                OpportunityCreate(
                    idempotency_key=f"pack:{row.id}:opportunity",
                    economic_source_key=f"industry-pack:{row.id}",
                    title=finding.title,
                    description=finding.summary,
                    currency_code=currency,
                    business_domain=finding.domain,
                    industry_pack_code=pack.code,
                    capability_code=rule.code,
                ),
                actor,
            )
            economics_service.add_finding(
                db,
                org,
                opportunity.id,
                FindingLinkCreate(finding_id=finding.id),
                actor,
            )
            recovery = RecoveryAction(
                organization_id=org,
                finding_id=finding.id,
                title=f"Execute {rule.code} recovery playbook",
                owner="unassigned",
                status="planned",
                expected_recovery=float(exposure),
            )
            db.add(recovery)
            db.flush()
            result["opportunity_id"] = str(opportunity.id)
            result["recovery_action_id"] = str(recovery.id)
            row.result_json = result
        db.add(
            UsageEvent(
                organization_id=org,
                meter_code="rule_executions",
                idempotency_key=f"pack-execution:{payload.idempotency_key}",
                quantity=Decimal(1),
                source_type="industry_pack_execution",
                source_id=str(row.id),
                occurred_at=datetime.now(UTC),
                metadata_json={"pack_code": pack.code, "rule_code": rule.code},
            )
        )
        db.commit()
        db.refresh(row)
        return row

    def effective_components(
        self,
        db: Session,
        org: UUID,
        assignment_id: UUID,
        component_type: str | None = None,
    ) -> list[IndustryPackComponent]:
        _, state = self._assignment(db, org, assignment_id)
        query = select(IndustryPackComponent).where(
            IndustryPackComponent.pack_version_id == state.pack_version_id
        )
        if component_type is not None:
            query = query.where(IndustryPackComponent.component_type == component_type)
        return list(
            db.scalars(
                query.order_by(
                    IndustryPackComponent.component_type,
                    IndustryPackComponent.code,
                )
            )
        )

    def effective_configuration(
        self, db: Session, org: UUID, assignment_id: UUID
    ) -> dict[str, object]:
        _, state = self._assignment(db, org, assignment_id)
        version = governance_service._version(db, state.pack_version_id)
        return {
            "pack_version_id": str(version.id),
            "semantic_version": version.semantic_version,
            "lifecycle_status": version.lifecycle_status,
            "minimum_platform_revision": version.minimum_platform_revision,
            "manifest": version.manifest_json,
            "configuration_overrides": state.configuration_overrides,
        }

    def executions(
        self, db: Session, org: UUID, assignment_id: UUID
    ) -> list[IndustryPackExecution]:
        self._assignment(db, org, assignment_id)
        return list(
            db.scalars(
                select(IndustryPackExecution)
                .where(
                    IndustryPackExecution.organization_id == org,
                    IndustryPackExecution.assignment_id == assignment_id,
                )
                .order_by(IndustryPackExecution.created_at.desc())
            )
        )

    def execution(
        self, db: Session, org: UUID, assignment_id: UUID, execution_id: UUID
    ) -> IndustryPackExecution:
        self._assignment(db, org, assignment_id)
        row = db.scalar(
            select(IndustryPackExecution).where(
                IndustryPackExecution.id == execution_id,
                IndustryPackExecution.organization_id == org,
                IndustryPackExecution.assignment_id == assignment_id,
            )
        )
        if row is None:
            raise CommercialServiceError(
                "PACK_EXECUTION_NOT_FOUND", "Pack execution not found", 404
            )
        return row

    @staticmethod
    def _require_entitlement(db: Session, org: UUID, entitlement_key: str) -> Entitlement:
        entitlement = entitlement_service.require(db, org, entitlement_key)
        if entitlement is None:
            raise CommercialServiceError(
                "ENTITLEMENT_REQUIRED",
                f"Entitlement {entitlement_key} is required",
                403,
            )
        return entitlement

    @staticmethod
    def _assignment(
        db: Session, org: UUID, assignment_id: UUID
    ) -> tuple[IndustryPackAssignment, IndustryPackAssignmentState]:
        row = db.scalar(
            select(IndustryPackAssignment).where(
                IndustryPackAssignment.id == assignment_id,
                IndustryPackAssignment.organization_id == org,
            )
        )
        if row is None:
            raise CommercialServiceError(
                "PACK_ASSIGNMENT_NOT_FOUND", "Pack assignment not found", 404
            )
        state = db.scalar(
            select(IndustryPackAssignmentState).where(
                IndustryPackAssignmentState.assignment_id == row.id,
                IndustryPackAssignmentState.organization_id == org,
            )
        )
        if state is None:
            raise CommercialServiceError(
                "PACK_ASSIGNMENT_STATE_NOT_FOUND", "Pack assignment state not found", 404
            )
        return row, state


governance_service = IndustryPackGovernanceService()
tenant_industry_pack_service = TenantIndustryPackService()
