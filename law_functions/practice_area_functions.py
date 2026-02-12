from services.database_service import DatabaseService

class PracticeAreaManager:
    def __init__(self):
        self.db = DatabaseService()

    def get_practice_area_details(self, area_code="personal_injury"):
        """Get practice area details from database"""
        result = self.db.client.table("practice_areas").select(
            "practice_area_id, name, area_code, description, specialization_level"
        ).eq("is_active", True).eq("area_code", area_code).single().execute()
        
        return result.data if result else None

    def get_practice_area_attorneys(self, practice_area_id):
        """Get attorneys assigned to practice area"""
        attorneys = self.db.client.table("law_firm_attorney_practice_areas").select(
            "user_profile_id, is_primary"
        ).eq("practice_area_id", practice_area_id).eq("is_active", True).execute()

        if not attorneys.data:
            return []

        # Get attorney details
        attorney_ids = [a["user_profile_id"] for a in attorneys.data]
        profiles = self.db.client.table("user_profiles").select(
            "user_profile_id, contact_id"
        ).in_("user_profile_id", attorney_ids).execute()

        return profiles.data