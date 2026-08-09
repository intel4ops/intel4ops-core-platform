from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import NoReturn, cast
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.canonical_mapping import (
    CanonicalEntityType,
    CanonicalEventType,
    CanonicalFieldDefinition,
    CanonicalMetricType,
    MappingRecordResult,
    MappingReview,
    MappingTemplate,
    MappingTemplateVersion,
    SourceSchema,
)
from app.models.entities import Organization, OrganizationStatus, utc_now
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.schemas.operational_memory import (
    FieldMappingPayload,
    MemoryCandidateCreate,
    MemoryContext,
    MemoryDecisionRequest,
    MemoryRetrieveRead,
    MemoryRetrieveRequest,
    MemorySuggestionRead,
    SchemaPatternPayload,
    TerminologyPayload,
)

NORMALIZATION_POLICY = "memory_normalization_v1"
CONTEXT_POLICY = "memory_context_v1"
IDENTITY_POLICY = "memory_identity_v1"
RETRIEVAL_CONSUMER = "operational_memory_api"
RETRIEVAL_VERSION = "1.0"
MAX_JSON_DEPTH = 3
MAX_JSON_KEYS = 16
MAX_NESTED_KEYS = 12
MAX_LIST = 20

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SEPARATORS = re.compile(r"[^\w\s]", re.UNICODE)
_SECRET = re.compile(
    r"(?i)(?:password\s*[:=]|api[_ -]?key\s*[:=]|bearer\s+[a-z0-9._-]{8,}|"
    r"postgres(?:ql)?(?:\+\w+)?://|sk-[a-z0-9_-]{8,}|"
    r"eyJ[a-zA-Z0-9_-]{8,}\.eyJ[a-zA-Z0-9_-]{8,}\.)"
)
_PROHIBITED_KEY = re.compile(
    r"(?i)(?:amount|price|cost|revenue|salary|employee|customer|vendor|contract|"
    r"password|secret|token|credential|prompt|response|raw_row|document)"
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ALIASES = {"no": "number", "num": "number", "nbr": "number"}

_SUBJECTS = {
    "FIELD_MAPPING": "SOURCE_FIELD",
    "SCHEMA_PATTERN": "SOURCE_SCHEMA",
    "TERMINOLOGY": "TERM",
}
_ASSERTIONS = {
    "FIELD_MAPPING": "FIELD_TO_CANONICAL_FIELD",
    "SCHEMA_PATTERN": "SCHEMA_TO_CANONICAL_DOMAIN",
    "TERMINOLOGY": "TERM_TO_CANONICAL_CONCEPT",
}
_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "FIELD_MAPPING": FieldMappingPayload,
    "SCHEMA_PATTERN": SchemaPatternPayload,
    "TERMINOLOGY": TerminologyPayload,
}
_REUSABLE = {"CONFIRMED", "CORRECTED"}


class OperationalMemoryServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 422) -> NoReturn:
    raise OperationalMemoryServiceError(code, message, status)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_subject(value: str) -> str:
    if _CONTROL.search(value):
        _fail("UNSAFE_TEXT", "Control characters are not permitted")
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _CAMEL.sub(" ", normalized)
    normalized = normalized.replace("_", "-")
    normalized = _SEPARATORS.sub(" ", normalized).casefold()
    tokens = [_ALIASES.get(token, token) for token in normalized.split()]
    normalized = " ".join(tokens).strip()
    if not normalized or len(normalized) > 500:
        _fail("INVALID_SUBJECT", "Normalized subject must contain 1 to 500 characters")
    return normalized


