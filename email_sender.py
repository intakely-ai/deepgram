# email_sender.py
import os
import ssl
import smtplib
from email.message import EmailMessage
from typing import List, Optional, Union

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # STARTTLS
SMTP_USER = os.getenv("SMTP_USER")              # e.g. youraddress@gmail.com
SMTP_PASS = os.getenv("SMTP_PASS")              # App Password (16 chars)
SENDER_NAME = os.getenv("SENDER_NAME", "")      # e.g. "Oakwood Law Firm"

def _normalize_recipients(value: Union[str, List[str], None]) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        # split by comma if a single string with multiple addresses
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return parts
    return [v.strip() for v in value if v and v.strip()]

def send_email_smtp(
    to: Union[str, List[str]],
    subject: str,
    html: str,
    text: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """
    Sends an email via SMTP (Gmail-ready). Returns dict with ok, message_id, error.
    """
    if not SMTP_USER or not SMTP_PASS:
        return {"ok": False, "error": "SMTP_USER/SMTP_PASS not set in environment"}

    to_list = _normalize_recipients(to)
    cc_list = _normalize_recipients(cc)
    bcc_list = _normalize_recipients(bcc)

    if not to_list:
        return {"ok": False, "error": "No 'to' recipients provided"}

    msg = EmailMessage()
    from_header = f"{SENDER_NAME} <{SMTP_USER}>" if SENDER_NAME else SMTP_USER
    msg["From"] = from_header
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject

    # Set body (both text/plain and text/html). Fallback text if not given.
    if not text:
        # very light fallback text from html (strip tags naïvely)
        stripped = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        for tag in ["<p>", "</p>", "<strong>", "</strong>", "<em>", "</em>"]:
            stripped = stripped.replace(tag, "")
        text = stripped
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    # All recipients for SMTP (To + Cc + Bcc)
    all_rcpts = list(dict.fromkeys(to_list + cc_list + bcc_list))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            resp = server.send_message(msg, from_addr=SMTP_USER, to_addrs=all_rcpts)
            # smtplib returns a dict of refused recipients; {} means success.
            if resp:
                return {"ok": False, "error": f"Some recipients refused: {resp}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # EmailMessage generates a Message-ID automatically when sending
    return {"ok": True, "message_id": msg.get("Message-ID")}
