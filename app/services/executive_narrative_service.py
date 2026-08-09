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
    GroundedExecutiveNarrativeProvider,
    ProviderResponseError,
    ProviderUnavailableError,
    StructuredNarrativeRequest,
)
from app.core.config import Settings, get_settings
from app.models.ai_profile import AIOperationalProfile, AIProfileInference
from app.models.entities import Organization, OrganizationStatus, utc_now
from app.models.executive_narrative import GroundedExecutiveNarrative
from app.models.findings import FindingEvidenceItem
from app.models.value_scan import DirectionalValueScan
from app.narrative.claim_policy import ClaimType
from app.narrative.renderer import deterministic_fallback, render_narrative
from app.narrative.validator import NarrativeValidationError, validate_narrative_draft
from app.schemas.executive_narrative import ExecutiveNarrativeCreate, StructuredNarrative

TEMPLATE_CODE = "GROUNDED_EXECUTIVE_NARRATIVE_V1"
TEMPLATE_VERSION = "1.0"
SCHEMA_VERSION = "1.0"
MAX_OPPORTUNITIES = 5
MAX_GAPS = 5
MAX_LIMITATIONS = 5
_SECRET_PATTERN = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|bearer\s+[a-z0-9._-]{8,}|password\s*[:=]|"
    r"postgres(?:ql)?(?:\+\w+)?://|eyJ[a-zA-Z0-9_-]{8,}\.eyJ[a-zA-Z0-9_-]{8,}\.)"
)


class ExecutiveNarrativeServiceError(ValueError):
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
        return [_sanitize(item) for item in value[:25]]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value[:25]]
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _evidence_reference(item: object) -> str | None:
    if isinstance(item, dict) and item.get("id"):
        return f"evidence:{item['id']}"
    if isinstance(item, str):
        return item if item.startswith("evidence:") else f"evidence:{item}"
    return None