def _bounded_json(value: object, *, max_size: int, label: str) -> None:
    def visit(node: object, depth: int, top: bool = False) -> None:
        if isinstance(node, (dict, list)) and depth > MAX_JSON_DEPTH:
            _fail("JSON_BOUNDS_EXCEEDED", f"{label} exceeds maximum nesting depth")
        if isinstance(node, dict):
            if len(node) > (MAX_JSON_KEYS if top else MAX_NESTED_KEYS):
                _fail("JSON_BOUNDS_EXCEEDED", f"{label} contains too many keys")
            for key, item in node.items():
                if len(str(key)) > 80:
                    _fail("JSON_BOUNDS_EXCEEDED", f"{label} contains an oversized key")
                if _PROHIBITED_KEY.search(str(key)):
                    _fail("SENSITIVE_MEMORY_CONTENT", f"{label} contains prohibited content")
                visit(item, depth + 1)
        elif isinstance(node, list):
            if len(node) > MAX_LIST and label != "value_payload":
                _fail("JSON_BOUNDS_EXCEEDED", f"{label} contains an oversized list")
            for item in node:
                visit(item, depth + 1)
        elif isinstance(node, str):
            if len(node) > 500:
                _fail("JSON_BOUNDS_EXCEEDED", f"{label} contains an oversized string")
            if _CONTROL.search(node) or _SECRET.search(node):
                _fail("SENSITIVE_MEMORY_CONTENT", f"{label} contains prohibited content")

    visit(value, 1, top=True)
    if len(_canonical_json(value).encode("utf-8")) > max_size:
        _fail("JSON_BOUNDS_EXCEEDED", f"{label} exceeds serialized-size limit")


def _context_payload(
    source_system_family: str | None,
    canonical_domain: str | None,
    context: MemoryContext,
    governed_industry: str | None,
) -> dict[str, object]:
    return {
        "policy": CONTEXT_POLICY,
        "source_system_family": (
            normalize_subject(source_system_family) if source_system_family else None
        ),
        "schema_fingerprint": context.schema_fingerprint.casefold()
        if context.schema_fingerprint
        else None,
        "canonical_domain": normalize_subject(canonical_domain) if canonical_domain else None,
        "source_table_or_entity_context": normalize_subject(context.source_table_or_entity_context)
        if context.source_table_or_entity_context
        else None,
        "neighboring_field_signatures": sorted(
            normalize_subject(item) for item in context.neighboring_field_signatures
        ),
        "governed_industry_code": governed_industry,
    }


def context_signature(
    source_system_family: str | None,
    canonical_domain: str | None,
    context: MemoryContext,
    governed_industry: str | None,
) -> str:
    return _sha(
        _context_payload(source_system_family, canonical_domain, context, governed_industry)
    )


def memory_fingerprint(
    organization_id: UUID,
    category: str,
    subject_kind: str,
    normalized_subject: str,
    source_system_family: str | None,
    canonical_domain: str | None,
    signature: str,
) -> str:
    return _sha(
        {
            "policy": IDENTITY_POLICY,
            "organization_id": str(organization_id),
            "category": category,
            "subject_kind": subject_kind,
            "normalized_subject": normalized_subject,
            "source_system_family": normalize_subject(source_system_family)
            if source_system_family
            else None,
            "canonical_domain": normalize_subject(canonical_domain) if canonical_domain else None,
            "context_signature": signature,
        }
    )


