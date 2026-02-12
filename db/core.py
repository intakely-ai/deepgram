# db/core.py
import os
from dotenv import load_dotenv
from supabase import create_client, Client

class SupabaseManager:
    _instance = None
    _client: Client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseManager, cls).__new__(cls)
            load_dotenv()
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY")
            if not url or not key:
                raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE/SUPABASE_KEY in environment")
            cls._client = create_client(url, key)
        return cls._instance

    @property
    def client(self) -> Client:
        """Get the singleton Supabase client instance."""
        return self._client

# Convenience function to get the client
def get_client() -> Client:
    """Convenience function to get the Supabase client."""
    return SupabaseManager().client
