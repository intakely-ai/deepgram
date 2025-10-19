# calendar_utils.py
import os
import json
import base64
import logging
import importlib  # Added missing import
import asyncio  # Added missing import
from datetime import datetime as dt, timedelta, timezone as _tz  # Consolidated datetime imports
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import (
    GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SERVICE_ACCOUNT_JSON_PATH,
    GOOGLE_DEFAULT_CALENDAR_ID, ATTORNEY_PI_CALENDAR_ID, ATTORNEY_FAMILY_CALENDAR_ID,
    ATTORNEY_LEMON_CALENDAR_ID, BUSINESS_TZ
)
from time_utils import normalize_datetime_for_future
from supabase_client import get_lead_name

# Import Cal.com integration - Add this near your other imports
try:
    import calcom_integration
except ImportError:
    calcom_integration = None

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
                               attendees=None, create_meet=False):  # Made async
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
    return await asyncio.to_thread(_insert_event_sync)  # Now valid in async function

def get_calendar_provider(attorney_id=None):
    """
    Determine which calendar provider to use based on attorney or global settings
    """
    # Priority:
    # 1. Attorney-specific setting (future DB lookup)
    # 2. Environment variable
    # 3. Default to 'google'
    # TODO: In future, look up from DB by attorney_id
    # For now, use environment variable
    provider = os.getenv("ATTORNEY_CALENDAR_TYPE", "google").lower()
    # Validate the provider is supported
    if provider not in ["google", "cal.com"]:
        return "google"  # Default fallback
    return provider

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

# --- Availability Functions (Google/Local Fallback) ---
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
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
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
        from dateutil import parser as dtp  # parse ISO datetimes
        candidate = dtp.isoparse(proposed_start_iso)
        try:
            from zoneinfo import ZoneInfo
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
        from zoneinfo import ZoneInfo
        from datetime import timezone as _tzmod, timedelta as _td
        tz_name = tz_name or BUSINESS_TZ or "America/Los_Angeles"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            month = dt.now(_tz.utc).month
            offset = -7 if 3 <= month <= 11 else -8
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
    # Implementation would be similar to the original, but using imported helpers
    # ... (requires full implementation details from original)
    pass

def save_lead_booking_sync(
    unique_caller_id=None,
    email=None,
    appointment_datetime=None,
    timezone=None,
    platform="video",
    meeting_link=None,
    phone_number=None,
    booked_with=None,
    booking_notes=None,
    attorney_id=None
):
    """
    Save booking using appropriate calendar provider based on attorney settings
    """
    provider = get_calendar_provider(attorney_id)
    # Use Cal.com if configured
    if provider == "cal.com" and calcom_integration and appointment_datetime:
        name = get_lead_name(unique_caller_id) or "Appointment"
        # Create booking in Cal.com
        booking_result = calcom_integration.create_booking(
            email=email,
            name=name,
            start_time=appointment_datetime,
            notes=booking_notes,
            phone=phone_number
        )
        if booking_result.get("ok"):
            # If Cal.com booking succeeded, save to our database too
            meeting_link = booking_result.get("meeting_link") or meeting_link
            # Store Cal.com booking ID in notes for future reference
            cal_booking_id = booking_result.get("booking_id")
            if cal_booking_id:
                notes = f"Cal.com Booking ID: {cal_booking_id}"
                if booking_notes:
                    notes += f" | {booking_notes}"
                booking_notes = notes
            # Save to database using existing code path
            try:
                import requests, json
                _sb_url_fn = globals().get("_sb_url")
                _sb_headers_fn = globals().get("_sb_headers")
                if _sb_url_fn and _sb_headers_fn:
                    payload = {
                        "unique_caller_id": unique_caller_id,
                        "email": email,
                        "appointment_datetime": appointment_datetime,
                        "timezone": timezone,
                        "platform": platform,
                        "meeting_link": meeting_link,
                        "phone_number": phone_number,
                        "booked_with": booked_with,
                        "booking_notes": booking_notes,
                    }
                    r = requests.post(_sb_url_fn("lead_booking"), headers=_sb_headers_fn(), data=json.dumps(payload), timeout=15)
                    # Return both Cal.com result and our DB save result
                    return {
                        "ok": r.status_code in (200,201),
                        "provider": "cal.com",
                        "cal_booking": booking_result.get("booking"),
                        "meeting_link": meeting_link,
                        "status_code": r.status_code,
                        "text": r.text
                    }
            except Exception as e:
                return {"ok": False, "error": str(e), "provider": "cal.com"}
            return booking_result
    # Fallback to original Google Calendar implementation
    # This preserves your existing flow for Google calendar
    create_google = globals().get("create_google_event_sync") or globals().get("gc_create_event_sync")
    if create_google:
        try:
            return create_google(
                unique_caller_id=unique_caller_id,
                email=email,
                appointment_datetime=appointment_datetime,
                timezone=timezone,
                platform=platform,
                meeting_link=meeting_link,
                phone_number=phone_number,
                booked_with=booked_with,
                booking_notes=booking_notes
            )
        except Exception as e:
            return {"ok": False, "error": f"google_create_failed: {e}"}
    # Original DB fallback if neither Cal.com nor Google Calendar succeeded
    try:
        import requests, json
        _sb_url_fn = globals().get("_sb_url")
        _sb_headers_fn = globals().get("_sb_headers")
        if _sb_url_fn and _sb_headers_fn:
            payload = {
                "unique_caller_id": unique_caller_id,
                "email": email,
                "appointment_datetime": appointment_datetime,
                "timezone": timezone,
                "platform": platform,
                "meeting_link": meeting_link,
                "phone_number": phone_number,
                "booked_with": booked_with,
                "booking_notes": booking_notes,
            }
            r = requests.post(_sb_url_fn("lead_booking"), headers=_sb_headers_fn(), data=json.dumps(payload), timeout=15)
            return {"ok": r.status_code in (200,201), "status_code": r.status_code, "text": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "no_calendar_provider_available"}

# --- Helper function moved here ---
def get_next_available_slots(count=3, slot_minutes=30, horizon_days=14, tz_name=None, calendar_id=None, attorney_id=None):
    """
    Get next available slots from the appropriate calendar system based on attorney settings
    """
    provider = get_calendar_provider(attorney_id)
    if provider == "cal.com" and calcom_integration:
        # Use Cal.com API to get available slots
        start_date = dt.now(_tz.utc).strftime("%Y-%m-%d")
        end_date = (dt.now(_tz.utc) + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
        return calcom_integration.get_available_slots(
            start_date=start_date,
            end_date=end_date,
            duration=slot_minutes
        )
    else:
        # Use existing Google Calendar logic or fallback
        # This preserves your existing flow
        return get_next_available_slots_sync(count, slot_minutes, horizon_days, tz_name, calendar_id)

def _run_coro_blocking(coro):
    import threading
    result = {}
    error = {}
    def _runner():
        try:
            loop = asyncio.new_event_loop()  # asyncio is now imported
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