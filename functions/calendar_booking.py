import os
import uuid
from datetime import datetime, timedelta

def calendar_booking(attorney_name: str, start_iso: str, duration_min: int,
                     caller_first_name: str = "", caller_last_name: str = "",
                     email: str = None, cell_phone: str = None, location: str = None):
    """
    Lightweight booking stub. Replace with call to your google_calendar module.
    Returns booking_id and echo of params.
    """
    booking_id = f"bk_{uuid.uuid4().hex[:10]}"
    # compute end time if possible
    end_iso = None
    try:
        from dateutil import parser as dtp
        start = dtp.isoparse(start_iso)
        end = start + timedelta(minutes=int(duration_min))
        end_iso = end.isoformat()
    except Exception:
        end_iso = None

    # In production call google_calendar.create_event(...) here
    return {
        "ok": True,
        "booking_id": booking_id,
        "attorney_name": attorney_name,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "caller_first_name": caller_first_name,
        "caller_last_name": caller_last_name,
        "email": email,
        "cell_phone": cell_phone,
        "location": location,
        "note": "stub — replace with real Google Calendar create_event call"
    }