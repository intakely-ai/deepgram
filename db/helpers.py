import json
from datetime import datetime, timezone, timedelta

# reuse existing supabase client primitives in codebase
try:
    from law_functions.supabase_client import (
        _sb_insert,
        _sb_upsert,
        _sb_insert_async,
        _sb_upsert_async,
        _spawn,
    )
except Exception:
    from supabase_client import (
        _sb_insert,
        _sb_upsert,
        _sb_insert_async,
        _sb_upsert_async,
        _spawn,
    )

# reuse existing lead_management.create_or_get_caller_id if available
try:
    from law_functions.lead_management import create_or_get_caller_id as lm_create_or_get_caller_id
except Exception:
    lm_create_or_get_caller_id = None


async def db_connect():
    """Placeholder: no explicit connection object; supabase client primitives are used."""
    return True


async def get_firm(id_or_key: str):
    sql = """
        SELECT * FROM law_firmpointing
        WHERE id = $1 OR tenant_key = $1
        LIMIT 1
    """
    rows = await _spawn(sql, [id_or_key])
    return rows[0] if rows else None


async def create_or_get_caller_id(source_channel: str = "twilio_voice", tenant_key: str | None = None):
    if lm_create_or_get_caller_id:
        return await lm_create_or_get_caller_id(source_channel, tenant_key)
    raise NotImplementedError("create_or_get_caller_id not implemented in lead_management; please expose it.")


async def upsert_pi_lead(payload: dict):
    try:
        return await _sb_upsert_async("pi_leads", payload)
    except Exception:
        return _sb_upsert("pi_leads", payload)


async def save_pi_answer(lead_id: str, question_key: str, answer_payload: dict):
    """
    Store answer_json as native dict (JSONB) not as a dumped string.
    """
    row = {
        "lead_id": lead_id,
        "question_key": question_key,
        "question_text": answer_payload.get("question_text"),
        "answer_text": answer_payload.get("answer_text"),
        "answer_enum": answer_payload.get("answer_enum"),
        "answer_json": answer_payload.get("answer_json") or {},  # keep as dict for JSONB
        "question_type": answer_payload.get("question_type"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        return await _sb_insert_async("pi_answers", row)
    except Exception:
        return _sb_insert("pi_answers", row)


async def get_pi_questions(firm_id: str, path_id: str):
    sql = """
        SELECT * FROM pi_questions
        WHERE firm_id = $1 AND path_id = $2
        ORDER BY question_order ASC
    """
    return await _spawn(sql, [firm_id, path_id])


async def get_pi_blocklist(firm_id: str):
    sql = """
        SELECT block_key, phrase, regex_pattern, severity, default_action
        FROM pi_blocklist
        WHERE firm_id = $1 AND practice_area = 'personal_injury'
        ORDER BY severity DESC NULLS LAST
    """
    return await _spawn(sql, [firm_id])


async def append_session_ephemera(session_id: str, update: dict):
    payload = {"session_id": session_id}
    payload.update(update)
    if "expires_at" in payload and isinstance(payload["expires_at"], datetime):
        payload["expires_at"] = payload["expires_at"].isoformat()
    try:
        return await _sb_upsert_async("session_clock_ephemera", payload)
    except Exception:
        return _sb_upsert("session_clock_ephemera", payload)


async def set_session_expiry(session_id: str, ttl_seconds: int = 7):
    expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    payload = {"session_id": session_id, "expires_at": expires}
    try:
        return await _sb_upsert_async("session_clock_ephemera", payload)
    except Exception:
        return _sb_upsert("session_clock_ephemera", payload)


async def get_session_ephemera(session_id: str):
    sql = "SELECT * FROM session_clock_ephemera WHERE session_id = $1 LIMIT 1"
    rows = await _spawn(sql, [session_id])
    return rows[0] if rows else None


async def save_lead_qa(unique_caller_id: str, email: str | None, all_q_and_a: list, practice_area_version: str | None, completion_status: str = "complete"):
    """
    Store all_q_and_a as native JSON array (list), not a JSON-encoded string.
    """
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "all_q_and_a": all_q_and_a,
        "practice_area_version": practice_area_version,
        "completion_status": completion_status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        return await _sb_insert_async("lead_qa", row)
    except Exception:
        return _sb_insert("lead_qa", row)


async def create_lead_booking(unique_caller_id: str, email: str, appointment_datetime: str, timezone_str: str, platform: str, extra: dict | None = None):
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "appointment_datetime": appointment_datetime,
        "timezone": timezone_str,
        "platform": platform,
        "meeting_link": (extra or {}).get("meeting_link"),
        "phone_number": (extra or {}).get("phone_number"),
        "booked_with": (extra or {}).get("booked_with"),
        "booking_notes": (extra or {}).get("booking_notes"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        return await _sb_insert_async("lead_booking", row)
    except Exception:
        return _sb_insert("lead_booking", row)


async def get_attorney_by_practice(firm_id: str, practice_area: str = "personal_injury"):
    sql = """
        SELECT * FROM attorney_table
        WHERE firm_id = $1 AND practice_area = $2 AND is_active = true
        LIMIT 1
    """
    rows = await _spawn(sql, [firm_id, practice_area])
    return rows[0] if rows else None


async def seed_pi_blocklist(firm_id: str, entries: list):
    results = []
    for e in entries:
        payload = {
            "firm_id": firm_id,
            "practice_area": "personal_injury",
            "block_key": e["block_key"],
            "phrase": e.get("phrase", ""),
            "regex_pattern": e.get("regex_pattern", ""),
            "severity": e.get("severity", "high"),
            "default_action": e.get("default_action", "redact"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            r = await _sb_upsert_async("pi_blocklist", payload)
        except Exception:
            r = _sb_upsert("pi_blocklist", payload)
        results.append(r)
    return results