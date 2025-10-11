import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from typing import Optional, Dict, Any, List

# reuse helpers
from db import helpers
# try to reuse project's time util (fallback to UTC now)
try:
    from law_functions.time_utils import get_current_datetime
except Exception:
    def get_current_datetime(timezones: List[str] = ["UTC"]) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        return {
            "utc_iso": now.isoformat(),
            "pt_iso": now.isoformat(),  # fallback — caller can override if needed
            "pt_date": now.date().isoformat(),
            "pt_year": str(now.year),
        }

# direct SQL runner (used for expiry deletion). Try project supabase client import like helpers does.
try:
    from law_functions.supabase_client import _spawn
except Exception:
    from supabase_client import _spawn  # type: ignore


async def create_session_clock(unique_caller_id: str, firm_id: str, session_id: Optional[str] = None, ttl_seconds: int = 7) -> Dict[str, Any]:
    """
    Create / upsert a session_clock_ephemera row.
    Returns {session_id, session_clock, expires_at, row}
    """
    if session_id is None:
        session_id = f"sess-{uuid4().hex}"

    session_clock = get_current_datetime(timezones=["UTC", "America/Los_Angeles"])
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()

    payload = {
        "session_id": session_id,
        "firm_id": firm_id,
        "lead_id": None,
        "session_clock": session_clock,
        "high_risk_flags": [],
        "redactions_applied": False,
        "ephemeral_logs": [],
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # use helpers append (upsert) to persist
    await helpers.append_session_ephemera(session_id, payload)
    return {"session_id": session_id, "session_clock": session_clock, "expires_at": expires_at, "row": payload}


async def upsert_ephemeral_log(session_id: str, event: Dict[str, Any], extend_ttl_seconds: Optional[int] = None) -> Dict[str, Any]:
    """
    Append an anonymized event to session_clock_ephemera.ephemeral_logs.
    If event contains 'flag' (block_key), also append to high_risk_flags.
    Optionally extend TTL by extend_ttl_seconds.
    Returns the updated ephemeral row (best-effort).
    """
    # fetch current ephemera
    ep = await helpers.get_session_ephemera(session_id)
    if not ep:
        # create minimal session if missing (no firm_id known)
        await helpers.append_session_ephemera(session_id, {
            "session_id": session_id,
            "session_clock": get_current_datetime(timezones=["UTC"]),
            "ephemeral_logs": [event],
            "high_risk_flags": [event.get("flag")] if event.get("flag") else [],
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=extend_ttl_seconds or 7)).isoformat()
        })
        return await helpers.get_session_ephemera(session_id)

    # merge logs
    logs = list(ep.get("ephemeral_logs") or [])
    logs.append(event)
    update = {"ephemeral_logs": logs}

    # merge high_risk_flags if present
    if event.get("flag"):
        flags = list(ep.get("high_risk_flags") or [])
        if event["flag"] not in flags:
            flags.append(event["flag"])
        update["high_risk_flags"] = flags
        update["redactions_applied"] = True

    # optionally extend TTL
    if extend_ttl_seconds:
        update["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=extend_ttl_seconds)).isoformat()

    await helpers.append_session_ephemera(session_id, update)
    return await helpers.get_session_ephemera(session_id)


async def expire_sessions_worker(interval_seconds: int = 60, run_once: bool = False) -> int:
    """
    Delete expired ephemeral session rows.
    If run_once is True, run a single pass and return deleted count.
    Otherwise loop forever with interval_seconds between runs (cancellable).
    Returns number of rows deleted on the pass.
    """
    async def _delete_pass() -> int:
        sql = "DELETE FROM session_clock_ephemera WHERE expires_at IS NOT NULL AND expires_at < now() RETURNING id"
        try:
            rows = await _spawn(sql, [])
            # _spawn may return list of deleted rows; return length if so, else 0
            return len(rows) if rows else 0
        except Exception:
            # best-effort fallback: attempt non-async spawn (some clients return sync)
            try:
                res = _spawn(sql, [])
                return len(res) if res else 0
            except Exception:
                return 0

    if run_once:
        return await _delete_pass()

    deleted_total = 0
    try:
        while True:
            deleted = await _delete_pass()
            deleted_total += deleted
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        return deleted_total