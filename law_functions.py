# law_functions.py
import os, json, uuid, requests, asyncio
from datetime import datetime, timezone
from dateutil import parser as dtp  # keep if you plan to parse dates later

from email_sender import send_email_smtp  # real SMTP sender

# ---------- Env ----------
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")

BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")

# ---------- Time helpers ----------
def _utc_now_iso() -> str:
    """Return an RFC3339/ISO-8601 timestamp with explicit UTC offset (+00:00)."""
    return datetime.now(timezone.utc).isoformat()

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

# Upsert helper (merge by unique constraint)
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

# ---------- Async wrappers (fire-and-forget) ----------
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

# ---------- ID helpers ----------
def _normalize_caller_id(candidate):
    value = (candidate or "").strip()
    if value.lower() in {"", "undefined", "null", "none", "unique_caller_id"}:
        return str(uuid.uuid4())
    try:
        uuid.UUID(value)
        return value
    except Exception:
        return str(uuid.uuid4())

# ---------- Agent-callable functions ----------


def practice_area(practice_area):
    # No DB write here; legacy table 'leads' does not exist. Only echo back.
    return {"ok": True, "practice_area": practice_area}

def contact_information(first_name, last_name, email, cell_phone):
    row = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "cell_phone": cell_phone,
        "created_at": _utc_now_iso()
    }
    _sb_insert("leads", row)
    return {"ok": True, **row}

def intake_answers_qualification(practice_area, answers, qualified=False):
    _sb_insert("intakes", {
        "practice_area": practice_area,
        "answers": answers,
        "qualified": qualified,
        "created_at": _utc_now_iso()
    })
    return {"ok": True, "qualified": qualified}

def practice_area_attorney_name(practice_area):
    mapping = {"personal_injury": "John Doe", "lemon_law": "Jane Roe", "family_law": "Rhonda Fernandez"}
    return {"ok": True, "attorney_name": mapping.get(practice_area)}

def calendar_booking(attorney_name, start_iso, duration_min, caller_first_name, caller_last_name, email=None, cell_phone=None, location=None):
    # Keep calendar mock and avoid writing to non-existent 'bookings' table;
    # saving occurs via save_lead_booking after confirmation.
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
        "created_at": _utc_now_iso(),
    }
    return {"ok": True, "booking_id": booking_ref, **row}

def reschedule_calendar_booking(booking_id, new_start_iso):
    _sb_insert("crm_updates", {
        "fields": {"event": "reschedule_requested", "booking_id": booking_id, "new_start_iso": new_start_iso},
        "created_at": _utc_now_iso()
    })
    return {"ok": True, "booking_id": booking_id, "new_start_iso": new_start_iso, "note": "reschedule logged; calendar not wired yet"}

def terms_of_engagement_letter(email=None, cell_phone=None, cc=None):
    html = "<p>Please review and sign the attached Terms of Engagement (placeholder).</p>"
    subj = "Terms of Engagement (Oakwood Law Firm)"
    # send real email
    result = send_email_smtp(to=email, subject=subj, html=html, cc=cc)
    # log to Supabase
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
    Backward-compatible with prior signature (to, subject, html).
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
    # Optional: log call session start
    try:
        _spawn(_sb_insert_async("call_sessions", {
            "unique_caller_id": caller_id,
            "source_channel": source_channel,
            "created_at": _utc_now_iso(),
        }))
    except Exception:
        pass
    return {"ok": True, "unique_caller_id": caller_id}

def upsert_lead_information(unique_caller_id=None, full_name=None, email=None, phone=None, practice_area=None,
                            assigned_attorney=None, summary=None, source_channel=None, caller_type=None,
                            consent_timestamp=None, locale=None, timezone=None):
    """Upsert lead_information keyed by unique_caller_id; generates one if missing/invalid."""
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    # Coerce required fields to safe non-null placeholders if missing to avoid DB NOT NULL errors
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
    }
    # Fire-and-forget upsert; return immediately
    _spawn(_sb_upsert_async("lead_information", row, on_conflict="unique_caller_id"))
    return {"ok": True, "unique_caller_id": unique_caller_id}

