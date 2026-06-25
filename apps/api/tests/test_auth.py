def test_login_missing_fields(client):
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422


def test_login_invalid_credentials(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


def test_me_without_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_without_token(client):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401