import os, json, asyncio
from datetime import datetime as dt, timedelta, timezone as _tz

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from dateutil import parser as _p
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DEFAULT_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")
TZ_MODE = (os.getenv("AVAIL_TZ_MODE") or "").upper()  # Set to 'UTC' to force UTC-only
# Optional: force PT offset hours globally (e.g., -7 for PDT, -8 for PST)
PT_OFFSET_OVERRIDE = os.getenv("PT_OFFSET_HOURS")

# ------------------------------
# Helpers
# ------------------------------

def _pt_offset_hours_for_pt_date(pt_date=None):
    """
    Return PT UTC offset in hours. Heuristic if tzdata is missing:
    -7 for Mar–Nov (PDT), else -8 (PST).
    Override with PT_OFFSET_HOURS env if provided.
    """
    if PT_OFFSET_OVERRIDE:
        try:
            return int(PT_OFFSET_OVERRIDE)
        except Exception:
            pass
    d = pt_date or dt.utcnow().date()
    m = d.month
    return -7 if 3 <= m <= 11 else -8

def _pt_to_utc(dt_pt_naive, off_hours):
    """Treat dt_pt_naive as PT clock time and convert to aware UTC."""
    return (dt_pt_naive - timedelta(hours=off_hours)).replace(tzinfo=_tz.utc)

def _utc_to_pt(dt_utc_aware, off_hours):
    """Convert aware UTC to naive PT clock time using a fixed offset (no tzdb)."""
    return (dt_utc_aware + timedelta(hours=off_hours)).replace(tzinfo=None)

def _safe_zoneinfo(tz_name):
    """
    Best-effort tzinfo:
    1) stdlib ZoneInfo if available
    2) dateutil.gettz fallback
    3) Fixed offset approximation (DST by month)
    """
    if tz_name is None:
        tz_name = DEFAULT_TZ

    if ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass

    try:
        from dateutil.tz import gettz
        z = gettz(tz_name) or gettz("US/Pacific")
        if z:
            return z
    except Exception:
        pass

    # Final: fixed offset-ish PT
    off = timedelta(hours=_pt_offset_hours_for_pt_date())
    return _tz(off)

