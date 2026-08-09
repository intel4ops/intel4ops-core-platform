from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.openai_adapter import OpenAIOperationalProfileAdapter
from app.ai.provider import (
    OperationalProfileInferenceProvider,
    ProviderResponseError,
    ProviderUnavailableError,
    StructuredInferenceRequest,
)
from app.core.config import Settings, get_settings
from app.models.ai_profile import AIOperationalProfile, AIProfileInference
from app.models.canonical_mapping import MappingRun, SourceSchema
from app.models.entities import Finding, Organization, OrganizationStatus, utc_now
from app.models.findings import FindingEvidenceItem
from app.models.ingestion import Dataset, DatasetVersion
from app.models.source_system import SourceSystem
from app.models.trust import AnalyticalReadinessDecision, TrustAssessment
from app.models.value_scan import DirectionalValueScan
from app.models.workspace import OrganizationChallenge, OrganizationObjective, OrganizationSystem
from app.registries.challenge_registry import is_valid_challenge_code
from app.registries.industry_registry import is_valid_industry_code
from app.registries.objective_registry import is_valid_objective_code
from app.registries.operational_profile_registry import (
    INFERENCE_TYPES,
    QUESTION_TARGET_TYPES,
    is_valid_inference_type,
    is_valid_local_code,
)
from app.registries.system_registry import is_valid_system_code
from app.schemas.ai_profile import AIProfileDecision
from app.services.workspace_service import WorkspaceServiceError, reconcile_ai_profile_context

TEMPLATE_CODE = "AI_OPERATIONAL_PROFILE_V1"
TEMPLATE_VERSION = "1.0"
MAX_CONTEXT_ROWS = 25
_SECRET_PATTERN = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|bearer\s+[a-z0-9._-]{8,}|password\s*[:=]|"
    r"postgres(?:ql)?(?:\+\w+)?://|eyJ[a-zA-Z0-9_-]{8,}\.eyJ[a-zA-Z0-9_-]{8,}\.)"
)
_PROHIBITED_QUESTION = re.compile(
    r"(?i)\b(password|api\s*key|access\s*token|jwt|bank\s*(?:account|credential)|secret)\b"
)


class AIOperationalProfileServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode()).hexdigest()


def _sanitize(value: object) -> object:
    if isinstance(value, str):
        return "[REDACTED]" if _SECRET_PATTERN.search(value) else value[:500]
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:MAX_CONTEXT_ROWS]]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value[:MAX_CONTEXT_ROWS]]
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _reference(kind: str, identifier: UUID) -> str:
    return f"{kind}:{identifier}"


