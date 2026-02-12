# booking/booking_functions.py
import os, json, uuid, requests, asyncio, importlib, logging, re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes
from ..config import (
    SUPABASE_URL, 
    SUPABASE_KEY, 
    BUSINESS_TZ, 
    TENANT_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_SERVICE_ACCOUNT_JSON_PATH,
    GOOGLE_DEFAULT_CALENDAR_ID,
    ATTORNEY_PI_CALENDAR_ID,
    ATTORNEY_FAMILY_CALENDAR_ID,
    ATTORNEY_LEMON_CALENDAR_ID,
)
from ..utils.datetime_helpers import _utc_now_iso
from ..utils.id_helpers import _normalize_caller_id
from ..db.supabase_helpers import _sb_headers, _sb_url, _sb_insert_async, _spawn
from ..calendar.google_calender_helpers import _load_google_creds, _google_create_event_async, _build_event_summary, _build_event_description
from ..utils.email_sender import send_email_smtp  # real SMTP sender

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
        "tenant_id": TENANT_ID,
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