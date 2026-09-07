"""AGENTIC-CONTROL-001 Phase N: scoped machine-to-machine authentication
for the Local Worker Bridge. Deliberately separate from
`app.auth.identity`'s Supabase-JWT human-session path -- a local worker
is never a logged-in user and must never be able to reach any endpoint a
human session can reach. Token generation mirrors the existing
invitation-token precedent (`app.services.invitation_service`:
`secrets.token_urlsafe(32)` + a SHA-256 hash at rest; the raw token is
returned once at creation and never stored or logged again)."""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_jobs import AgentWorkerCredential


def hash_worker_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_worker_token() -> str:
    return secrets.token_urlsafe(32)


def require_worker_credential(
    organization_id: UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AgentWorkerCredential:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Worker credential required"
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Worker credential required"
        )
    token_hash = hash_worker_token(token)
    credential = db.scalar(
        select(AgentWorkerCredential).where(
            AgentWorkerCredential.organization_id == organization_id,
            AgentWorkerCredential.token_hash == token_hash,
            AgentWorkerCredential.is_active.is_(True),
        )
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked worker credential"
        )
    return credential
