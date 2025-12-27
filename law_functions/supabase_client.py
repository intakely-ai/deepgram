# supabase_client.py
import os
import json
import requests
import asyncio
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SCHEMA
from time_utils import _utc_now_iso
import logging
from datetime import datetime as dt, timedelta, timezone as _tz
from config import BUSINESS_TZ
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

# --- Specific Supabase Functions ---
# These could be moved to a higher-level module like 'lead_management.py' or 'booking.py'
# but keeping them here for now as they are purely DB operations.
def get_booking_info_by_email(email: str):
    """
    Return client info + the most relevant booking for a returning client:
    1) upcoming soonest (appointment_datetime >= now UTC), else
    2) last past booking.
    Also returns booking_is_future (PT) and PT-normalized ISO.
    """
    from urllib.parse import quote_plus
    import re
    from time_utils import get_current_datetime
    from dateutil import parser as dtp  # parse ISO datetimes
    from zoneinfo import ZoneInfo  # Python 3.9+
    import logging

    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, (email or "")):
        return {"ok": False, "error": "Invalid email format"}
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "error": "Supabase credentials missing."}

    headers = _sb_headers()
    client_info, chosen_booking = {}, None
    # 1) Client profile (latest)
    try:
        info_url = f"{_sb_url('lead_information')}?email=eq.{quote_plus(email)}&order=updated_at.desc&limit=1"
        r = requests.get(info_url, headers=headers, timeout=10); r.raise_for_status()
        data = r.json() or []
        if data: client_info = data[0]
    except Exception as e:
        logging.exception("Could not fetch client info: %s", e)

    # 2) Pick booking: upcoming ⇢ else last past
    now_z = dt.now(_tz.utc).isoformat().replace("+00:00", "Z")
    try:
        upc_url = (
            f"{_sb_url('lead_booking')}?email=eq.{quote_plus(email)}"
            f"&appointment_datetime=gte.{quote_plus(now_z)}"
            f"&order=appointment_datetime.asc&limit=1"
        )
        r = requests.get(upc_url, headers=headers, timeout=10); r.raise_for_status()
        upc = r.json() or []
        if upc:
            chosen_booking = upc[0]
        else:
            past_url = (
                f"{_sb_url('lead_booking')}?email=eq.{quote_plus(email)}"
                f"&appointment_datetime=lt.{quote_plus(now_z)}"
                f"&order=appointment_datetime.desc&limit=1"
            )
            r = requests.get(past_url, headers=headers, timeout=10); r.raise_for_status()
            pst = r.json() or []
            if pst:
                chosen_booking = pst[0]
    except Exception as e:
        logging.exception("Could not fetch bookings: %s", e)

    # Also get current practice area (latest QA or profile)
    current_practice_area = None
    try:
        qa_url = f"{_sb_url('lead_qa')}?email=eq.{quote_plus(email)}&order=created_at.desc&limit=1"
        r = requests.get(qa_url, headers=headers, timeout=10); r.raise_for_status()
        qa = r.json() or []
        if qa: current_practice_area = (qa[0] or {}).get("practice_area")
    except Exception as e:
        logging.exception("Could not fetch practice area: %s", e)
    if not current_practice_area and client_info:
        current_practice_area = client_info.get("practice_area")

    if not client_info and not chosen_booking:
        return {"ok": False, "error": "No client or booking records found for that email."}

    # Mark past/future relative to PT now
    booking_is_future, booking_parsed_iso = None, None
    booking_id = calendar_id = google_event_id = None
    if chosen_booking:
        start_iso = chosen_booking.get("appointment_datetime")
        booking_id = chosen_booking.get("id")
        calendar_id = chosen_booking.get("calendar_id")
        google_event_id = chosen_booking.get("google_event_id")
        if start_iso:
            try:
                pt_zone = ZoneInfo(BUSINESS_TZ)
            except Exception:
                pt_zone = None
            try:
                start = dtp.isoparse(start_iso)
                if pt_zone:
                    start = (start if start.tzinfo else start.replace(tzinfo=pt_zone)).astimezone(pt_zone)
                    now_pt = dtp.isoparse(get_current_datetime()["pt_iso"])
                else:
                    # Heuristic if tzdb missing
                    off = -7 if 3 <= dt.utcnow().month <= 11 else -8
                    now_pt = dt.utcnow() + timedelta(hours=off); now_pt = now_pt.replace(tzinfo=None)
                    start = start.replace(tzinfo=None)
                booking_parsed_iso = start.isoformat()
                booking_is_future = start >= now_pt
            except Exception:
                pass

    # Convenience fields for dialog logic (avoid asking contact info again)
    lead_full_name = (client_info or {}).get("full_name")
    lead_phone = (client_info or {}).get("phone")
    can_reschedule = bool(booking_is_future and google_event_id)

    return {
        "ok": True,
        "client_info": client_info,
        "current_practice_area": current_practice_area,
        "email": email,
        "booking_id": booking_id,
        "calendar_id": calendar_id,
        "google_event_id": google_event_id,
        "booking_is_future": booking_is_future,
        "booking_pt_iso": booking_parsed_iso,
        "lead_full_name": lead_full_name,
        "lead_phone": lead_phone,
        "can_reschedule": can_reschedule,
    }

def update_client_practice_area(unique_caller_id, email, new_practice_area):
    """
    Update a client's practice area in the database.
    """
    if not unique_caller_id or not email:
        return {"ok": False, "error": "Missing required parameters"}
    update_data = {"practice_area": new_practice_area, "updated_at": _utc_now_iso()}
    result = _sb_upsert(
        "lead_information",
        {"unique_caller_id": unique_caller_id, "email": email, **update_data},
        on_conflict="unique_caller_id"
    )
    if result.get("ok"):
        return {"ok": True, "message": "Practice area updated successfully"}
    else:
        return {"ok": False, "error": result.get("error", "Failed to update practice area")}

def get_lead_name(unique_caller_id):
    """Get lead name from the database using unique_caller_id"""
    if not unique_caller_id:
        return None
    try:
        import requests
        _sb_url_fn = globals().get("_sb_url")
        _sb_headers_fn = globals().get("_sb_headers")
        if _sb_url_fn and _sb_headers_fn:
            url = f"{_sb_url_fn('lead_information')}?unique_caller_id=eq.{unique_caller_id}&select=full_name"
            r = requests.get(url, headers=_sb_headers_fn(), timeout=10)
            if r.status_code == 200 and r.json():
                return r.json()[0].get("full_name")
    except Exception as e:
        logging.error(f"Error getting lead name: {e}")
    return None