# db/dynamic_data_helpers.py
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List
from dotenv import load_dotenv
from supabase import create_client, Client

class DynamicDataService:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DynamicDataService, cls).__new__(cls)
            load_dotenv()
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE")
            if not url or not key:
                raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE from environment variables.")
            cls._client = create_client(url, key)
        return cls._instance

    @property
    def client(self) -> Client:
        return self._client

    # --- Core Data Access Methods ---

    async def get_practice_area_by_code(self, area_code: str) -> Optional[Dict]:
        """
        Fetch practice area details by area code.
        Queries the 'practice_areas' table using 'area_code'.
        """
        try:
            # Select relevant fields from practice_areas table
            # Ensure column names match database.sql.txt schema for practice_areas
            result = self.client.table("practice_areas").select(
                "practice_area_id", "area_code", "name", "description", "category", "specialization_level"
                # Add other columns as needed by the application
            ).eq("area_code", area_code).execute()
            
            if not result.data:
                print(f"[get_practice_area_by_code] Practice area not found: {area_code}")
                return None
                
            return result.data[0]
        except Exception as e:
            print(f"[get_practice_area_by_code] Error fetching practice area '{area_code}': {str(e)}")
            return None

    async def get_questions_for_practice_area_subtype(
        self,
        practice_area_code: str,
        subtype_code: Optional[str] = None # Interpreted as 'state_name' based on schema
    ) -> List[Dict]:
        """
        Fetch questions for a practice area and optional subtype (state_name).
        Queries the 'intake_questions' table using 'practice_area' (VARCHAR) and 'state_name' (VARCHAR).
        Aligns with database.sql.txt schema for intake_questions.
        """
        try:
            # --- Align with database.sql.txt schema for intake_questions ---
            # The schema shows:
            # - question_id (uuid)
            # - tenant_id (uuid) -- Potentially relevant for filtering
            # - state_name (character varying(100)) -- Used for subtype filtering
            # - question_text (text)
            # - options (jsonb)
            # - validation_rules (jsonb)
            # - display_order (integer)
            # - is_active (boolean)
            # - practice_area (character varying(100)) -- Used for primary filtering
            # - created_by (uuid)
            # - modified_by (uuid)
            # - created_at (timestamp with time zone)
            # - updated_at (timestamp with time zone)
            # -----------------------------------------------------------------

            # Build base query for intake_questions using practice_area VARCHAR
            query_select_fields = ",".join([
                "question_id",
                "practice_area", # VARCHAR - Primary filter
                "state_name",    # VARCHAR - Subtype filter
                "question_text",
                "display_order",
                "validation_rules", # JSONB
                "options"          # JSONB
            ])
            
            query = self.client.table("intake_questions").select(query_select_fields)
            
            # Filter by practice area code (VARCHAR)
            query = query.eq("practice_area", practice_area_code)
            
            # Optional: Filter by active questions only
            query = query.eq("is_active", True)

            # Add subtype (state_name) filter if provided
            if subtype_code:
                query = query.eq("state_name", subtype_code)
            # Note: If subtype_code is None, this fetches all active questions for the practice_area_code

            # Execute query ordered by display_order
            result = query.order("display_order").execute()
            
            # Log the number of questions fetched for debugging/tracking
            # print(f"[get_questions_for_practice_area_subtype] Fetched {len(result.data)} questions for '{practice_area_code}' (subtype: {subtype_code})")
            
            # Return the list of questions (empty list if none found)
            return result.data if result.data else []

        except Exception as e:
            print(f"[get_questions_for_practice_area_subtype] Error fetching questions for '{practice_area_code}' (subtype: {subtype_code}): {str(e)}")
            # Return empty list on error to allow flow to continue gracefully if possible
            return []

    async def get_attorney_for_practice_area_subtype(
        self,
        practice_area_code: str,
        subtype_code: Optional[str] = None # Potentially used for future filtering/logging
    ) -> Optional[Dict]:
        """
        Fetch the primary attorney for a practice area.
        1. Gets practice_area_id from 'practice_areas' using 'area_code'.
        2. Finds the assignment in 'law_firm_practice_areas' using 'practice_area_id'.
        3. Gets contact details from 'contacts' using 'assigned_contact_id'.
        Aligns with database.sql.txt schema for practice_areas, law_firm_practice_areas, and contacts.
        """
        try:
            # --- Step 1: Get practice_area_id from practice_areas ---
            # This ensures we are using the correct UUID for subsequent joins
            practice_area = await self.get_practice_area_by_code(practice_area_code)
            if not practice_area:
                print(f"[get_attorney_for_practice_area_subtype] Practice area '{practice_area_code}' not found.")
                return None

            practice_area_id = practice_area.get("practice_area_id")
            if not practice_area_id:
                 print(f"[get_attorney_for_practice_area_subtype] practice_area_id missing for '{practice_area_code}'.")
                 return None

            # --- Step 2: Find attorney assignment in law_firm_practice_areas ---
            # Align with database.sql.txt schema for law_firm_practice_areas
            # The schema implies linking via practice_area_id.
            # It doesn't explicitly show 'is_primary' or 'subtype_id' columns in the provided snippets.
            # For now, we fetch the assignment based on practice_area_id.
            # If multiple assignments exist, .limit(1) fetches one.
            # Future logic might involve subtype_id if the schema supports it for linking assignments.

            # Select the assigned_contact_id from law_firm_practice_areas
            assignment_query = self.client.table("law_firm_practice_areas").select(
                "assigned_contact_id"
                # Add other relevant fields from law_firm_practice_areas if needed for decision making
            ).eq("practice_area_id", practice_area_id)
            # .eq("is_primary", True) # Add if 'is_primary' column exists and is used for designation

            # Optional: Add subtype_id filter if assignments are also subtype-specific
            # This would require fetching subtype_id first (e.g., from practice_area_subtypes)
            # and then filtering the assignment query.
            # For now, fetching the general assignment for the practice area.
            # if subtype_code:
            #     # Example (requires get_subtype_by_code or similar):
            #     # subtype = await self.get_subtype_by_code(practice_area_id, subtype_code)
            #     # if subtype:
            #     #     assignment_query = assignment_query.eq("subtype_id", subtype["subtype_id"])

            # Limit to 1 result for simplicity (assumes one primary or first available)
            assignment_result = assignment_query.limit(1).execute()

            if not assignment_result.data:
                print(f"[get_attorney_for_practice_area_subtype] No attorney assignment found for practice area ID '{practice_area_id}'.")
                return None

            assigned_contact_id = assignment_result.data[0].get("assigned_contact_id")
            if not assigned_contact_id:
                print(f"[get_attorney_for_practice_area_subtype] assigned_contact_id missing in assignment for practice area ID '{practice_area_id}'.")
                return None

            # --- Step 3: Get contact details from contacts table ---
            # Align with database.sql.txt schema for contacts
            # The schema shows 'primary_email' (not 'email') and 'cell_phone_number'.

            contact_result = self.client.table("contacts").select(
                "contact_id",
                "first_name",
                "last_name",
                "cell_phone_number", # Use correct column name from schema
                "primary_email",    # <-- CORRECTED COLUMN NAME (was 'email')
                # Add other relevant contact fields if required by the application
            ).eq("contact_id", assigned_contact_id
            ).eq("contact_type", "attorney" # Ensure we're getting an attorney contact
            ).execute()

            if not contact_result.data:
                 print(f"[get_attorney_for_practice_area_subtype] Contact details not found for contact ID '{assigned_contact_id}'.")
                 return None

            # Log the found attorney for tracking/debugging
            # print(f"[get_attorney_for_practice_area_subtype] Found attorney: {contact_result.data[0]['first_name']} {contact_result.data[0]['last_name']}")

            # Return the first (and presumably primary/selected) attorney's contact details
            return contact_result.data[0]

        except Exception as e:
            print(f"[get_attorney_for_practice_area_subtype] Error fetching attorney for '{practice_area_code}': {str(e)}")
            return None

    async def upsert_lead_new(self, lead_data: Dict) -> Optional[Dict]:
        """
        Create or update a lead record in the 'intake_leads' table.
        Maps agent-provided keys to correct database column names.
        Aligns with database.sql.txt schema for intake_leads.
        """
        try:
            # --- Align with database.sql.txt schema for intake_leads ---
            # The schema shows required columns: lead_id, tenant_id, session_id
            # Other important columns: practice_area (VARCHAR), caller_name, caller_email,
            # caller_phone, case_summary (was 'summary'), lead_status, priority_level,
            # client_stage, follow_up_required, follow_up_date, follow_up_notes, notes,
            # estimated_value, assigned_attorney_id, created_by, modified_by,
            # created_at, updated_at.
            # ---------------------------------------------------------------

            # --- Map Agent Keys to Database Column Names ---
            # 1. Map 'practice_area_code' (from agent) to 'practice_area' (VARCHAR column)
            practice_area_code = lead_data.pop("practice_area_code", None)
            if practice_area_code:
                lead_data["practice_area"] = practice_area_code
            # else: # Decide if this is mandatory. If so, handle error.

            # 2. Map 'summary' (common agent key) to 'case_summary' (actual database column)
            summary = lead_data.pop("summary", None)
            if summary:
                lead_data["case_summary"] = summary
            lead_data.pop("source_channel", None) 

            # 3. Ensure required fields are present or have defaults
            #    - tenant_id: Critical for multi-tenancy. Must be provided by caller/context.
            #    - session_id: Critical. Must be provided by caller/context.
            #    If not present, the upsert will likely fail.
            #    The service method assumes these are provided correctly by the caller.
            
            # Example of providing a default if missing (use cautiously):
            # if "session_id" not in lead_data:
            #     lead_data["session_id"] = str(uuid.uuid4()) # Or get from context

                        # --- Add/Update Standard Timestamps ---
            # Ensure updated_at is set using timezone-aware UTC
            lead_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # Ensure created_at is set for new records (Supabase default usually handles this)
            # lead_data.setdefault("created_at", datetime.now(timezone.utc).isoformat())

            # --- Ensure Required Identifiers are Present ---
            # Ensure session_id is present (generate a new one if not provided by caller/context)
            # This is CRITICAL as the database table has a NOT NULL constraint.
            lead_data.setdefault("session_id", str(uuid.uuid4()))
            
            # Ensure tenant_id is present.
            # While the test provides it, defensive coding suggests ensuring it's not null.
            # If it's missing here and not nullable in DB, the upsert would fail on tenant_id too.
            # The test should provide it, but this safeguards against unexpected calls.
            # lead_data.setdefault("tenant_id", "YOUR_DEFAULT_TENANT_ID_IF_CRITICAL_AND_MISSING") 
            # # Add if needed# --- Perform Upsert Operation ---
            # Target table: intake_leads
            # Conflict resolution: Based on schema, likely on primary key (lead_id) or
            # a unique combination like (tenant_id, caller_email) if caller_email is unique per tenant.
            # The schema doesn't explicitly define a unique constraint on caller_email.
            # However, upsert typically works best with a unique constraint.
            # For now, assuming upsert works on lead_id (if provided) or fails gracefully.
            # A more robust approach would be to define a unique constraint and use on_conflict.
            # Example unique constraint needed in DB: UNIQUE(tenant_id, caller_email)
            # If that exists, use:
            # on_conflict_columns = "tenant_id,caller_email" # Define if constraint exists
            # result = self.client.table("intake_leads").upsert(
            #     lead_data,
            #     on_conflict=on_conflict_columns
            # ).execute()

            # For now, perform a basic upsert (will insert if no matching row based on primary key)
            result = self.client.table("intake_leads").upsert(lead_data).execute()

            # Check if the upsert operation returned data
            if result.data:
                # Log successful upsert (optional)
                # lead_id_returned = result.data[0].get('lead_id')
                # print(f"[upsert_lead_new] Lead upserted successfully. Lead ID: {lead_id_returned}")
                # Return the first item from the result data (the upserted/inserted record)
                return result.data[0]
            else:
                # Log a message if no data was returned
                print(f"[upsert_lead_new] Upsert returned no data. Input data might have issues.")
                return None

        except Exception as e:
            # Log the error with context for easier debugging
            print(f"[upsert_lead_new] Error upserting lead: {str(e)}")
            # Optionally log lead_data (be careful with PII)
            # print(f"[upsert_lead_new] Lead Data: {lead_data}")
            # Return None to indicate failure to the calling function
            return None

# Note on Removed Helper:
# The helper method 'get_subtype_by_code' was removed because the updated logic for
# 'get_questions_for_practice_area_subtype' and 'get_attorney_for_practice_area_subtype'
# now correctly uses the 'state_name' VARCHAR column for subtypes in 'intake_questions'
# and relies on 'practice_area_id' for linking in 'law_firm_practice_areas'.
# If future requirements dictate querying 'practice_area_subtypes' by UUID FKs,
# this helper can be reintroduced.