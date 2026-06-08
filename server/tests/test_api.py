"""End-to-end API tests.

Exercises the FastAPI app with the real DB.
The verify endpoint is harder to test without a running Ollama.
Cover the deterministic surface here (history + validation)
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.api.generated.models import (
    FinalVerdictPayload,
    SearchStartedPayload,
    SseEventType,
    Verdict,
)
from app.api.verify import EVENT_PAYLOAD, sse
from app.main import create_app
from app.platform.auth.tokens import mint_access_token
from tests.conftest import seed_user

TEST_EMAIL = "test@example.com"


@pytest.fixture
def db_url(monkeypatch):
    # Point the DB at a fresh temp file per test to avoid cross-test pollution.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    monkeypatch.setenv("DATABASE_URL", url)
    yield url
    os.unlink(tmp.name)


@pytest.fixture
def client(db_url):
    """Authenticated client: seeds a user and presents a valid access cookie."""
    user_id = seed_user(db_url, email=TEST_EMAIL)
    token = mint_access_token(user_id, TEST_EMAIL)
    with TestClient(create_app()) as c:
        c.cookies.set("access_token", token)
        yield c


@pytest.fixture
def anon_client(db_url):
    """Unauthenticated client — no cookie."""
    with TestClient(create_app()) as c:
        yield c


class TestHistory:
    def test_empty_history_returns_empty_list(self, client):
        r = client.get("/api/v1/history")
        assert r.status_code == 200
        assert r.json() == {"items": []}

    def test_limit_param_accepted(self, client):
        r = client.get("/api/v1/history?limit=5")
        assert r.status_code == 200

    def test_limit_out_of_range_rejected(self, client):
        r = client.get("/api/v1/history?limit=999")
        assert r.status_code == 422

    def test_requires_authentication(self, anon_client):
        r = anon_client.get("/api/v1/history")
        assert r.status_code == 401


class TestVerifyValidation:
    def test_empty_claim_rejected(self, client):
        r = client.post("/api/v1/verify", json={"claim": ""})
        assert r.status_code == 422

    def test_missing_claim_rejected(self, client):
        r = client.post("/api/v1/verify", json={})
        assert r.status_code == 422

    def test_oversized_claim_rejected(self, client):
        r = client.post("/api/v1/verify", json={"claim": "x" * 1001})
        assert r.status_code == 422

    def test_invalid_prefer_source_rejected(self, client):
        r = client.post(
            "/api/v1/verify",
            json={"claim": "ok", "prefer_source": "elasticsearch"},
        )
        assert r.status_code == 422


class TestSsePayloads:
    """
    The SSE event->payload pairing has no codegen-level enforcement.
    Every event must have a registry entry, and sse() must emit
    the event name + spec-shaped JSON data.
    """

    def test_registry_covers_every_event(self):
        assert set(EVENT_PAYLOAD) == set(SseEventType)

    def test_sse_emits_event_and_json_data(self):
        frame = sse(SseEventType.search_started, SearchStartedPayload(queries=["a", "b"]))
        assert frame["event"] == "search_started"
        assert json.loads(frame["data"]) == {"queries": ["a", "b"]}

    def test_done_event_has_empty_data(self):
        frame = sse(SseEventType.done)
        assert frame["event"] == "done"
        assert json.loads(frame["data"]) == {}

    def test_wrong_payload_type_raises(self):
        with pytest.raises(TypeError, match="final_verdict"):
            sse(SseEventType.final_verdict, SearchStartedPayload(queries=["x"]))

    def test_done_with_payload_raises(self):
        with pytest.raises(TypeError, match="done"):
            sse(SseEventType.done, SearchStartedPayload(queries=["x"]))

    def test_verdict_enum_serialises_to_value(self):
        frame = sse(
            SseEventType.final_verdict,
            FinalVerdictPayload(verdict=Verdict.SUPPORTED, citations=[]),
        )
        assert json.loads(frame["data"])["verdict"] == "SUPPORTED"
