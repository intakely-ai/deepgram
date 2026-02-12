# crm/crm_functions.py
import os, json, uuid, requests, asyncio, importlib, logging, re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes
from googleapiclient.errors import HttpError
from ..config import SUPABASE_URL, SUPABASE_KEY, BUSINESS_TZ, TENANT_ID
from ..utils.datetime_helpers import _utc_now_iso, get_current_datetime
from ..utils.id_helpers import _normalize_caller_id
from ..db.supabase_helpers import _sb_headers, _sb_url, _sb_insert, _sb_upsert
from ..calendar.google_calender_helpers import _load_google_creds, _build_event_summary, _build_event_description

def get_booking_info_by_email(email: str):
    """
    Return client info + the most relevant booking for a returning client:
    1) upcoming soonest (appointment_datetime >= now UTC), else
    2) last past booking.
    Also returns booking_is_future (PT) and PT-normalized ISO.
    """
    from urllib.parse import quote_plus
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