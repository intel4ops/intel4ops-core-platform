from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.knowledge_pack import (
    KnowledgePack,
    KnowledgePackAuditEvent,
    KnowledgePackLearningLink,
    KnowledgePackVersion,
)
from app.models.learning import OperationalLearning
from app.schemas.knowledge_pack import (
    KnowledgePackAuditRead,
    KnowledgePackCreate,
    KnowledgePackLearningAdd,
    KnowledgePackMemberRead,
    KnowledgePackPage,
    KnowledgePackRead,
    KnowledgePackVersionCreate,
    KnowledgePackVersionRead,
)
from app.services.learning_service import learning_service


class KnowledgePackServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class KnowledgePackService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: KnowledgePackCreate,
        actor_id: UUID,
        actor_role: str,
    ) -> KnowledgePackRead:
        pack = KnowledgePack(
            organization_id=organization_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            industry=payload.industry,
            domain=payload.domain,
            scope=payload.scope,
            created_by_user_id=actor_id,
        )
        db.add(pack)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise KnowledgePackServiceError(
                "KNOWLEDGE_PACK_SLUG_EXISTS", "Knowledge Pack slug already exists"
            ) from exc
        version = KnowledgePackVersion(
            organization_id=organization_id,
            knowledge_pack_id=pack.id,
            version_number=1,
            lifecycle_status="draft",
            change_summary=payload.change_summary,
            created_by_user_id=actor_id,
        )
        db.add(version)
        db.flush()
        db.add(self._audit(db, pack, version, "pack_created", None, "draft", actor_id, actor_role))
        # Flush explicitly so the pack_created row (and its assigned sequence) is durably
        # visible before version_created's sequence is computed -- this makes the ordering
        # airtight rather than depending on autoflush batching behavior.
        db.flush()
        db.add(
            self._audit(
                db=db,
                version=version,
                pack=pack,
                event="version_created",
                prior=None,
                target="draft",
                actor=actor_id,
                role=actor_role,
            )
        )
        db.commit()
        return self.get(db, organization_id, pack.id)

    def create_version(
        self,
        db: Session,
        organization_id: UUID,
        pack_id: UUID,
        payload: KnowledgePackVersionCreate,
        actor_id: UUID,
        actor_role: str,
    ) -> KnowledgePackRead:
        pack = self._pack(db, organization_id, pack_id, lock=True)
        versions = self._versions(db, organization_id, pack_id)
        if any(row.lifecycle_status in {"draft", "in_review"} for row in versions):
            raise KnowledgePackServiceError(
                "EDITABLE_VERSION_EXISTS", "A draft or review version already exists"
            )
        approved = next((row for row in versions if row.lifecycle_status == "approved"), None)
        if approved is None:
            raise KnowledgePackServiceError(
                "APPROVED_VERSION_REQUIRED", "Approve the first version before creating another"
            )
        version = KnowledgePackVersion(
            organization_id=organization_id,
            knowledge_pack_id=pack_id,
            version_number=max(row.version_number for row in versions) + 1,
            lifecycle_status="draft",
            change_summary=payload.change_summary,
            provenance_summary=approved.provenance_summary,
            created_by_user_id=actor_id,
        )
        db.add(version)
        db.flush()
        for link in self._links(db, organization_id, approved.id):
            db.add(
                KnowledgePackLearningLink(
                    organization_id=organization_id,
                    knowledge_pack_version_id=version.id,
                    operational_learning_id=link.operational_learning_id,
                    inclusion_rationale=link.inclusion_rationale,
                )
            )
        db.add(
            self._audit(db, pack, version, "version_created", None, "draft", actor_id, actor_role)
        )
        db.commit()
        return self.get(db, organization_id, pack_id)

    def add_learning(
        self,
        db: Session,
        organization_id: UUID,
        pack_id: UUID,
        version_id: UUID,
        payload: KnowledgePackLearningAdd,
        actor_id: UUID,
        actor_role: str,
    ) -> KnowledgePackVersionRead:
        pack = self._pack(db, organization_id, pack_id, lock=True)
        version = self._version(db, organization_id, pack_id, version_id)
        self._editable(version)
        learning = self._eligible_learning(db, organization_id, payload.learning_id)
        existing = db.scalar(
            select(KnowledgePackLearningLink).where(
                KnowledgePackLearningLink.organization_id == organization_id,
                KnowledgePackLearningLink.knowledge_pack_version_id == version_id,
                KnowledgePackLearningLink.operational_learning_id == learning.id,
            )
        )
        if existing is not None:
            raise KnowledgePackServiceError(
                "LEARNING_ALREADY_INCLUDED", "Learning is already included"
            )
        db.add(
            KnowledgePackLearningLink(
                organization_id=organization_id,
                knowledge_pack_version_id=version_id,
                operational_learning_id=learning.id,
                inclusion_rationale=payload.inclusion_rationale,
            )
        )
        db.flush()
        self._refresh_provenance(db, organization_id, version)
        db.add(
            self._audit(
                db,
                pack,
                version,
                "learning_added",
                version.lifecycle_status,
                version.lifecycle_status,
                actor_id,
                actor_role,
                metadata={"learning_id": str(learning.id)},
            )
        )
        db.commit()
        return self.get_version(db, organization_id, pack_id, version_id)

    def remove_learning(
        self,
        db: Session,
        organization_id: UUID,
        pack_id: UUID,
        version_id: UUID,
        learning_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> KnowledgePackVersionRead:
        pack = self._pack(db, organization_id, pack_id, lock=True)
        version = self._version(db, organization_id, pack_id, version_id)
        self._editable(version)
        link = db.scalar(
            select(KnowledgePackLearningLink).where(
                KnowledgePackLearningLink.organization_id == organization_id,
                KnowledgePackLearningLink.knowledge_pack_version_id == version_id,
                KnowledgePackLearningLink.operational_learning_id == learning_id,
            )
        )
        if link is None:
            raise KnowledgePackServiceError(
                "PACK_LEARNING_NOT_FOUND", "Pack Learning not found", 404
            )
        db.delete(link)
        db.flush()
        self._refresh_provenance(db, organization_id, version)
        db.add(
            self._audit(
                db,
                pack,
                version,
                "learning_removed",
                version.lifecycle_status,
                version.lifecycle_status,
                actor_id,
                actor_role,
                metadata={"learning_id": str(learning_id)},
            )
        )
        db.commit()
        return self.get_version(db, organization_id, pack_id, version_id)

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        pack_id: UUID,
        version_id: UUID,
        command: str,
        rationale: str,
        actor_id: UUID,
        actor_role: str,
    ) -> KnowledgePackRead:
        pack = self._pack(db, organization_id, pack_id, lock=True)
        version = self._version(db, organization_id, pack_id, version_id)
        transitions = {
            ("draft", "submit"): "in_review",
            ("in_review", "approve"): "approved",
            ("in_review", "reject"): "rejected",
            ("approved", "retire"): "retired",
        }
        target = transitions.get((version.lifecycle_status, command))
        if target is None:
            raise KnowledgePackServiceError(
                "INVALID_PACK_TRANSITION",
                f"Cannot {command} a {version.lifecycle_status} Knowledge Pack version",
            )
        if command in {"submit", "approve"}:
            self._validate_members(db, organization_id, version)
        now = datetime.now(UTC)
        prior = version.lifecycle_status
        if command == "approve":
            previous = db.scalar(
                select(KnowledgePackVersion).where(
                    KnowledgePackVersion.organization_id == organization_id,
                    KnowledgePackVersion.knowledge_pack_id == pack_id,
                    KnowledgePackVersion.lifecycle_status == "approved",
                    KnowledgePackVersion.id != version.id,
                )
            )
            if previous is not None:
                previous.lifecycle_status = "superseded"
                previous.superseded_at = now
                db.add(
                    self._audit(
                        db,
                        pack,
                        previous,
                        "version_superseded",
                        "approved",
                        "superseded",
                        actor_id,
                        actor_role,
                        rationale,
                        {"superseded_by_version_id": str(version.id)},
                    )
                )
                # Flush so version_superseded's sequence is durably assigned before the
                # transition event below computes its own -- same rationale as create().
                db.flush()
            version.approved_by_user_id = actor_id
            version.approved_at = now
        if command in {"submit", "approve", "reject"}:
            version.reviewed_by_user_id = actor_id
            version.reviewed_at = now
        if command == "retire":
            version.retired_at = now
        version.lifecycle_status = target
        db.add(
            self._audit(db, pack, version, command, prior, target, actor_id, actor_role, rationale)
        )
        db.commit()
        return self.get(db, organization_id, pack_id)

    def list_packs(
        self,
        db: Session,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        lifecycle: str | None = None,
        provenance: str | None = None,
        industry: str | None = None,
        domain: str | None = None,
    ) -> KnowledgePackPage:
        query = select(KnowledgePack).where(KnowledgePack.organization_id == organization_id)
        if industry:
            query = query.where(KnowledgePack.industry == industry)
        if domain:
            query = query.where(KnowledgePack.domain == domain)
        if lifecycle or provenance:
            version_filter = select(KnowledgePackVersion.knowledge_pack_id).where(
                KnowledgePackVersion.organization_id == organization_id
            )
            if lifecycle:
                version_filter = version_filter.where(
                    KnowledgePackVersion.lifecycle_status == lifecycle
                )
            if provenance:
                version_filter = version_filter.where(
                    KnowledgePackVersion.provenance_summary == provenance
                )
            query = query.where(KnowledgePack.id.in_(version_filter))
        total = int(
            db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
        )
        packs = list(
            db.scalars(
                query.order_by(KnowledgePack.updated_at.desc(), KnowledgePack.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return KnowledgePackPage(
            items=self._reads(db, organization_id, packs),
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, db: Session, organization_id: UUID, pack_id: UUID) -> KnowledgePackRead:
        return self._reads(db, organization_id, [self._pack(db, organization_id, pack_id)])[0]

    def get_version(
        self, db: Session, organization_id: UUID, pack_id: UUID, version_id: UUID
    ) -> KnowledgePackVersionRead:
        self._pack(db, organization_id, pack_id)
        version = self._version(db, organization_id, pack_id, version_id)
        return self._version_reads(db, organization_id, [version])[0]

    def _reads(
        self, db: Session, organization_id: UUID, packs: list[KnowledgePack]
    ) -> list[KnowledgePackRead]:
        if not packs:
            return []
        pack_ids = [pack.id for pack in packs]
        versions = list(
            db.scalars(
                select(KnowledgePackVersion)
                .where(
                    KnowledgePackVersion.organization_id == organization_id,
                    KnowledgePackVersion.knowledge_pack_id.in_(pack_ids),
                )
                .order_by(KnowledgePackVersion.version_number.desc())
            )
        )
        version_reads = {
            row.id: read
            for row, read in zip(
                versions, self._version_reads(db, organization_id, versions), strict=True
            )
        }
        audits = list(
            db.scalars(
                select(KnowledgePackAuditEvent)
                .where(
                    KnowledgePackAuditEvent.organization_id == organization_id,
                    KnowledgePackAuditEvent.knowledge_pack_id.in_(pack_ids),
                )
                .order_by(
                    KnowledgePackAuditEvent.knowledge_pack_id, KnowledgePackAuditEvent.sequence
                )
            )
        )
        return [
            KnowledgePackRead(
                id=pack.id,
                organization_id=pack.organization_id,
                name=pack.name,
                slug=pack.slug,
                description=pack.description,
                industry=pack.industry,
                domain=pack.domain,
                scope=pack.scope,
                created_by_user_id=pack.created_by_user_id,
                created_at=pack.created_at,
                updated_at=pack.updated_at,
                current_approved_version=next(
                    (
                        version_reads[v.id]
                        for v in versions
                        if v.knowledge_pack_id == pack.id and v.lifecycle_status == "approved"
                    ),
                    None,
                ),
                latest_draft_version=next(
                    (
                        version_reads[v.id]
                        for v in versions
                        if v.knowledge_pack_id == pack.id
                        and v.lifecycle_status in {"draft", "in_review"}
                    ),
                    None,
                ),
                versions=[version_reads[v.id] for v in versions if v.knowledge_pack_id == pack.id],
                audit_history=[
                    KnowledgePackAuditRead.model_validate(a)
                    for a in audits
                    if a.knowledge_pack_id == pack.id
                ],
            )
            for pack in packs
        ]

    def _version_reads(
        self, db: Session, organization_id: UUID, versions: list[KnowledgePackVersion]
    ) -> list[KnowledgePackVersionRead]:
        if not versions:
            return []
        version_ids = [version.id for version in versions]
        links = list(
            db.scalars(
                select(KnowledgePackLearningLink).where(
                    KnowledgePackLearningLink.organization_id == organization_id,
                    KnowledgePackLearningLink.knowledge_pack_version_id.in_(version_ids),
                )
            )
        )
        learning_ids = list({link.operational_learning_id for link in links})
        learnings = (
            list(
                db.scalars(
                    select(OperationalLearning).where(
                        OperationalLearning.organization_id == organization_id,
                        OperationalLearning.id.in_(learning_ids),
                    )
                )
            )
            if learning_ids
            else []
        )
        learning_reads = {
            row.id: read
            for row, read in zip(
                learnings, learning_service._reads(db, organization_id, learnings), strict=True
            )
        }
        return [
            KnowledgePackVersionRead(
                id=version.id,
                organization_id=version.organization_id,
                knowledge_pack_id=version.knowledge_pack_id,
                version_number=version.version_number,
                lifecycle_status=version.lifecycle_status,
                change_summary=version.change_summary,
                provenance_summary=version.provenance_summary,
                created_by_user_id=version.created_by_user_id,
                reviewed_by_user_id=version.reviewed_by_user_id,
                approved_by_user_id=version.approved_by_user_id,
                created_at=version.created_at,
                reviewed_at=version.reviewed_at,
                approved_at=version.approved_at,
                superseded_at=version.superseded_at,
                retired_at=version.retired_at,
                members=[
                    KnowledgePackMemberRead(
                        learning=learning_reads[link.operational_learning_id],
                        inclusion_rationale=link.inclusion_rationale,
                        created_at=link.created_at,
                    )
                    for link in links
                    if link.knowledge_pack_version_id == version.id
                ],
            )
            for version in versions
        ]

    def _validate_members(
        self, db: Session, organization_id: UUID, version: KnowledgePackVersion
    ) -> None:
        links = self._links(db, organization_id, version.id)
        if not links:
            raise KnowledgePackServiceError(
                "PACK_MEMBERSHIP_REQUIRED", "A Knowledge Pack version requires approved Learning"
            )
        for link in links:
            self._eligible_learning(db, organization_id, link.operational_learning_id)
        self._refresh_provenance(db, organization_id, version)

    @staticmethod
    def _refresh_provenance(
        db: Session, organization_id: UUID, version: KnowledgePackVersion
    ) -> None:
        provenances = list(
            db.scalars(
                select(OperationalLearning.provenance_type)
                .join(
                    KnowledgePackLearningLink,
                    KnowledgePackLearningLink.operational_learning_id == OperationalLearning.id,
                )
                .where(
                    KnowledgePackLearningLink.organization_id == organization_id,
                    KnowledgePackLearningLink.knowledge_pack_version_id == version.id,
                    OperationalLearning.organization_id == organization_id,
                )
            )
        )
        version.provenance_summary = (
            None if not provenances else provenances[0] if len(set(provenances)) == 1 else "mixed"
        )

    @staticmethod
    def _eligible_learning(
        db: Session, organization_id: UUID, learning_id: UUID
    ) -> OperationalLearning:
        learning = db.scalar(
            select(OperationalLearning).where(
                OperationalLearning.organization_id == organization_id,
                OperationalLearning.id == learning_id,
            )
        )
        if learning is None:
            raise KnowledgePackServiceError("LEARNING_NOT_FOUND", "Learning not found", 404)
        if learning.status != "approved_for_reuse":
            raise KnowledgePackServiceError(
                "LEARNING_NOT_ELIGIBLE", "Only Learning approved for reuse may enter a pack"
            )
        return learning

    @staticmethod
    def _editable(version: KnowledgePackVersion) -> None:
        if version.lifecycle_status != "draft":
            raise KnowledgePackServiceError(
                "PACK_VERSION_IMMUTABLE", "Only draft Knowledge Pack versions are editable"
            )

    @staticmethod
    def _pack(
        db: Session, organization_id: UUID, pack_id: UUID, *, lock: bool = False
    ) -> KnowledgePack:
        query = select(KnowledgePack).where(
            KnowledgePack.organization_id == organization_id, KnowledgePack.id == pack_id
        )
        if lock:
            query = query.with_for_update()
        pack = db.scalar(query)
        if pack is None:
            raise KnowledgePackServiceError(
                "KNOWLEDGE_PACK_NOT_FOUND", "Knowledge Pack not found", 404
            )
        return pack

    @staticmethod
    def _version(
        db: Session, organization_id: UUID, pack_id: UUID, version_id: UUID
    ) -> KnowledgePackVersion:
        version = db.scalar(
            select(KnowledgePackVersion).where(
                KnowledgePackVersion.organization_id == organization_id,
                KnowledgePackVersion.knowledge_pack_id == pack_id,
                KnowledgePackVersion.id == version_id,
            )
        )
        if version is None:
            raise KnowledgePackServiceError("PACK_VERSION_NOT_FOUND", "Pack version not found", 404)
        return version

    @staticmethod
    def _versions(db: Session, organization_id: UUID, pack_id: UUID) -> list[KnowledgePackVersion]:
        return list(
            db.scalars(
                select(KnowledgePackVersion)
                .where(
                    KnowledgePackVersion.organization_id == organization_id,
                    KnowledgePackVersion.knowledge_pack_id == pack_id,
                )
                .order_by(KnowledgePackVersion.version_number.desc())
            )
        )

    @staticmethod
    def _links(
        db: Session, organization_id: UUID, version_id: UUID
    ) -> list[KnowledgePackLearningLink]:
        return list(
            db.scalars(
                select(KnowledgePackLearningLink).where(
                    KnowledgePackLearningLink.organization_id == organization_id,
                    KnowledgePackLearningLink.knowledge_pack_version_id == version_id,
                )
            )
        )

    @staticmethod
    def _audit(
        db: Session,
        pack: KnowledgePack,
        version: KnowledgePackVersion,
        event: str,
        prior: str | None,
        target: str | None,
        actor: UUID,
        role: str,
        rationale: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgePackAuditEvent:
        # `sequence` is the authoritative read-order key (see the model docstring). It is
        # computed here, under the session's default autoflush, so any audit event already
        # `db.add()`-ed earlier in the same call is visible to this MAX query before this
        # row is constructed -- this is what makes back-to-back audit events within one
        # service call (e.g. create()'s pack_created + version_created) deterministically
        # ordered even when they share an identical `occurred_at` timestamp.
        next_sequence = (
            db.scalar(
                select(func.max(KnowledgePackAuditEvent.sequence)).where(
                    KnowledgePackAuditEvent.organization_id == pack.organization_id,
                    KnowledgePackAuditEvent.knowledge_pack_id == pack.id,
                )
            )
            or 0
        ) + 1
        return KnowledgePackAuditEvent(
            organization_id=pack.organization_id,
            knowledge_pack_id=pack.id,
            knowledge_pack_version_id=version.id,
            event_type=event,
            prior_status=prior,
            new_status=target,
            actor_user_id=actor,
            actor_role=role,
            rationale=rationale,
            metadata_json={"version_number": version.version_number, **(metadata or {})},
            occurred_at=datetime.now(UTC),
            sequence=next_sequence,
        )


knowledge_pack_service = KnowledgePackService()
