# law_functions.py

import os, json, uuid, requests, asyncio, importlib, logging, re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dateutil import parser as dtp  # parse ISO datetimes

from email_sender import send_email_smtp  # real SMTP sender

# ---------------- Google Calendar provider (optional) ----------------
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

# ---------------- Environment ----------------
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")

BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")

# Google Calendar env
GOOGLE_SERVICE_ACCOUNT_JSON       = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")       # full JSON string OR path (legacy)
GOOGLE_SERVICE_ACCOUNT_JSON_PATH  = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")  # preferred: file path
GOOGLE_DEFAULT_CALENDAR_ID        = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID")
ATTORNEY_PI_CALENDAR_ID           = os.getenv("ATTORNEY_PI_CALENDAR_ID")
ATTORNEY_FAMILY_CALENDAR_ID       = os.getenv("ATTORNEY_FAMILY_CALENDAR_ID")
ATTORNEY_LEMON_CALENDAR_ID        = os.getenv("ATTORNEY_LEMON_CALENDAR_ID")
GOOGLE_AUTO_MEET                  = os.getenv("GOOGLE_AUTO_MEET", "true").lower() in ("1", "true", "yes")

# ---------------- Time helpers ----------------
def _utc_now_iso() -> str:
    """Return an RFC3339/ISO-8601 timestamp with explicit UTC offset (+00:00)."""
    return dt.now(_tz.utc).isoformat().replace("+00:00", "Z")

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

# ---------------- ID helpers ----------------
def _normalize_caller_id(candidate):
    value = (candidate or "").strip()
    if value.lower() in {"", "undefined", "null", "none", "unique_caller_id"}:
        return str(uuid.uuid4())
    try:
        uuid.UUID(value)
        return value
    except Exception:
        return str(uuid.uuid4())

