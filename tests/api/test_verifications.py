from sqlalchemy import event

from app.cache.redis_client import redis_client


def test_verification_suite(client, db_session):
    # Setup user
    client.post("/api/v1/auth/register", json={"username": "verify_user", "email": "verify@test.com", "password": "password123"})
    login_res = client.post("/api/v1/auth/login", json={"email": "verify@test.com", "password": "password123"})
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

    # Track SQL queries
    query_count = {"select": 0, "update": 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        stmt = statement.strip().lower()
        if stmt.startswith("select") and "urls" in stmt:
            query_count["select"] += 1
        if stmt.startswith("update") and "urls" in stmt:
            query_count["update"] += 1

    event.listen(db_session.bind, "before_cursor_execute", before_cursor_execute)

    # First request: Cache miss, should SELECT urls (but no UPDATE — clicks go to Redis)
    res1 = client.get(f"/{short_code}", follow_redirects=False)
    assert res1.status_code == 302
    assert query_count["select"] > 0

    # Verify click was buffered in Redis
    assert int(redis_client.get(f"clicks:count:{short_code}") or 0) >= 1

    # Reset counts
    query_count["select"] = 0
    query_count["update"] = 0

    # Second request: Cache hit, should NOT SELECT or UPDATE Postgres — clicks go to Redis
    res2 = client.get(f"/{short_code}", follow_redirects=False)
    assert res2.status_code == 302
    assert query_count["select"] == 0, "A SELECT query was executed on a cache hit!"
    assert query_count["update"] == 0, "An UPDATE query was executed — clicks should go to Redis, not Postgres!"

    # Verify click was buffered in Redis (counter incremented)
    assert int(redis_client.get(f"clicks:count:{short_code}") or 0) >= 2

    print("Verification 1 passed: Cache hit does not touch Postgres for SELECT or UPDATE.")

    event.remove(db_session.bind, "before_cursor_execute", before_cursor_execute)

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