class OperationalMemoryService:
    def record_candidate(
        self,
        db: Session,
        organization_id: UUID,
        payload: MemoryCandidateCreate,
        actor_user_id: UUID | None = None,
        actor_role: str = "system",
        *,
        _retry: bool = True,
    ) -> tuple[OperationalMemoryItem, OperationalMemoryVersion]:
        organization = self._organization(db, organization_id)
        self._validate_subject_pair(payload.category, payload.subject_kind)
        value_payload = self._validate_payload(payload.category, payload.value_payload)
        provenance = payload.provenance.model_dump(mode="json")
        _bounded_json(value_payload, max_size=16 * 1024, label="value_payload")
        _bounded_json(provenance, max_size=16 * 1024, label="provenance_snapshot")
        if not _HEX64.fullmatch(payload.source_fingerprint.casefold()):
            _fail("SOURCE_FINGERPRINT_INVALID", "Source fingerprint must be SHA-256")
        self._validate_provenance(db, organization_id, payload, value_payload)

        normalized = normalize_subject(payload.subject)
        signature = context_signature(
            payload.source_system_family,
            payload.canonical_domain,
            payload.context,
            organization.industry,
        )
        fingerprint = memory_fingerprint(
            organization_id,
            payload.category,
            payload.subject_kind,
            normalized,
            payload.source_system_family,
            payload.canonical_domain,
            signature,
        )
        request_fingerprint = _sha(
            {
                "operation": "record_candidate",
                "organization_id": str(organization_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing_version = self._idempotent_version(
            db, organization_id, payload.idempotency_key, request_fingerprint
        )
        if existing_version is not None:
            return self._item(db, organization_id, existing_version.memory_id), existing_version

        item = db.scalar(
            select(OperationalMemoryItem)
            .where(
                OperationalMemoryItem.organization_id == organization_id,
                OperationalMemoryItem.category == payload.category,
                OperationalMemoryItem.memory_fingerprint == fingerprint,
            )
            .with_for_update()
        )
        now = utc_now()
        if item is None:
            item = OperationalMemoryItem(
                organization_id=organization_id,
                category=payload.category,
                subject_kind=payload.subject_kind,
                normalized_subject=normalized,
                source_system_family=payload.source_system_family,
                canonical_domain=payload.canonical_domain,
                context_signature=signature,
                memory_fingerprint=fingerprint,
                current_version_number=1,
                current_status="OBSERVED",
                support_count=1,
                valid_from=now,
                valid_to=payload.valid_to,
                security_classification=payload.security_classification,
                retention_until=now + timedelta(days=180),
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            db.flush()
            prior = None
            version_number = 1
            status = "OBSERVED"
        else:
            prior = self._current_version(db, item)
            version_number = item.current_version_number + 1
            same_value = _canonical_json(prior.value_payload) == _canonical_json(value_payload)
            if same_value:
                status = (
                    "OBSERVED"
                    if item.current_status in {"REJECTED", "DEPRECATED"}
                    else item.current_status
                )
                item.support_count += 1
                if status == "OBSERVED":
                    self._clear_stale(item)
            else:
                status = "AMBIGUOUS"
                item.contradiction_count += 1
                item.is_stale = True
                item.stale_reason_code = "CONTRADICTORY_EVIDENCE"
                item.stale_detected_at = now
                provenance["conflicting_version_ids"] = [str(prior.id)]

        version = self._new_version(
            item=item,
            version_number=version_number,
            prior=prior,
            status=status,
            value_payload=value_payload,
            provenance=provenance,
            source_schema_id=payload.provenance.source_schema_id,
            mapping_record_result_id=payload.provenance.mapping_record_result_id,
            source_fingerprint=payload.source_fingerprint.casefold(),
            request_fingerprint=request_fingerprint,
            idempotency_key=payload.idempotency_key,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            effective_from=now,
        )
        db.add(version)
        item.current_version_number = version_number
        item.current_status = status
        item.last_validated_at = now
        item.updated_at = now
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            concurrent = self._idempotent_version(
                db, organization_id, payload.idempotency_key, request_fingerprint
            )
            if concurrent is not None:
                return self._item(db, organization_id, concurrent.memory_id), concurrent
            if _retry:
                return self.record_candidate(
                    db,
                    organization_id,
                    payload,
                    actor_user_id,
                    actor_role,
                    _retry=False,
                )
            raise
        db.refresh(item)
        db.refresh(version)
        return item, version

    def decide(
        self,
        db: Session,
        organization_id: UUID,
        memory_id: UUID,
        payload: MemoryDecisionRequest,
        actor_user_id: UUID,
        actor_role: str,
    ) -> tuple[OperationalMemoryItem, OperationalMemoryVersion]:
        request_fingerprint = _sha(
            {
                "operation": "decision",
                "organization_id": str(organization_id),
                "memory_id": str(memory_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing = self._idempotent_version(
            db, organization_id, payload.idempotency_key, request_fingerprint
        )
        if existing is not None:
            return self._item(db, organization_id, existing.memory_id), existing
        item = db.scalar(
            select(OperationalMemoryItem)
            .where(
                OperationalMemoryItem.organization_id == organization_id,
                OperationalMemoryItem.id == memory_id,
            )
            .with_for_update()
        )
        if item is None:
            _fail("MEMORY_NOT_FOUND", "Operational memory not found", 404)
        if item.current_version_number != payload.expected_current_version:
            _fail("MEMORY_VERSION_CONFLICT", "Operational memory version changed", 409)
        prior = self._current_version(db, item)
        status = self._decision_status(item.current_status, payload.action)
        if payload.action == "CORRECT":
            if payload.corrected_payload is None:
                _fail("CORRECTION_REQUIRED", "Correction payload is required")
            value_payload = self._validate_payload(item.category, payload.corrected_payload)
        else:
            if payload.corrected_payload is not None:
                _fail("CORRECTION_NOT_ALLOWED", "Correction payload is only valid for CORRECT")
            value_payload = dict(prior.value_payload)
        _bounded_json(value_payload, max_size=16 * 1024, label="value_payload")
        now = utc_now()
        version_number = item.current_version_number + 1
        provenance = dict(prior.provenance_snapshot)
        provenance["decision_correlation_id"] = payload.correlation_id
        version = self._new_version(
            item=item,
            version_number=version_number,
            prior=prior,
            status=status,
            value_payload=value_payload,
            provenance=provenance,
            source_schema_id=prior.source_schema_id,
            mapping_record_result_id=prior.mapping_record_result_id,
            source_fingerprint=prior.source_fingerprint,
            request_fingerprint=request_fingerprint,
            idempotency_key=payload.idempotency_key,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            effective_from=now,
            decision_reason_code=payload.decision_reason_code,
            human_confirmed=status in {"CONFIRMED", "CORRECTED"},
        )
        db.add(version)
        item.current_version_number = version_number
        item.current_status = status
        item.updated_at = now
        item.last_validated_at = now
        if status in {"CONFIRMED", "CORRECTED"}:
            item.confirmation_count += 1
            item.last_confirmed_at = now
            item.retention_until = now + timedelta(days=730)
            self._clear_stale(item)
        elif status == "REJECTED":
            item.rejection_count += 1
            item.retention_until = now + timedelta(days=180)
            self._clear_stale(item)
        elif status == "DEPRECATED":
            item.retention_until = now + timedelta(days=730)
            self._clear_stale(item)
        db.commit()
        db.refresh(item)
        db.refresh(version)
        return item, version

    def get(
        self, db: Session, organization_id: UUID, memory_id: UUID
    ) -> tuple[OperationalMemoryItem, OperationalMemoryVersion]:
        item = self._item(db, organization_id, memory_id)
        return item, self._current_version(db, item)

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        category: str | None = None,
        status: str | None = None,
        source_system_family: str | None = None,
        canonical_domain: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[OperationalMemoryItem], str | None]:
        query = select(OperationalMemoryItem).where(
            OperationalMemoryItem.organization_id == organization_id
        )
        if category:
            query = query.where(OperationalMemoryItem.category == category)
        if status:
            query = query.where(OperationalMemoryItem.current_status == status)
        if source_system_family:
            query = query.where(OperationalMemoryItem.source_system_family == source_system_family)
        if canonical_domain:
            query = query.where(OperationalMemoryItem.canonical_domain == canonical_domain)
        if stale is not None:
            query = query.where(OperationalMemoryItem.is_stale == stale)
        if cursor:
            cursor_time, cursor_id = self._decode_cursor(cursor)
            query = query.where(
                or_(
                    OperationalMemoryItem.updated_at < cursor_time,
                    and_(
                        OperationalMemoryItem.updated_at == cursor_time,
                        OperationalMemoryItem.id < cursor_id,
                    ),
                )
            )
        rows = list(
            db.scalars(
                query.order_by(
                    OperationalMemoryItem.updated_at.desc(), OperationalMemoryItem.id.desc()
                ).limit(limit + 1)
            )
        )
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = self._encode_cursor(last.updated_at, last.id)
        return rows, next_cursor

    def retrieve(
        self,
        db: Session,
        organization_id: UUID,
        payload: MemoryRetrieveRequest,
    ) -> MemoryRetrieveRead:
        started = perf_counter()
        organization = self._organization(db, organization_id)
        self._validate_subject_pair(payload.category, payload.subject_kind)
        normalized = normalize_subject(payload.subject)
        signature = context_signature(
            payload.source_system_family,
            payload.canonical_domain,
            payload.context,
            organization.industry,
        )
        request_fingerprint = _sha(
            {
                "operation": "retrieve",
                "organization_id": str(organization_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        prior_events = list(
            db.scalars(
                select(OperationalMemoryReuseEvent)
                .where(
                    OperationalMemoryReuseEvent.organization_id == organization_id,
                    OperationalMemoryReuseEvent.consumer_code == RETRIEVAL_CONSUMER,
                    OperationalMemoryReuseEvent.idempotency_key == payload.idempotency_key,
                )
                .order_by(OperationalMemoryReuseEvent.event_sequence)
            )
        )
        if prior_events:
            if any(event.request_fingerprint != request_fingerprint for event in prior_events):
                _fail("IDEMPOTENCY_CONFLICT", "Idempotency key was reused", 409)
            return self._replay_retrieval(db, request_fingerprint, prior_events)

        items = list(
            db.scalars(
                select(OperationalMemoryItem)
                .where(
                    OperationalMemoryItem.organization_id == organization_id,
                    OperationalMemoryItem.category == payload.category,
                    OperationalMemoryItem.normalized_subject == normalized,
                    OperationalMemoryItem.current_status.in_(_REUSABLE),
                )
                .limit(20)
            )
        )
        candidates: list[tuple[OperationalMemoryItem, OperationalMemoryVersion, list[str]]] = []
        now = utc_now()
        for item in items:
            version = self._current_version(db, item)
            self._refresh_staleness(db, item, version, now)
            if item.is_stale or item.valid_to is not None and item.valid_to <= now:
                continue
            reasons = ["exact_category", "exact_normalized_subject", "tenant_scope"]
            if item.context_signature == signature:
                reasons.append("exact_context_signature")
            if item.source_system_family == payload.source_system_family:
                reasons.append("exact_source_system_family")
            if item.canonical_domain == payload.canonical_domain:
                reasons.append("exact_canonical_domain")
            candidates.append((item, version, reasons))
        candidates.sort(key=lambda row: self._ranking_key(row, signature, payload))
        selected = candidates[: payload.max_suggestions]
        latency = max(0, int((perf_counter() - started) * 1000))
        suggestions: list[MemorySuggestionRead] = []
        if selected:
            for sequence, (item, version, reasons) in enumerate(selected, start=1):
                suggestion = self._suggestion(item, version, reasons, sequence)
                suggestions.append(suggestion)
                db.add(
                    OperationalMemoryReuseEvent(
                        organization_id=organization_id,
                        memory_id=item.id,
                        memory_version_id=version.id,
                        event_type="RETRIEVED",
                        consumer_code=RETRIEVAL_CONSUMER,
                        consumer_version=RETRIEVAL_VERSION,
                        context_fingerprint=signature,
                        rank=sequence,
                        event_sequence=sequence,
                        suggestion_count=len(selected),
                        match_reasons=reasons,
                        retrieval_latency_ms=latency,
                        idempotency_key=payload.idempotency_key,
                        request_fingerprint=request_fingerprint,
                        correlation_id=payload.correlation_id,
                        occurred_at=now,
                    )
                )
        else:
            db.add(
                OperationalMemoryReuseEvent(
                    organization_id=organization_id,
                    memory_id=None,
                    memory_version_id=None,
                    event_type="NO_MATCH",
                    consumer_code=RETRIEVAL_CONSUMER,
                    consumer_version=RETRIEVAL_VERSION,
                    context_fingerprint=signature,
                    rank=None,
                    event_sequence=1,
                    suggestion_count=0,
                    match_reasons=[],
                    retrieval_latency_ms=latency,
                    idempotency_key=payload.idempotency_key,
                    request_fingerprint=request_fingerprint,
                    correlation_id=payload.correlation_id,
                    occurred_at=now,
                )
            )
        db.commit()
        return MemoryRetrieveRead(
            request_fingerprint=request_fingerprint,
            evaluated_count=len(candidates),
            suggestions=suggestions,
        )

    @staticmethod
    def _validate_subject_pair(category: str, subject_kind: str) -> None:
        if _SUBJECTS.get(category) != subject_kind:
            _fail("CATEGORY_SUBJECT_MISMATCH", "Category and subject kind are incompatible")

    @staticmethod
    def _validate_payload(category: str, payload: dict[str, object]) -> dict[str, object]:
        model = _PAYLOAD_MODELS.get(category)
        if model is None:
            _fail("CATEGORY_INVALID", "Unsupported operational-memory category")
        try:
            validated = model.model_validate(payload).model_dump(mode="json")
            return cast(dict[str, object], validated)
        except ValidationError as exc:
            raise OperationalMemoryServiceError(
                "CATEGORY_PAYLOAD_INVALID", "Category payload is invalid", 422
            ) from exc

    def _validate_provenance(
        self,
        db: Session,
        organization_id: UUID,
        payload: MemoryCandidateCreate,
        value_payload: dict[str, object],
    ) -> None:
        provenance = payload.provenance
        if provenance.source_schema_id is None and provenance.mapping_record_result_id is None:
            _fail("PROVENANCE_REQUIRED", "Governed mapping provenance is required")
        if provenance.source_schema_id is not None:
            source_schema = db.scalar(
                select(SourceSchema).where(
                    SourceSchema.id == provenance.source_schema_id,
                    SourceSchema.organization_id == organization_id,
                )
            )
            if source_schema is None:
                _fail("PROVENANCE_NOT_FOUND", "Source schema is outside tenant scope", 404)
        if provenance.mapping_record_result_id is not None:
            mapping_result = db.scalar(
                select(MappingRecordResult).where(
                    MappingRecordResult.id == provenance.mapping_record_result_id,
                    MappingRecordResult.organization_id == organization_id,
                )
            )
            if mapping_result is None:
                _fail("PROVENANCE_NOT_FOUND", "Mapping result is outside tenant scope", 404)
        if provenance.mapping_review_id is not None:
            mapping_review = db.scalar(
                select(MappingReview).where(
                    MappingReview.id == provenance.mapping_review_id,
                    MappingReview.organization_id == organization_id,
                )
            )
            if mapping_review is None:
                _fail("PROVENANCE_NOT_FOUND", "Mapping review is outside tenant scope", 404)
        if provenance.mapping_template_version_id is not None:
            template_version = db.scalar(
                select(MappingTemplateVersion)
                .join(MappingTemplate, MappingTemplate.id == MappingTemplateVersion.template_id)
                .where(MappingTemplateVersion.id == provenance.mapping_template_version_id)
            )
            if template_version is None:
                _fail("PROVENANCE_NOT_FOUND", "Mapping version was not found", 404)
            template = db.get(MappingTemplate, template_version.template_id)
            if template is None or (
                template.scope_type == "organization"
                and template.owner_organization_id != organization_id
            ):
                _fail("PROVENANCE_NOT_FOUND", "Mapping version is outside tenant scope", 404)
        canonical_ids = set(provenance.canonical_field_definition_ids)
        field_id = value_payload.get("canonical_field_definition_id")
        if field_id:
            canonical_ids.add(UUID(str(field_id)))
        for canonical_id in canonical_ids:
            self._validate_canonical_field(db, organization_id, canonical_id)

    @staticmethod
    def _validate_canonical_field(db: Session, organization_id: UUID, canonical_id: UUID) -> None:
        field = db.get(CanonicalFieldDefinition, canonical_id)
        if field is None:
            _fail("CANONICAL_FIELD_NOT_FOUND", "Canonical field was not found", 404)
        owner: CanonicalEntityType | CanonicalEventType | CanonicalMetricType | None
        if field.canonical_type_kind == "entity":
            owner = db.get(CanonicalEntityType, field.canonical_type_id)
        elif field.canonical_type_kind == "event":
            owner = db.get(CanonicalEventType, field.canonical_type_id)
        else:
            owner = db.get(CanonicalMetricType, field.canonical_type_id)
        if owner is None or (
            owner.scope_type == "organization" and owner.owner_organization_id != organization_id
        ):
            _fail("CANONICAL_FIELD_NOT_FOUND", "Canonical field is outside tenant scope", 404)

    @staticmethod
    def _organization(db: Session, organization_id: UUID) -> Organization:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            _fail("ORGANIZATION_NOT_FOUND", "Organization is unavailable", 404)
        return organization

    @staticmethod
    def _item(db: Session, organization_id: UUID, memory_id: UUID) -> OperationalMemoryItem:
        item = db.scalar(
            select(OperationalMemoryItem).where(
                OperationalMemoryItem.organization_id == organization_id,
                OperationalMemoryItem.id == memory_id,
            )
        )
        if item is None:
            _fail("MEMORY_NOT_FOUND", "Operational memory not found", 404)
        return item

    @staticmethod
    def _current_version(db: Session, item: OperationalMemoryItem) -> OperationalMemoryVersion:
        version = db.scalar(
            select(OperationalMemoryVersion).where(
                OperationalMemoryVersion.organization_id == item.organization_id,
                OperationalMemoryVersion.memory_id == item.id,
                OperationalMemoryVersion.version_number == item.current_version_number,
            )
        )
        if version is None or version.status != item.current_status:
            _fail("MEMORY_PROJECTION_INVALID", "Operational memory projection is inconsistent", 409)
        return version

    @staticmethod
    def _idempotent_version(
        db: Session, organization_id: UUID, key: str, fingerprint: str
    ) -> OperationalMemoryVersion | None:
        existing = db.scalar(
            select(OperationalMemoryVersion).where(
                OperationalMemoryVersion.organization_id == organization_id,
                OperationalMemoryVersion.idempotency_key == key,
            )
        )
        if existing is not None and existing.request_fingerprint != fingerprint:
            _fail("IDEMPOTENCY_CONFLICT", "Idempotency key was reused", 409)
        return existing

    @staticmethod
    def _new_version(
        *,
        item: OperationalMemoryItem,
        version_number: int,
        prior: OperationalMemoryVersion | None,
        status: str,
        value_payload: dict[str, object],
        provenance: dict[str, object],
        source_schema_id: UUID | None,
        mapping_record_result_id: UUID | None,
        source_fingerprint: str,
        request_fingerprint: str,
        idempotency_key: str,
        actor_user_id: UUID | None,
        actor_role: str,
        effective_from: datetime,
        decision_reason_code: str | None = None,
        human_confirmed: bool = False,
    ) -> OperationalMemoryVersion:
        content = {
            "memory_id": str(item.id),
            "version_number": version_number,
            "status": status,
            "value_payload": value_payload,
            "provenance": provenance,
            "source_fingerprint": source_fingerprint,
            "context_fingerprint": item.context_signature,
            "decision_reason_code": decision_reason_code,
        }
        return OperationalMemoryVersion(
            organization_id=item.organization_id,
            memory_id=item.id,
            version_number=version_number,
            supersedes_version_id=prior.id if prior else None,
            status=status,
            assertion_kind=_ASSERTIONS[item.category],
            value_payload=value_payload,
            source_schema_id=source_schema_id,
            mapping_record_result_id=mapping_record_result_id,
            source_fingerprint=source_fingerprint,
            context_fingerprint=item.context_signature,
            provenance_snapshot=provenance,
            confidence_label="HUMAN_CONFIRMED" if human_confirmed else "UNASSESSED",
            confidence_method_code="governed_human_confirmation" if human_confirmed else None,
            confidence_method_version="1.0" if human_confirmed else None,
            decision_reason_code=decision_reason_code,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            effective_from=effective_from,
            content_hash=_sha(content),
            created_at=effective_from,
        )

    @staticmethod
    def _decision_status(current: str, action: str) -> str:
        transitions = {
            ("OBSERVED", "CONFIRM"): "CONFIRMED",
            ("OBSERVED", "REJECT"): "REJECTED",
            ("CONFIRMED", "CORRECT"): "CORRECTED",
            ("CONFIRMED", "DEPRECATE"): "DEPRECATED",
            ("CORRECTED", "CORRECT"): "CORRECTED",
            ("CORRECTED", "DEPRECATE"): "DEPRECATED",
            ("AMBIGUOUS", "CORRECT"): "CORRECTED",
            ("AMBIGUOUS", "REJECT"): "REJECTED",
        }
        status = transitions.get((current, action))
        if status is None:
            _fail("INVALID_MEMORY_TRANSITION", "Operational-memory transition is invalid", 409)
        return status

    @staticmethod
    def _clear_stale(item: OperationalMemoryItem) -> None:
        item.is_stale = False
        item.stale_reason_code = None
        item.stale_detected_at = None

    def _refresh_staleness(
        self,
        db: Session,
        item: OperationalMemoryItem,
        version: OperationalMemoryVersion,
        now: datetime,
    ) -> None:
        reason = None
        if item.valid_to is not None and item.valid_to <= now:
            reason = "VALIDITY_EXPIRED"
        elif item.current_status == "AMBIGUOUS":
            reason = "CONTRADICTORY_EVIDENCE"
        elif version.source_schema_id is not None:
            schema = db.get(SourceSchema, version.source_schema_id)
            if schema is None or schema.status in {"changed", "incompatible"}:
                reason = "SCHEMA_CHANGED"
        template_id = version.provenance_snapshot.get("mapping_template_version_id")
        if reason is None and template_id:
            template_version = db.get(MappingTemplateVersion, UUID(str(template_id)))
            if template_version is None or template_version.lifecycle_status in {
                "deprecated",
                "retired",
            }:
                reason = "MAPPING_VERSION_RETIRED"
        raw_canonical_ids = version.provenance_snapshot.get("canonical_field_definition_ids", [])
        canonical_ids = raw_canonical_ids if isinstance(raw_canonical_ids, list) else []
        if reason is None:
            for identifier in canonical_ids:
                try:
                    self._validate_canonical_field(db, item.organization_id, UUID(str(identifier)))
                except OperationalMemoryServiceError:
                    reason = "CANONICAL_DEFINITION_INCOMPATIBLE"
                    break
        if reason:
            item.is_stale = True
            item.stale_reason_code = reason
            item.stale_detected_at = item.stale_detected_at or now
        elif item.stale_reason_code != "CONTRADICTORY_EVIDENCE":
            self._clear_stale(item)
        item.last_validated_at = now

    @staticmethod
    def _ranking_key(
        row: tuple[OperationalMemoryItem, OperationalMemoryVersion, Sequence[str]],
        signature: str,
        payload: MemoryRetrieveRequest,
    ) -> tuple[object, ...]:
        item, version, _ = row
        schema = str(version.value_payload.get("schema_fingerprint", "")).casefold()
        requested_schema = (payload.context.schema_fingerprint or "").casefold()
        timestamp = item.last_confirmed_at or item.last_validated_at or item.created_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return (
            item.context_signature != signature,
            item.source_system_family != payload.source_system_family,
            schema != requested_schema,
            item.canonical_domain != payload.canonical_domain,
            -timestamp.timestamp(),
            -item.confirmation_count,
            -item.support_count,
            str(item.id),
        )

    @staticmethod
    def _suggestion(
        item: OperationalMemoryItem,
        version: OperationalMemoryVersion,
        reasons: Sequence[str],
        rank: int,
    ) -> MemorySuggestionRead:
        dimensions = [
            reason.removeprefix("exact_") for reason in reasons if reason.startswith("exact_")
        ]
        provenance = {
            key: value
            for key, value in version.provenance_snapshot.items()
            if key
            in {
                "source_schema_id",
                "mapping_record_result_id",
                "mapping_review_id",
                "mapping_template_version_id",
                "canonical_field_definition_ids",
                "source_content_hashes",
                "raw_data_included",
            }
        }
        return MemorySuggestionRead(
            memory_id=item.id,
            version_id=version.id,
            category=item.category,
            status=item.current_status,
            normalized_subject=item.normalized_subject,
            matched_context_dimensions=dimensions,
            match_reasons=list(reasons),
            last_confirmed_at=item.last_confirmed_at,
            last_validated_at=item.last_validated_at,
            actor_class="system" if version.actor_user_id is None else version.actor_role,
            stale=item.is_stale,
            ambiguous=item.current_status == "AMBIGUOUS",
            provenance_references=provenance,
            interpreted_payload=version.value_payload,
            rank=rank,
        )

    def _replay_retrieval(
        self,
        db: Session,
        request_fingerprint: str,
        events: Sequence[OperationalMemoryReuseEvent],
    ) -> MemoryRetrieveRead:
        if events[0].event_type == "NO_MATCH":
            return MemoryRetrieveRead(
                request_fingerprint=request_fingerprint, evaluated_count=0, suggestions=[]
            )
        suggestions = []
        for event in events:
            assert event.memory_id is not None and event.memory_version_id is not None
            item = self._item(db, event.organization_id, event.memory_id)
            version = db.get(OperationalMemoryVersion, event.memory_version_id)
            if version is None or version.organization_id != event.organization_id:
                _fail("MEMORY_PROJECTION_INVALID", "Retrieval history is inconsistent", 409)
            suggestions.append(
                self._suggestion(
                    item, version, [str(v) for v in event.match_reasons], event.rank or 1
                )
            )
        return MemoryRetrieveRead(
            request_fingerprint=request_fingerprint,
            evaluated_count=len(suggestions),
            suggestions=suggestions,
        )

    @staticmethod
    def _encode_cursor(updated_at: datetime, identifier: UUID) -> str:
        raw = _canonical_json({"updated_at": updated_at.isoformat(), "id": str(identifier)})
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            value = json.loads(raw)
            return datetime.fromisoformat(value["updated_at"]), UUID(value["id"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise OperationalMemoryServiceError("CURSOR_INVALID", "Cursor is invalid", 422) from exc


operational_memory_service = OperationalMemoryService()
