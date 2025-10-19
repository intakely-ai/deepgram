# config.py
import os

# --- Supabase ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")

# --- Business Logic ---
BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")
DEFAULT_TENANT_ID = "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1"  # Oakwood Law Firm fixed tenant

# --- Google Calendar ---
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
GOOGLE_DEFAULT_CALENDAR_ID = os.getenv("GOOGLE_DEFAULT_CALENDAR_ID")
ATTORNEY_PI_CALENDAR_ID = os.getenv("ATTORNEY_PI_CALENDAR_ID")
ATTORNEY_FAMILY_CALENDAR_ID = os.getenv("ATTORNEY_FAMILY_CALENDAR_ID")
ATTORNEY_LEMON_CALENDAR_ID = os.getenv("ATTORNEY_LEMON_CALENDAR_ID")
GOOGLE_AUTO_MEET = os.getenv("GOOGLE_AUTO_MEET", "true").lower() in ("1", "true", "yes")

# --- Calendar Provider ---
ATTORNEY_CALENDAR_TYPE = os.getenv("ATTORNEY_CALENDAR_TYPE", "google").lower()