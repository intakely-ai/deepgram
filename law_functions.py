import os, json, uuid, requests
from datetime import datetime
from dateutil import parser as dtp  # kept if you plan to parse dates later
import pytz

# ---------- Env ----------
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")

BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")

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

# ---------- Agent-callable functions (Supabase logging only) ----------
def inbound_call(caller_id=None, timestamp_iso=None):
    row = {"caller_id": caller_id, "timestamp_iso": timestamp_iso or datetime.utcnow().isoformat()}
    _sb_insert("calls", row)
    return {"ok": True, **row}

def inbound_message(channel, text, message_id=None):
    _sb_insert("messages", {"channel": channel, "text": text, "message_id": message_id, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True}

def outbound_call(to_e164, reason=None):
    _sb_insert("sms", {"to_e164": to_e164, "message": reason or "", "status": "pending", "created_at": datetime.utcnow().isoformat()})
    return {"ok": True}

def practice_area(practice_area):
    _sb_insert("leads", {"practice_area": practice_area, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "practice_area": practice_area}

def contact_information(first_name, last_name, email, cell_phone):
    row = {"first_name": first_name, "last_name": last_name, "email": email, "cell_phone": cell_phone, "created_at": datetime.utcnow().isoformat()}
    _sb_insert("leads", row)
    return {"ok": True, **row}

def intake_answers_qualification(practice_area, answers, qualified=False):
    _sb_insert("intakes", {"practice_area": practice_area, "answers": answers, "qualified": qualified, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "qualified": qualified}

def practice_area_attorney_name(practice_area):
    mapping = {"personal_injury": "John Doe", "lemon_law": "Jane Roe", "family_law": "Rhonda Fernandez"}
    return {"ok": True, "attorney_name": mapping.get(practice_area)}

# For now: calendar/email are NO-OPs that still return ok=True and log to Supabase,
# so your agent doesn't break while we wire the real integrations in next steps.
def calendar_booking(attorney_name, start_iso, duration_min, caller_first_name, caller_last_name, email=None, cell_phone=None, location=None):
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
        "created_at": datetime.utcnow().isoformat(),
    }
    _sb_insert("bookings", row)
    return {"ok": True, "booking_id": booking_ref, **row}

def reschedule_calendar_booking(booking_id, new_start_iso):
    _sb_insert("crm_updates", {"fields": {"event": "reschedule_requested", "booking_id": booking_id, "new_start_iso": new_start_iso}, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "booking_id": booking_id, "new_start_iso": new_start_iso, "note": "reschedule logged; calendar not wired yet"}

def terms_of_engagement_letter(email=None, cell_phone=None):
    _sb_insert("emails", {"to": email, "subject": "Terms of Engagement (pending)", "html": "<p>To be sent by SMTP.</p>", "status": "pending", "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "note": "logged to Supabase; email not sent yet"}

def send_email(to, subject, html):
    _sb_insert("emails", {"to": to, "subject": subject, "html": html, "status": "pending", "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "to": to, "subject": subject, "note": "logged to Supabase; email not sent yet"}

def send_sms(to_e164, message):
    _sb_insert("sms", {"to_e164": to_e164, "message": message, "status": "pending", "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "note": "logged to Supabase; no SMS provider yet"}

def send_whatsapp(to_e164, message):
    return send_sms(to_e164, message)

def send_linkedin_invite(profile_url):
    _sb_insert("crm_updates", {"fields": {"event": "linkedin_invite", "profile_url": profile_url}, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True}

def send_facebook_invite(profile_url):
    _sb_insert("crm_updates", {"fields": {"event": "facebook_invite", "profile_url": profile_url}, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True}

def update_crm(fields=None):
    # ← make fields optional + robust parsing so empty {} calls don't crash
    if not isinstance(fields, dict):
        try:
            fields = json.loads(fields or "{}")
        except Exception:
            fields = {}
    _sb_insert("crm_updates", {"fields": fields, "created_at": datetime.utcnow().isoformat()})
    return {"ok": True, "updated_fields": fields}

FUNCTION_MAP = {
    "inbound_call": inbound_call,
    "inbound_message": inbound_message,
    "outbound_call": outbound_call,
    "practice_area": practice_area,
    "contact_information": contact_information,
    "intake_answers_qualification": intake_answers_qualification,
    "practice_area_attorney_name": practice_area_attorney_name,
    "calendar_booking": calendar_booking,
    "reschedule_calendar_booking": reschedule_calendar_booking,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,
    "send_sms": send_sms,
    "send_whatsapp": send_whatsapp,
    "send_linkedin_invite": send_linkedin_invite,
    "send_facebook_invite": send_facebook_invite,
    "update_crm": update_crm,
}
