# law_functions.py

import os, json, uuid, requests, asyncio
from datetime import datetime,timedelta, timezone
from zoneinfo import ZoneInfo  # Python 3.9+
import os, json, re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from dateutil import parser as dtp  # keep if you plan to parse dates later

from email_sender import send_email_smtp  # real SMTP sender

import importlib, logging

_gca = None
try:
    _gca = importlib.import_module("google_calendar_availability")
except Exception:
    logging.warning("google_calendar_availability module not importable; calendar features will be disabled.")

_gc_get_next_slots = getattr(_gca, "get_next_available_slots", None)
_gc_check_slot = getattr(_gca, "check_slot_and_alternatives", None)

# Try several common names for the reschedule helper
_gc_reschedule_event = None
if _gca is not None:
    for name in ("reschedule_event", "reschedule_booking", "reschedule"):
        _gc_reschedule_event = getattr(_gca, name, None)
        if _gc_reschedule_event:
            break

if not (_gc_get_next_slots and _gc_check_slot and _gc_reschedule_event):
    logging.debug(
        "google_calendar_availability: get_next_available_slots=%s, check_slot_and_alternatives=%s, reschedule=%s",
        bool(_gc_get_next_slots), bool(_gc_check_slot), bool(_gc_reschedule_event)
    )

# ---------- Env ----------
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")

BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")

# Google Calendar env (safe to leave unset)

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")  # full JSON string
GOOGLE_DEFAULT_CALENDAR_ID  = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID")
ATTORNEY_PI_CALENDAR_ID     = os.getenv("ATTORNEY_PI_CALENDAR_ID")
ATTORNEY_FAMILY_CALENDAR_ID = os.getenv("ATTORNEY_FAMILY_CALENDAR_ID")
ATTORNEY_LEMON_CALENDAR_ID  = os.getenv("ATTORNEY_LEMON_CALENDAR_ID")
GOOGLE_AUTO_MEET            = os.getenv("GOOGLE_AUTO_MEET", "true").lower() in ("1", "true", "yes")

# ---------- Time helpers ----------
def _utc_now_iso() -> str:
    """Return an RFC3339/ISO-8601 timestamp with explicit UTC offset (+00:00)."""
    return datetime.now(timezone.utc).isoformat()

# ---------- Supabase helpers ----------
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

# Upsert helper (merge by unique constraint)
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

# ---------- Async wrappers (fire-and-forget) ----------
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

# ---------- ID helpers ----------
def _normalize_caller_id(candidate):
    value = (candidate or "").strip()
    if value.lower() in {"", "undefined", "null", "none", "unique_caller_id"}:
        return str(uuid.uuid4())
    try:
        uuid.UUID(value)
        return value
    except Exception:
        return str(uuid.uuid4())