# ---------------- Google Calendar helpers (NO delegation) ----------------
def _load_google_creds():
    """
    Load Google service-account credentials from either:
    - GOOGLE_SERVICE_ACCOUNT_JSON (full JSON string), or
    - GOOGLE_SERVICE_ACCOUNT_JSON_PATH (path to JSON file),
    - or legacy: GOOGLE_SERVICE_ACCOUNT_JSON if it contains a valid file path.
    """
    sa_json_str  = (GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    sa_json_path = (GOOGLE_SERVICE_ACCOUNT_JSON_PATH or "").strip()

    scopes = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]

    # Full JSON in env var
    if sa_json_str.startswith("{"):
        info = json.loads(sa_json_str)
        return Credentials.from_service_account_info(info, scopes=scopes)

    # Preferred: explicit PATH env var
    if sa_json_path:
        with open(sa_json_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        return Credentials.from_service_account_info(info, scopes=scopes)

    # Legacy: env contains a path
    if sa_json_str and os.path.exists(sa_json_str):
        with open(sa_json_str, "r", encoding="utf-8") as f:
            info = json.load(f)
        return Credentials.from_service_account_info(info, scopes=scopes)

    return None

async def _google_create_event_async(calendar_id, summary, description, start_iso, end_iso, tz,
                                     attendees=None, create_meet=False):
    """
    Creates a Google Calendar event using a service account WITHOUT domain-wide delegation.
    - Requires calendar_id to be a HUMAN calendar that is shared with the service account.
    - No attendees, no Meet in no-DWD mode.
    """
    def _insert_event_sync():
        cal_id = (calendar_id or "").strip().lstrip("=")
        if not cal_id:
            return {"ok": False, "error": "Missing calendar_id. Set GOOGLE_DEFAULT_CALENDAR_ID to a human calendar email/ID."}
        if cal_id.lower() == "primary":
            return {"ok": False, "error": "In no-delegation mode 'primary' is invalid. Use a human calendar ID shared with the service account."}

        creds = _load_google_creds()
        if not creds:
            return {"ok": False, "error": "No service account creds. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_PATH."}

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            event = {
                "summary": summary or "Consultation",
                "description": (description or ""),
                "start": {"dateTime": start_iso, "timeZone": tz},
                "end":   {"dateTime": end_iso,   "timeZone": tz},
            }
            created = service.events().insert(calendarId=cal_id, body=event, sendUpdates="none").execute()
            return {"ok": True, "eventId": created.get("id"), "htmlLink": created.get("htmlLink")}
        except HttpError as he:
            try:
                body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
            except Exception:
                body = str(he)
            return {"ok": False, "error": f"Google API error: {body}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return await asyncio.to_thread(_insert_event_sync)

# ---------------- Agent-callable functions ----------------
def practice_area(practice_area):
    # No DB write here; legacy table 'leads' may not exist. Only echo back.
    return {"ok": True, "practice_area": practice_area}

def terms_of_engagement_letter(email=None, cell_phone=None, cc=None):
    html = "<p>Please review and sign the attached Terms of Engagement (placeholder).</p>"
    subj = "Terms of Engagement (Oakwood Law Firm)"
    result = send_email_smtp(to=email, subject=subj, html=html, cc=cc)
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
    try:
        _spawn(_sb_insert_async("call_sessions", {
            "unique_caller_id": caller_id,
            "source_channel": source_channel,
            "created_at": _utc_now_iso(),
            "tenant_id": "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1"  # Oakwood Law Firm fixed tenant
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

    # Try stdlib zoneinfo first
    pt_zone = None
    try:
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
        month = dt.now(_tz.utc).month
        offset_hours = -7 if 3 <= month <= 11 else -8  # PDT ~ Mar–Nov, PST otherwise
        from datetime import timezone as _tzmod, timedelta as _td
        pt_zone = _tzmod(_td(hours=offset_hours))

    now_utc = dt.now(_tz.utc)
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
                            consent_timestamp=None, locale=None, timezone=None,tenant_id=None):
    """Upsert lead_information keyed by unique_caller_id; generates one if missing/invalid."""
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    # Coerce required fields to safe non-null placeholders
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
        "tenant_id": tenant_id or "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1" ,
    }
    _spawn(_sb_upsert_async("lead_information", row, on_conflict="unique_caller_id"))
    return {"ok": True, "unique_caller_id": unique_caller_id}

def save_lead_qa(unique_caller_id=None, email=None,tenant_id=None, all_q_and_a=None, practice_area_version=None, completion_status="complete"):
    """Insert a Q&A capture row for this call (one write)."""
    now = _utc_now_iso()

    # For returning clients, try to find their existing unique_caller_id
    if not unique_caller_id and email and SUPABASE_URL and SUPABASE_KEY:
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
    if all_q_and_a is None:
        all_q_and_a = []

    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "tenant_id": tenant_id or "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1",
        "all_q_and_a": all_q_and_a,
        "practice_area_version": practice_area_version,
        "completion_status": completion_status or "complete",
        "created_at": now,
        "updated_at": now,
    }
    _spawn(_sb_insert_async("lead_qa", row))
    return {"ok": True, "unique_caller_id": unique_caller_id}

# ---------------- Helpers for booking metadata ----------------
def _fetch_lead_profile(unique_caller_id=None, email=None):
    """
    Return (full_name, phone, practice_area) from lead_information, preferring unique_caller_id then email.
    """
    full_name = phone = practice_area = None
    if SUPABASE_URL and SUPABASE_KEY:
        headers = _sb_headers()
        try:
            if unique_caller_id:
                url = f"{_sb_url('lead_information')}?unique_caller_id=eq.{requests.utils.quote(unique_caller_id)}&select=full_name,phone,practice_area&limit=1"
                r = requests.get(url, headers=headers, timeout=10); r.raise_for_status()
                data = r.json() or []
                if data:
                    rec = data[0]
                    full_name = rec.get("full_name") or full_name
                    phone = rec.get("phone") or phone
                    practice_area = rec.get("practice_area") or practice_area
            if (not full_name or not phone or not practice_area) and email:
                url = f"{_sb_url('lead_information')}?email=eq.{requests.utils.quote(email)}&select=full_name,phone,practice_area&order=updated_at.desc&limit=1"
                r = requests.get(url, headers=headers, timeout=10); r.raise_for_status()
                data = r.json() or []
                if data:
                    rec = data[0]
                    full_name = full_name or rec.get("full_name")
                    phone = phone or rec.get("phone")
                    practice_area = practice_area or rec.get("practice_area")
        except Exception as e:
            logging.exception("Lead profile fetch failed: %s", e)
    return full_name, phone, practice_area

def _build_event_summary(booked_with, lead_name):
    """
    Required format: Consultation – {Attorney Name} with {Lead Name}
    """
    atty = (booked_with or "Attorney").strip()
    lname = (lead_name or "Client").strip()
    return f"Consultation – {atty} with {lname}"

def _build_event_description(full_name, email, phone, practice_area, unique_caller_id, booking_notes=None, old_appointment_datetime=None):
    lines = [
        f"Lead: {full_name or '—'} <{email or '—'}>",
        f"Phone: {phone or '—'}",
        f"Practice Area: {practice_area or '—'}",
        f"Unique Caller ID: {unique_caller_id or '—'}",
    ]
    if booking_notes:
        lines.append(f"Notes: {booking_notes}")
    if old_appointment_datetime:
        lines.append(f"Rescheduled from: {old_appointment_datetime}")
    return "\n".join(lines)

# ---------------- Booking (create) ----------------
async def save_lead_booking(unique_caller_id=None, email=None, appointment_datetime=None, timezone=None, platform=None,
                            meeting_link=None, phone_number=None, booked_with=None, booking_notes=None):
    """
    Insert a booking row for this call after Q&A completion.
    Creates Google Calendar event (no DWD) if creds+calendar configured, then emails a confirmation.
    """
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)

    # Enrich from profile so we can format title/description consistently
    prof_name, prof_phone, prof_practice = _fetch_lead_profile(unique_caller_id=unique_caller_id, email=email)
    lead_name = prof_name or (email.split("@")[0] if email else "Client")
    phone_for_desc = phone_number or prof_phone
    practice_for_desc = prof_practice

    google_event_id = None
    final_meeting_link = meeting_link

    # Allow either JSON string or JSON file path
    sa_json_str  = (GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    sa_json_path = (GOOGLE_SERVICE_ACCOUNT_JSON_PATH or "").strip()
    have_google_creds = bool(sa_json_str or sa_json_path)

    # Will use this for the email formatting so it reflects any normalization
    normalized_start_dt = None

    if appointment_datetime and have_google_creds:
        try:
            # parse incoming ISO and normalize to FUTURE (protect against e.g., past-year input)
            start_dt = dt.fromisoformat(appointment_datetime.replace("Z", "+00:00"))
            tz_name = timezone or BUSINESS_TZ

            def _normalize_future(_start_dt, _tzname):
                try:
                    local = ZoneInfo(_tzname)
                    now_local = dt.now(local)
                    s_local = _start_dt.astimezone(local)
                    if s_local < now_local:
                        candidate = s_local.replace(year=now_local.year)
                        if candidate < now_local:
                            try:
                                candidate = candidate.replace(year=now_local.year + 1)
                            except ValueError:
                                # Feb 29 edge → Mar 1 next year
                                candidate = candidate.replace(month=3, day=1, year=now_local.year + 1)
                        return candidate.astimezone(_start_dt.tzinfo)
                    return _start_dt
                except Exception:
                    return _start_dt

            orig_start = start_dt
            start_dt = _normalize_future(start_dt, tz_name)
            if start_dt != orig_start:
                print(f"[calendar] normalized past appointment from {orig_start.isoformat()} -> {start_dt.isoformat()}")

            normalized_start_dt = start_dt
            end_dt = start_dt + timedelta(minutes=30)

            # Calendar ID (no DWD): sanitize and forbid 'primary'
            cal_id = (GOOGLE_DEFAULT_CALENDAR_ID or "").strip().lstrip("=")
            if not cal_id or cal_id.lower() == "primary":
                print("[google] skipped: in no-DWD mode set GOOGLE_DEFAULT_CALENDAR_ID to a HUMAN calendar email/ID (not 'primary'), shared with the service account.")
            else:
                event_summary = _build_event_summary(booked_with, lead_name)
                event_description = _build_event_description(
                    full_name=lead_name,
                    email=email,
                    phone=phone_for_desc,
                    practice_area=practice_for_desc,
                    unique_caller_id=unique_caller_id,
                    booking_notes=booking_notes
                )

                res = await _google_create_event_async(
                    cal_id,
                    event_summary,
                    event_description,
                    start_dt.isoformat(),
                    end_dt.isoformat(),
                    tz_name,
                    attendees=None,
                    create_meet=False
                )
                if res.get("ok"):
                    google_event_id = res.get("eventId")

                    # Canonical link: eid = b64url("{eventId} {calendarId}")
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
            appt_dt = normalized_start_dt or (dt.fromisoformat(appointment_datetime.replace("Z", "+00:00")) if appointment_datetime else None)
            formatted_time = appt_dt.strftime("%A, %B %d, %Y at %I:%M %p") if appt_dt else "your scheduled time"
            link_html = f'<li>Event Link: <a href="{final_meeting_link}">{final_meeting_link}</a></li>' if final_meeting_link else ""

            html_content = f"""
            <p>Dear {lead_name},</p>
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
        "phone_number": phone_number or phone_for_desc,
        "booked_with": booked_with,
        "booking_notes": booking_notes,
        "google_event_id": google_event_id,
        "created_at": now,
        "updated_at": now,
        "tenant_id": "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1",
    }
    _spawn(_sb_insert_async("lead_booking", row))
    return {"ok": True, "unique_caller_id": unique_caller_id, "meeting_link": final_meeting_link, "google_event_id": google_event_id}

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

def save_lead_booking_sync(**kwargs):
    """
    Sync wrapper for async save_lead_booking with a single-appointment guard:
    - If a future appointment already exists for this email, return an error so the agent can reschedule.
    """
    try:
        email = kwargs.get("email")
        if email and SUPABASE_URL and SUPABASE_KEY:
            from urllib.parse import quote_plus
            now_z = dt.now(_tz.utc).isoformat().replace("+00:00", "Z")
            q = (
                f"{_sb_url('lead_booking')}?email=eq.{quote_plus(email)}"
                f"&appointment_datetime=gte.{quote_plus(now_z)}&select=id,appointment_datetime&limit=1"
            )
            r = requests.get(q, headers=_sb_headers(), timeout=10); r.raise_for_status()
            if (r.json() or []):
                return {"ok": False, "error": "Client already has a future appointment. Please reschedule instead.", "error_code": "already_has_future_booking"}

        return _run_coro_blocking(save_lead_booking(**kwargs))
    except Exception as e:
        print(f"[booking ERROR] {e}")
        return {"ok": False, "error": str(e)}

# ---------------- Practice area Qs ----------------
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

    return {"ok": True, "calendar_id": (calendar_id or "").strip().lstrip("=")}

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

# ---------------- Slots & Availability ----------------
def get_next_available_slots_sync(count=3, slot_minutes=30, horizon_days=21, tz_name=None, cal_id=None):
    cal_id = cal_id or (GOOGLE_DEFAULT_CALENDAR_ID or "")
    tz_name = tz_name or BUSINESS_TZ
    # Try provider
    if _gc_get_next_slots:
        try:
            res = _run_coro_blocking(_gc_get_next_slots(cal_id=cal_id, tz_name=tz_name, slot_minutes=slot_minutes, count=count, horizon_days=horizon_days))
            # Fallback if provider reports missing creds or fails
            if isinstance(res, dict) and res.get("ok"):
                return res
            if isinstance(res, dict) and (("No service account creds" in (res.get("error") or "")) or ("creds" in (res.get("error") or "").lower())):
                pass  # fall through to local
            else:
                # If provider failed for other reasons, still fall back to local to keep flow smooth
                pass
        except Exception as e:
            logging.exception("google_calendar_availability get_next_available_slots failed: %s", e)

    # Local fallback: generate simple weekday 9:00–16:30 PT slots
    try:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = _tz.utc
        now_local = dt.now(tz)
        slots = []
        candidate = now_local

        # start at the next 9:00 slot (or now if within business day)
        candidate = candidate.replace(hour=9, minute=0, second=0, microsecond=0)
        if candidate <= now_local:
            candidate = now_local

        while len(slots) < count and (candidate.date() - now_local.date()).days <= horizon_days:
            day = candidate
            # Move to next business day at 9:00 if after hours or weekend
            if day.weekday() >= 5 or day.hour >= 17:
                day = (day + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                candidate = day
                continue
            if day.hour < 9:
                day = day.replace(hour=9, minute=0, second=0, microsecond=0)

            cur = day
            last_start = day.replace(hour=16, minute=30, second=0, microsecond=0)
            while cur <= last_start and len(slots) < count:
                if cur > now_local and cur.weekday() < 5:
                    slots.append({
                        "start_iso": cur.isoformat(),
                        "end_iso": (cur + timedelta(minutes=slot_minutes)).isoformat(),
                        "label": cur.strftime("%A, %B %d, %Y at %I:%M %p").lstrip("0") + " PT"
                    })
                cur += timedelta(minutes=slot_minutes)

            candidate = (day + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

        return {"ok": True, "slots": slots}
    except Exception as fe:
        return {"ok": False, "error": f"Availability fallback failed: {fe}"}

def check_slot_and_alternatives_sync(proposed_start_iso, count=3, slot_minutes=30, tz_name=None, cal_id=None):
    cal_id = cal_id or (GOOGLE_DEFAULT_CALENDAR_ID or "")
    tz_name = tz_name or BUSINESS_TZ

    # Try provider
    if _gc_check_slot:
        try:
            res = _run_coro_blocking(_gc_check_slot(proposed_start_iso=proposed_start_iso, cal_id=cal_id, tz_name=tz_name, slot_minutes=slot_minutes, count=count))
            if isinstance(res, dict) and res.get("ok"):
                return res
            if isinstance(res, dict) and (("No service account creds" in (res.get("error") or "")) or ("creds" in (res.get("error") or "").lower())):
                pass  # fall through
            else:
                pass
        except Exception as e:
            logging.exception("google_calendar_availability check failed: %s", e)

    # Basic local validation fallback:
    try:
        candidate = dtp.isoparse(proposed_start_iso)
        try:
            tz = ZoneInfo(tz_name)
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=tz)
            else:
                candidate = candidate.astimezone(tz)
        except Exception:
            pass
        # weekend guard
        if candidate.weekday() >= 5:
            return {"ok": True, "available": False, "reason": "Requested time is on a weekend."}
        # business hours guard 9:00-17:00 (end exclusive)
        if not (9 <= candidate.hour < 17 or (candidate.hour == 17 and candidate.minute == 0)):
            return {"ok": True, "available": False, "reason": "Requested time is outside 9:00 AM–5:00 PM PT."}
        # If we reach here, optimistic "available"
        return {"ok": True, "available": True, "note": "No calendar provider; optimistic availability"}
    except Exception as e:
        return {"ok": False, "error": f"Slot check failed: {e}"}

def get_slots_for_dates(cal_id, dates, tz_name=None, slot_minutes=30, count_per_day=3):
    """
    Synchronous: For each YYYY-MM-DD (PT), return up to `count_per_day` *available* 30-min slots
    within business hours (Mon–Fri, 9–5 PT). Uses check_slot_and_alternatives_sync so booked
    times are excluded.
    """
    try:
        tz_name = tz_name or BUSINESS_TZ or "America/Los_Angeles"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            month = dt.now(_tz.utc).month
            offset = -7 if 3 <= month <= 11 else -8
            from datetime import timezone as _tzmod, timedelta as _td
            tz = _tzmod(_td(hours=offset))

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

# ---------------- Reschedule (lookup fallback) ----------------
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
    - If google_event_id is not provided, look up in Supabase by (email + old_appointment_datetime ±15m).
    - No attendees; no sendUpdates (service account without DWD).
    - Supabase: PATCH existing row by google_event_id; INSERT if not found.
    """
    try:
        import base64

        # PT timezone (fallback if ZoneInfo unavailable)
        tz_name = BUSINESS_TZ or "America/Los_Angeles"
        try:
            local_tz = ZoneInfo(tz_name)
        except Exception:
            month = dt.now(_tz.utc).month
            off = -7 if 3 <= month <= 11 else -8
            from datetime import timezone as _tzmod, timedelta as _td
            local_tz = _tzmod(_td(hours=off))

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
                f"&email=eq.{requests.utils.quote(email)}"
                f"&appointment_datetime=gte.{requests.utils.quote(start_z)}"
                f"&appointment_datetime=lte.{requests.utils.quote(end_z)}"
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

        # Google service creds
        creds = _load_google_creds()
        if not creds:
            return {"ok": False, "error": "Missing/invalid Google service account credentials."}
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        # Calendar id: use provided or resolve defaults
        cal_id = (calendar_id or GOOGLE_DEFAULT_CALENDAR_ID or "").strip().lstrip("=")
        if not cal_id or cal_id.lower() == "primary":
            for env_cal in (ATTORNEY_PI_CALENDAR_ID, ATTORNEY_FAMILY_CALENDAR_ID, ATTORNEY_LEMON_CALENDAR_ID):
                if env_cal:
                    cal_id = str(env_cal).strip().lstrip("=")
                    break
        if not cal_id or cal_id.lower() == "primary":
            return {"ok": False, "error": "Missing calendar id. Set GOOGLE_DEFAULT_CALENDAR_ID to a human calendar shared with the service account."}

        # Ensure we have a lead name/phone/practice for description and title parity
        lead_name, lead_phone, lead_pa = full_name, phone_number, practice_area
        if not (lead_name and lead_phone and lead_pa):
            prof_name, prof_phone, prof_pa = _fetch_lead_profile(unique_caller_id=unique_caller_id, email=email)
            lead_name = lead_name or prof_name or (email.split("@")[0] if email else "Client")
            lead_phone = lead_phone or prof_phone
            lead_pa = lead_pa or prof_pa

        # Build patch (NO attendees) with parity description
        summary = _build_event_summary(booked_with, lead_name)
        description = _build_event_description(
            full_name=lead_name,
            email=email,
            phone=lead_phone,
            practice_area=lead_pa,
            unique_caller_id=unique_caller_id,
            booking_notes=booking_notes,
            old_appointment_datetime=old_appointment_datetime
        )
        patch = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": new_start.isoformat(), "timeZone": tz_name},
            "end":   {"dateTime": new_end.isoformat(),   "timeZone": tz_name},
        }

        updated = service.events().patch(
            calendarId=cal_id,
            eventId=google_event_id,
            body=patch,
            sendUpdates="none"
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
            payload = {
                "unique_caller_id": unique_caller_id,
                "email": email,
                "appointment_datetime": new_start.astimezone(_tz.utc).isoformat().replace("+00:00", "Z"),
                "timezone": tz_name,
                "platform": platform,
                "meeting_link": html_link,
                "phone_number": lead_phone,
                "booked_with": booked_with,
                "booking_notes": booking_notes or "",
                "google_event_id": used_event_id,
                "updated_at": _utc_now_iso(),
                "tenant_id": "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1",
                # "note": f"rescheduled via {ev_id_source}"
            }

            # Try PATCH existing row by google_event_id
            url = _sb_url("lead_booking") + f"?google_event_id=eq.{requests.utils.quote(used_event_id)}"
            r = requests.patch(url, headers=_sb_headers(), data=json.dumps(payload), timeout=15)

            # If no row updated, fallback to INSERT
            do_insert = False
            if r.status_code in (200, 201):
                try:
                    body = r.json()
                    if isinstance(body, list) and len(body) == 0:
                        do_insert = True
                except Exception:
                    pass
            elif r.status_code == 204:
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

# ---------------- Function map ----------------
FUNCTION_MAP = {
    "practice_area": practice_area,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,

    # Intake Agent core
    "create_or_get_caller_id": create_or_get_caller_id,
    "get_current_datetime": get_current_datetime,
    "upsert_lead_information": upsert_lead_information,
    "get_practice_area_questions": get_practice_area_questions,
    "save_lead_qa": save_lead_qa,

    # Booking
    "get_calendar_id_by_practice_area": get_calendar_id_by_practice_area,
    "get_next_available_slots": get_next_available_slots_sync,
    "check_slot_and_alternatives": check_slot_and_alternatives_sync,
    "get_slots_for_dates": get_slots_for_dates,
    "save_lead_booking": save_lead_booking_sync,
    "reschedule_lead_booking": reschedule_lead_booking,

    # CRM / returning client
    "get_booking_info_by_email": get_booking_info_by_email,
    "update_client_practice_area": update_client_practice_area,
}
