
from app.cache.flush_worker import flush_once
from app.cache.redis_client import redis_client
from app.database.session import engine


def test_analytics_flow(client):
    # 1. Register User 1
    client.post("/api/v1/auth/register", json={"username": "user1", "email": "user1@test.com", "password": "password123"})
    login_res1 = client.post("/api/v1/auth/login", json={"email": "user1@test.com", "password": "password123"})
    assert login_res1.status_code == 200
    token1 = login_res1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # 2. Register User 2
    client.post("/api/v1/auth/register", json={"username": "user2", "email": "user2@test.com", "password": "password123"})
    login_res2 = client.post("/api/v1/auth/login", json={"email": "user2@test.com", "password": "password123"})
    assert login_res2.status_code == 200
    token2 = login_res2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # 3. Create URL for User 1
    url_res = client.post("/api/v1/urls", json={"original_url": "https://python.org"}, headers=headers1)
    assert url_res.status_code == 201
    url_data = url_res.json()
    short_code = url_data["short_code"]
    url_id = url_data["id"]

    # 4. Click URL from different browsers
    ua_chrome_desktop = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ua_safari_mobile = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    ua_firefox_desktop = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"

    client.get(f"/{short_code}", headers={"User-Agent": ua_chrome_desktop}, follow_redirects=False)
    client.get(f"/{short_code}", headers={"User-Agent": ua_safari_mobile}, follow_redirects=False)
    client.get(f"/{short_code}", headers={"User-Agent": ua_firefox_desktop}, follow_redirects=False)

    # Flush buffered clicks from Redis to Postgres so analytics can read them
    flush_once(redis_client, engine)

    # 5. Get Analytics (User 1)
    analytics_res = client.get(f"/api/v1/urls/{url_id}/analytics", headers=headers1)
    assert analytics_res.status_code == 200
    analytics_data = analytics_res.json()

    assert analytics_data["total_clicks"] == 3

    # check devices
    devices = analytics_data["top_devices"]
    assert devices.get("desktop") == 2
    assert devices.get("mobile") == 1

    # check browsers
    browsers = analytics_data["top_browsers"]
    assert any("Chrome" in b for b in browsers)
    assert any("Safari" in b for b in browsers)
    assert any("Firefox" in b for b in browsers)

    print("Analytics correct!")

    # 6. Unauthorized access (User 2 tries to access User 1's analytics)
    bad_res = client.get(f"/api/v1/urls/{url_id}/analytics", headers=headers2)
    assert bad_res.status_code == 404
    print("Unauthorized access blocked successfully!")

    print("All tests passed.")