# ---------- Google Calendar helper (NO DELEGATION) ----------
async def _google_create_event_async(calendar_id, summary, description, start_iso, end_iso, tz,
                                     attendees=None, create_meet=False):
    """
    Creates a Google Calendar event using a service account WITHOUT domain-wide delegation.

    Rules in no-DWD mode:
    - MUST post to a HUMAN calendar ID that is shared with the service account (Make changes).
    - 'primary' is INVALID (service accounts don't have one).
    - Attendees are ignored; sendUpdates='none'.
    - Google Meet is not created.

    Returns: {"ok": True, "eventId", "htmlLink"} OR {"ok": False, "error"}.
    """
    import os, json as _json, asyncio
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    sa_json_str  = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sa_json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "").strip()
    def _load_creds():
        scopes = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]
        if sa_json_str.startswith("{"):
            info = _json.loads(sa_json_str)
            return Credentials.from_service_account_info(info, scopes=scopes)
        if sa_json_path:
            with open(sa_json_path, "r", encoding="utf-8") as f:
                info = _json.load(f)
            return Credentials.from_service_account_info(info, scopes=scopes)
        return None
    def _google_update_event(calendar_id, event_id, new_start_iso, duration_min=30, tz="America/Los_Angeles"):
        sa_json_str  = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        sa_json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "").strip()
        scopes = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]

        if sa_json_str.startswith("{"):
            info = json.loads(sa_json_str)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        elif sa_json_path:
            with open(sa_json_path, "r", encoding="utf-8") as f:
                info = json.load(f)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        else:
            return {"ok": False, "error": "No service account creds."}

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            # Get the event
            event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            # Update start/end
            event["start"]["dateTime"] = new_start_iso
            event["start"]["timeZone"] = tz
            from dateutil import parser as dtp
            start_dt = dtp.isoparse(new_start_iso)
            end_dt = start_dt + timedelta(minutes=duration_min)
            event["end"]["dateTime"] = end_dt.isoformat()
            event["end"]["timeZone"] = tz
            updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
            return {"ok": True, "eventId": updated.get("id"), "htmlLink": updated.get("htmlLink")}
        except HttpError as he:
            body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
            return {"ok": False, "error": f"Google API error: {body}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _insert_event_sync():
        # Sanitize calendar id (strip stray '=' and spaces)
        cal_id = (calendar_id or "").strip().lstrip("=")
        if not cal_id:
            return {"ok": False, "error": "Missing calendar_id. Set GOOGLE_DEFAULT_CALENDAR_ID to a human calendar email/ID."}
        if cal_id.lower() == "primary":
            return {"ok": False, "error": "In no-delegation mode 'primary' is invalid. Use a human calendar email/ID that is shared with the service account."}

        creds = _load_creds()
        if not creds:
            return {"ok": False, "error": "No service account creds. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_PATH."}

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            # Build minimal event (no attendees / no Meet in no-DWD)
            event = {
                "summary": summary or "Consultation",
                "description": (description or ""),
                "start": {"dateTime": start_iso, "timeZone": tz},
                "end":   {"dateTime": end_iso,   "timeZone": tz},
            }

            created = service.events().insert(
                calendarId=cal_id,
                body=event,
                sendUpdates="none"  # no invites in no-DWD
            ).execute()

            return {
                "ok": True,
                "eventId": created.get("id"),
                "htmlLink": created.get("htmlLink"),
            }
        except HttpError as he:
            try:
                body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
            except Exception:
                body = str(he)
            return {"ok": False, "error": f"Google API error: {body}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # Run in worker thread to avoid event-loop conflicts
    return await asyncio.to_thread(_insert_event_sync)

# --- ADDED: expose a top-level _google_update_event (exact logic moved from nested helper) ---
def _google_update_event(calendar_id, event_id, new_start_iso, duration_min=30, tz="America/Los_Angeles"):
    sa_json_str  = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sa_json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "").strip()
    scopes = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]

    if sa_json_str.startswith("{"):
        info = json.loads(sa_json_str)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    elif sa_json_path:
        with open(sa_json_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        return {"ok": False, "error": "No service account creds."}

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        # Get the event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        # Update start/end
        event["start"]["dateTime"] = new_start_iso
        event["start"]["timeZone"] = tz
        from dateutil import parser as dtp
        start_dt = dtp.isoparse(new_start_iso)
        end_dt = start_dt + timedelta(minutes=duration_min)
        event["end"]["dateTime"] = end_dt.isoformat()
        event["end"]["timeZone"] = tz
        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        return {"ok": True, "eventId": updated.get("id"), "htmlLink": updated.get("htmlLink")}
    except HttpError as he:
        body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
        return {"ok": False, "error": f"Google API error: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------- Agent-callable functions ----------

def practice_area(practice_area):
    # No DB write here; legacy table 'leads' does not exist. Only echo back.
    return {"ok": True, "practice_area": practice_area}

def contact_information(first_name, last_name, email, cell_phone):
    row = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "cell_phone": cell_phone,
        "created_at": _utc_now_iso()
    }
    _sb_insert("leads", row)
    return {"ok": True, **row}

def intake_answers_qualification(practice_area, answers, qualified=False):
    _sb_insert("intakes", {
        "practice_area": practice_area,
        "answers": answers,
        "qualified": qualified,
        "created_at": _utc_now_iso()
    })
    return {"ok": True, "qualified": qualified}

def practice_area_attorney_name(practice_area):
    mapping = {"personal_injury": "John Doe", "lemon_law": "Jane Roe", "family_law": "Rhonda Fernandez"}
    return {"ok": True, "attorney_name": mapping.get(practice_area)}

def calendar_booking(attorney_name, start_iso, duration_min, caller_first_name, caller_last_name, email=None, cell_phone=None, location=None):
    # Keep calendar mock and avoid writing to non-existent 'bookings' table;
    # saving occurs via save_lead_booking after confirmation.
    booking_ref = f"bk_{uuid.uuid4().hex[:10]}"
    row = {
        "booking_ref": booking_ref,
        "attorney_name": attorney_name,
        "start_iso": start_iso,
        "duration_min": duration_min,
        "location": location or "In-person",
        "first_name": caller_first_name,
        "last_name": caller_last_name,
        "email": email,
        "cell_phone": cell_phone,
        "status": "pending",
        "created_at": _utc_now_iso(),
    }
    return {"ok": True, "booking_id": booking_ref, **row}

def reschedule_calendar_booking(booking_id, new_start_iso, calendar_id=None, event_id=None, duration_min=30, tz="America/Los_Angeles"):
    # Lookup calendar_id and event_id if not provided (from Supabase or context)
    # For now, require both as arguments
    if not calendar_id or not event_id:
        return {"ok": False, "error": "calendar_id and event_id required for rescheduling."}
    result = _google_update_event(calendar_id, event_id, new_start_iso, duration_min, tz)
    # Log to Supabase
    _sb_insert("crm_updates", {
        "fields": {
            "event": "reschedule_requested",
            "booking_id": booking_id,
            "new_start_iso": new_start_iso,
            "calendar_id": calendar_id,
            "event_id": event_id,
            "google_result": result,
        },
        "created_at": _utc_now_iso()
    })
    return {"ok": True, "booking_id": booking_id, "new_start_iso": new_start_iso, "google_result": result}

def terms_of_engagement_letter(email=None, cell_phone=None, cc=None):
    html = "<p>Please review and sign the attached Terms of Engagement (placeholder).</p>"
    subj = "Terms of Engagement (Oakwood Law Firm)"
    # send real email
    result = send_email_smtp(to=email, subject=subj, html=html, cc=cc)
    # log to Supabase
    row = {
        "to": email,
        "cc": cc,
        "subject": subj,
        "html": html,
        "status": "sent" if result.get("ok") else "error",
        "provider_message_id": result.get("message_id"),
        "error": result.get("error"),
        "created_at": _utc_now_iso(),
    }
    _sb_insert("emails", row)
    return {"ok": bool(result.get("ok")), "note": "email sent" if result.get("ok") else f"send failed: {result.get('error')}"}

def send_email(to, subject, html, cc=None, bcc=None, text=None, reply_to=None):
    """
    Sends email via SMTP (Gmail App Password) and logs the outcome to Supabase.
    Backward-compatible with prior signature (to, subject, html).
    """
    result = send_email_smtp(
        to=to,
        subject=subject,
        html=html,
        text=text,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
    )
    row = {
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "html": html,
        "status": "sent" if result.get("ok") else "error",
        "provider_message_id": result.get("message_id"),
        "error": result.get("error"),
        "created_at": _utc_now_iso(),
    }
    try:
        _sb_insert("emails", row)
    except Exception:
        pass
    return {"ok": bool(result.get("ok")), "to": to, "subject": subject, "message_id": result.get("message_id"), "error": result.get("error")}

# ---------------- Intake Agent (Normalized Data Capture) ----------------
def create_or_get_caller_id(existing_id=None, source_channel=None):
    """Generate or validate a unique_caller_id for this call session."""
    caller_id = _normalize_caller_id(existing_id)
    # Optional: log call session start
    try:
        _spawn(_sb_insert_async("call_sessions", {
            "unique_caller_id": caller_id,
            "source_channel": source_channel,
            "created_at": _utc_now_iso(),
        }))
    except Exception:
        pass
    return {"ok": True, "unique_caller_id": caller_id}

def get_current_datetime(timezones=None):
    """
    Return current time in UTC and America/Los_Angeles to pin 'today' for the session.
    Robust to missing IANA tzdata: tries zoneinfo, then dateutil, then a fixed-offset fallback.
    """
    if timezones is None:
        timezones = ['UTC', 'America/Los_Angeles']

    from datetime import datetime, timezone, timedelta

    # Try stdlib zoneinfo first
    pt_zone = None
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        try:
            pt_zone = ZoneInfo('America/Los_Angeles')
        except Exception:
            pt_zone = None
    except Exception:
        pt_zone = None

    # Fallback: python-dateutil (if installed)
    if pt_zone is None:
        try:
            from dateutil.tz import gettz
            pt_zone = gettz('America/Los_Angeles') or gettz('US/Pacific')
        except Exception:
            pt_zone = None

    # Last-resort fallback: fixed offset approximating PT (DST heuristic)
    if pt_zone is None:
        now_utc_probe = datetime.now(timezone.utc)
        month = int(now_utc_probe.strftime('%m'))
        offset_hours = -7 if 3 <= month <= 11 else -8  # PDT ~ Mar–Nov, PST otherwise
        pt_zone = timezone(timedelta(hours=offset_hours))

    # Build payload
    now_utc = datetime.now(timezone.utc)
    now_pt = now_utc.astimezone(pt_zone)

    return {
        "epoch_ms": int(now_utc.timestamp() * 1000),
        "utc_iso": now_utc.isoformat().replace("+00:00", "Z"),
        "pt_iso": now_pt.isoformat(),
        "pt_date": now_pt.date().isoformat(),
        "pt_year": now_pt.year,
        "pt_weekday": now_pt.strftime("%A"),
        "pt_time_24": now_pt.strftime("%H:%M"),
        "tz": "America/Los_Angeles"
    }


def upsert_lead_information(unique_caller_id=None, full_name=None, email=None, phone=None, practice_area=None,
                            assigned_attorney=None, summary=None, source_channel=None, caller_type=None,
                            consent_timestamp=None, locale=None, timezone=None):
    """Upsert lead_information keyed by unique_caller_id; generates one if missing/invalid."""
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    # Coerce required fields to safe non-null placeholders if missing to avoid DB NOT NULL errors
    safe_full_name = full_name or "unknown"
    safe_email = email or "unknown"
    safe_phone = phone or "pending"
    safe_practice_area = practice_area or "unsure"
    safe_summary = summary or ""
    row = {
        "unique_caller_id": unique_caller_id,
        "full_name": safe_full_name,
        "email": safe_email,
        "phone": safe_phone,
        "practice_area": safe_practice_area,
        "assigned_attorney": assigned_attorney,
        "summary": safe_summary,
        "source_channel": source_channel,
        "caller_type": caller_type,
        "consent_timestamp": consent_timestamp,
        "locale": locale,
        "timezone": timezone,
        "updated_at": now,
    }
    # Fire-and-forget upsert; return immediately
    _spawn(_sb_upsert_async("lead_information", row, on_conflict="unique_caller_id"))
    return {"ok": True, "unique_caller_id": unique_caller_id}

def save_lead_qa(unique_caller_id=None, email=None, all_q_and_a=None, practice_area_version=None, completion_status="complete"):
    """Insert a Q&A capture row for this call (one write)."""
    now = _utc_now_iso()
     # For returning clients, try to find their existing unique_caller_id
    if not unique_caller_id and email:
        # Try to find their existing unique_caller_id from lead_information table
        if SUPABASE_URL and SUPABASE_KEY:
            headers = _sb_headers()
            url = f"{SUPABASE_URL}/rest/v1/lead_information?email=eq.{email}&select=unique_caller_id&limit=1"
            try:
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data[0].get("unique_caller_id"):
                        unique_caller_id = data[0].get("unique_caller_id")
                        print(f"[DEBUG] Found existing unique_caller_id: {unique_caller_id} for email: {email}")
            except Exception as e:
                print(f"[ERROR] Could not fetch unique_caller_id: {e}")

    # If still no unique_caller_id, generate one
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    # Coerce list
    if all_q_and_a is None:
        all_q_and_a = []
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "all_q_and_a": all_q_and_a,
        "practice_area_version": practice_area_version,
        "completion_status": completion_status or "complete",
        "created_at": now,
        "updated_at": now,
    }
    _spawn(_sb_insert_async("lead_qa", row))
    return {"ok": True, "unique_caller_id": unique_caller_id}

