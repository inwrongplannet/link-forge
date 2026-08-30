import uuid

def test_register_then_login_returns_tokens(client):
    uid = uuid.uuid4().hex[:8]
    client.post("/api/v1/auth/register", json={
        "username": f"alice_{uid}", "email": f"alice_{uid}@example.com", "password": "supersecret1"
    })
    response = client.post("/api/v1/auth/login", json={
        "email": f"alice_{uid}@example.com", "password": "supersecret1"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_with_wrong_password_fails(client):
    uid = uuid.uuid4().hex[:8]
    client.post("/api/v1/auth/register", json={
        "username": f"bob_{uid}", "email": f"bob_{uid}@example.com", "password": "supersecret1"
    })
    response = client.post("/api/v1/auth/login", json={
        "email": f"bob_{uid}@example.com", "password": "wrongpassword"
    })
    assert response.status_code == 401

def test_cannot_edit_another_users_url(client, auth_headers_for_two_users):
    headers_a, headers_b = auth_headers_for_two_users
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com"}, headers=headers_a)
    url_id = created.json()["id"]
    response = client.patch(f"/api/v1/urls/{url_id}", json={"is_active": False}, headers=headers_b)
    assert response.status_code == 403
