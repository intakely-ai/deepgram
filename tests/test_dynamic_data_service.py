# tests/test_dynamic_data_service.py
import os
import asyncio
import uuid
import unittest
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from db.dynamic_data_helpers import DynamicDataService # Ensure this points to the updated service code

class TestDynamicDataService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize test environment and service"""
        load_dotenv()
        # Use a default Oakwood Tenant ID if TEST_TENANT_ID is not set in .env for tests
        cls.test_tenant_id = os.getenv("TEST_TENANT_ID") or "72761cd2-d733-4cb8-a4c9-114d4a7ebbc1"
        if not cls.test_tenant_id:
            raise ValueError("TEST_TENANT_ID not found in environment variables")

        cls.service = DynamicDataService()
        cls.test_data = {}  # store created IDs for cleanup
        cls.setup_test_data()

    @classmethod
    def setup_test_data(cls):
        """Create or get required records in Supabase before running tests, aligned with database.sql.txt schema"""
        try:
            print("\n--- Setting up Test Data (Aligned with database.sql.txt) ---")
            
            # 1️⃣ Practice Area (Ensure it exists in practice_areas table)
            # Note: practice_areas table definition in database.sql.txt doesn't show tenant_id as a column,
            # so we don't filter or insert it here for this table based on the provided schema.
            practice_result = cls.service.client.table("practice_areas").select(
                "practice_area_id, area_code, name, description"
            ).eq("area_code", "personal_injury").execute()

            if not practice_result.data:
                print("Creating practice area 'personal_injury'...")
                # Generate a new UUID for the practice area
                pa_id = str(uuid.uuid4())
                practice_data = {
                    "practice_area_id": pa_id,
                    "area_code": "personal_injury",
                    "name": "Personal Injury",
                    "description": "Personal injury law practice"
                }
                practice_result = cls.service.client.table("practice_areas").insert(practice_data).execute()

                if not practice_result.data:
                    raise ValueError("Failed to create practice area 'personal_injury'")

            practice_area = practice_result.data[0]
            practice_area_id = practice_area["practice_area_id"]
            cls.test_data["practice_area_id"] = practice_area_id
            print(f"Using practice area ID: {practice_area_id} (Code: personal_injury)")

            # 2️⃣ Attorney Contact (Ensure it exists in contacts table)
            # Based on previous errors and schema, inserting without tenant_id for now.
            # If RLS requires it, the service role or test setup might need adjustment.
            contact_result = cls.service.client.table("contacts").select(
                "contact_id, first_name, last_name, cell_phone_number, contact_type"
            ).eq("first_name", "Test"
            ).eq("last_name", "Attorney").execute()

            if not contact_result.data:
                print("Creating attorney contact 'Test Attorney'...")
                contact_data = {
                    "contact_id": str(uuid.uuid4()),
                    "first_name": "Test",
                    "last_name": "Attorney",
                    "cell_phone_number": "1234567890",
                    "contact_type": "attorney"
                    # tenant_id: Excluded based on schema/table definition and previous errors
                }
                contact_result = cls.service.client.table("contacts").insert(contact_data).execute()

                if not contact_result.data:
                    print(f"Debug - Contact insert data attempted: {contact_data}")
                    raise ValueError("Failed to create contact 'Test Attorney' - check schema/columns/permissions")

            contact = contact_result.data[0]
            contact_id = contact["contact_id"]
            cls.test_data["contact_id"] = contact_id
            print(f"Using contact ID: {contact_id} (Name: Test Attorney)")

            # 3️⃣ Attorney Assignment (Link contact to practice area in law_firm_practice_areas)
            # Note: The schema for law_firm_practice_areas isn't fully shown in the provided snippets,
            # but it's implied it links contacts to practice areas.
            # We'll assume it has practice_area_id and assigned_contact_id.
            # Filtering by practice_area_id and assigned_contact_id.
            assignment_result = cls.service.client.table("law_firm_practice_areas").select(
                "*" # Select all to see structure if needed
            ).eq("practice_area_id", practice_area_id
            ).eq("assigned_contact_id", contact_id
            ).limit(1).execute() # Limit 1 in case of duplicates

            if not assignment_result.data:
                print("Creating attorney assignment...")
                assignment_data = {
                    "practice_area_id": practice_area_id,
                    "assigned_contact_id": contact_id,
                    # is_primary: Assume default or set if column exists
                    # law_firm_id / tenant_id: Handled by context or not direct columns based on schema snippets
                    # subtype_id: Not used as linking is via practice_area VARCHAR and state_name VARCHAR
                }
                # Insert the assignment
                insert_result = cls.service.client.table("law_firm_practice_areas").insert(assignment_data).execute()

                if not insert_result.data:
                    raise ValueError("Failed to create attorney assignment")

                print("Attorney assignment created.")
            else:
                print("Attorney assignment found.")
                # Optionally update if needed, but for a test setup, existence might be enough.
                # Example update:
                # cls.service.client.table("law_firm_practice_areas").update({"is_primary": True}).eq(...).execute()

            # 4️⃣ Intake Questions (Create test questions linked via practice_area and state_name)
            # Check for existing questions for 'personal_injury' and 'car_accident'
            # Note: state_name is used as the subtype identifier in this schema version.
            question_check_result = cls.service.client.table("intake_questions").select(
                "question_id"
            ).eq("practice_area", "personal_injury"
            ).eq("state_name", "car_accident"
            ).limit(1).execute() # Just check if any exist

            if not question_check_result.data:
                print("Creating test questions for 'personal_injury' -> 'car_accident'...")
                # Create test questions using practice_area VARCHAR and state_name VARCHAR
                question1_data = {
                    # question_id: Let Supabase generate if not specified, or specify if linking is needed elsewhere
                    "practice_area": "personal_injury", # VARCHAR linking
                    "state_name": "car_accident",       # VARCHAR subtype identifier
                    "question_text": "When did the accident occur?",
                    "display_order": 1,
                    "validation_rules": {"required": True},
                    "options": ["Today", "Within last week", "Over a week ago"]
                    # tenant_id: Not typically on intake_questions based on schema, but check if your instance requires it.
                    # If insertion fails due to missing tenant_id, it needs to be added or RLS adjusted.
                }
                question2_data = {
                    "practice_area": "personal_injury",
                    "state_name": "car_accident",
                    "question_text": "Were you treated by a medical professional?",
                    "display_order": 2,
                    "validation_rules": {"required": False},
                    "options": ["Yes - ER", "Yes - Doctor", "No"]
                }

                # Insert questions
                questions_insert_result = cls.service.client.table("intake_questions").insert(
                    [question1_data, question2_data]
                ).execute()

                if not questions_insert_result.data or len(questions_insert_result.data) != 2:
                     print(f"Debug - Questions insert attempted. Result data: {questions_insert_result.data}")
                     raise ValueError("Failed to create test questions for 'personal_injury' -> 'car_accident'")

                print("Test questions created.")
            else:
                print("Test questions for 'personal_injury' -> 'car_accident' found.")

            print("--- Test data setup complete ---\n")

        except APIError as e:
            print(f"\n❌ Supabase API Error during setup: {e.code} - {e.message}")
            if hasattr(e, 'details'):
                print(f"Details: {e.details}")
            raise # Re-raise to fail the test setup
        except Exception as e:
            print(f"\n💥 Unexpected Error setting up test data: {str(e)}")
            raise # Re-raise to fail the test setup

    @classmethod
    def tearDownClass(cls):
        """Clean up test data after all tests, respecting foreign key constraints"""
        try:
            print("\n--- Cleaning up Test Data ---")
            # Cleanup order: Delete dependent data first

            # 1. Delete test questions (depend on practice_area/state_name values)
            # Delete questions specifically created for the test
            if cls.test_data.get("practice_area_id"): # Use PA ID as proxy for 'personal_injury' questions
                delete_questions_result = cls.service.client.table("intake_questions").delete().eq(
                    "practice_area", "personal_injury"
                ).eq("state_name", "car_accident").execute()
                print(f"Deleted test questions. Count: {len(delete_questions_result.data) if delete_questions_result.data else 0}")

            # 2. Delete attorney assignments (depend on practice_area_id and contact_id)
            if cls.test_data.get("practice_area_id") and cls.test_data.get("contact_id"):
                delete_assignments_result = cls.service.client.table("law_firm_practice_areas").delete().eq(
                    "practice_area_id", cls.test_data["practice_area_id"]
                ).eq("assigned_contact_id", cls.test_data["contact_id"]).execute()
                print(f"Deleted attorney assignments. Count: {len(delete_assignments_result.data) if delete_assignments_result.data else 0}")

            # 3. Delete contact (be cautious if used elsewhere, but it's a test contact)
            # Consider if deletion is strictly necessary or if re-use is better for speed/isolation
            if cls.test_data.get("contact_id"):
                delete_contact_result = cls.service.client.table("contacts").delete().eq(
                    "contact_id", cls.test_data["contact_id"]
                ).execute()
                print(f"Deleted test contact. Count: {len(delete_contact_result.data) if delete_contact_result.data else 0}")

            # 4. Delete practice area (be cautious if used elsewhere, but it's a test area)
            # Consider if deletion is strictly necessary. PA 'personal_injury' might be standard.
            # For true isolation, deleting is safer, but might conflict with shared dev data.
            # if cls.test_data.get("practice_area_id"):
            #     delete_pa_result = cls.service.client.table("practice_areas").delete().eq(
            #         "practice_area_id", cls.test_data["practice_area_id"]
            #     ).execute()
            #     print(f"Deleted test practice area. Count: {len(delete_pa_result.data) if delete_pa_result.data else 0}")

            print("--- Test data cleanup complete ---\n")

        except APIError as e:
            print(f"\n⚠️ Supabase API Error during cleanup: {e.code} - {e.message}")
        except Exception as e:
            print(f"\n⚠️ Error cleaning up test data: {str(e)}")
        finally:
            # Clear test data dict regardless of cleanup success/failure
            cls.test_data.clear()


    # ------------------------------
    # ✅ Tests
    # ------------------------------

    def test_get_practice_area(self):
        """Test fetching practice area details by code"""
        print("Running test_get_practice_area...")
        result = asyncio.run(self.service.get_practice_area_by_code("personal_injury"))
        self.assertIsNotNone(result, "Practice area 'personal_injury' should be found")
        self.assertEqual(result["area_code"], "personal_injury", "Area code should match")
        self.assertIn("name", result, "Result should contain 'name'")
        self.assertIn("description", result, "Result should contain 'description'")
        self.assertIn("practice_area_id", result, "Result should contain 'practice_area_id'")
        try:
            uuid.UUID(result["practice_area_id"])
        except ValueError:
            self.fail("'practice_area_id' should be a valid UUID")

    # Note: The service method `get_questions_for_practice_area_subtype` needs to be updated
    # to use `practice_area` (VARCHAR) and `state_name` (VARCHAR) for querying `intake_questions`.
    # The test below assumes the service method has been updated accordingly.
    def test_get_questions_with_subtype(self):
        """Test fetching questions for a specific practice area and subtype (state_name)"""
        print("Running test_get_questions_with_subtype...")
        # This test relies on the service method correctly using practice_area and state_name
        result = asyncio.run(self.service.get_questions_for_practice_area_subtype("personal_injury", "car_accident"))
        self.assertIsInstance(result, list, "Result should be a list")
        # Assert that we get the questions we specifically linked to 'personal_injury' and 'car_accident'
        self.assertGreater(len(result), 0, "Should return at least one question for 'personal_injury' -> 'car_accident'")
        # Basic check on the structure of the first question
        first_question = result[0]
        self.assertIn("question_id", first_question)
        self.assertIn("question_text", first_question)
        self.assertIn("display_order", first_question)
        # Note: The service should ideally filter by practice_area='personal_injury' AND state_name='car_accident'
        # The test asserts > 0, implying the filter worked. Further validation could check question_text content.

    # Note: The service method `get_attorney_for_practice_area_subtype` needs to be updated
    # to query `law_firm_practice_areas` using `practice_area_id` (obtained from `practice_areas`)
    # and potentially filter by `subtype_id` if that column/linking exists and is used.
    # The test below assumes the service method finds the attorney linked to the practice area.
    def test_get_attorney(self):
        """Test fetching attorney for a practice area"""
        print("Running test_get_attorney...")
        # Fetch attorney for the practice area.
        result = asyncio.run(self.service.get_attorney_for_practice_area_subtype("personal_injury"))
        self.assertIsNotNone(result, "Attorney data should be found for 'personal_injury'")
        self.assertEqual(result["first_name"], "Test", "First name should match")
        self.assertEqual(result["last_name"], "Attorney", "Last name should match")
        # Check for contact_id presence and validity
        self.assertIn("contact_id", result, "Result should contain 'contact_id'")
        try:
            uuid.UUID(result["contact_id"])
        except ValueError:
            self.fail("'contact_id' should be a valid UUID")
        # Schema shows cell_phone_number, not phone
        self.assertIn("cell_phone_number", result, "Result should contain 'cell_phone_number'")

    # Note: The service method `upsert_lead_new` needs to be updated to map `practice_area_code`
    # from the input data to the `practice_area` column in the `intake_leads` table.
    def test_upsert_lead_new(self):
        """Test creating/updating a lead record"""
        print("Running test_upsert_lead_new...")
        test_email = "test_lead_upsert@example.com"
        lead_data = {
            "caller_name": "Test Lead For Upsert",
            "caller_email": test_email,
            "caller_phone": "0987654321",
            "practice_area_code": "personal_injury", # This should be mapped by the service to `practice_area`
            "summary": "Test lead for upsert functionality",
            "source_channel": "unit_test",
            "tenant_id": self.test_tenant_id # Include tenant_id if required by intake_leads table or RLS
            # session_id will be generated by the service if not provided
        }

        # Perform upsert
        result = asyncio.run(self.service.upsert_lead_new(lead_data))

        # Assertions
        self.assertIsNotNone(result, "Upsert should return lead data")
        self.assertIn("lead_id", result, "Result should contain 'lead_id'")
        self.assertEqual(result["caller_email"], test_email, "Email should match")
        # The service should map practice_area_code to the practice_area column
        self.assertEqual(result.get("practice_area"), "personal_injury", "Mapped 'practice_area' should be present and correct")
        # Verify the lead_id is a valid UUID
        try:
            uuid.UUID(result["lead_id"])
        except ValueError:
            self.fail("'lead_id' should be a valid UUID")

        # Cleanup: Delete the test lead created to keep the test environment clean
        try:
            delete_result = self.service.client.table("intake_leads").delete().eq("caller_email", test_email).execute()
            if delete_result.data:
                print(f"Cleaned up test lead: {test_email}")
            else:
                print(f"Warning: Test lead {test_email} might not have been deleted.")
        except Exception as e:
            print(f"Warning: Could not clean up test lead {test_email}: {e}")


if __name__ == "__main__":
    # Run tests with increased verbosity for detailed output
    unittest.main(verbosity=2)