async def save_lead_booking(unique_caller_id=None, email=None, appointment_datetime=None, timezone=None, platform=None,
                            meeting_link=None, phone_number=None, booked_with=None, booking_notes=None):
    """Insert a booking row for this call after Q&A completion. Also tries Google Calendar and sends a confirmation email."""
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)

    google_event_id = None
    final_meeting_link = meeting_link

    # Allow either JSON string or JSON file path
    import os as _os
    sa_json_str  = _os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sa_json_path = _os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")
    have_google_creds = bool(sa_json_str or sa_json_path)

    # Will use this for the email formatting so it reflects any normalization
    normalized_start_dt = None

    if appointment_datetime and have_google_creds:
        try:
            from datetime import datetime as dt, timedelta, timezone as _tz
            try:
                from zoneinfo import ZoneInfo
            except Exception:
                ZoneInfo = None

            # parse incoming ISO and normalize to FUTURE (protect against 2023, etc.)
            start_dt = dt.fromisoformat(appointment_datetime.replace("Z", "+00:00"))
            tz_name = timezone or BUSINESS_TZ

            def _normalize_future(_start_dt, _tzname):
                try:
                    if ZoneInfo and _tzname:
                        local = ZoneInfo(_tzname)
                        now_local = dt.now(local)
                        s_local = _start_dt.astimezone(local)
                    else:
                        now_local = dt.now(_tz.utc)
                        s_local = _start_dt.astimezone(_tz.utc)
                    if s_local < now_local:
                        candidate = s_local.replace(year=now_local.year)
                        if candidate < now_local:
                            try:
                                candidate = candidate.replace(year=now_local.year + 1)
                            except ValueError:
                                # e.g., Feb 29 → Mar 1
                                candidate = candidate.replace(month=3, day=1, year=now_local.year + 1)
                        return candidate.astimezone(_start_dt.tzinfo)
                    return _start_dt
                except Exception:
                    return _start_dt

            orig_start = start_dt
            start_dt = _normalize_future(start_dt, tz_name)
            if start_dt != orig_start:
                print(f"[calendar] normalized past appointment from {orig_start.isoformat()} -> {start_dt.isoformat()}")

            normalized_start_dt = start_dt  # for email formatting later
            end_dt = start_dt + timedelta(minutes=30)

            # Calendar ID (no DWD): sanitize and forbid 'primary'
            cal_id = (GOOGLE_DEFAULT_CALENDAR_ID or "").strip().lstrip("=")
            if not cal_id or cal_id.lower() == "primary":
                print("[google] skipped: in no-DWD mode set GOOGLE_DEFAULT_CALENDAR_ID to a HUMAN calendar email/ID (not 'primary'), shared with the service account.")
            else:
                res = await _google_create_event_async(
                    cal_id,
                    f"Consultation with {booked_with or 'Attorney'}",
                    booking_notes or "",
                    start_dt.isoformat(),
                    end_dt.isoformat(),
                    tz_name,
                    attendees=None,  # ignored in no-DWD helper anyway
                    create_meet=False
                )
                if res.get("ok"):
                    google_event_id = res.get("eventId")

                    # Build canonical, whitespace-proof link: eid = b64url("{eventId} {calendarId}")
                    try:
                        import base64
                        eid = base64.urlsafe_b64encode(f"{google_event_id} {cal_id}".encode("utf-8")).decode("ascii").rstrip("=")
                        canonical_link = f"https://calendar.google.com/calendar/event?eid={eid}"
                    except Exception:
                        canonical_link = res.get("htmlLink")

                    final_meeting_link = canonical_link or res.get("htmlLink")
                    print(f"[google] event created: {google_event_id}, link: {final_meeting_link}")
                else:
                    print(f"[google] create event failed: {res.get('error')}")
        except Exception as e:
            print(f"[google] create event failed: {e}")

    # Step 2: Send confirmation email (use NORMALIZED time if we have it)
    if email:
        try:
            from datetime import datetime as dt
            appt_dt = normalized_start_dt or (dt.fromisoformat(appointment_datetime.replace("Z", "+00:00")) if appointment_datetime else None)
            formatted_time = appt_dt.strftime("%A, %B %d, %Y at %I:%M %p") if appt_dt else "your scheduled time"
            link_html = f'<li>Event Link: <a href="{final_meeting_link}">{final_meeting_link}</a></li>' if final_meeting_link else ""

            html_content = f"""
            <p>Dear {email.split('@')[0]},</p>
            <p>Your consultation with {booked_with or 'our attorney'} has been successfully scheduled.</p>
            <p><strong>Meeting Details:</strong></p>
            <ul>
                <li>Date & Time: {formatted_time} ({timezone or BUSINESS_TZ})</li>
                <li>Platform: {platform or 'Video/Phone'}</li>
                {link_html}
            </ul>
            <p>If you have any questions or need to reschedule, please reply to this email.</p>
            <p>Thank you,<br>Oakwood Law Firm</p>
            """
            subject = f"Consultation Confirmation - {formatted_time}"
            email_result = send_email_smtp(to=email, subject=subject, html=html_content)
            if email_result.get("ok"):
                print(f"[email] confirmation sent to {email}")
            else:
                print(f"[email] failed to send: {email_result.get('error')}")
        except Exception as e:
            print(f"[email] error: {e}")

    # Step 3: DB
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "appointment_datetime": appointment_datetime,
        "timezone": timezone,
        "platform": platform,
        "meeting_link": final_meeting_link,
        "phone_number": phone_number,
        "booked_with": booked_with,
        "booking_notes": booking_notes,
        "google_event_id": google_event_id,
        "created_at": now,
        "updated_at": now,
    }
    _spawn(_sb_insert_async("lead_booking", row))
    return {"ok": True, "unique_caller_id": unique_caller_id, "meeting_link": final_meeting_link, "google_event_id": google_event_id}

