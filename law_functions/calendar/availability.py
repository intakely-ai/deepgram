# calendar/availability.py
import os, json, uuid, requests, asyncio, importlib, logging, re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes
from ..config import BUSINESS_TZ, GOOGLE_DEFAULT_CALENDAR_ID, ATTORNEY_PI_CALENDAR_ID, ATTORNEY_FAMILY_CALENDAR_ID, ATTORNEY_LEMON_CALENDAR_ID
from ..utils.datetime_helpers import _utc_now_iso
from ..booking.booking_functions import _fetch_lead_profile, _run_coro_blocking # Import from booking functions

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