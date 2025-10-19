import pytest
from importlib import import_module

helpers = import_module("db.helpers")

@pytest.mark.asyncio
async def test_save_pi_answer_inserts_jsonb_and_keys(monkeypatch):
    if not hasattr(helpers, "save_pi_answer"):
        pytest.skip("db.helpers.save_pi_answer not implemented")

    captured = {}
    async def fake_insert_async(table, row):
        captured["table"] = table
        captured["row"] = row
        return row

    def fake_insert(table, row):
        captured["table_sync"] = table
        captured["row_sync"] = row
        return row

    monkeypatch.setattr(helpers, "_sb_insert_async", fake_insert_async, raising=False)
    monkeypatch.setattr(helpers, "_sb_insert", fake_insert, raising=False)

    answer_payload = {
        "question_text": "Were there witnesses?",
        "answer_text": "No",
        "answer_enum": "no",
        "answer_json": {"choice":"no"},
        "question_type": "yes_no"
    }

    res = await helpers.save_pi_answer("lead-uuid-1", "witnesses", answer_payload)
    # verify the async insert path recorded expected content
    row = captured.get("row") or captured.get("row_sync") or res
    assert row is not None
    assert row["lead_id"] == "lead-uuid-1"
    assert row["question_key"] == "witnesses"
    # answer_json must remain a dict (JSONB), not a dumped string
    assert isinstance(row["answer_json"], dict)
    assert row["answer_enum"] == "no" or row.get("answer_enum") == "no"