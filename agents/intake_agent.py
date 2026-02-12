# agents/intake_agent.py
import os
import json
import uuid
import requests
import asyncio
import importlib
import logging
import re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes
from typing import Optional, Dict, List, Any # Import necessary types

from ..law_functions.config import SUPABASE_URL, SUPABASE_KEY, BUSINESS_TZ, TENANT_ID
from ..law_functions.utils.datetime_helpers import _utc_now_iso, get_current_datetime
from ..law_functions.utils.id_helpers import _normalize_caller_id
from ..law_functions.db.supabase_helpers import _sb_headers, _sb_url, _sb_upsert_async, _sb_insert_async, _spawn, _sb_upsert
# Import the DynamicDataService facade - Ensure the path is correct based on your structure
from ..db.dynamic_data_service import DynamicDataService # Adjust import path if needed

logger = logging.getLogger(__name__)

# --- Agent-callable functions (Updated for Personal Injury & Dynamic Data) ---

async def practice_area(practice_area_code: str) -> Dict[str, Any]:
    """Echo back the practice area. No DB write here for legacy reasons."""
    # Enforce Personal Injury Only
    if practice_area_code != "personal_injury":
        logger.warning(f"[practice_area] Requested non-PI area: {practice_area_code}. Denying.")
        return {"ok": False, "error": "Only Personal Injury cases are supported at this time."}
    return {"ok": True, "practice_area": practice_area_code}

async def create_or_get_caller_id(existing_id: Optional[str] = None, source_channel: Optional[str] = None) -> Dict[str, Any]:
    """Generate or validate a unique_caller_id for this call session."""
    caller_id = _normalize_caller_id(existing_id)
    try:
        _spawn(_sb_insert_async("call_sessions", {
            "unique_caller_id": caller_id,
            "source_channel": source_channel,
            "created_at": _utc_now_iso(),
            "tenant_id": TENANT_ID  # Oakwood Law Firm fixed tenant
        }))
    except Exception:
        pass # Silently handle DB errors for session creation
    return {"ok": True, "unique_caller_id": caller_id}

async def get_current_datetime(timezones: Optional[List[str]] = None) -> Dict[str, Any]:
    """Return current time in UTC and America/Los_Angeles to pin 'today' for the session."""
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