def reschedule_lead_booking(
    unique_caller_id,
    email,
    new_appointment_datetime,     # ISO; may include PT offset (-07:00); will be stored as UTC in Calendar
    booked_with,
    old_appointment_datetime=None,# ISO; optional if google_event_id is provided
    google_event_id=None,         # preferred for precise update
    slot_minutes=30,
    calendar_id=None,
    full_name=None,
    phone_number=None,
    practice_area=None,
    platform="video",
    booking_notes=""
):
    """
    Reschedule an existing consultation to a new time.
    - Confirms to 30-minute duration (policy).
    - Stores lead info (name/email/phone/practice area/Caller ID) in the event description.
    - Notifies attendee via Google (sendUpdates='all').
    - Returns meeting link & event id.

    Returns: { ok, google_event_id, old_start_iso, new_start_iso, meeting_link, event_html_link }
    """
    try:
        cal_id = calendar_id or os.getenv("GOOGLE_CALENDAR_ID") or ""
        if not cal_id:
            return {"ok": False, "error": "Missing calendar id. Set GOOGLE_CALENDAR_ID or pass calendar_id."}

        # Build a friendly summary
        pa = (practice_area or "").strip()
        who = (full_name or email or "").strip()
        summary = f"Consultation – {booked_with}"
        if pa:
            summary += f" ({pa})"
        if who:
            summary += f" – {who}"

        # Lead info to embed in description
        desc_fields = {
            "Name": full_name or "",
            "Email": email or "",
            "Phone": phone_number or "",
            "Practice Area": practice_area or "",
            "Caller ID": unique_caller_id or "",
            "Notes": booking_notes or "",
            "Platform": platform or "",
        }

        result = _run_coro_blocking(_gc_reschedule_event(
            cal_id=cal_id,
            new_start_iso=new_appointment_datetime,
            slot_minutes=slot_minutes,
            tz_name="UTC",  # do everything in UTC for robustness
            google_event_id=google_event_id,
            old_start_iso=old_appointment_datetime,
            attendee_email=email,
            attendee_name=full_name,
            summary=summary,
            description_fields=desc_fields
        ))

        # Optional: email confirmation (keeps your existing style)
        try:
            if result.get("ok"):
                old_txt = result.get("old_start_iso") or (old_appointment_datetime or "")
                new_txt = result.get("new_start_iso") or new_appointment_datetime
                meeting_link = result.get("meeting_link") or result.get("event_html_link", "")

                html = f"""Dear {full_name or 'Client'},<br><br>
                Your consultation with <b>{booked_with}</b> has been <b>rescheduled</b>.<br><br>
                <b>Old:</b> {old_txt}<br>
                <b>New:</b> {new_txt} (30 minutes)<br>
                <b>Platform:</b> {platform}<br>
                <b>Join:</b> <a href="{meeting_link}">{meeting_link}</a><br><br>
                If the new time does not work, reply to this email and we’ll find another time.<br><br>
                — Oakwood Law Firm
                """
                _ = send_email({
                    "to": email,
                    "subject": "Your Oakwood Consultation Has Been Rescheduled",
                    "html": html
                })
        except Exception:
            pass

        return result

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------- Safe sync wrapper to avoid event-loop deadlocks ----------
def _run_coro_blocking(coro):
    import threading
    result = {}
    error = {}

    def _runner():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except Exception as e:
            error["e"] = e
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "e" in error:
        raise error["e"]
    return result.get("value")

