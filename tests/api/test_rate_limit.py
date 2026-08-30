import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.config import settings

@pytest.mark.xfail(reason="Rate limiter removed from middleware stack (commit e809b63). Dead code — needs re-implementation with per-user keying.")
def test_rate_limit(client):
    from app.middleware.rate_limit import limiter
    limiter.enabled = True
    # Reset storage for this test to ensure it starts fresh
    limiter._storage.reset()
    # 1. Register User
    client.post("/api/v1/auth/register", json={"username": "rl_user", "email": "rl_user@test.com", "password": "password123"})
    login_res = client.post("/api/v1/auth/login", json={"email": "rl_user@test.com", "password": "password123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Hit the endpoint 10 times (should succeed)
    for i in range(10):
        res = client.post("/api/v1/urls", json={"original_url": f"https://example.com/{i}"}, headers=headers)
        assert res.status_code == 201

    # 3. Hit the endpoint the 11th time (should fail with 429)
    res_429 = client.post("/api/v1/urls", json={"original_url": "https://example.com/11"}, headers=headers)
    assert res_429.status_code == 429
    assert "Retry-After" in res_429.headers
    
    print("Rate limit verified successfully!")