class ExecutiveNarrativeService:
    def __init__(
        self,
        settings: Settings | None = None,
        provider_factory: Callable[[Settings], GroundedExecutiveNarrativeProvider] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider_factory = provider_factory or OpenAIOperationalProfileAdapter
        self.provider_override: GroundedExecutiveNarrativeProvider | None = None

    def set_provider_for_testing(self, provider: GroundedExecutiveNarrativeProvider | None) -> None:
        self.provider_override = provider

    def _provider(self) -> GroundedExecutiveNarrativeProvider:
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
        payload: ExecutiveNarrativeCreate,
    ) -> GroundedExecutiveNarrative:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise ExecutiveNarrativeServiceError(
                "ORGANIZATION_NOT_FOUND", "Organization is unavailable", 404
            )
        scan = db.scalar(
            select(DirectionalValueScan).where(
                DirectionalValueScan.id == payload.scan_id,
                DirectionalValueScan.organization_id == organization_id,
            )
        )
        if scan is None:
            raise ExecutiveNarrativeServiceError(
                "VALUE_SCAN_NOT_FOUND", "Directional Value Scan not found", 404
            )
        self._validate_evidence_tenancy(db, organization_id, scan)
        profile, inferences = self._profile_context(db, organization_id, payload.profile_id)
        source_snapshot, provider_context, allowed_claim_types, values = self._source_contract(
            scan, profile, inferences
        )
        input_fingerprint = _hash(source_snapshot)
        source_profile_fingerprint = (
            _hash(source_snapshot.get("context", [])) if profile is not None else None
        )
        execution_contract = {
            "organization_id": str(organization_id),
            "scan_id": str(scan.id),
            "scan_content_hash": scan.result_content_hash,
            "profile_id": str(profile.id) if profile is not None else None,
            "profile_fingerprint": source_profile_fingerprint,
            "audience": payload.audience,
            "template": [TEMPLATE_CODE, TEMPLATE_VERSION],
            "schema_version": SCHEMA_VERSION,
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model,
            "ai_enabled": self.settings.ai_enabled,
            "max_input_chars": self.settings.ai_narrative_max_input_chars,
            "max_output_tokens": self.settings.ai_narrative_max_output_tokens,
        }
        execution_fingerprint = _hash(execution_contract)
        request_hash = _hash(
            {
                **execution_contract,
                "scan_id": str(scan.id),
                "profile_id": str(profile.id) if profile is not None else None,
                "idempotency_key": payload.idempotency_key,
            }
        )
        existing_key = db.scalar(
            select(GroundedExecutiveNarrative).where(
                GroundedExecutiveNarrative.organization_id == organization_id,
                GroundedExecutiveNarrative.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_key is not None:
            if existing_key.request_hash != request_hash:
                raise ExecutiveNarrativeServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was reused with a different narrative request",
                    409,
                )
            return existing_key
        reusable = db.scalar(
            select(GroundedExecutiveNarrative).where(
                GroundedExecutiveNarrative.organization_id == organization_id,
                GroundedExecutiveNarrative.execution_fingerprint == execution_fingerprint,
            )
        )
        if reusable is not None:
            return reusable

        provider_code: str | None = None
        model_code: str | None = None
        model_version: str | None = None
        provider_failure_code: str | None = None
        observability: dict[str, object] = {
            "template_version": TEMPLATE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "raw_request_logged": False,
            "raw_response_logged": False,
        }
        narrative: StructuredNarrative
        source_opportunities = source_snapshot.get("opportunities", [])
        deterministic_source_state = scan.status == "refused" or not source_opportunities
        if deterministic_source_state:
            status = "fallback"
            narrative = deterministic_fallback(organization_id, scan.id, source_snapshot, values)
            observability["deterministic_reason"] = "SOURCE_STATE"
        else:
            try:
                request = StructuredNarrativeRequest(
                    organization_id=organization_id,
                    scan_id=scan.id,
                    template_code=TEMPLATE_CODE,
                    template_version=TEMPLATE_VERSION,
                    schema_version=SCHEMA_VERSION,
                    audience=payload.audience,
                    governed_context=provider_context,
                    allowed_source_reference_ids=tuple(sorted(allowed_claim_types)),
                    allowed_value_reference_ids=tuple(sorted(values)),
                )
                if (
                    len(_stable_json(request.governed_context))
                    > self.settings.ai_narrative_max_input_chars
                ):
                    raise ProviderResponseError(
                        "Narrative provider input exceeds the governed limit"
                    )
                result = self._provider().generate_narrative(request)
                validate_narrative_draft(
                    result.response,
                    organization_id,
                    scan.id,
                    allowed_claim_types,
                    set(values),
                    (
                        f"next-investigation:{scan.id}"
                        if scan.next_investigation_snapshot is not None
                        else None
                    ),
                )
                narrative = render_narrative(result.response, values)
                status = "completed"
                provider_code = result.provider_code
                model_code = result.model_code
                model_version = result.model_version
                observability.update(
                    {
                        "latency_ms": result.latency_ms,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "retry_count": result.retry_count,
                    }
                )
            except ProviderUnavailableError:
                provider_failure_code = "PROVIDER_UNAVAILABLE"
                status = "fallback"
                narrative = deterministic_fallback(
                    organization_id, scan.id, source_snapshot, values
                )
            except (ProviderResponseError, NarrativeValidationError, ValidationError, ValueError):
                provider_failure_code = "INVALID_PROVIDER_RESPONSE"
                status = "fallback"
                narrative = deterministic_fallback(
                    organization_id, scan.id, source_snapshot, values
                )

        narrative_snapshot = narrative.model_dump(mode="json")
        limitations = [str(item) for item in scan.limitations[:MAX_LIMITATIONS]]
        row = GroundedExecutiveNarrative(
            organization_id=organization_id,
            scan_id=scan.id,
            profile_id=profile.id if profile is not None else None,
            requested_by_user_id=actor_user_id,
            idempotency_key=payload.idempotency_key,
            audience=payload.audience,
            status=status,
            provider_code=provider_code,
            model_code=model_code,
            model_version=model_version,
            template_code=TEMPLATE_CODE,
            template_version=TEMPLATE_VERSION,
            schema_version=SCHEMA_VERSION,
            request_hash=request_hash,
            input_fingerprint=input_fingerprint,
            execution_fingerprint=execution_fingerprint,
            source_scan_content_hash=scan.result_content_hash,
            source_profile_fingerprint=source_profile_fingerprint,
            structured_source_snapshot=source_snapshot,
            structured_narrative_snapshot=narrative_snapshot,
            limitations=limitations,
            observability_snapshot=observability,
            provider_failure_code=provider_failure_code,
            content_hash=_hash(narrative_snapshot),
            generated_at=utc_now(),
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            concurrent = db.scalar(
                select(GroundedExecutiveNarrative).where(
                    GroundedExecutiveNarrative.organization_id == organization_id,
                    (
                        (GroundedExecutiveNarrative.idempotency_key == payload.idempotency_key)
                        | (
                            GroundedExecutiveNarrative.execution_fingerprint
                            == execution_fingerprint
                        )
                    ),
                )
            )
            if concurrent is not None:
                if (
                    concurrent.idempotency_key == payload.idempotency_key
                    and concurrent.request_hash != request_hash
                ):
                    raise ExecutiveNarrativeServiceError(
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key was reused with a different narrative request",
                        409,
                    )
                return concurrent
            raise
        db.refresh(row)
        return row

    def get(
        self, db: Session, organization_id: UUID, narrative_id: UUID
    ) -> GroundedExecutiveNarrative:
        row = db.scalar(
            select(GroundedExecutiveNarrative).where(
                GroundedExecutiveNarrative.id == narrative_id,
                GroundedExecutiveNarrative.organization_id == organization_id,
            )
        )
        if row is None:
            raise ExecutiveNarrativeServiceError(
                "NARRATIVE_NOT_FOUND", "Executive narrative not found", 404
            )
        return row

    def list_for_organization(
        self, db: Session, organization_id: UUID
    ) -> list[GroundedExecutiveNarrative]:
        return list(
            db.scalars(
                select(GroundedExecutiveNarrative)
                .where(GroundedExecutiveNarrative.organization_id == organization_id)
                .order_by(GroundedExecutiveNarrative.generated_at.desc())
            )
        )

    @staticmethod
    def _validate_evidence_tenancy(
        db: Session, organization_id: UUID, scan: DirectionalValueScan
    ) -> None:
        evidence_ids: set[UUID] = set()
        for opportunity in scan.opportunity_snapshot[:MAX_OPPORTUNITIES]:
            raw_evidence = opportunity.get("evidence_references", [])
            items = raw_evidence if isinstance(raw_evidence, list) else []
            for item in items[:10]:
                raw_id = item.get("id") if isinstance(item, dict) else item
                if isinstance(raw_id, str) and raw_id.startswith("evidence:"):
                    raw_id = raw_id.removeprefix("evidence:")
                try:
                    evidence_ids.add(UUID(str(raw_id)))
                except (TypeError, ValueError):
                    raise ExecutiveNarrativeServiceError(
                        "INVALID_EVIDENCE_REFERENCE",
                        "Directional Value Scan contains an invalid evidence reference",
                        422,
                    ) from None
        if not evidence_ids:
            return
        owned_ids = set(
            db.scalars(
                select(FindingEvidenceItem.id).where(
                    FindingEvidenceItem.organization_id == organization_id,
                    FindingEvidenceItem.id.in_(evidence_ids),
                )
            )
        )
        if owned_ids != evidence_ids:
            raise ExecutiveNarrativeServiceError(
                "INVALID_EVIDENCE_REFERENCE",
                "Directional Value Scan contains evidence outside tenant scope",
                422,
            )

    @staticmethod
    def _profile_context(
        db: Session, organization_id: UUID, profile_id: UUID | None
    ) -> tuple[AIOperationalProfile | None, list[AIProfileInference]]:
        if profile_id is None:
            return None, []
        profile = db.scalar(
            select(AIOperationalProfile).where(
                AIOperationalProfile.id == profile_id,
                AIOperationalProfile.organization_id == organization_id,
                AIOperationalProfile.status.in_(("completed", "partial")),
            )
        )
        if profile is None:
            raise ExecutiveNarrativeServiceError(
                "PROFILE_NOT_FOUND", "AI operational profile not found", 404
            )
        inferences = list(
            db.scalars(
                select(AIProfileInference)
                .where(
                    AIProfileInference.organization_id == organization_id,
                    AIProfileInference.profile_id == profile.id,
                    AIProfileInference.status.in_(("INFERRED", "CONFIRMED", "CORRECTED")),
                )
                .order_by(AIProfileInference.sequence_number)
            )
        )
        return profile, inferences

    @staticmethod
    def _source_contract(
        scan: DirectionalValueScan,
        profile: AIOperationalProfile | None,
        inferences: list[AIProfileInference],
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        dict[str, set[ClaimType]],
        dict[str, dict[str, object]],
    ]:
        scan_ref = f"scan:{scan.id}"
        allowed: dict[str, set[ClaimType]] = {
            scan_ref: {ClaimType.GOVERNED_SCAN_FACT, ClaimType.LIMITATION}
        }
        values: dict[str, dict[str, object]] = {}
        opportunities: list[dict[str, object]] = []
        provider_opportunities: list[dict[str, object]] = []
        governed_opportunities = (
            [] if scan.status == "refused" else scan.opportunity_snapshot[:MAX_OPPORTUNITIES]
        )
        for index, item in enumerate(governed_opportunities, start=1):
            rank = int(str(item.get("rank") or index))
            opportunity_ref = f"opportunity:{scan.id}:{rank}"
            finding_id = str(item.get("finding_id"))
            finding_ref = f"finding:{finding_id}"
            allowed[opportunity_ref] = {
                ClaimType.GOVERNED_SCAN_FACT,
                ClaimType.GOVERNED_FINDING,
                ClaimType.POTENTIAL_EXPOSURE,
            }
            allowed[finding_ref] = {
                ClaimType.GOVERNED_FINDING,
                ClaimType.POTENTIAL_EXPOSURE,
            }
            raw_evidence = item.get("evidence_references", [])
            evidence_items = raw_evidence if isinstance(raw_evidence, list) else []
            evidence_refs = [
                reference
                for raw in evidence_items[:10]
                if (reference := _evidence_reference(raw)) is not None
            ]
            for reference in evidence_refs:
                allowed[reference] = {ClaimType.GOVERNED_FINDING}
            exposure = item.get("potential_exposure")
            value_ref = f"value:{scan.id}:{rank}:potential_exposure"
            if isinstance(exposure, dict):
                values[value_ref] = dict(exposure)
            confidence = item.get("confidence")
            confidence_level = (
                str(confidence.get("level"))
                if isinstance(confidence, dict) and confidence.get("level")
                else "NOT_ASSESSED"
            )
            raw_limitations = item.get("limitations", [])
            item_limitations = raw_limitations if isinstance(raw_limitations, list) else []
            safe_item = {
                "rank": rank,
                "reference_id": opportunity_ref,
                "finding_reference_id": finding_ref,
                "finding_id": finding_id,
                "title": item.get("title"),
                "finding_code": item.get("finding_code"),
                "support_state": item.get("support_state"),
                "confidence": confidence_level,
                "evidence_reference_ids": evidence_refs,
                "potential_exposure_reference_id": value_ref if value_ref in values else None,
                "potential_exposure": values.get(value_ref),
                "limitations": item_limitations[:3],
            }
            opportunities.append(safe_item)
            provider_opportunities.append(
                {
                    key: value
                    for key, value in safe_item.items()
                    if key not in {"potential_exposure"}
                }
            )

        gaps: list[dict[str, object]] = []
        for item in scan.data_gap_snapshot[:MAX_GAPS]:
            code = str(item.get("gap_code") or "UNSPECIFIED")
            gap_ref = f"gap:{scan.id}:{code}"
            allowed[gap_ref] = {ClaimType.LIMITATION, ClaimType.RECOMMENDATION}
            gaps.append(
                {
                    "reference_id": gap_ref,
                    "gap_code": code,
                    "support_state": item.get("support_state"),
                    "remediation_guidance": item.get("remediation_guidance"),
                    "priority": item.get("priority"),
                }
            )
        next_ref = None
        if scan.next_investigation_snapshot is not None:
            next_ref = f"next-investigation:{scan.id}"
            allowed[next_ref] = {ClaimType.RECOMMENDATION}

        context: list[dict[str, object]] = []
        for inference in inferences[:3]:
            reference = f"profile-inference:{inference.id}"
            claim_type = (
                ClaimType.CUSTOMER_CONFIRMED_CONTEXT
                if inference.status in {"CONFIRMED", "CORRECTED"}
                else ClaimType.AI_INFERENCE
            )
            allowed[reference] = {claim_type}
            value = (
                inference.corrected_value
                if inference.status == "CORRECTED" and inference.corrected_value is not None
                else inference.display_value or inference.proposed_value
            )
            context.append(
                {
                    "reference_id": reference,
                    "claim_type": claim_type.value,
                    "status": inference.status,
                    "inference_type": inference.inference_type,
                    "value": value,
                    "tentative": inference.status == "INFERRED",
                }
            )

        source_snapshot: dict[str, object] = {
            "scan_reference_id": scan_ref,
            "status": scan.status,
            "scan_content_hash": scan.result_content_hash,
            "opportunities": opportunities,
            "data_gaps": gaps,
            "next_investigation_reference_id": next_ref,
            "next_investigation": scan.next_investigation_snapshot,
            "limitations": scan.limitations[:MAX_LIMITATIONS],
            "context": context,
            "profile_id": str(profile.id) if profile is not None else None,
            "profile_input_fingerprint": (
                profile.input_fingerprint if profile is not None else None
            ),
            "expected_recovery_included": False,
            "raw_evidence_included": False,
        }
        provider_context = {
            "status": scan.status,
            "scan_reference_id": scan_ref,
            "opportunities": provider_opportunities,
            "data_gaps": gaps,
            "next_investigation_reference_id": next_ref,
            "limitations": scan.limitations[:MAX_LIMITATIONS],
            "context": context,
            "claim_type_contract": {
                reference: sorted(claim_type.value for claim_type in claim_types)
                for reference, claim_types in allowed.items()
            },
            "policy": {
                "potential_exposure_values_are_renderer_owned": True,
                "expected_recovery_allowed": False,
                "causal_claims_allowed": False,
                "numbers_in_wording_allowed": False,
            },
        }
        sanitized_source = _sanitize(source_snapshot)
        sanitized_context = _sanitize(provider_context)
        assert isinstance(sanitized_source, dict)
        assert isinstance(sanitized_context, dict)
        return sanitized_source, sanitized_context, allowed, values


executive_narrative_service = ExecutiveNarrativeService()
