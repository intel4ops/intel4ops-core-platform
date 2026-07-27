from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial import Entitlement, Subscription


class CommercialRepository:
    def active_subscription(
        self, db: Session, organization_id: UUID, now: datetime
    ) -> Subscription | None:
        return db.scalar(
            select(Subscription)
            .where(
                Subscription.organization_id == organization_id,
                Subscription.status.in_(("active", "trial", "enterprise", "partner")),
                Subscription.starts_at <= now,
                Subscription.current_period_end > now,
            )
            .order_by(Subscription.created_at.desc())
        )

    def active_entitlement(
        self, db: Session, organization_id: UUID, key: str, now: datetime
    ) -> Entitlement | None:
        return db.scalar(
            select(Entitlement)
            .where(
                Entitlement.organization_id == organization_id,
                Entitlement.entitlement_key == key,
                Entitlement.enabled.is_(True),
                Entitlement.effective_at <= now,
                (Entitlement.expires_at.is_(None) | (Entitlement.expires_at > now)),
            )
            .order_by(Entitlement.created_at.desc())
        )


commercial_repository = CommercialRepository()
