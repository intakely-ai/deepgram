# db/supabase_helpers.py
import os, json, requests, asyncio
from ..config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SCHEMA, TENANT_ID
from ..utils.datetime_helpers import _utc_now_iso

# ---------------- Supabase helpers ----------------
def _sb_headers():
    return {
        "apikey": SUPABASE_KEY or "",
        "Authorization": f"Bearer {SUPABASE_KEY}" if SUPABASE_KEY else "",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _sb_url(table):
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL not set")
    return f"{SUPABASE_URL}/rest/v1/{table}"

def _sb_insert(table, row):
    if not SUPABASE_KEY:
        print("[supabase ERROR] SUPABASE_SERVICE_ROLE not set")
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE not set"}
    try:
        r = requests.post(_sb_url(table), headers=_sb_headers(), data=json.dumps(row), timeout=15)
        r.raise_for_status()
        data = r.json() if r.text else {}
        print(f"[supabase] inserted into {table}: {data if data else row}")
        return {"ok": True, "data": data[0] if isinstance(data, list) and data else data}
    except Exception as e:
        body = None
        try:
            body = r.text  # may not exist if request failed before assignment
        except Exception:
            body = None
        print(f"[supabase ERROR] table={table} err={e} body={body}")
        return {"ok": False, "error": str(e), "table": table, "body": body}

def _sb_upsert(table, row, on_conflict=None):
    if not SUPABASE_KEY:
        print("[supabase ERROR] SUPABASE_SERVICE_ROLE not set")
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE not set"}
    try:
        url = _sb_url(table)
        if on_conflict:
            url = f"{url}?on_conflict={on_conflict}"
        headers = dict(_sb_headers())
        headers["Prefer"] = "resolution=merge-duplicates"
        r = requests.post(url, headers=headers, data=json.dumps(row), timeout=15)
        r.raise_for_status()
        data = r.json() if r.text else {}
        print(f"[supabase] upsert into {table}: {data if data else row}")
        return {"ok": True, "data": data[0] if isinstance(data, list) and data else data}
    except Exception as e:
        body = None
        try:
            body = r.text
        except Exception:
            body = None
        print(f"[supabase ERROR] upsert table={table} err={e} body={body}")
        return {"ok": False, "error": str(e), "table": table, "body": body}

# ---------------- Async wrappers ----------------
async def _sb_insert_async(table, row):
    return await asyncio.to_thread(_sb_insert, table, row)

async def _sb_upsert_async(table, row, on_conflict=None):
    return await asyncio.to_thread(_sb_upsert, table, row, on_conflict)

def _spawn(coro):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop; best-effort synchronous
        try:
            asyncio.run(coro)
        except Exception:
            pass