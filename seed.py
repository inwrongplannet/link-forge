import requests
import uuid

base_url = "http://localhost:8080/api/v1"
username = f"k6user_{uuid.uuid4().hex[:8]}@example.com"
password = "password123"

# Register
requests.post(f"{base_url}/auth/register", json={
    "username": username.split("@")[0],
    "email": username,
    "password": password
})

# Login
login_res = requests.post(f"{base_url}/auth/login", json={
    "email": username,
    "password": password
})
token = login_res.json()["access_token"]

# Create URL
res = requests.post(
    f"{base_url}/urls",
    headers={"Authorization": f"Bearer {token}"},
    json={"original_url": "https://example.com/k6-test"}
)
print(res.json()["short_code"])
