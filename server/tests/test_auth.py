"""Auth tests: token round-trips, the get_current_user guard, refresh-token
rotation, and per-user history scoping. The Google HTTP boundary is not
exercised here (it needs a live consent screen); everything downstream of a
minted session is tested against the real SQLite DB.
"""

from __future__ import annotations

import os
import tempfile
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.platform.auth.tokens import (
    decode_access_token,
    hash_token,
    mint_access_token,
    new_refresh_token,
)
from tests.conftest import seed_refresh_token, seed_search_request, seed_user

EMAIL = "test@example.com"


@pytest.fixture
def db_url(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    monkeypatch.setenv("DATABASE_URL", url)
    yield url
    os.unlink(tmp.name)


class TestTokens:
    def test_mint_decode_round_trip(self):
        token = mint_access_token(42, EMAIL)
        claims = decode_access_token(token)
        assert claims is not None
        assert claims["sub"] == "42"
        assert claims["email"] == EMAIL

    def test_expired_token_rejected(self, monkeypatch):
        monkeypatch.setenv("ACCESS_TOKEN_TTL_SECONDS", "1")
        from app.platform.config import get_settings

        get_settings.cache_clear()
        token = mint_access_token(1, EMAIL)
        time.sleep(2)
        assert decode_access_token(token) is None

    def test_tampered_token_rejected(self):
        token = mint_access_token(1, EMAIL)
        assert decode_access_token(token + "x") is None

    def test_refresh_tokens_are_unique(self):
        raw1, hash1 = new_refresh_token()
        raw2, hash2 = new_refresh_token()
        assert raw1 != raw2
        assert hash1 != hash2
        assert hash_token(raw1) == hash1


class TestGetCurrentUser:
    def test_no_cookie_is_401(self, db_url):
        with TestClient(create_app()) as c:
            assert c.get("/api/v1/auth/me").status_code == 401

    def test_invalid_cookie_is_401(self, db_url):
        with TestClient(create_app()) as c:
            c.cookies.set("access_token", "not-a-jwt")
            assert c.get("/api/v1/auth/me").status_code == 401

    def test_valid_cookie_returns_user(self, db_url):
        user_id = seed_user(db_url, email=EMAIL, name="Alice")
        token = mint_access_token(user_id, EMAIL)
        with TestClient(create_app()) as c:
            c.cookies.set("access_token", token)
            r = c.get("/api/v1/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == EMAIL
        assert body["name"] == "Alice"

    def test_token_for_unknown_user_is_401(self, db_url):
        # Valid signature but no matching row.
        token = mint_access_token(999, EMAIL)
        with TestClient(create_app()) as c:
            c.cookies.set("access_token", token)
            assert c.get("/api/v1/auth/me").status_code == 401


class TestRefreshRotation:
    def test_valid_refresh_rotates_and_sets_cookies(self, db_url):
        user_id = seed_user(db_url, email=EMAIL)
        raw, token_hash = new_refresh_token()
        seed_refresh_token(db_url, user_id, token_hash)

        with TestClient(create_app()) as c:
            c.cookies.set("refresh_token", raw)
            r = c.post("/api/v1/auth/refresh")
            assert r.status_code == 204
            # New cookies issued.
            assert "access_token" in r.cookies
            assert "refresh_token" in r.cookies

    def test_reusing_rotated_token_is_rejected(self, db_url):
        user_id = seed_user(db_url, email=EMAIL)
        raw, token_hash = new_refresh_token()
        seed_refresh_token(db_url, user_id, token_hash)

        with TestClient(create_app()) as c:
            # First use rotates (revokes) the original token.
            c.cookies.set("refresh_token", raw)
            assert c.post("/api/v1/auth/refresh").status_code == 204
            # Presenting the now-revoked original again must fail.
            c.cookies.set("refresh_token", raw)
            assert c.post("/api/v1/auth/refresh").status_code == 401

    def test_unknown_refresh_token_is_401(self, db_url):
        seed_user(db_url, email=EMAIL)
        with TestClient(create_app()) as c:
            c.cookies.set("refresh_token", "bogus")
            assert c.post("/api/v1/auth/refresh").status_code == 401

    def test_no_refresh_cookie_is_401(self, db_url):
        with TestClient(create_app()) as c:
            assert c.post("/api/v1/auth/refresh").status_code == 401


class TestHistoryScoping:
    def test_history_is_per_user(self, db_url):
        alice = seed_user(db_url, email="alice@example.com", name="Alice")
        bob = seed_user(db_url, email="bob@example.com", name="Bob")
        seed_search_request(db_url, alice, "Alice's claim")
        seed_search_request(db_url, bob, "Bob's claim 1")
        seed_search_request(db_url, bob, "Bob's claim 2")

        with TestClient(create_app()) as c:
            c.cookies.set("access_token", mint_access_token(alice, "alice@example.com"))
            alice_items = c.get("/api/v1/history").json()["items"]

            c.cookies.set("access_token", mint_access_token(bob, "bob@example.com"))
            bob_items = c.get("/api/v1/history").json()["items"]

        assert [i["claim"] for i in alice_items] == ["Alice's claim"]
        assert {i["claim"] for i in bob_items} == {"Bob's claim 1", "Bob's claim 2"}


def test_access_token_has_expiry_claim():
    token = mint_access_token(1, EMAIL)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert "exp" in claims and "iat" in claims
