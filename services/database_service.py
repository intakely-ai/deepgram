import os
from dotenv import load_dotenv
from supabase import create_client, Client

class DatabaseService:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseService, cls).__new__(cls)
            load_dotenv()
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE")
            cls._client = create_client(url, key)
        return cls._instance

    @property
    def client(self) -> Client:
        return self._client

    def get_practice_areas(self):
        """Get all active practice areas"""
        return self.client.table("practice_areas").select(
            "practice_area_id, name, area_code, description, specialization_level"
        ).eq("is_active", True).execute()

    def get_attorneys(self):
        """Get all active attorneys with their details"""
        profiles = self.client.table("user_profiles").select(
            "user_profile_id, contact_id, is_active"
        ).eq("is_active", True).execute()

        contacts = self.client.table("contacts").select(
            "contact_id, first_name, last_name, contact_type"
        ).eq("contact_type", "attorney").execute()

        calendar_prefs = self.client.table("calendar_attorney_preferences").select(
            "user_profile_id, timezone"
        ).execute()

        return {
            "profiles": profiles.data,
            "contacts": contacts.data,
            "calendar_preferences": calendar_prefs.data
        }

    def get_calendar_providers(self):
        """Get all active calendar providers"""
        return self.client.table("calendar_providers").select(
            "calendar_provider_id, provider_type, provider_name, is_active"
        ).eq("is_active", True).execute()