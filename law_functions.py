# main_law_functions.py
# Import from modules
from config import DEFAULT_TENANT_ID
from time_utils import _utc_now_iso, get_current_datetime
from id_utils import _normalize_caller_id
from supabase_client import (
    _sb_headers, _sb_url, _sb_insert, _sb_upsert, _sb_insert_async, _sb_upsert_async, _spawn,
    get_booking_info_by_email, update_client_practice_area, get_lead_name
)
from law_functions.calender_utils import (  # Changed from calender_utils
    get_calendar_provider, get_calendar_id_by_practice_area, get_next_available_slots,
    check_slot_and_alternatives_sync, get_slots_for_dates, save_lead_booking_sync,
    reschedule_lead_booking
)
from lead_management import (
    create_or_get_caller_id, upsert_lead_information, save_lead_qa, get_practice_area_questions, practice_area
)
from email_sender import send_email_smtp  # real SMTP sender

def terms_of_engagement_letter(email=None, cell_phone=None, cc=None):
    html = "<p>Please review and sign the attached Terms of Engagement (placeholder).</p>"
    subj = "Terms of Engagement (Oakwood Law Firm)"
    result = send_email_smtp(to=email, subject=subj, html=html, cc=cc)
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

# ---------------- Function map ----------------
FUNCTION_MAP = {
    "practice_area": practice_area,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,
    # Intake Agent core
    "create_or_get_caller_id": create_or_get_caller_id,
    "get_current_datetime": get_current_datetime,
    "upsert_lead_information": upsert_lead_information,
    "get_practice_area_questions": get_practice_area_questions,
    "save_lead_qa": save_lead_qa,
    # Booking
    "get_calendar_id_by_practice_area": get_calendar_id_by_practice_area,
    "get_next_available_slots": get_next_available_slots,  # Note: This points to the new function that handles both providers
    "check_slot_and_alternatives": check_slot_and_alternatives_sync,
    "get_slots_for_dates": get_slots_for_dates,
    "save_lead_booking": save_lead_booking_sync,  # This now handles both Google and Cal.com
    "reschedule_lead_booking": reschedule_lead_booking,
    # CRM / returning client
    "get_booking_info_by_email": get_booking_info_by_email,
    "update_client_practice_area": update_client_practice_area,
    # New functions
    "get_calendar_provider": get_calendar_provider,
    "get_lead_name": get_lead_name,
}