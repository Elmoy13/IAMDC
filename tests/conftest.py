import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.middleware.auth import get_current_user, get_user_agency
from main import app

# Use an in-memory SQLite for tests (swap for a test Postgres if preferred)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)

FAKE_USER_ID = str(uuid.uuid4())
FAKE_AGENCY_ID = str(uuid.uuid4())


def _fake_current_user() -> dict:
    return {
        "user_id": FAKE_USER_ID,
        "email": "test@test.com",
        "jwt_token": "fake-token",
        "jwt_alg": "HS256",
    }


def _fake_user_agency() -> dict:
    return {
        "agency_id": FAKE_AGENCY_ID,
        "agency_name": "Test Agency",
        "role": "admin",
        "user_id": FAKE_USER_ID,
        "jwt_token": "fake-token",
    }


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_test() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[get_user_agency] = _fake_user_agency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_auth(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Client without auth overrides — for testing 401 responses."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