def get_next_available_slots_sync(count=3, slot_minutes=30, horizon_days=21, tz_name=None, cal_id=None):
    cal_id = cal_id or (GOOGLE_DEFAULT_CALENDAR_ID or "")
    tz_name = tz_name or BUSINESS_TZ
    try:
        return _run_coro_blocking(_gc_get_next_slots(cal_id=cal_id, tz_name=tz_name, slot_minutes=slot_minutes, count=count, horizon_days=horizon_days))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def check_slot_and_alternatives_sync(proposed_start_iso, count=3, slot_minutes=30, tz_name=None, cal_id=None):
    cal_id = cal_id or (GOOGLE_DEFAULT_CALENDAR_ID or "")
    tz_name = tz_name or BUSINESS_TZ
    try:
        return _run_coro_blocking(_gc_check_slot(proposed_start_iso=proposed_start_iso, cal_id=cal_id, tz_name=tz_name, slot_minutes=slot_minutes, count=count))
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------
# Date-specific slots (per-day)
# ------------------------------
def get_slots_for_dates(cal_id, dates, tz_name=None, slot_minutes=30, count_per_day=3):
    """
    Synchronous: For each YYYY-MM-DD (PT), return up to `count_per_day` *available* 30-min slots
    within business hours (Mon–Fri, 9–5 PT). Uses check_slot_and_alternatives_sync so booked
    times are excluded.
    """
    try:
        from datetime import datetime as dt, timedelta
        # Resolve timezone
        tz_name = tz_name or BUSINESS_TZ or "America/Los_Angeles"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            # Fallback: fixed -7/-8 heuristic by month
            month = dt.utcnow().month
            offset = -7 if 3 <= month <= 11 else -8
            from datetime import timezone as _tz, timedelta as _td
            tz = _tz(_td(hours=offset))

        now_local = dt.now(tz)
        out_days = []

        for dstr in dates or []:
            # Parse date
            try:
                y, m, d = map(int, dstr.split("-"))
                day_local = dt(y, m, d, tzinfo=tz)
            except Exception:
                return {"ok": False, "error": f"Bad date format (expected YYYY-MM-DD): {dstr}"}

            # Skip weekends
            if day_local.weekday() >= 5:
                out_days.append({"date": dstr, "slots": []})
                continue

            # Build 30-min candidates 09:00..16:30
            first = day_local.replace(hour=9, minute=0, second=0, microsecond=0)
            last_start = day_local.replace(hour=16, minute=30, second=0, microsecond=0)

            slots = []
            cur = first
            while cur <= last_start and len(slots) < count_per_day:
                # Skip past times if the day is today
                if cur.date() > now_local.date() or cur >= now_local:
                    proposed_iso = cur.isoformat()
                    chk = check_slot_and_alternatives_sync(
                        proposed_start_iso=proposed_iso,
                        cal_id=cal_id,
                        tz_name=tz_name,
                        slot_minutes=slot_minutes,
                        count=3
                    )
                    if chk.get("ok") and chk.get("available"):
                        end_local = cur + timedelta(minutes=slot_minutes)
                        label = cur.strftime("%A, %B %d, %Y at %I:%M %p").lstrip("0") + " PT"
                        slots.append({
                            "start_iso": cur.isoformat(),
                            "end_iso": end_local.isoformat(),
                            "label": label
                        })
                cur += timedelta(minutes=slot_minutes)

            out_days.append({"date": dstr, "slots": slots})

        return {"ok": True, "days": out_days}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------
