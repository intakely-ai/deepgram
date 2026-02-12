# db/practice_area_service.py
from typing import Optional, Dict, Any
from .core import get_client

class PracticeAreaService:
    """Service for interacting with practice areas and subtypes."""

    def __init__(self):
        self.client = get_client()

    async def get_practice_area_by_code(self, area_code: str) -> Optional[Dict[str, Any]]:
        """Fetch practice_area row by area_code (returns first match or None)."""
        try:
            # Select specific columns based on schema
            result = self.client.table("practice_areas").select(
                "practice_area_id", "area_code", "name", "description", "category", "specialization_level"
                # Add other columns if needed by application logic
            ).eq("is_active", True).eq("area_code", area_code).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[get_practice_area_by_code] Error fetching practice area '{area_code}': {e}")
            return None

    async def get_subtype_by_code(self, practice_area_id: str, subtype_code: str) -> Optional[Dict[str, Any]]:
        """Fetch practice_area_subtypes row by practice_area_id + subtype_code."""
        try:
            result = self.client.table("practice_area_subtypes").select("*") \
                .eq("practice_area_id", practice_area_id) \
                .eq("subtype_code", subtype_code).eq("is_active", True).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[get_subtype_by_code] Error fetching subtype '{subtype_code}' for practice area '{practice_area_id}': {e}")
            return None

# Global instance for easy access
practice_area_service = PracticeAreaService()
