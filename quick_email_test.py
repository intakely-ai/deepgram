# quick_email_test.py
import os
from dotenv import load_dotenv
from email_sender import send_email_smtp

load_dotenv()
print(send_email_smtp(
    to=os.getenv("SMTP_TO") or os.getenv("SMTP_USER"),
    subject="SMTP test ✓",
    html="<p>This is a test from Oakwood Voice Agent.</p>"
))
