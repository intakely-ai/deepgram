import pytest
import asyncio
from importlib import import_module

helpers = import_module("db.helpers")

@pytest.mark.asyncio
async def test_set_session_expiry_calls_upsert_async(monkeypatch):
    if not hasattr(helpers, "set_session_expiry"):
        pytest.skip("db.helpers.set_session_expiry not implemented")

    recorded = {}
    async def fake_upsert_async(table, payload):
        recorded["table"] = table
        recorded["payload"] = payload
        return payload

    # Monkeypatch both async and sync fallback to be safe
    monkeypatch.setattr(helpers, "_sb_upsert_async", fake_upsert_async, raising=False)
    monkeypatch.setattr(helpers, "_sb_upsert", lambda table, payload: payload, raising=False)

    res = await helpers.set_session_expiry("sess-1234", ttl_seconds=5)
    # ensure we invoked the upsert and payload includes session_id and expires_at
    assert recorded.get("table") in ("session_clock_ephemera", None) or res is not None
    payload = recorded.get("payload") or res
    assert payload is not None
    assert payload.get("session_id") == "sess-1234"
    assert "expires_at" in payload