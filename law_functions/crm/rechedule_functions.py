# crm/reschedule_functions.py
import os, json, uuid, requests, asyncio, importlib, logging, re, base64
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from ..config import SUPABASE_URL, SUPABASE_KEY, BUSINESS_TZ, TENANT_ID, GOOGLE_DEFAULT_CALENDAR_ID, ATTORNEY_PI_CALENDAR_ID, ATTORNEY_FAMILY_CALENDAR_ID, ATTORNEY_LEMON_CALENDAR_ID
from ..utils.datetime_helpers import _utc_now_iso
from ..db.supabase_helpers import _sb_headers, _sb_url, _sb_insert
from ..calendar.google_calender_helpers import _load_google_creds, _build_event_summary, _build_event_description
from ..booking.booking_functions import _fetch_lead_profile # Import from booking functions

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
                "tenant_id": TENANT_ID,
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