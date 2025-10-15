# calendar/google_calendar_helpers.py
import os, json, requests, asyncio
from datetime import datetime as dt, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ..config import (
    GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SERVICE_ACCOUNT_JSON_PATH,
    GOOGLE_DEFAULT_CALENDAR_ID, GOOGLE_AUTO_MEET, BUSINESS_TZ
)

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