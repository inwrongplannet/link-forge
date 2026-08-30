import requests
import jwt
import time
import uuid

BASE_URL = "http://127.0.0.1:8000"
API_URL = f"{BASE_URL}/api/v1"

def test_flow(client):
    uid = uuid.uuid4().hex[:8]
    print("\n--- 1. Register/login work and return valid JWTs ---")
    user_a = f"usera_{uid}"
    pwd_a = "password123"
    
    r_reg = client.post("/api/v1/auth/register", json={"username": user_a, "email": f"{user_a}@test.com", "password": pwd_a})
    assert r_reg.status_code == 201, f"Failed to register User A: {r_reg.text}"
    user_a_id = r_reg.json()["id"]
    print("User A registered successfully.")
    
    r_log = client.post("/api/v1/auth/login", json={"email": f"{user_a}@test.com", "password": pwd_a})
    assert r_log.status_code == 200, "Failed to login User A"
    access_token_a = r_log.json()["access_token"]
    
    claims = jwt.decode(access_token_a, options={"verify_signature": False})
    print(f"Decoded claims: {claims}")
    assert claims["sub"] == user_a_id, "Subject claim does not match user ID"
    assert claims["type"] == "access", "Token type is not 'access'"
    print("Valid JWT claims sanity-checked.")
    
    print("\n--- 2. An expired or tampered access token is rejected with 401 ---")
    tampered_token = access_token_a[:-5] + "aaaaa"
    r_tampered = client.post("/api/v1/urls", headers={"Authorization": f"Bearer {tampered_token}"}, json={"original_url": "https://example.com"})
    assert r_tampered.status_code == 401, f"Expected 401, got {r_tampered.status_code}"
    print("Tampered token rejected with 401.")
    
    print("\n--- 3. A user cannot PATCH/DELETE another user's URL (403) ---")
    user_b = f"userb_{uid}"
    res_reg_b = client.post("/api/v1/auth/register", json={"username": user_b, "email": f"{user_b}@test.com", "password": "password123"})
    assert res_reg_b.status_code == 201
    res_log_b = client.post("/api/v1/auth/login", json={"email": f"{user_b}@test.com", "password": "password123"})
    access_token_b = res_log_b.json()["access_token"]
    
    r_create = client.post("/api/v1/urls", headers={"Authorization": f"Bearer {access_token_a}"}, json={"original_url": "https://url-a.com"})
    assert r_create.status_code == 201
    url_id = r_create.json()["id"]
    print(f"User A created URL {url_id}")
    
    res_list = client.get(
        "/api/v1/urls",
        headers={"Authorization": f"Bearer {access_token_a}"}
    )
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1
    assert any(u["id"] == url_id for u in res_list.json())

    res_update = client.patch(
        f"/api/v1/urls/{url_id}",
        json={"original_url": "https://example.com/longer"},
        headers={"Authorization": f"Bearer {access_token_a}"}
    )
    assert res_update.status_code == 200
    assert res_update.json()["original_url"] == "https://example.com/longer"
    
    r_patch = client.patch(f"/api/v1/urls/{url_id}", headers={"Authorization": f"Bearer {access_token_b}"}, json={"is_active": False})
    assert r_patch.status_code == 403
    
    r_delete = client.delete(f"/api/v1/urls/{url_id}", headers={"Authorization": f"Bearer {access_token_b}"})
    assert r_delete.status_code == 403
    
    print("\n--- 4. Dashboard endpoint supports search, sort, pagination together ---")
    urls_to_create = [
        {"original_url": "https://test1.com"},
        {"original_url": "https://test2.com"},
        {"original_url": "https://somethingelse.com"},
        {"original_url": "https://test3.com"},
    ]
    for u in urls_to_create:
        client.post("/api/v1/urls", headers={"Authorization": f"Bearer {access_token_a}"}, json=u)
        
    r_dash = client.get("/api/v1/urls?q=test&sort_by=created_at&order=desc&page=1&page_size=2", headers={"Authorization": f"Bearer {access_token_a}"})
    assert r_dash.status_code == 200
    results = r_dash.json()
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"
    
    print("Page 1 Results:")
    for r in results:
        print(f" - {r['original_url']} (created_at: {r['created_at']})")
        assert "test" in r["original_url"] or "test" in r["short_code"]
        
    r_dash2 = client.get("/api/v1/urls?q=test&sort_by=created_at&order=desc&page=2&page_size=2", headers={"Authorization": f"Bearer {access_token_a}"})
    assert r_dash2.status_code == 200
    results2 = r_dash2.json()
    assert len(results2) == 1, f"Expected 1 result, got {len(results2)}"
    print("Page 2 Results:")
    for r in results2:
        print(f" - {r['original_url']} (created_at: {r['created_at']})")
        
    print("\nAll verifications passed successfully!")

