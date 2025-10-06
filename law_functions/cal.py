# cal_check.py  (NO-DELEGATE MODE)
from dotenv import load_dotenv
load_dotenv()  # ← load env BEFORE anything reads os.environ

import os, json, sys
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Required envs (NO DWD)
CAL_ID = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID", "").strip()      # human calendar email or secondary calendar ID
print(f"GOOGLE_DEFAULT_CALENDAR_ID='{CAL_ID}'")
SA_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()    # full JSON (optional)
print(f"GOOGLE_SERVICE_ACCOUNT_JSON starts with: '{SA_JSON[:30]}'")
SA_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()# path to JSON (optional)
print(f"GOOGLE_SERVICE_ACCOUNT_JSON_PATH='{SA_PATH}'")

if not CAL_ID:
    sys.exit("Set GOOGLE_DEFAULT_CALENDAR_ID to a human calendar email/ID (not 'primary' in no-DWD mode).")
if CAL_ID.lower() == "primary":
    sys.exit("In NO-DELEGATE mode, do NOT use 'primary'. Use a human calendar email/ID shared with the service account.")

def load_creds():
    scopes = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]
    if SA_JSON.startswith("{"):
        info = json.loads(SA_JSON)
        return Credentials.from_service_account_info(info, scopes=scopes)
    if SA_PATH:
        with open(SA_PATH, "r", encoding="utf-8") as f:
            info = json.load(f)
        return Credentials.from_service_account_info(info, scopes=scopes)
    sys.exit("Set either GOOGLE_SERVICE_ACCOUNT_JSON (full JSON) or GOOGLE_SERVICE_ACCOUNT_JSON_PATH to your .json file.")

print(f"Using calendar ID: {CAL_ID}")
creds = load_creds()
svc = build("calendar", "v3", credentials=creds, cache_discovery=False)

# 1) Verify the service account can see the calendar (must be shared with 'Make changes')
try:
    meta = svc.calendars().get(calendarId=CAL_ID).execute()
    print("calendars.get OK:", {"summary": meta.get("summary"), "id": meta.get("id")})
except HttpError as he:
    body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
    sys.exit(f"calendars.get FAILED for '{CAL_ID}'. Likely not shared or wrong ID.\nHTTP: {body}")

# 2) Insert a tiny test event (NO attendees; NO Meet; NO DWD)
evt = {
    "summary": "SA Write Test",
    "start": {"dateTime": "2025-09-01T10:00:00-07:00", "timeZone": "America/Los_Angeles"},
    "end":   {"dateTime": "2025-09-01T11:00:00-07:00", "timeZone": "America/Los_Angeles"},
}
try:
    created = svc.events().insert(calendarId=CAL_ID, body=evt, sendUpdates="none").execute()
    print("Created:", created.get("id"), created.get("htmlLink"))
except HttpError as he:
    body = he.content.decode() if hasattr(he, "content") and isinstance(he.content, (bytes, bytearray)) else str(he)
    sys.exit(f"events.insert FAILED.\nHTTP: {body}")
