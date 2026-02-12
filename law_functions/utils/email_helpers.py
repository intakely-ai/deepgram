# email/email_functions.py
import os, json, uuid, requests, asyncio, importlib, logging, re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from ..config import SUPABASE_URL, SUPABASE_KEY, TENANT_ID
from ..utils.datetime_helpers import _utc_now_iso
from ..db.supabase_helpers import _sb_insert
from .email_sender import send_email_smtp  # real SMTP sender

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