class AIOperationalProfileService:
    def __init__(
        self,
        settings: Settings | None = None,
        provider_factory: Callable[[Settings], OperationalProfileInferenceProvider] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider_factory = provider_factory or OpenAIOperationalProfileAdapter
        self.provider_override: OperationalProfileInferenceProvider | None = None

    def set_provider_for_testing(
        self, provider: OperationalProfileInferenceProvider | None
    ) -> None:
        self.provider_override = provider

    def _provider(self) -> OperationalProfileInferenceProvider:
        if self.provider_override is not None:
            return self.provider_override
        if self.settings.ai_provider != "openai":
            raise ProviderUnavailableError("Configured AI provider is unsupported")
        return self.provider_factory(self.settings)

    def create(
        self,
        db: Session,
        organization_id: UUID,
        actor_user_id: UUID,
        idempotency_key: str,
    ) -> AIOperationalProfile:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise AIOperationalProfileServiceError(
                "ORGANIZATION_NOT_FOUND", "Organization is unavailable", 404
            )
        context, allowed_references = self._build_context(db, organization)
        input_fingerprint = _hash(context)
        execution_contract = {
            "organization_id": str(organization_id),
            "input_fingerprint": input_fingerprint,
            "template": [TEMPLATE_CODE, TEMPLATE_VERSION],
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model,
        }
        execution_fingerprint = _hash(execution_contract)
        request_hash = _hash({**execution_contract, "idempotency_key": idempotency_key})
        existing_key = db.scalar(
            select(AIOperationalProfile).where(
                AIOperationalProfile.organization_id == organization_id,
                AIOperationalProfile.idempotency_key == idempotency_key,
            )
        )
        if existing_key is not None:
            if existing_key.request_hash != request_hash:
                raise AIOperationalProfileServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was reused with different governed input",
                    409,
                )
            return existing_key
        reusable = db.scalar(
            select(AIOperationalProfile).where(
                AIOperationalProfile.organization_id == organization_id,
                AIOperationalProfile.execution_fingerprint == execution_fingerprint,
            )
        )
        if reusable is not None:
            return reusable

        profile = AIOperationalProfile(
            organization_id=organization_id,
            requested_by_user_id=actor_user_id,
            idempotency_key=idempotency_key,
            status="running",
            provider_code=self.settings.ai_provider,
            model_code=self.settings.ai_model,
            template_code=TEMPLATE_CODE,
            template_version=TEMPLATE_VERSION,
            input_fingerprint=input_fingerprint,
            execution_fingerprint=execution_fingerprint,
            request_hash=request_hash,
            profile_summary_snapshot={},
            input_provenance_snapshot={
                "reference_ids": sorted(allowed_references),
                "input_fingerprint": input_fingerprint,
                "raw_evidence_included": False,
                "document_excerpts_included": False,
            },
            observability_snapshot={},
            limitations=[],
        )
        db.add(profile)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            concurrent = db.scalar(
                select(AIOperationalProfile).where(
                    AIOperationalProfile.organization_id == organization_id,
                    (
                        (AIOperationalProfile.idempotency_key == idempotency_key)
                        | (AIOperationalProfile.execution_fingerprint == execution_fingerprint)
                    ),
                )
            )
            if concurrent is not None:
                return concurrent
            raise

        request = StructuredInferenceRequest(
            organization_id=organization_id,
            template_code=TEMPLATE_CODE,
            template_version=TEMPLATE_VERSION,
            governed_context=context,
            allowed_inference_types=INFERENCE_TYPES,
            max_inference_items=self.settings.ai_max_inference_items,
            max_clarification_questions=self.settings.ai_max_clarification_questions,
        )
        try:
            result = self._provider().generate_profile(request)
        except ProviderUnavailableError:
            return self._finish_failure(db, profile, "unavailable", "PROVIDER_UNAVAILABLE")
        except (ProviderResponseError, ValidationError):
            return self._finish_failure(db, profile, "failed", "INVALID_PROVIDER_RESPONSE")

        if result.response.organization_id != organization_id:
            return self._finish_failure(db, profile, "failed", "CROSS_TENANT_PROVIDER_OUTPUT")

        limitations = list(result.response.limitations)
        accepted = 0
        question_count = 0
        for candidate in result.response.inferences[: self.settings.ai_max_inference_items]:
            if not is_valid_inference_type(candidate.inference_type):
                limitations.append("Provider returned an unsupported inference type.")
                continue
            if candidate.inference_type == "CLARIFICATION_QUESTION":
                if question_count >= self.settings.ai_max_clarification_questions:
                    limitations.append("Clarification question limit was reached.")
                    continue
                if _PROHIBITED_QUESTION.search(candidate.proposed_value or ""):
                    limitations.append("A prohibited clarification question was rejected.")
                    continue
                question_count += 1
            invalid_refs = set(candidate.evidence_references) - allowed_references
            if invalid_refs:
                limitations.append("An inference with invalid evidence references was rejected.")
                continue
            registry_valid = self._registry_valid(candidate.inference_type, candidate.proposed_code)
            confidence = self._confidence(candidate.evidence_references, registry_valid)
            db.add(
                AIProfileInference(
                    organization_id=organization_id,
                    profile_id=profile.id,
                    sequence_number=accepted + 1,
                    inference_type=candidate.inference_type,
                    proposed_code=candidate.proposed_code,
                    proposed_value=candidate.proposed_value,
                    display_value=candidate.display_value,
                    confidence=confidence,
                    status="INFERRED",
                    reasoning_summary=candidate.reasoning_summary,
                    evidence_references=candidate.evidence_references,
                    alternative_candidates=candidate.alternative_candidates,
                    provider_metadata={
                        "provider_confidence": candidate.confidence,
                        "registry_valid": registry_valid,
                    },
                )
            )
            accepted += 1
        profile.status = "completed" if not limitations else "partial"
        profile.model_version = result.model_version
        profile.response_hash = _hash(result.response.model_dump(mode="json"))
        profile.completed_at = utc_now()
        profile.profile_summary_snapshot = {
            "inference_count": accepted,
            "clarification_question_count": question_count,
            "truth_classification": "INFERRED",
        }
        profile.observability_snapshot = {
            "provider": result.provider_code,
            "model": result.model_code,
            "model_version": result.model_version,
            "template_version": TEMPLATE_VERSION,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "retry_count": result.retry_count,
            "raw_request_logged": False,
            "raw_response_logged": False,
        }
        profile.limitations = limitations
        self._supersede_prior(db, profile)
        db.commit()
        db.refresh(profile)
        return profile

    def get(
        self, db: Session, organization_id: UUID, profile_id: UUID
    ) -> tuple[AIOperationalProfile, list[AIProfileInference]]:
        profile = db.scalar(
            select(AIOperationalProfile).where(
                AIOperationalProfile.id == profile_id,
                AIOperationalProfile.organization_id == organization_id,
            )
        )
        if profile is None:
            raise AIOperationalProfileServiceError(
                "PROFILE_NOT_FOUND", "AI operational profile not found", 404
            )
        rows = list(
            db.scalars(
                select(AIProfileInference)
                .where(
                    AIProfileInference.organization_id == organization_id,
                    AIProfileInference.profile_id == profile.id,
                )
                .order_by(AIProfileInference.sequence_number)
            )
        )
        return profile, rows

    def decide(
        self,
        db: Session,
        organization_id: UUID,
        profile_id: UUID,
        inference_id: UUID,
        actor_user_id: UUID,
        payload: AIProfileDecision,
    ) -> AIProfileInference:
        inference = db.scalar(
            select(AIProfileInference)
            .where(
                AIProfileInference.id == inference_id,
                AIProfileInference.profile_id == profile_id,
                AIProfileInference.organization_id == organization_id,
            )
            .with_for_update()
        )
        if inference is None:
            raise AIOperationalProfileServiceError(
                "INFERENCE_NOT_FOUND", "AI profile inference not found", 404
            )
        if inference.status not in {"INFERRED", "DEFERRED"}:
            raise AIOperationalProfileServiceError(
                "INVALID_INFERENCE_TRANSITION",
                "Inference decision is already final",
                409,
            )
        now = utc_now()
        if payload.decision == "DEFER":
            inference.status = "DEFERRED"
            inference.deferred_by_user_id = actor_user_id
            inference.deferred_at = now
        else:
            code = (
                payload.corrected_code if payload.decision == "CORRECT" else inference.proposed_code
            )
            value = (
                payload.corrected_value
                if payload.decision == "CORRECT"
                else inference.proposed_value
            )
            if not self._registry_valid(inference.inference_type, code):
                raise AIOperationalProfileServiceError(
                    "INVALID_REGISTRY_CODE",
                    "Inference cannot be governed without a valid code",
                    422,
                )
            try:
                reconcile_ai_profile_context(
                    db,
                    organization_id,
                    inference.inference_type,
                    code,
                    value,
                    actor_user_id,
                )
            except WorkspaceServiceError as exc:
                raise AIOperationalProfileServiceError(exc.code, str(exc), exc.status) from exc
            inference.status = "CORRECTED" if payload.decision == "CORRECT" else "CONFIRMED"
            inference.confirmed_by_user_id = actor_user_id
            inference.confirmed_at = now
            inference.corrected_code = payload.corrected_code
            inference.corrected_value = payload.corrected_value
        db.commit()
        db.refresh(inference)
        return inference

    def reject(
        self,
        db: Session,
        organization_id: UUID,
        profile_id: UUID,
        inference_id: UUID,
        actor_user_id: UUID,
    ) -> AIProfileInference:
        inference = db.scalar(
            select(AIProfileInference)
            .where(
                AIProfileInference.id == inference_id,
                AIProfileInference.profile_id == profile_id,
                AIProfileInference.organization_id == organization_id,
            )
            .with_for_update()
        )
        if inference is None:
            raise AIOperationalProfileServiceError(
                "INFERENCE_NOT_FOUND", "AI profile inference not found", 404
            )
        if inference.status not in {"INFERRED", "DEFERRED"}:
            raise AIOperationalProfileServiceError(
                "INVALID_INFERENCE_TRANSITION", "Inference decision is already final", 409
            )
        inference.status = "REJECTED"
        inference.rejected_by_user_id = actor_user_id
        inference.rejected_at = utc_now()
        db.commit()
        db.refresh(inference)
        return inference

    def _finish_failure(
        self, db: Session, profile: AIOperationalProfile, status: str, code: str
    ) -> AIOperationalProfile:
        profile.status = status
        profile.failure_code = code
        profile.failure_message_sanitized = "AI operational profiling did not complete"
        profile.completed_at = utc_now()
        profile.profile_summary_snapshot = {"inference_count": 0}
        profile.observability_snapshot = {
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model,
            "failure_category": code,
            "raw_request_logged": False,
            "raw_response_logged": False,
        }
        db.commit()
        db.refresh(profile)
        return profile

    @staticmethod
    def _confidence(evidence: list[str], registry_valid: bool) -> str:
        source_classes = {item.split(":", 1)[0] for item in evidence}
        if registry_valid and len(source_classes) >= 2:
            return "HIGH"
        if registry_valid and source_classes:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _registry_valid(inference_type: str, code: str | None) -> bool:
        if inference_type == "INDUSTRY":
            return code is not None and is_valid_industry_code(code)
        if inference_type == "BUSINESS_OBJECTIVE":
            return code is not None and is_valid_objective_code(code)
        if inference_type == "OPERATIONAL_CHALLENGE":
            return code is not None and is_valid_challenge_code(code)
        if inference_type == "SYSTEM_IN_USE":
            return code is not None and is_valid_system_code(code)
        if inference_type == "CLARIFICATION_QUESTION":
            return code is None or code in QUESTION_TARGET_TYPES
        return is_valid_local_code(inference_type, code)

    @staticmethod
    def _supersede_prior(db: Session, profile: AIOperationalProfile) -> None:
        prior_items = list(
            db.scalars(
                select(AIProfileInference)
                .join(
                    AIOperationalProfile, AIOperationalProfile.id == AIProfileInference.profile_id
                )
                .where(
                    AIProfileInference.organization_id == profile.organization_id,
                    AIProfileInference.profile_id != profile.id,
                    AIProfileInference.status.in_({"INFERRED", "DEFERRED"}),
                    AIOperationalProfile.status.in_({"completed", "partial"}),
                )
            )
        )
        for row in prior_items:
            row.status = "SUPERSEDED"

    def _build_context(
        self, db: Session, organization: Organization
    ) -> tuple[dict[str, object], set[str]]:
        org_id = organization.id
        references: set[str] = {_reference("organization", org_id)}
        objectives = list(
            db.scalars(
                select(OrganizationObjective).where(OrganizationObjective.organization_id == org_id)
            )
        )
        challenges = list(
            db.scalars(
                select(OrganizationChallenge).where(OrganizationChallenge.organization_id == org_id)
            )
        )
        systems = list(
            db.scalars(
                select(OrganizationSystem).where(OrganizationSystem.organization_id == org_id)
            )
        )
        sources = list(
            db.scalars(
                select(SourceSystem)
                .where(SourceSystem.organization_id == org_id)
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        datasets = list(
            db.scalars(
                select(Dataset).where(Dataset.organization_id == org_id).limit(MAX_CONTEXT_ROWS)
            )
        )
        versions = list(
            db.scalars(
                select(DatasetVersion)
                .where(DatasetVersion.organization_id == org_id)
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        schemas = list(
            db.scalars(
                select(SourceSchema)
                .where(SourceSchema.organization_id == org_id)
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        mapping_runs = list(
            db.scalars(
                select(MappingRun)
                .where(MappingRun.organization_id == org_id)
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        trusts = list(
            db.scalars(
                select(TrustAssessment)
                .where(TrustAssessment.organization_id == org_id)
                .order_by(TrustAssessment.created_at.desc())
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        readiness = list(
            db.scalars(
                select(AnalyticalReadinessDecision)
                .where(AnalyticalReadinessDecision.organization_id == org_id)
                .order_by(AnalyticalReadinessDecision.created_at.desc())
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        findings = list(
            db.scalars(
                select(Finding)
                .where(Finding.organization_id == org_id)
                .order_by(Finding.created_at.desc())
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        evidence = list(
            db.scalars(
                select(FindingEvidenceItem)
                .where(FindingEvidenceItem.organization_id == org_id)
                .order_by(FindingEvidenceItem.created_at.desc())
                .limit(MAX_CONTEXT_ROWS)
            )
        )
        scan = db.scalar(
            select(DirectionalValueScan)
            .where(DirectionalValueScan.organization_id == org_id)
            .order_by(DirectionalValueScan.generated_at.desc())
            .limit(1)
        )
        for kind, rows in (
            ("objective", objectives),
            ("challenge", challenges),
            ("workspace_system", systems),
            ("source_system", sources),
            ("dataset", datasets),
            ("dataset_version", versions),
            ("source_schema", schemas),
            ("mapping_run", mapping_runs),
            ("trust", trusts),
            ("readiness", readiness),
            ("finding", findings),
            ("evidence", evidence),
        ):
            references.update(_reference(kind, row.id) for row in rows)
        if scan is not None:
            references.add(_reference("value_scan", scan.id))
        context: dict[str, object] = {
            "organization": {
                "reference_id": _reference("organization", org_id),
                "country_code": organization.country_code,
                "default_currency": organization.default_currency,
                "industry": organization.industry,
                "sub_industry": organization.sub_industry,
                "employee_count_range": organization.employee_count_range,
                "annual_revenue_range": organization.annual_revenue_range,
                "operating_site_count": organization.operating_site_count,
            },
            "workspace": {
                "objectives": [
                    {"reference_id": _reference("objective", row.id), "code": row.objective_code}
                    for row in objectives
                ],
                "challenges": [
                    {"reference_id": _reference("challenge", row.id), "code": row.challenge_code}
                    for row in challenges
                ],
                "systems": [
                    {
                        "reference_id": _reference("workspace_system", row.id),
                        "code": row.system_code,
                        "custom_label": row.custom_label,
                    }
                    for row in systems
                ],
            },
            "source_systems": [
                {
                    "reference_id": _reference("source_system", row.id),
                    "system_type": row.system_type,
                    "provider": row.provider,
                    "integration_method": row.integration_method,
                    "environment": row.environment,
                    "status": row.status,
                    "capabilities": row.capabilities or [],
                }
                for row in sources
            ],
            "datasets": [
                {
                    "reference_id": _reference("dataset", row.id),
                    "domain": row.domain,
                    "dataset_type": row.dataset_type,
                    "status": row.status,
                    "schema_status": row.schema_status,
                }
                for row in datasets
            ],
            "dataset_versions": [
                {
                    "reference_id": _reference("dataset_version", row.id),
                    "status": row.status,
                    "file_extension": row.source_file_extension,
                    "media_type": row.media_type,
                    "record_count": row.record_count,
                    "column_count": row.column_count,
                    "schema_fingerprint": row.schema_fingerprint,
                }
                for row in versions
            ],
            "canonical_mapping": {
                "schemas": [
                    {
                        "reference_id": _reference("source_schema", row.id),
                        "status": row.status,
                        "schema_fingerprint": row.schema_fingerprint,
                    }
                    for row in schemas
                ],
                "runs": [
                    {
                        "reference_id": _reference("mapping_run", row.id),
                        "status": row.status,
                        "mapped_count": row.mapped_count,
                        "exception_count": row.exception_count,
                    }
                    for row in mapping_runs
                ],
            },
            "trust_readiness": {
                "assessments": [
                    {"reference_id": _reference("trust", row.id), "status": row.status}
                    for row in trusts
                ],
                "decisions": [
                    {
                        "reference_id": _reference("readiness", row.id),
                        "status": row.readiness_status,
                        "analytical_level": row.analytical_level,
                        "blocking_rule_codes": row.blocking_rule_codes,
                        "warning_rule_codes": row.warning_rule_codes,
                    }
                    for row in readiness
                ],
            },
            "findings": [
                {
                    "reference_id": _reference("finding", row.id),
                    "finding_code": row.finding_code,
                    "domain_code": row.domain_code,
                    "process_code": row.process_code,
                    "status": row.status,
                    "severity": row.severity,
                    "content_fingerprint": row.content_fingerprint,
                }
                for row in findings
            ],
            "evidence_metadata": [
                {
                    "reference_id": _reference("evidence", row.id),
                    "evidence_type": row.evidence_type,
                    "reference_type": row.reference_type,
                    "reference_fingerprint": row.reference_fingerprint,
                }
                for row in evidence
            ],
            "directional_value_scan": (
                {
                    "reference_id": _reference("value_scan", scan.id),
                    "status": scan.status,
                    "input_fingerprint": scan.input_fingerprint,
                    "result_content_hash": scan.result_content_hash,
                    "opportunities": [
                        {
                            "finding_code": item.get("finding_code"),
                            "domain": item.get("domain"),
                            "process": item.get("process"),
                            "support_state": item.get("support_state"),
                        }
                        for item in scan.opportunity_snapshot[:10]
                    ],
                    "data_gaps": [
                        {
                            "gap_code": item.get("gap_code"),
                            "support_state": item.get("support_state"),
                        }
                        for item in scan.data_gap_snapshot[:10]
                    ],
                    "limitations": scan.limitations[:10],
                    "next_investigation": scan.next_investigation_snapshot,
                }
                if scan is not None
                else None
            ),
        }
        sanitized = _sanitize(context)
        assert isinstance(sanitized, dict)
        if len(_stable_json(sanitized)) > self.settings.ai_max_input_chars:
            raise AIOperationalProfileServiceError(
                "AI_INPUT_LIMIT_EXCEEDED",
                "Governed AI context exceeds the configured input limit",
                422,
            )
        return sanitized, references


ai_operational_profile_service = AIOperationalProfileService()
