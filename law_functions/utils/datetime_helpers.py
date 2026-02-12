# utils/datetime_helpers.py
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes

# ---------------- Time helpers ----------------
def _utc_now_iso() -> str:
    """Return an RFC3339/ISO-8601 timestamp with explicit UTC offset (+00:00)."""
    return dt.now(_tz.utc).isoformat().replace("+00:00", "Z")

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