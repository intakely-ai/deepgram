# email_sender.py
import os, ssl, smtplib
from email.message import EmailMessage
from typing import List, Optional, Union
from dotenv import load_dotenv

# Load .env so this module works in tests and scripts
load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))      # 587=STARTTLS, 465=SSL
SMTP_USER = os.getenv("SMTP_USER")                  # e.g. youraddress@gmail.com OR "apikey" (SendGrid)
SMTP_PASS = os.getenv("SMTP_PASS")                  # Gmail App Password OR SendGrid API key
SENDER_NAME = os.getenv("SENDER_NAME", "")          # e.g. "Oakwood Law Firm"
FROM_EMAIL  = os.getenv("SMTP_FROM_EMAIL") or SMTP_USER

def _normalize_recipients(value: Union[str, List[str], None]) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
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
    if not SMTP_USER or not SMTP_PASS:
        return {"ok": False, "error": "SMTP_USER/SMTP_PASS not set in environment"}

    to_list  = _normalize_recipients(to)
    cc_list  = _normalize_recipients(cc)
    bcc_list = _normalize_recipients(bcc)
    if not to_list:
        return {"ok": False, "error": "No 'to' recipients provided"}

    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{FROM_EMAIL}>" if SENDER_NAME else FROM_EMAIL
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject

    # plain text fallback if none provided (very light)
    if not text:
        stripped = (
            html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
                .replace("</p>", "\n").replace("<p>", "").replace("<strong>", "")
                .replace("</strong>", "").replace("<em>", "").replace("</em>", "")
        )
        text = stripped
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    all_rcpts = list(dict.fromkeys(to_list + cc_list + bcc_list))
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as server:
                server.login(SMTP_USER, SMTP_PASS)
                refused = server.send_message(msg, from_addr=FROM_EMAIL, to_addrs=all_rcpts)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASS)
                refused = server.send_message(msg, from_addr=FROM_EMAIL, to_addrs=all_rcpts)

        if refused:  # dict of recipients that were refused
            return {"ok": False, "error": f"Some recipients refused: {refused}"}
        return {"ok": True, "to": to_list, "cc": cc_list, "bcc": bcc_list, "message_id": msg.get("Message-ID")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
