# db/question_attorney_service.py
import uuid
from typing import Optional, Dict, Any, List
from .core import get_client
from .practice_area_service import practice_area_service

class QuestionAttorneyService:
    """Service for fetching questions and attorneys."""

    def __init__(self):
        self.client = get_client()
        self.pa_service = practice_area_service # Dependency

    async def get_questions_for_practice_area_subtype(
        self,
        practice_area_code: str,
        subtype_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Return intake_questions rows for the given practice_area_code and optional subtype_code.
        Uses practice_area (VARCHAR) and state_name (VARCHAR) columns in queries.
        """
        try:
            pa = await self.pa_service.get_practice_area_by_code(practice_area_code)
            if not pa:
                print(f"[get_questions] practice area not found: {practice_area_code}")
                return []

            # Build base query for intake_questions using practice_area VARCHAR
            query_select_fields = ",".join([
                "question_id",
                "practice_area", # VARCHAR - Primary filter
                "state_name",    # VARCHAR - Subtype filter (schema uses this for subtype)
                "question_text",
                "display_order",
                "validation_rules", # JSONB
                "options"          # JSONB
            ])

            query = self.client.table("intake_questions").select(query_select_fields)

            # Filter by practice area code (VARCHAR) and active status
            query = query.eq("practice_area", practice_area_code).eq("is_active", True)

            # Add subtype (state_name) filter if provided
            if subtype_code:
                query = query.eq("state_name", subtype_code)

            # Execute query ordered by display_order
            result = query.order("display_order").execute()

            # Return the list of questions (empty list if none found)
            return result.data if result.data else []

        except Exception as e:
            print(f"[get_questions_for_practice_area_subtype] Error fetching questions for '{practice_area_code}' (subtype: {subtype_code}): {e}")
            return []

    async def get_attorney_for_practice_area_subtype(
        self,
        practice_area_code: str,
        subtype_code: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find primary attorney assigned for a practice area / optional subtype.
        Queries law_firm_practice_areas using practice_area_id and subtype_id (if applicable).
        Returns contact row (contacts) for the assigned_contact_id.
        """
        try:
            # --- Step 1: Get practice_area_id ---
            pa = await self.pa_service.get_practice_area_by_code(practice_area_code)
            if not pa:
                print(f"[get_attorney] practice area not found: {practice_area_code}")
                return None
            practice_area_id = pa["practice_area_id"]

            # --- Step 2: Find attorney assignment in law_firm_practice_areas ---
            # Build base query for assignment
            query = self.client.table("law_firm_practice_areas").select(
                "assigned_contact_id" # , subtype_id, is_primary if needed for complex logic
            ).eq("practice_area_id", practice_area_id).eq("is_active", True) # Ensure active assignment

            # Add subtype filter if subtype_code is provided
            if subtype_code:
                # First, get the subtype_id
                subtype = await self.pa_service.get_subtype_by_code(practice_area_id, subtype_code)
                if subtype:
                    # Filter assignment by subtype_id
                    query = query.eq("subtype_id", subtype["subtype_id"])
                else:
                    # If subtype not found, log and potentially fallback
                    # For now, let's proceed with practice area level query
                    print(f"[get_attorney] subtype '{subtype_code}' not found for practice area '{practice_area_code}', searching general assignment.")
                    # You might choose to return None here if subtype-specific assignment is mandatory
                    # Or continue with the practice-area level query (without subtype filter)
                    # Let's assume we proceed with the query as is (practice area level)

            # Execute query (potentially filtered by subtype_id)
            # If subtype_id was not found, this query will look for *any* active assignment for the practice area
            # You might refine this to specifically look for is_primary=True if that's the logic
            query = query.eq("is_primary", True) # Add if is_primary determines the main attorney
            assignment_result = query.limit(1).execute() # Get one assignment

            if not assignment_result.data:
                print(f"[get_attorney] no active attorney assignment found for practice area '{practice_area_code}' (subtype: {subtype_code})")
                return None

            assigned_contact_id = assignment_result.data[0].get("assigned_contact_id")
            if not assigned_contact_id:
                print(f"[get_attorney] assignment found but assigned_contact_id is null for practice area '{practice_area_code}'")
                return None

            # --- Step 3: Get contact details from contacts table ---
            # Query contacts table for the attorney's details using assigned_contact_id
            # Ensure column names match the schema (e.g., primary_email, cell_phone_number)
            contact_result = self.client.table("contacts").select(
                "contact_id",
                "first_name",
                "last_name",
                "cell_phone_number", # Use correct column name from schema
                "primary_email",    # Use correct column name from schema (was 'email')
                "calendar_config_id" # Include if needed for calendar integration
                # Add other relevant contact fields if required by the application
            ).eq("contact_id", assigned_contact_id
            ).eq("contact_type", "attorney" # Ensure we're getting an attorney contact
            ).eq("is_active", True).execute() # Ensure the contact is active

            if not contact_result.data:
                 print(f"[get_attorney] Contact details not found for active attorney contact ID '{assigned_contact_id}'.")
                 return None

            # Return the first (and presumably primary/selected) attorney's contact details
            return contact_result.data[0]

        except Exception as e:
            print(f"[get_attorney_for_practice_area_subtype] Error fetching attorney for '{practice_area_code}' (subtype: {subtype_code}): {e}")
            return None

# Global instance for easy access
question_attorney_service = QuestionAttorneyService()