async def upsert_lead_information(
    unique_caller_id: Optional[str] = None,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    practice_area_code: str = "personal_injury", # Default to PI, enforce PI
    summary: Optional[str] = None,
    source_channel: Optional[str] = None,
    caller_type: Optional[str] = None,
    consent_timestamp: Optional[str] = None,
    locale: Optional[str] = None,
    timezone: Optional[str] = None,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create or update lead_information keyed by unique_caller_id; generates one if missing/invalid. Enforces Personal Injury."""
    # Enforce Personal Injury Only
    if practice_area_code != "personal_injury":
        logger.warning(f"[upsert_lead_information] Attempted to save non-PI lead: {practice_area_code}. Denying.")
        return {"ok": False, "error": "Only Personal Injury leads are accepted at this time."}

    now = _utc_now_iso()
    unique_caller_id = _normalize_caller_id(unique_caller_id)
    # Coerce required fields to safe non-null placeholders
    safe_full_name = full_name or "unknown"
    safe_email = email or "unknown"
    safe_phone = phone or "pending"
    safe_practice_area = practice_area_code or "personal_injury" # Enforce PI
    safe_summary = summary or ""
    row = {
        "unique_caller_id": unique_caller_id,
        "full_name": safe_full_name,
        "email": safe_email,
        "phone": safe_phone,
        "practice_area": safe_practice_area, # Use 'practice_area' (VARCHAR) column directly
        "assigned_attorney": None, # Will be assigned later
        "summary": safe_summary, # Use 'summary' -> 'case_summary' mapping in service if needed
        "source_channel": source_channel,
        "caller_type": caller_type,
        "consent_timestamp": consent_timestamp,
        "locale": locale,
        "timezone": timezone,
        "updated_at": now,
        "tenant_id": tenant_id or TENANT_ID,
    }
    _spawn(_sb_upsert_async("lead_information", row, on_conflict="unique_caller_id"))
    return {"ok": True, "unique_caller_id": unique_caller_id}

# --- Core Dynamic Data Functions ---

async def get_practice_area_questions(practice_area_code: str, subtype_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches dynamic questions for a given practice area and optional subtype.
    Uses DynamicDataService.
    """
    # Enforce Personal Injury Only
    if practice_area_code != "personal_injury":
        logger.warning(f"[get_practice_area_questions] Requested non-PI area: {practice_area_code}. Denying.")
        return {"ok": False, "error": "Only Personal Injury cases are supported at this time."}

    try:
        logger.info(f"[get_practice_area_questions] Fetching questions for PA: {practice_area_code}, Subtype: {subtype_code}")
        service = DynamicDataService() # Instantiate the service

        # 1. Get Practice Area Details (for version/name if needed)
        pa_details = await service.get_practice_area_by_code(practice_area_code)
        if not pa_details:
            logger.warning(f"[get_practice_area_questions] Practice area '{practice_area_code}' not found in DB.")
            return {"ok": False, "error": f"Practice area '{practice_area_code}' not found."}

        # Derive version, perhaps from pa_details or statically
        version = pa_details.get("name", practice_area_code) # Fallback to code

        # 2. Fetch Questions using the service
        questions = await service.get_questions_for_practice_area_subtype(practice_area_code, subtype_code)

        logger.info(f"[get_practice_area_questions] Fetched {len(questions)} questions.")
        return {
            "ok": True,
            "practice_area": practice_area_code,
            "practice_area_version": version,
            "questions": questions # This list comes directly from the service
        }
    except Exception as e:
        logger.error(f"[get_practice_area_questions] Error fetching questions for PA '{practice_area_code}', Subtype '{subtype_code}': {e}")
        return {"ok": False, "error": f"Failed to fetch questions: {str(e)}"}

async def save_lead_qa(
    unique_caller_id: str,
    email: str,
    tenant_id: str,
    all_q_and_a: List[Dict[str, Any]],
    practice_area_version: str, # This should be the practice_area_code like 'personal_injury'
    completion_status: str = "complete",
    session_id: Optional[str] = None # Crucial for linking responses
) -> Dict[str, Any]:
    """
    Save the completed Q&A for a lead using DynamicDataService.
    Requires session_id to link responses.
    """
    # Enforce Personal Injury Only (implicitly via practice_area_version context)
    if practice_area_version != "personal_injury":
        logger.warning(f"[save_lead_qa] Attempted to save QA for non-PI area: {practice_area_version}. Denying.")
        return {"ok": False, "error": "Only Personal Injury QA is accepted at this time."}

    try:
        logger.info(f"[save_lead_qa] Saving QA for caller ID: {unique_caller_id}, Email: {email}")
        now = _utc_now_iso()

        # --- Critical: Ensure session_id is available ---
        if not session_id:
            # Try to fetch session_id from intake_leads using unique_caller_id or email
            # This requires a direct Supabase call or a helper in DynamicDataService
            # For now, let's assume it's passed or fetched correctly upstream.
            # If missing here, it's a problem.
            logger.error("[save_lead_qa] session_id is required but was None.")
            return {"ok": False, "error": "Session ID is required to save Q&A."}

        # Use DynamicDataService
        service = DynamicDataService()

        # --- Save each Q&A item ---
        results = []
        for qa_item in all_q_and_a:
            # Extract data - adjust based on actual QA item structure from agent
            question_id = qa_item.get("question_id") # Might be None for freeform
            question_text = qa_item.get("question") or qa_item.get("question_text")
            answer_text = qa_item.get("answer")
            answer_metadata = qa_item.get("metadata") or {}
            # state_name could be subtype_code or derived context
            state_name_context = None # Or derive from practice_area_version if it encodes subtype

            if question_text and answer_text: # Basic validation
                # Call the service method for each Q&A item
                # Pass session_id, question details, answer details, context
                qa_result = await service.save_lead_qa_response(
                    session_id=session_id, # <-- Now available
                    question_id=question_id,
                    state_name=state_name_context, # <-- Context (subtype)
                    question_text=question_text,
                    answer_text=answer_text,
                    answer_metadata=answer_metadata # Pass if exists
                    # confidence_score=? # Add if agent provides or calculated
                )
                results.append(qa_result)
                if not qa_result.get("ok"):
                    logger.warning(f"[save_lead_qa] Error saving individual QA: {qa_result.get('error')}")
                    # Decide: Log and continue, or return error immediately?
                    # For now, log and continue to try saving others.
            else:
                logger.warning(f"[save_lead_qa] Skipping invalid QA item: {qa_item}")
                # results.append({"ok": False, "error": "Invalid QA item structure"})
                # Decide how to handle skipped items

        # --- Check overall success of saving all Q&A items ---
        all_ok = all(r.get("ok") for r in results)
        if all_ok:
            logger.info(f"[save_lead_qa] Saved {len(results)} Q&A items successfully.")
            return {
                "ok": True,
                "unique_caller_id": unique_caller_id,
                "message": f"Saved {len(results)} Q&A items.",
                "practice_area_version": practice_area_version,
                "completion_status": completion_status or "complete",
            }
        else:
            # Find first error or aggregate errors
            first_error = next((r.get("error") for r in results if not r.get("ok")), "Unknown QA save error")
            logger.error(f"[save_lead_qa] Some Q&A items failed to save: {first_error}")
            return {"ok": False, "error": f"Some Q&A items failed to save: {first_error}"}

    except Exception as e:
        logger.error(f"[save_lead_qa] Error saving Q&A for caller ID '{unique_caller_id}': {e}")
        return {"ok": False, "error": str(e)}

# --- Practice area Qs (Legacy - Remove or Comment Out) ---
# def get_practice_area_questions_old(practice_area):
#     # ... old hardcoded logic ...
#     pass

# --- Export functions for FUNCTION_MAP ---
# Ensure the names exported match the keys expected in FUNCTION_MAP in law_functions.py
# get_practice_area_questions = get_practice_area_questions # Updated version
# upsert_lead_information = upsert_lead_information     # Updated version
# save_lead_qa = save_lead_qa                             # Updated version
# Ensure other functions like save_lead_booking are also updated and exported correctly
