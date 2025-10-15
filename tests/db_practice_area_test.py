import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

def test_practice_area_via_api():
    """
    Connects to Supabase via HTTPS API (no direct DB ports)
    and verifies access to key tables used in the practice area module.
    """
    try:
        load_dotenv()

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE")

        if not url or not key:
            return {
                "success": False,
                "message": "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE in .env"
            }

        print(f"Connecting via Supabase API: {url}")

        supabase: Client = create_client(url, key)

        # -----------------------------
        # Test 1: Practice Areas
        # -----------------------------
        practice_areas = supabase.table("practice_areas").select(
            "practice_area_id, name, area_code, description, specialization_level"
        ).eq("is_active", True).eq("area_code", "personal_injury").execute()

        # -----------------------------
        # Test 2: Attorney Assignments
        # -----------------------------
        attorneys = supabase.table("user_profiles").select(
            "user_profile_id, contact_id, is_active"
        ).eq("is_active", True).execute()

        # Get related contact + calendar details using multiple joins (if RPC not available)
        # For richer joins, we fetch them separately:
        contacts = supabase.table("contacts").select(
            "contact_id, first_name, last_name, contact_type"
        ).eq("contact_type", "attorney").execute()

        calendar_prefs = supabase.table("calendar_attorney_preferences").select(
            "user_profile_id, timezone"
        ).execute()

        booking_rules = supabase.table("calendar_attorney_booking_rules").select(
            "user_profile_id, min_notice_minutes, max_advance_days"
        ).execute()

        # -----------------------------
        # Test 3: Calendar Providers
        # -----------------------------
        calendar_providers = supabase.table("calendar_providers").select(
            "calendar_provider_id, provider_type, provider_name, is_active"
        ).eq("is_active", True).execute()

        # -----------------------------
        # Return all results
        # -----------------------------
        return {
            "success": True,
            "message": "Supabase API connection successful ✅",
            "data": {
                "practice_areas": practice_areas.data,
                "attorneys": {
                    "profiles": attorneys.data,
                    "contacts": contacts.data,
                    "calendar_preferences": calendar_prefs.data,
                    "booking_rules": booking_rules.data
                },
                "calendar_providers": calendar_providers.data
            }
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Supabase API test failed: {str(e)}"
        }


if __name__ == "__main__":
    result = test_practice_area_via_api()
    print(json.dumps(result, indent=2))