def _load_creds():
    scopes = ["https://www.googleapis.com/auth/calendar"]
    sa_json_str  = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    sa_json_path = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if sa_json_str.startswith("{"):
        info = json.loads(sa_json_str)
        return Credentials.from_service_account_info(info, scopes=scopes)
    if sa_json_path:
        with open(sa_json_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        return Credentials.from_service_account_info(info, scopes=scopes)
    raise RuntimeError("No service account creds. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_PATH.")

def _build_service():
    creds = _load_creds()
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def _ceil_to_slot(dt_obj, minutes=30):
    discard = dt_obj.minute % minutes
    if discard == 0 and dt_obj.second == 0 and dt_obj.microsecond == 0:
        return dt_obj.replace(second=0, microsecond=0)
    delta = minutes - discard
    return (dt_obj + timedelta(minutes=delta)).replace(second=0, microsecond=0)

def _generate_free_slots_from_busy(busy_intervals, start_dt, end_dt, now_dt, slot_minutes=30):
    """All datetimes passed here should be timezone-aware (UTC)."""
    free = []
    cursor = start_dt
    for (bs, be) in busy_intervals:
        if be <= cursor:
            continue
        if bs > cursor:
            free.append((cursor, min(bs, end_dt)))
        cursor = max(cursor, be)
        if cursor >= end_dt:
            break
    if cursor < end_dt:
        free.append((cursor, end_dt))

    slots = []
    cur = now_dt
    if cur < start_dt:
        cur = start_dt
    cur = _ceil_to_slot(cur, slot_minutes)
    while cur + timedelta(minutes=slot_minutes) <= end_dt:
        conflict = any(cur < be and bs < cur + timedelta(minutes=slot_minutes) for (bs, be) in busy_intervals)
        if not conflict:
            slots.append((cur, cur + timedelta(minutes=slot_minutes)))
        cur += timedelta(minutes=slot_minutes)
    return slots

# ------------------------------
# Google FreeBusy
# ------------------------------

async def _freebusy_async(calendar_id, time_min_iso, time_max_iso, tz_name):
    cal_id = (calendar_id or "").strip().lstrip("=")
    if not cal_id or cal_id.lower() == "primary":
        return {"ok": False, "error": "Invalid calendar_id for no-delegation mode."}

    query_tz = "UTC" if TZ_MODE == "UTC" or (tz_name or "").upper() == "UTC" else (tz_name or DEFAULT_TZ)

    def _query():
        svc = _build_service()
        body = {
            "timeMin": time_min_iso,
            "timeMax": time_max_iso,
            "timeZone": query_tz,
            "items": [{"id": cal_id}],
        }
        return svc.freebusy().query(body=body).execute()

    try:
        resp = await asyncio.to_thread(_query)
        raw_busy = (resp.get("calendars", {}).get(cal_id, {}) or {}).get("busy", [])
        busy_utc = []
        for b in raw_busy:
            s = _p.isoparse(b["start"])
            e = _p.isoparse(b["end"])
            # Normalize to UTC regardless of query timezone
            if s.tzinfo is None:
                s = s.replace(tzinfo=_tz.utc)
            else:
                s = s.astimezone(_tz.utc)
            if e.tzinfo is None:
                e = e.replace(tzinfo=_tz.utc)
            else:
                e = e.astimezone(_tz.utc)
            busy_utc.append((s, e))
        busy_utc.sort(key=lambda x: x[0])
        return {"ok": True, "busy": busy_utc}
    except HttpError as he:
        try:
            body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
        except Exception:
            body = str(he)
        return {"ok": False, "error": f"Google API error: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------
# Public API
# ------------------------------

async def get_next_available_slots(cal_id, tz_name=None, slot_minutes=30, count=3, horizon_days=21):
    """
    Return up to `count` upcoming free 9–5 PT slots within `horizon_days`.
    Works in UTC-only mode when AVAIL_TZ_MODE=UTC or tz_name='UTC'.
    """
    use_utc = TZ_MODE == "UTC" or (tz_name or "").upper() == "UTC"

    now_utc = dt.now(_tz.utc)
    horizon_utc = now_utc + timedelta(days=horizon_days)

    time_min_iso = now_utc.isoformat().replace("+00:00", "Z")
    time_max_iso = horizon_utc.isoformat().replace("+00:00", "Z")

    fb = await _freebusy_async(cal_id, time_min_iso, time_max_iso, "UTC" if use_utc else (tz_name or DEFAULT_TZ))
    if not fb.get("ok"):
        return {"ok": False, "error": fb.get("error")}
    busy_utc = fb["busy"]

    slots_out = []

    # Determine today's PT date
    off_now = _pt_offset_hours_for_pt_date()
    now_pt = _utc_to_pt(now_utc, off_now)
    cur_day_pt = now_pt.date()

    # Iterate day by day in PT
    while len(slots_out) < count:
        # weekdays only (PT)
        if cur_day_pt.weekday() < 5:
            off = _pt_offset_hours_for_pt_date(cur_day_pt)

            day_start_pt = dt(cur_day_pt.year, cur_day_pt.month, cur_day_pt.day, 9, 0, 0)
            day_end_pt   = dt(cur_day_pt.year, cur_day_pt.month, cur_day_pt.day, 17, 0, 0)
            day_start_utc = _pt_to_utc(day_start_pt, off)
            day_end_utc   = _pt_to_utc(day_end_pt, off)

            # Busy intervals overlapping this PT work window (in UTC)
            day_busy = []
            for (bs, be) in busy_utc:
                if be <= day_start_utc or bs >= day_end_utc:
                    continue
                day_busy.append((max(bs, day_start_utc), min(be, day_end_utc)))
            day_busy.sort(key=lambda x: x[0])

            day_now_utc = now_utc if cur_day_pt == now_pt.date() else day_start_utc

            day_slots = _generate_free_slots_from_busy(day_busy, day_start_utc, day_end_utc, day_now_utc, slot_minutes)

            # Label and return slots in PT (with fixed-offset tzinfo)
            pt_tz = _tz(timedelta(hours=off))
            for (ss_utc, se_utc) in day_slots:
                ss_pt = ss_utc.astimezone(pt_tz)
                se_pt = se_utc.astimezone(pt_tz)
                label = ss_pt.strftime("%A, %B %d, %Y at %I:%M %p").lstrip("0") + " PT"
                slots_out.append({
                    "start_iso": ss_pt.isoformat(),
                    "end_iso": se_pt.isoformat(),
                    "label": label
                })
                if len(slots_out) >= count:
                    break

        # Stop if beyond horizon
        if _pt_to_utc(dt(cur_day_pt.year, cur_day_pt.month, cur_day_pt.day, 23, 59, 59), _pt_offset_hours_for_pt_date(cur_day_pt)) > horizon_utc:
            break

        cur_day_pt = cur_day_pt + timedelta(days=1)

    return {"ok": True, "slots": slots_out}

async def check_slot_and_alternatives(proposed_start_iso, cal_id, tz_name=None, slot_minutes=30, count=3):
    """
    Validate proposed PT slot (ISO may contain -07:00/-08:00 offset). If unavailable, return alternatives.
    Works without IANA tzdata by using the ISO's fixed offset and UTC internally.
    """
    # Parse proposed time
    try:
        start = dt.fromisoformat(proposed_start_iso.replace("Z", "+00:00"))
        if start.tzinfo is None:
            # Assume provided time is PT clock with current heuristic offset
            off = _pt_offset_hours_for_pt_date()
            start = start.replace(tzinfo=_tz(timedelta(hours=off)))
    except Exception as e:
        return {"ok": False, "error": f"Bad start ISO: {e}"}

    # UTC references
    start_utc = start.astimezone(_tz.utc)
    end_utc = start_utc + timedelta(minutes=slot_minutes)
    now_utc = dt.now(_tz.utc)

    # Policy checks (use caller's provided local offset for weekday/hour)
    reason = None
    if start_utc < now_utc:
        reason = "Requested time is in the past."
    else:
        local_hour = start.hour
        local_min = start.minute
        local_wd = start.weekday()  # 0=Mon, 6=Sun in the proposed local offset
        if local_wd >= 5:
            reason = "Requested day is on a weekend."
        elif not (9 <= local_hour < 17 or (local_hour == 17 and local_min == 0)):
            reason = "Requested time is outside 9:00 AM–5:00 PM PT."

    # Freebusy for PT day that contains 'start'
    day_start_local = start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(_tz.utc)
    day_end_utc = day_end_local.astimezone(_tz.utc)

    fb_day = await _freebusy_async(cal_id,
                                   day_start_utc.isoformat().replace("+00:00", "Z"),
                                   day_end_utc.isoformat().replace("+00:00", "Z"),
                                   "UTC")
    if not fb_day.get("ok"):
        return {"ok": False, "error": fb_day.get("error")}
    busy_utc = fb_day["busy"]

    # Conflicts?
    def overlaps(s1, e1, s2, e2):
        return s1 < e2 and s2 < e1

    conflict = any(overlaps(start_utc, end_utc, bs, be) for (bs, be) in busy_utc)

    if not reason and not conflict:
        return {"ok": True, "available": True}

    # Alternatives (from the same PT day forward)
    alternatives = []
    cur_day_local = day_start_local.date()
    pt_tz = start.tzinfo  # fixed offset tz from the provided ISO

    while len(alternatives) < count:
        # Weekdays only
        wd_probe = dt(cur_day_local.year, cur_day_local.month, cur_day_local.day, 12, 0, tzinfo=pt_tz).weekday()
        if wd_probe < 5:
            ds_local = dt(cur_day_local.year, cur_day_local.month, cur_day_local.day, 9, 0, tzinfo=pt_tz)
            de_local = dt(cur_day_local.year, cur_day_local.month, cur_day_local.day, 17, 0, tzinfo=pt_tz)

            ds_utc = ds_local.astimezone(_tz.utc)
            de_utc = de_local.astimezone(_tz.utc)

            # Freebusy for that PT day (if not the first day we already fetched)
            if cur_day_local != day_start_local.date():
                fb2 = await _freebusy_async(cal_id,
                                            ds_utc.isoformat().replace("+00:00", "Z"),
                                            de_utc.isoformat().replace("+00:00", "Z"),
                                            "UTC")
                if not fb2.get("ok"):
                    return {"ok": False, "error": fb2.get("error")}
                day_busy = fb2["busy"]
            else:
                # Restrict busy to the 9–5 window on the first day
                day_busy = []
                for (bs, be) in busy_utc:
                    if be <= ds_utc or bs >= de_utc:
                        continue
                    day_busy.append((max(bs, ds_utc), min(be, de_utc)))

            day_now_utc = start_utc if cur_day_local == start.astimezone(pt_tz).date() else ds_utc
            day_slots = _generate_free_slots_from_busy(day_busy, ds_utc, de_utc, day_now_utc, slot_minutes)

            for (ss_utc, se_utc) in day_slots:
                ss_local = ss_utc.astimezone(pt_tz)
                se_local = se_utc.astimezone(pt_tz)
                label = ss_local.strftime("%A, %B %d, %Y at %I:%M %p").lstrip("0") + " PT"
                alternatives.append({
                    "start_iso": ss_local.isoformat(),
                    "end_iso": se_local.isoformat(),
                    "label": label
                })
                if len(alternatives) >= count:
                    break

        cur_day_local = cur_day_local + timedelta(days=1)

    return {
        "ok": True,
        "available": False,
        "reason": reason or "Slot conflicts with an existing event.",
        "alternatives": alternatives
    }
