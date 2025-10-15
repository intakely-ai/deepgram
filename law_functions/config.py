# config.py
import os

# ---------------- Environment ----------------
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")
BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")
# Google Calendar env
GOOGLE_SERVICE_ACCOUNT_JSON       = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")       # full JSON string OR path (legacy)
GOOGLE_SERVICE_ACCOUNT_JSON_PATH  = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")  # preferred: file path
GOOGLE_DEFAULT_CALENDAR_ID        = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID")
ATTORNEY_PI_CALENDAR_ID           = os.getenv("ATTORNEY_PI_CALENDAR_ID")
ATTORNEY_FAMILY_CALENDAR_ID       = os.getenv("ATTORNEY_FAMILY_CALENDAR_ID")
ATTORNEY_LEMON_CALENDAR_ID        = os.getenv("ATTORNEY_LEMON_CALENDAR_ID")
GOOGLE_AUTO_MEET                  = os.getenv("GOOGLE_AUTO_MEET", "true").lower() in ("1", "true", "yes")
TENANT_ID = "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1"  # Oakwood Law Firm fixed tenant