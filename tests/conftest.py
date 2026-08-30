import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app
from app.database.session import Base, get_db, get_async_db, async_engine, AsyncSessionLocal
from app.database.config import DATABASE_URL
import app.cache.redis_client as redis_module
import redis.asyncio as aioredis

# Use the same database URL, but we will roll back transactions
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield

@pytest.fixture
def db_session():
    """Returns a sqlalchemy session, and after the test tears down everything inside a transaction"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

from app.middleware.rate_limit import limiter
@pytest.fixture(autouse=True)
def reset_rate_limit():
    # Disable rate limiting globally for tests to prevent 429 errors
    limiter.enabled = False
    yield
    limiter.enabled = True

@pytest.fixture(autouse=True)
def reset_async_redis():
    """Recreate the async Redis client before each test to avoid event loop issues."""
    from app.database.config import settings
    redis_module.async_redis_client = aioredis.from_url(
        settings.redis_url, decode_responses=True,
    )
    yield

@pytest.fixture
def client():
    """Returns a TestClient that uses a fresh async session per request"""
    async def override_get_async_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_async_db] = override_get_async_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture()
def auth_headers_for_two_users(client):
    def register_and_login(username, email):
        client.post("/api/v1/auth/register", json={"username": username, "email": email, "password": "supersecret1"})
        login = client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret1"})
        token = login.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    uid = uuid.uuid4().hex[:8]
    return register_and_login(f"user_a_{uid}", f"a_{uid}@example.com"), register_and_login(f"user_b_{uid}", f"b_{uid}@example.com")