def save_lead_qa(unique_caller_id=None, email=None, all_q_and_a=None, practice_area_version=None, completion_status="complete"):
    """Insert a Q&A capture row for this call (one write)."""
    now = _utc_now_iso()
    # Coerce list
    if all_q_and_a is None:
        all_q_and_a = []
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "all_q_and_a": all_q_and_a,
        "practice_area_version": practice_area_version,
        "completion_status": completion_status or "complete",
        "created_at": now,
        "updated_at": now,
    }
    _spawn(_sb_insert_async("lead_qa", row))
    return {"ok": True, "unique_caller_id": unique_caller_id}

def save_lead_booking(unique_caller_id=None, email=None, appointment_datetime=None, timezone=None, platform=None,
                      meeting_link=None, phone_number=None, booked_with=None, booking_notes=None):
    """Insert a booking row for this call after Q&A completion."""
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "appointment_datetime": appointment_datetime,
        "timezone": timezone,
        "platform": platform,
        "meeting_link": meeting_link,
        "phone_number": phone_number,
        "booked_with": booked_with,
        "booking_notes": booking_notes,
        "created_at": now,
        "updated_at": now,
    }
    _spawn(_sb_insert_async("lead_booking", row))
    return {"ok": True, "unique_caller_id": unique_caller_id}

# Provide ordered practice-area questions for the agent to ask
def get_practice_area_questions(practice_area):
    version_map = {
        "personal_injury": "PI_v1.3",
        "family_law": "FL_v1.0",
        "lemon_law": "LL_v1.2",
    }
    questions_map = {
        "personal_injury": [
            # {"id": "accident_description", "question": "Briefly describe the accident.", "required": True},
            {"id": "accident_date", "question": "What was the date of the accident?", "required": True},
            {"id": "police_report", "question": "Was there a police report?", "required": True},
            # {"id": "witnesses", "question": "Were there any witnesses?", "required": True},
            # {"id": "passengers", "question": "Were there passengers with you?", "required": True},
            # {"id": "damage_extent", "question": "What is the extent of property damage?", "required": True},
            # {"id": "injury_types", "question": "What injuries did you sustain?", "required": True},
            # {"id": "received_treatment", "question": "Did you receive medical treatment?", "required": True},
            # {"id": "still_in_treatment", "question": "Are you still in treatment?", "required": True},
            # {"id": "missed_work", "question": "Did you miss work due to injuries?", "required": True},
            # {"id": "other_party_injuries", "question": "Do you know if others were injured?", "required": True},
            # {"id": "citations", "question": "Were any citations issued, and to whom?", "required": True},
            # {"id": "contacted_insurance", "question": "Have you contacted insurance?", "required": True},
            # {"id": "coverage_type", "question": "What coverage applies (e.g., liability, UM/UIM)?", "required": True},
            # {"id": "repair_estimate", "question": "Do you have a repair estimate?", "required": True},
            # {"id": "settlement_offer", "question": "Has any settlement been offered?", "required": True}
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

FUNCTION_MAP = {

    "practice_area": practice_area,
    "contact_information": contact_information,
    "intake_answers_qualification": intake_answers_qualification,
    "practice_area_attorney_name": practice_area_attorney_name,
    "calendar_booking": calendar_booking,
    "reschedule_calendar_booking": reschedule_calendar_booking,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,  # real email now
   
    # Intake Agent
    "create_or_get_caller_id": create_or_get_caller_id,
    "upsert_lead_information": upsert_lead_information,
    "save_lead_qa": save_lead_qa,
    "save_lead_booking": save_lead_booking,
    "get_practice_area_questions": get_practice_area_questions,
}
