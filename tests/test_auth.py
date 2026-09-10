from advisor.api.security import hash_password, verify_password
from advisor.api.crypto import encrypt_json, decrypt_json


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_long_password_not_silently_truncated():
    a = "x" * 100 + "A"
    b = "x" * 100 + "B"
    h = hash_password(a)
    assert verify_password(a, h)
    assert not verify_password(b, h)   # would collide if bcrypt-72 truncation leaked


def test_broker_cred_encryption_roundtrip():
    payload = {"api_key": "k", "api_secret": "s3cr3t"}
    blob = encrypt_json(payload)
    assert "s3cr3t" not in blob
    assert decrypt_json(blob) == payload


def _register(client, email="a@example.com", pw="password123"):
    return client.post("/auth/register", json={"email": email, "password": pw, "full_name": "A"})


def test_register_login_me_flow(client):
    r = _register(client)
    assert r.status_code == 201, r.text
    tokens = r.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"

    dup = _register(client)
    assert dup.status_code == 409

    login = client.post("/auth/login", data={"username": "a@example.com", "password": "password123"})
    assert login.status_code == 200
    bad = client.post("/auth/login", data={"username": "a@example.com", "password": "nope"})
    assert bad.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client):
    tokens = _register(client).json()
    rt = tokens["refresh_token"]

    first = client.post("/auth/refresh", json={"refresh_token": rt})
    assert first.status_code == 200
    new_rt = first.json()["refresh_token"]
    assert new_rt != rt

    # old refresh token is now revoked -> reuse triggers family revocation
    reuse = client.post("/auth/refresh", json={"refresh_token": rt})
    assert reuse.status_code == 401

    # the rotated-in token was also revoked by the reuse defense
    assert client.post("/auth/refresh", json={"refresh_token": new_rt}).status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = _register(client).json()
    assert client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_google_login_unconfigured_returns_503(client):
    assert client.get("/auth/google/authorize").status_code == 503


def test_brokers_crud(client):
    tokens = _register(client).json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/brokers", headers=h).json() == []

    put = client.put("/brokers/zerodha", headers=h,
                     json={"fields": {"api_key": "abc123", "api_secret": "shhhh1234"}})
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["fields_set"] == ["api_key", "api_secret"]
    assert body["masked"]["api_secret"].endswith("1234")
    assert "shhhh" not in body["masked"]["api_secret"]

    bad = client.put("/brokers/zerodha", headers=h, json={"fields": {"api_key": "x"}})
    assert bad.status_code == 422  # missing api_secret

    assert client.delete("/brokers/zerodha", headers=h).status_code == 204
    assert client.get("/brokers", headers=h).json() == []
