# tests/test_dynamic_data_service.py
import os
import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4, UUID
from dotenv import load_dotenv
from supabase import create_client, Client # Import client directly for setup/teardown
from db.dynamic_data_service import DynamicDataService # Import the facade for testing

class TestDynamicDataService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize test environment, Supabase client for setup/teardown, and service facade."""
        load_dotenv()
        # --- Supabase Client for Test Data Setup/Cleanup ---
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE/SUPABASE_KEY in environment for tests")
        cls._sb_client: Client = create_client(url, key) # Raw client for setup/teardown

        # --- Service Facade for Testing Methods ---
        cls.service = DynamicDataService() # Use the facade

        cls.test_data = {}  # store created IDs for cleanup
        cls.setup_test_data()

    @classmethod
    def setup_test_data(cls):
        """Create or get required records in Supabase before running tests, aligned with database.sql.txt schema."""
        try:
            print("\n--- Setting up Test Data (Aligned with database.sql.txt) ---")

            # Use cls._sb_client for setup operations
            # 1️⃣ Practice Area
            practice_result = cls._sb_client.table("practice_areas").select(
                "practice_area_id, area_code, name, description"
            ).eq("area_code", "personal_injury").execute()

            if not practice_result.
                print("Creating practice area 'personal_injury'...")
                pa_id = str(uuid4())
                practice_data = {
                    "practice_area_id": pa_id,
                    "area_code": "personal_injury",
                    "name": "Personal Injury",
                    "description": "Personal injury law practice"
                }
                practice_result = cls._sb_client.table("practice_areas").insert(practice_data).execute()

                if not practice_result.
                    raise ValueError("Failed to create practice area 'personal_injury'")

            practice_area = practice_result.data[0]
            practice_area_id = practice_area["practice_area_id"]
            cls.test_data["practice_area_id"] = practice_area_id
            print(f"Using practice area ID: {practice_area_id} (Code: personal_injury)")

            # 2️⃣ Attorney Contact
            contact_result = cls._sb_client.table("contacts").select(
                "contact_id, first_name, last_name, cell_phone_number, contact_type"
            ).eq("first_name", "Test"
            ).eq("last_name", "Attorney").execute()

            if not contact_result.
                print("Creating attorney contact 'Test Attorney'...")
                contact_data = {
                    "contact_id": str(uuid4()),
                    "first_name": "Test",
                    "last_name": "Attorney",
                    "cell_phone_number": "1234567890",
                    "contact_type": "attorney"
                    # Add tenant_id if required by your DB schema/RLS
                }
                contact_result = cls._sb_client.table("contacts").insert(contact_data).execute()

                if not contact_result.
                    print(f"Debug - Contact insert data attempted: {contact_data}")
                    raise ValueError("Failed to create contact 'Test Attorney' - check schema/columns/permissions")

            contact = contact_result.data[0]
            contact_id = contact["contact_id"]
            cls.test_data["contact_id"] = contact_id
            print(f"Using contact ID: {contact_id} (Name: Test Attorney)")

            # 3️⃣ Attorney Assignment
            assignment_result = cls._sb_client.table("law_firm_practice_areas").select(
                "*"
            ).eq("practice_area_id", practice_area_id
            ).eq("assigned_contact_id", contact_id
            ).limit(1).execute()

            if not assignment_result.
                print("Creating attorney assignment...")
                assignment_data = {
                    "practice_area_id": practice_area_id,
                    "assigned_contact_id": contact_id,
                    # Add other fields like is_primary if needed and exist
                }
                insert_result = cls._sb_client.table("law_firm_practice_areas").insert(assignment_data).execute()

                if not insert_result.data:
                    raise ValueError("Failed to create attorney assignment")

                print("Attorney assignment created.")
            else:
                print("Attorney assignment found.")

            # 4️⃣ Intake Questions
            question_check_result = cls._sb_client.table("intake_questions").select(
                "question_id"
            ).eq("practice_area", "personal_injury"
            ).eq("state_name", "car_accident"
            ).limit(1).execute()

            if not question_check_result.
                print("Creating test questions for 'personal_injury' -> 'car_accident'...")
                question1_data = {
                    "practice_area": "personal_injury",
                    "state_name": "car_accident",
                    "question_text": "When did the accident occur?",
                    "display_order": 1,
                    "validation_rules": {"required": True},
                    "options": ["Today", "Within last week", "Over a week ago"]
                }
                question2_data = {
                    "practice_area": "personal_injury",
                    "state_name": "car_accident",
                    "question_text": "Were you treated by a medical professional?",
                    "display_order": 2,
                    "validation_rules": {"required": False},
                    "options": ["Yes - ER", "Yes - Doctor", "No"]
                }

                questions_insert_result = cls._sb_client.table("intake_questions").insert(
                    [question1_data, question2_data]
                ).execute()

                if not questions_insert_result.data or len(questions_insert_result.data) != 2:
                     print(f"Debug - Questions insert attempted. Result  {questions_insert_result.data}")
                     raise ValueError("Failed to create test questions for 'personal_injury' -> 'car_accident'")

                print("Test questions created.")
            else:
                print("Test questions for 'personal_injury' -> 'car_accident' found.")

            print("--- Test data setup complete ---\n")

        except Exception as e: # Catch general exceptions, including APIError
            print(f"\n💥 Error setting up test  {str(e)}")
            # Print traceback for more details in case of unexpected errors
            import traceback
            traceback.print_exc()
            raise # Re-raise to fail the test setup

    @classmethod
    def tearDownClass(cls):
        """Clean up test data after all tests, respecting foreign key constraints."""
        try:
            print("\n--- Cleaning up Test Data ---")

            # Use cls._sb_client for cleanup operations
            # Cleanup order: Delete dependent data first

            # 1. Delete test questions
            if cls.test_data.get("practice_area_id"):
                delete_questions_result = cls._sb_client.table("intake_questions").delete().eq(
                    "practice_area", "personal_injury"
                ).eq("state_name", "car_accident").execute()
                print(f"Deleted test questions. Count: {len(delete_questions_result.data) if delete_questions_result.data else 0}")

            # 2. Delete attorney assignments
            if cls.test_data.get("practice_area_id") and cls.test_data.get("contact_id"):
                delete_assignments_result = cls._sb_client.table("law_firm_practice_areas").delete().eq(
                    "practice_area_id", cls.test_data["practice_area_id"]
                ).eq("assigned_contact_id", cls.test_data["contact_id"]).execute()
                print(f"Deleted attorney assignments. Count: {len(delete_assignments_result.data) if delete_assignments_result.data else 0}")

            # 3. Delete contact (Consider if strictly necessary)
            if cls.test_data.get("contact_id"):
                delete_contact_result = cls._sb_client.table("contacts").delete().eq(
                    "contact_id", cls.test_data["contact_id"]
                ).execute()
                print(f"Deleted test contact. Count: {len(delete_contact_result.data) if delete_contact_result.data else 0}")

            # 4. Delete practice area (Consider if strictly necessary)
            # if cls.test_data.get("practice_area_id"):
            #     delete_pa_result = cls._sb_client.table("practice_areas").delete().eq(
            #         "practice_area_id", cls.test_data["practice_area_id"]
            #     ).execute()
            #     print(f"Deleted test practice area. Count: {len(delete_pa_result.data) if delete_pa_result.data else 0}")

            print("--- Test data cleanup complete ---\n")

        except Exception as e:
            print(f"\n⚠️ Error cleaning up test  {str(e)}")
            # Print traceback for more details in case of unexpected errors
            import traceback
            traceback.print_exc()
        finally:
            # Clear test data dict regardless of cleanup success/failure
            cls.test_data.clear()

    # ------------------------------
    # ✅ Tests (Use the service facade)
    # ------------------------------

    def test_get_practice_area(self):
        """Test fetching practice area details by code"""
        print("Running test_get_practice_area...")
        # Use the service facade instance (cls.service) for the actual test
        result = asyncio.run(self.service.get_practice_area_by_code("personal_injury"))
        self.assertIsNotNone(result, "Practice area 'personal_injury' should be found")
        self.assertEqual(result["area_code"], "personal_injury", "Area code should match")
        self.assertIn("name", result, "Result should contain 'name'")
        self.assertIn("description", result, "Result should contain 'description'")
        self.assertIn("practice_area_id", result, "Result should contain 'practice_area_id'")
        try:
            UUID(result["practice_area_id"])
        except ValueError:
            self.fail("'practice_area_id' should be a valid UUID")

    def test_get_questions_with_subtype(self):
        """Test fetching questions for a specific practice area and subtype (state_name)"""
        print("Running test_get_questions_with_subtype...")
        # Use the service facade instance (cls.service) for the actual test
        result = asyncio.run(self.service.get_questions_for_practice_area_subtype("personal_injury", "car_accident"))
        self.assertIsInstance(result, list, "Result should be a list")
        self.assertGreater(len(result), 0, "Should return at least one question for 'personal_injury' -> 'car_accident'")
        first_question = result[0]
        self.assertIn("question_id", first_question)
        self.assertIn("question_text", first_question)
        self.assertIn("display_order", first_question)

    def test_get_attorney(self):
        """Test fetching attorney for a practice area"""
        print("Running test_get_attorney...")
        # Use the service facade instance (cls.service) for the actual test
        result = asyncio.run(self.service.get_attorney_for_practice_area_subtype("personal_injury"))
        self.assertIsNotNone(result, "Attorney data should be found for 'personal_injury'")
        self.assertEqual(result["first_name"], "Test", "First name should match")
        self.assertEqual(result["last_name"], "Attorney", "Last name should match")
        self.assertIn("contact_id", result, "Result should contain 'contact_id'")
        try:
            UUID(result["contact_id"])
        except ValueError:
            self.fail("'contact_id' should be a valid UUID")
        self.assertIn("cell_phone_number", result, "Result should contain 'cell_phone_number'")

    def test_upsert_lead_new(self):
        """Test creating/updating a lead record"""
        print("Running test_upsert_lead_new...")
        # Use the service facade instance (cls.service) for the actual test
        test_email = "test_lead_upsert@example.com"
        lead_data = {
            "caller_name": "Test Lead For Upsert",
            "caller_email": test_email,
            "caller_phone": "0987654321",
            "practice_area_code": "personal_injury", # This should be mapped by the service
            "summary": "Test lead for upsert functionality", # This should be mapped by the service
            "source_channel": "unit_test",
            # "tenant_id": self.test_tenant_id # Include if required by intake_leads table or RLS
            # session_id will be generated by the service if not provided
        }

        result = asyncio.run(self.service.upsert_lead_new(lead_data))

        self.assertIsNotNone(result, "Upsert should return lead data")
        self.assertIn("lead_id", result, "Result should contain 'lead_id'")
        self.assertEqual(result["caller_email"], test_email, "Email should match")
        self.assertEqual(result.get("practice_area"), "personal_injury", "Mapped 'practice_area' should be present")
        try:
            UUID(result["lead_id"])
        except ValueError:
            self.fail("'lead_id' should be a valid UUID")

        # Cleanup: Delete the test lead created
        try:
            # Use the raw client for cleanup
            delete_result = self._sb_client.table("intake_leads").delete().eq("caller_email", test_email).execute()
            if delete_result.
                print(f"Cleaned up test lead: {test_email}")
            else:
                print(f"Warning: Test lead {test_email} might not have been deleted.")
        except Exception as e:
            print(f"Warning: Could not clean up test lead {test_email}: {e}")

if __name__ == "__main__":
    unittest.main(verbosity=2)
