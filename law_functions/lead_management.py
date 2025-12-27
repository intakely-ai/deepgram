# lead_management.py
import uuid
import os
import requests
from config import DEFAULT_TENANT_ID, SUPABASE_URL, SUPABASE_KEY
from time_utils import _utc_now_iso
from supabase_client import _sb_insert_async, _sb_upsert_async, _spawn, _sb_headers, _sb_url
from id_utils import _normalize_caller_id

def create_or_get_caller_id(existing_id=None, source_channel=None):
    """Generate or validate a unique_caller_id for this call session."""
    caller_id = _normalize_caller_id(existing_id)
    try:
        _spawn(_sb_insert_async("call_sessions", {
            "unique_caller_id": caller_id,
            "source_channel": source_channel,
            "created_at": _utc_now_iso(),
            "tenant_id": DEFAULT_TENANT_ID
        }))
    except Exception:
        pass
    return {"ok": True, "unique_caller_id": caller_id}

def upsert_lead_information(unique_caller_id=None, full_name=None, email=None, phone=None, practice_area=None,
                            assigned_attorney=None, summary=None, source_channel=None, caller_type=None,
                            consent_timestamp=None, locale=None, timezone=None,tenant_id=None):
    """Upsert lead_information keyed by unique_caller_id; generates one if missing/invalid."""
    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    # Coerce required fields to safe non-null placeholders
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
        "tenant_id": tenant_id or DEFAULT_TENANT_ID,
    }
    _spawn(_sb_upsert_async("lead_information", row, on_conflict="unique_caller_id"))
    return {"ok": True, "unique_caller_id": unique_caller_id}

def save_lead_qa(unique_caller_id=None, email=None,tenant_id=None, all_q_and_a=None, practice_area_version=None, completion_status="complete"):
    """Insert a Q&A capture row for this call (one write)."""
    now = _utc_now_iso()
    # For returning clients, try to find their existing unique_caller_id
    if not unique_caller_id and email and SUPABASE_URL and SUPABASE_KEY:
        headers = _sb_headers()
        url = f"{SUPABASE_URL}/rest/v1/lead_information?email=eq.{email}&select=unique_caller_id&limit=1"
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data and data[0].get("unique_caller_id"):
                    unique_caller_id = data[0].get("unique_caller_id")
                    print(f"[DEBUG] Found existing unique_caller_id: {unique_caller_id} for email: {email}")
        except Exception as e:
            print(f"[ERROR] Could not fetch unique_caller_id: {e}")

    # If still no unique_caller_id, generate one
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    if all_q_and_a is None:
        all_q_and_a = []
    row = {
        "unique_caller_id": unique_caller_id,
        "email": email,
        "tenant_id": tenant_id or DEFAULT_TENANT_ID,
        "all_q_and_a": all_q_and_a,
        "practice_area_version": practice_area_version,
        "completion_status": completion_status or "complete",
        "created_at": now,
        "updated_at": now,
    }
    _spawn(_sb_insert_async("lead_qa", row))
    return {"ok": True, "unique_caller_id": unique_caller_id}

def get_practice_area_questions(practice_area):
    version_map = {
        "personal_injury": "PI_v1.3",
        "family_law": "FL_v1.0",
        "lemon_law": "LL_v1.2",
    }
    questions_map = {
        "personal_injury": [
            {"id": "accident_date", "question": "What was the date of the accident?", "required": True},
            {"id": "police_report", "question": "Was there a police report?", "required": True},
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

def practice_area(practice_area):
    # No DB write here; legacy table 'leads' may not exist. Only echo back.
    return {"ok": True, "practice_area": practice_area}