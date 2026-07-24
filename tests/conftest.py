from collections.abc import Generator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.identity import AuthenticatedUser, get_current_user
from app.db.session import Base, get_db
from app.main import app


@dataclass
class IdentityState:
    user_id: UUID | None
    is_platform_admin: bool = False

    def authenticate(self) -> AuthenticatedUser:
        if self.user_id is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return AuthenticatedUser(
            user_id=self.user_id,
            is_platform_admin=self.is_platform_admin,
        )


@pytest.fixture
def db_engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def identity() -> IdentityState:
    return IdentityState(user_id=uuid4(), is_platform_admin=True)


@pytest.fixture
def client(db_engine: Engine, identity: IdentityState) -> Generator[TestClient, None, None]:
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = identity.authenticate
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