# Reschedule an existing booking (Supabase lookup -> Google patch, no attendees / no DWD)
# ------------------------------
def reschedule_lead_booking(
    unique_caller_id,
    email,
    booked_with,
    new_appointment_datetime,
    old_appointment_datetime=None,
    google_event_id=None,
    calendar_id=None,
    slot_minutes=30,
    full_name=None,
    phone_number=None,
    practice_area=None,
    platform="video",
    booking_notes=None
):
    """
    Synchronous: Move an existing event to a new time (30 min).
    - If google_event_id is not provided, look up in Supabase by (email + old_appointment_datetime).
    - NO ATTENDEES are added (service account without DWD).
    - sendUpdates='none' to avoid invite emails.
    - Supabase: PATCH the existing row by google_event_id; INSERT if not found.
    """
    try:
        import os, json, base64
        from urllib.parse import quote_plus
        from datetime import datetime as dt, timedelta, timezone as _tz
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        # PT timezone (fallback if ZoneInfo unavailable)
        tz_name = BUSINESS_TZ or "America/Los_Angeles"
        try:
            local_tz = ZoneInfo(tz_name)
        except Exception:
            month = dt.utcnow().month
            offset = -7 if 3 <= month <= 11 else -8
            from datetime import timezone as _tzmod, timedelta as _td
            local_tz = _tzmod(_td(hours=offset))

        # Parse/guard new time
        new_start = dtp.isoparse(new_appointment_datetime)
        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=local_tz)
        else:
            new_start = new_start.astimezone(local_tz)
        if new_start.weekday() >= 5:
            return {"ok": False, "error": "Requested day is on a weekend."}
        if not (9 <= new_start.hour < 17 or (new_start.hour == 17 and new_start.minute == 0)):
            return {"ok": False, "error": "Requested time is outside 9:00 AM–5:00 PM PT."}
        new_end = new_start + timedelta(minutes=int(slot_minutes or 30))

        # If event id missing, fetch from Supabase by (email + old time ± 15m)
        ev_id_source = "arg"
        if not google_event_id:
            if not (email and old_appointment_datetime):
                return {"ok": False, "error": "When google_event_id is not provided, both email and old_appointment_datetime are required."}
            if not SUPABASE_URL or not SUPABASE_KEY:
                return {"ok": False, "error": "Supabase env not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE)."}

            old_local = dtp.isoparse(old_appointment_datetime)
            if old_local.tzinfo is None:
                old_local = old_local.replace(tzinfo=local_tz)
            else:
                old_local = old_local.astimezone(local_tz)
            window = 15
            start_z = (old_local - timedelta(minutes=window)).astimezone(_tz.utc).isoformat().replace("+00:00", "Z")
            end_z   = (old_local + timedelta(minutes=window)).astimezone(_tz.utc).isoformat().replace("+00:00", "Z")

            base = _sb_url("lead_booking")
            q = (
                f"{base}?select=google_event_id,appointment_datetime"
                f"&email=eq.{quote_plus(email)}"
                f"&appointment_datetime=gte.{quote_plus(start_z)}"
                f"&appointment_datetime=lte.{quote_plus(end_z)}"
                f"&order=appointment_datetime.asc&limit=5"
            )
            try:
                r = requests.get(q, headers=_sb_headers(), timeout=15)
                r.raise_for_status()
                recs = r.json() if r.text else []
            except Exception as se:
                return {"ok": False, "error": f"Supabase lookup failed: {se}"}

            best_id, best_delta = None, None
            for rec in recs or []:
                gid = (rec or {}).get("google_event_id")
                appt = (rec or {}).get("appointment_datetime")
                if not (gid and appt):
                    continue
                try:
                    appt_dt = dtp.isoparse(appt).astimezone(local_tz)
                    delta = abs((appt_dt - old_local).total_seconds())
                    if best_id is None or delta < best_delta:
                        best_id, best_delta = gid, delta
                except Exception:
                    continue

            if not best_id:
                return {"ok": False, "error": "No matching booking found in Supabase for the provided email and old time (or booking has no google_event_id)."}
            google_event_id = best_id
            ev_id_source = "supabase"

        # Google service (JSON string or path)
        raw = (GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
        if not raw:
            return {"ok": False, "error": "Missing/invalid GOOGLE_SERVICE_ACCOUNT_JSON (JSON string or file path)."}
        if raw.lstrip().startswith("{"):
            info = json.loads(raw)
        elif os.path.exists(raw):
            with open(raw, "r", encoding="utf-8") as f:
                info = json.load(f)
        else:
            return {"ok": False, "error": "GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON string or a valid path to a JSON file."}

        scopes = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        # Calendar id (human calendar shared with the service account; not 'primary')
        cal_id = (calendar_id or GOOGLE_DEFAULT_CALENDAR_ID or "").strip().lstrip("=")
        if not cal_id or cal_id.lower() == "primary":
            for env_cal in (ATTORNEY_PI_CALENDAR_ID, ATTORNEY_FAMILY_CALENDAR_ID, ATTORNEY_LEMON_CALENDAR_ID):
                if env_cal:
                    cal_id = str(env_cal).strip().lstrip("=")
                    break
        if not cal_id or cal_id.lower() == "primary":
            return {"ok": False, "error": "Missing calendar id. Set GOOGLE_DEFAULT_CALENDAR_ID to a human calendar shared with the service account."}

        # Build patch (NO attendees)
        description_lines = [
            f"Lead: {full_name or '—'} <{email}>",
            f"Phone: {phone_number or '—'}",
            f"Practice Area: {practice_area or '—'}",
            f"Unique Caller ID: {unique_caller_id}",
        ]
        if booking_notes:
            description_lines.append(f"Notes: {booking_notes}")
        if old_appointment_datetime:
            description_lines.append(f"Rescheduled from: {old_appointment_datetime}")

        patch = {
            "summary": f"Consultation – {booked_with}",
            "description": "\n".join(description_lines),
            "start": {"dateTime": new_start.isoformat(), "timeZone": tz_name},
            "end":   {"dateTime": new_end.isoformat(),   "timeZone": tz_name},
            # NO "attendees" in no-DWD mode
        }

        updated = service.events().patch(
            calendarId=cal_id,
            eventId=google_event_id,
            body=patch,
            sendUpdates="none"  # no emails; service account cannot invite without DWD
        ).execute()

        used_event_id = updated.get("id") or google_event_id
        html_link = updated.get("htmlLink")
        # Canonical link (eid = base64url("{eventId} {calendarId}"))
        try:
            eid = base64.urlsafe_b64encode(f"{used_event_id} {cal_id}".encode("utf-8")).decode("ascii").rstrip("=")
            html_link = f"https://calendar.google.com/calendar/event?eid={eid}"
        except Exception:
            pass

        # -------- Supabase: UPDATE then fallback to INSERT --------
        try:
            # Data to persist
            payload = {
                "unique_caller_id": unique_caller_id,
                "email": email,
                "appointment_datetime": new_start.astimezone(_tz.utc).isoformat().replace("+00:00", "Z"),
                "timezone": tz_name,
                "platform": platform,
                "meeting_link": html_link,
                "phone_number": phone_number,
                "booked_with": booked_with,
                "booking_notes": booking_notes or "",
                "google_event_id": used_event_id,
                "updated_at": _utc_now_iso(),
                "note": f"rescheduled via {ev_id_source}"
            }

            # Try PATCH existing row by google_event_id
            url = _sb_url("lead_booking") + f"?google_event_id=eq.{quote_plus(used_event_id)}"
            r = requests.patch(url, headers=_sb_headers(), data=json.dumps(payload), timeout=15)

            # If no row updated (empty [] or 204 with no content), fallback to INSERT
            do_insert = False
            if r.status_code in (200, 201):
                try:
                    body = r.json()
                    if isinstance(body, list) and len(body) == 0:
                        do_insert = True
                except Exception:
                    # some setups return 204 even though we set Prefer; treat as success
                    pass
            elif r.status_code == 204:
                # 204 No Content -> assume success (row existed)
                pass
            else:
                do_insert = True

            if do_insert:
                ins_payload = dict(payload)
                ins_payload.setdefault("created_at", _utc_now_iso())
                _ = _sb_insert("lead_booking", ins_payload)
        except Exception as db_e:
            print(f"[supabase] reschedule upsert failed: {db_e}")

        return {
            "ok": True,
            "google_event_id": used_event_id,
            "meeting_link": html_link,
            "new_appointment_datetime": new_start.isoformat()
        }

    except HttpError as he:
        try:
            body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
        except Exception:
            body = str(he)
        return {"ok": False, "error": f"Google API error: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def save_lead_booking_sync(**kwargs):
    """Sync wrapper for async save_lead_booking that won't deadlock if a loop is running."""
    try:
        return _run_coro_blocking(save_lead_booking(**kwargs))
    except Exception as e:
        print(f"[booking ERROR] {e}")
        return {"ok": False, "error": str(e)}

# Provide ordered practice-area questions for the agent to ask
def get_practice_area_questions(practice_area):
    version_map = {
        "personal_injury": "PI_v1.3",
        "family_law": "FL_v1.0",
        "lemon_law": "LL_v1.2",
    }
    questions_map = {
        "personal_injury": [
            {"id": "accident_date", "question": "What was the date of the accident?", "required": True},
            {"id": "police_report", "question": "Was there a police report?", "required": True},
            # Additional questions can be re-enabled here as needed
        ],
        "family_law": [
            {"id": "issue_type", "question": "What type of family law issue is this?", "required": True},
            {"id": "duration", "question": "How long has this issue been ongoing?", "required": True},
            {"id": "existing_orders", "question": "Are there existing court orders?", "required": True},
            {"id": "children", "question": "Are children involved? If so, how many and ages?", "required": True},
            {"id": "children_concern", "question": "Any immediate concerns regarding the children?", "required": True},
            {"id": "prior_attorney", "question": "Have you worked with an attorney on this before?", "required": True},
            {"id": "mediation", "question": "Have you tried mediation?", "required": True},
            {"id": "desired_outcome", "question": "What outcome are you hoping for?", "required": True}
        ],
        "lemon_law": [
            {"id": "vehicle_year", "question": "What is the vehicle year?", "required": True},
            {"id": "vehicle_make_model", "question": "What is the make and model?", "required": True},
            {"id": "purchase_warranty", "question": "When was it purchased and what warranty applies?", "required": True},
            {"id": "defect_description", "question": "Describe the defect(s).", "required": True},
            {"id": "repair_history", "question": "How many repair attempts and dates?", "required": True},
            {"id": "dealer_manufacturer_interactions", "question": "Any interactions with dealer/manufacturer?", "required": True},
            {"id": "impact_use_value_safety", "question": "How does the issue affect use, value, or safety?", "required": True},
            {"id": "desired_outcome", "question": "What resolution are you seeking?", "required": True}
        ],
    }
    pa = (practice_area or "").strip().lower()
    return {
        "ok": True,
        "practice_area": pa,
        "practice_area_version": version_map.get(pa),
        "questions": questions_map.get(pa, [])
    }
def get_calendar_id_by_practice_area(practice_area):
    """
    Return the appropriate calendar ID based on practice area.
    """
    mapping = {
        "personal_injury": ATTORNEY_PI_CALENDAR_ID or GOOGLE_DEFAULT_CALENDAR_ID,
        "family_law": ATTORNEY_FAMILY_CALENDAR_ID or GOOGLE_DEFAULT_CALENDAR_ID,
        "lemon_law": ATTORNEY_LEMON_CALENDAR_ID or GOOGLE_DEFAULT_CALENDAR_ID
    }

    calendar_id = mapping.get(practice_area, GOOGLE_DEFAULT_CALENDAR_ID)
    if not calendar_id:
        return {"ok": False, "error": f"No calendar configured for practice area: {practice_area}"}

    return {"ok": True, "calendar_id": calendar_id}
def get_booking_info_by_email(email):
    """
    Retrieve comprehensive information for a returning client by email.
    Returns booking history, practice area, and contact information.
    """
    import re

    # Validate email format
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return {"ok": False, "error": "Invalid email format"}

    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "error": "Supabase credentials missing."}

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    # Get client information from lead_information
    client_info = {}
    try:
        info_url = f"{SUPABASE_URL}/rest/v1/lead_information?email=eq.{email}&order=updated_at.desc&limit=1"
        info_resp = requests.get(info_url, headers=headers)
        if info_resp.status_code == 200:
            info_data = info_resp.json()
            if info_data:
                client_info = info_data[0]
    except Exception as e:
        print(f"[ERROR] Could not fetch client info: {e}")

    # Get booking history
    bookings = []
    try:
        bookings_url = f"{SUPABASE_URL}/rest/v1/lead_booking?email=eq.{email}&order=created_at.desc"
        bookings_resp = requests.get(bookings_url, headers=headers)
        if bookings_resp.status_code == 200:
            bookings = bookings_resp.json()
    except Exception as e:
        print(f"[ERROR] Could not fetch bookings: {e}")

    # Get most recent practice area from lead_qa
    current_practice_area = None
    try:
        qa_url = f"{SUPABASE_URL}/rest/v1/lead_qa?email=eq.{email}&order=created_at.desc&limit=1"
        qa_resp = requests.get(qa_url, headers=headers)
        if qa_resp.status_code == 200:
            qa_data = qa_resp.json()
            if qa_data:
                current_practice_area = qa_data[0].get("practice_area")
    except Exception as e:
        print(f"[ERROR] Could not fetch practice area: {e}")

    # If no practice area from QA, try to get it from client info
    if not current_practice_area and client_info:
        current_practice_area = client_info.get("practice_area")

    # Get the most recent booking for backward compatibility
    most_recent_booking = bookings[0] if bookings else {}

    return {
        "ok": True,
        "client_info": client_info,
        "bookings": bookings,
        "current_practice_area": current_practice_area,
        "email": email,
        # Backward compatibility fields
        "booking_id": most_recent_booking.get("id"),
        "calendar_id": most_recent_booking.get("calendar_id"),
        "event_id": most_recent_booking.get("google_event_id"),
        "start_iso": most_recent_booking.get("appointment_datetime"),
        "details": most_recent_booking
    }
def update_client_practice_area(unique_caller_id, email, new_practice_area):
    """
    Update a client's practice area in the database.
    """
    if not unique_caller_id or not email:
        return {"ok": False, "error": "Missing required parameters"}

    # Update lead_information table
    update_data = {
        "practice_area": new_practice_area,
        "updated_at": _utc_now_iso()
    }

    # Use upsert to update the record
    result = _sb_upsert(
        "lead_information", 
        {"unique_caller_id": unique_caller_id, "email": email, **update_data},
        on_conflict="unique_caller_id"
    )

    if result.get("ok"):
        return {"ok": True, "message": "Practice area updated successfully"}
    else:
        return {"ok": False, "error": result.get("error", "Failed to update practice area")}

FUNCTION_MAP = {
    "practice_area": practice_area,
    "contact_information": contact_information,
    "intake_answers_qualification": intake_answers_qualification,
    "practice_area_attorney_name": practice_area_attorney_name,
    "calendar_booking": calendar_booking,
    "reschedule_calendar_booking": reschedule_calendar_booking,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,  # real email now
    "get_booking_info_by_email": get_booking_info_by_email,
    "update_client_practice_area": update_client_practice_area,
    # Intake Agent
    "create_or_get_caller_id": create_or_get_caller_id,
    "upsert_lead_information": upsert_lead_information,
    "save_lead_qa": save_lead_qa,
    "save_lead_booking": save_lead_booking_sync,
    "get_practice_area_questions": get_practice_area_questions,
    "get_calendar_id_by_practice_area": get_calendar_id_by_practice_area,

    "get_next_available_slots": get_next_available_slots_sync,
    "check_slot_and_alternatives": check_slot_and_alternatives_sync,

    "get_current_datetime": get_current_datetime,
    "get_slots_for_dates": get_slots_for_dates,
    "reschedule_lead_booking": reschedule_lead_booking,
}
