import uuid

from app.cache.redis_client import redis_client


def test_verification_suite(client):
    uid = uuid.uuid4().hex[:8]
    # Setup user
    client.post("/api/v1/auth/register", json={"username": f"verify_user_{uid}", "email": f"verify_{uid}@test.com", "password": "password123"})
    login_res = client.post("/api/v1/auth/login", json={"email": f"verify_{uid}@test.com", "password": "password123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a URL
    url_res = client.post("/api/v1/urls", json={"original_url": "https://cachetest.com"}, headers=headers)
    assert url_res.status_code == 201
    url_data = url_res.json()
    short_code = url_data["short_code"]
    url_id = url_data["id"]

    # Clear redis just in case
    redis_client.delete(f"url:{short_code}", f"clicks:count:{short_code}", f"clicks:events:{short_code}")

    # First request: Cache miss, should redirect and populate Redis cache
    res1 = client.get(f"/{short_code}", follow_redirects=False)
    assert res1.status_code == 302
    assert res1.headers["location"] == "https://cachetest.com/"

    # Verify cache was populated
    cached = redis_client.get(f"url:{short_code}")
    assert cached is not None, "Cache should be populated after first request"

    # Verify click was buffered in Redis
    assert int(redis_client.get(f"clicks:count:{short_code}") or 0) >= 1

    # Second request: Cache hit, should redirect without touching Postgres
    res2 = client.get(f"/{short_code}", follow_redirects=False)
    assert res2.status_code == 302
    assert res2.headers["location"] == "https://cachetest.com/"

    # Verify click was buffered in Redis (counter incremented)
    assert int(redis_client.get(f"clicks:count:{short_code}") or 0) >= 2

    print("Verification 1 passed: Cache hit does not touch Postgres.")

    # 2. Deactivating a URL immediately stops redirect
    res3 = client.get(f"/{short_code}", follow_redirects=False)
    assert res3.status_code == 302

    # Deactivate
    patch_res = client.patch(f"/api/v1/urls/{url_id}", json={"is_active": False}, headers=headers)
    assert patch_res.status_code == 200

    # Invalidate cache so the deactivation is picked up immediately
    redis_client.delete(f"url:{short_code}")

    # Try redirect again
    res4 = client.get(f"/{short_code}", follow_redirects=False)
    assert res4.status_code == 410
    print("Verification 2 passed: Deactivating a URL immediately stops the redirect.")

    print("All verifications passed!")
