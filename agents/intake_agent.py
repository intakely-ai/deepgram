# agents/intake_agent.py
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from db.dynamic_data_service import DynamicDataService

logger = logging.getLogger(__name__)

class IntakeAgent:
    """Handles core intake logic by delegating to DynamicDataService."""

    def __init__(self):
        """Initialize the IntakeAgent with a DynamicDataService instance."""
        self.service = DynamicDataService()

    async def get_practice_area_questions(
        self,
        practice_area: str,
        subtype_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetches dynamic questions for a given practice area and optional subtype.
        Args:
            practice_area (str): The practice area code (e.g., 'personal_injury').
            subtype_code (str, optional): The subtype code (e.g., 'car_accident').
        Returns:
            dict: A dictionary containing the practice area, version, and list of questions.
        """
        try:
            logger.info(f"[get_practice_area_questions] Fetching questions for PA: {practice_area}, Subtype: {subtype_code}")

            # --- Use DynamicDataService ---
            # 1. Get Practice Area Details (for version/name if needed)
            pa_details = await self.service.get_practice_area_by_code(practice_area)
            if not pa_details:
                logger.warning(f"[get_practice_area_questions] Practice area '{practice_area}' not found in DB.")
                # Return an error indicating PA not supported dynamically yet.
                return {"ok": False, "error": f"Practice area '{practice_area}' not found."}

            # Derive version, perhaps from pa_details or statically
            version = pa_details.get("name", practice_area) # Fallback to code if name missing

            # 2. Fetch Questions using the service
            questions = await self.service.get_questions_for_practice_area_subtype(
                practice_area_code=practice_area,
                subtype_code=subtype_code
            )

            logger.info(f"[get_practice_area_questions] Fetched {len(questions)} questions.")
            return {
                "ok": True,
                "practice_area": practice_area,
                "practice_area_version": version,
                "questions": questions # This list comes directly from the service
            }
        except Exception as e:
            logger.error(f"[get_practice_area_questions] Error fetching questions for PA '{practice_area}', Subtype '{subtype_code}': {e}")
            return {"ok": False, "error": f"Failed to fetch questions: {str(e)}"}

    async def upsert_lead_information(self, lead_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """
        Creates or updates lead information using DynamicDataService.
        Maps agent-provided keys to database columns.
        Args:
            lead_data (dict): Dictionary containing lead information.
                              Expected keys: unique_caller_id, caller_name, caller_email,
                              caller_phone, practice_area_code, summary, source_channel, etc.
            tenant_id (str): The tenant ID for the lead.
        Returns:
            dict: A dictionary indicating success/failure and relevant IDs/messages.
        """
        try:
            logger.info(f"[upsert_lead_information] Upserting lead info for {lead_data.get('caller_email')} (PA: {lead_data.get('practice_area_code')})")

            # --- Use DynamicDataService ---
            # Ensure tenant_id is included in the data passed to the service
            # The service method `upsert_lead_new` is expected to handle mapping
            # 'practice_area_code' -> 'practice_area' column.
            lead_data_with_tenant = {**lead_data, "tenant_id": tenant_id}

            # 2. Call the service method
            result = await self.service.upsert_lead_new(lead_data_with_tenant)

            # 3. Check result and return appropriate response
            if result and isinstance(result, dict):
                logger.info(f"[upsert_lead_information] Lead upserted successfully. Lead ID: {result.get('lead_id')}")
                return {
                    "ok": True,
                    "unique_caller_id": result.get("unique_caller_id"),
                    "message": "Lead information saved.",
                    "lead_id": result.get("lead_id") # Optional: Return lead_id if needed by caller
                }
            else:
                logger.error("[upsert_lead_information] Service returned no data or invalid data.")
                return {"ok": False, "error": "Failed to save lead information."}

        except Exception as e:
            logger.error(f"[upsert_lead_information] Error upserting lead for {lead_data.get('caller_email')}: {e}")
            return {"ok": False, "error": f"Failed to save lead information: {str(e)}"}

    async def save_lead_qa(
        self,
        session_id: str, # Crucial: Needs to be passed or derived
        all_q_and_a: List[Dict[str, Any]], # List of Q&A dictionaries
        practice_area_version: str, # Practice area code/version identifier (might be used for context)
        completion_status: str, # e.g., "complete", "partial"
        unique_caller_id: Optional[str] = None, # Optional: For deriving session_id if needed
        email: Optional[str] = None # Optional: For deriving session_id if needed
    ) -> Dict[str, Any]:
        """
        Saves the Q&A responses for a lead using DynamicDataService.
        Requires session_id to link responses.
        Args:
            session_id (str): The session ID linking these Q&A responses.
            all_q_and_a (list): List of dictionaries, each containing 'question_id', 'question', 'answer', etc.
            practice_area_version (str): Identifier for the practice area/questions version (context).
            completion_status (str): Status of the Q&A completion.
            unique_caller_id (str, optional): Caller ID, used if session_id derivation is needed.
            email (str, optional): Caller email, used if session_id derivation is needed.
        Returns:
            dict: A dictionary indicating success/failure and a message.
        """
        try:
            logger.info(f"[save_lead_qa] Saving Q&A for session {session_id}, Status: {completion_status}")

            # --- Critical: Ensure session_id is available ---
            # The function signature now includes session_id.
            # If it's not passed by the caller, you MUST derive it.
            # For now, assume it's passed correctly by the agent/context.
            if not session_id:
                logger.error("[save_lead_qa] session_id is required but was None.")
                return {"ok": False, "error": "Session ID is required to save Q&A."}

            # --- Use DynamicDataService ---
            service = self.service # Alias for clarity
            results = []

            # 2. Iterate through Q&A and save each response
            for qa_item in all_q_and_a:
                # Extract data from the QA item structure
                # This depends on the exact structure provided by the agent
                # Example structure assumed: {"question_id": "...", "question": "...", "answer": "...", "metadata": {...}}
                question_id = qa_item.get("question_id") # Might be None if new/freeform
                question_text = qa_item.get("question") or qa_item.get("question_text")
                answer_text = qa_item.get("answer")
                answer_metadata = qa_item.get("metadata") or {} # If metadata exists
                # state_name could be passed into the function or derived, or taken from practice_area_version if it encodes subtype
                # For now, passing None for state_name/subtype_code context in QA, or derive if needed.
                # Let's assume practice_area_version is just the practice_area_code (e.g., "personal_injury")
                # If subtype is encoded differently, adjust.
                state_name_context = None # Or derive from practice_area_version if needed, or pass separately

                if question_text and answer_text: # Basic validation
                    # 3. Call the service method for each Q&A item
                    # Pass session_id, question details, answer details, context
                    qa_result = await service.save_lead_qa_response(
                        session_id=session_id, # <-- Now available
                        question_id=question_id,
                        state_name=state_name_context, # <-- Context (subtype)
                        question_text=question_text,
                        answer_text=answer_text,
                        answer_metadata=answer_metadata, # Pass if exists
                        # confidence_score=? # Add if agent provides or calculated
                    )
                    results.append(qa_result)
                    if not qa_result.get("ok"):
                        logger.warning(f"[save_lead_qa] Error saving individual QA: {qa_result.get('error')}")
                        # Decide: Log and continue, or return error immediately?
                        # For now, log and continue to try saving others.
                else:
                    logger.warning(f"[save_lead_qa] Skipping invalid QA item: {qa_item}")
                    # results.append({"ok": False, "error": "Invalid QA item structure"})
                    # Decide how to handle skipped items

            # 4. Check overall success of saving all Q&A items
            all_ok = all(r.get("ok") for r in results)
            if all_ok:
                logger.info(f"[save_lead_qa] Saved {len(results)} Q&A items successfully.")
                return {"ok": True, "message": f"Saved {len(results)} Q&A items."}
            else:
                # Find first error or aggregate errors
                first_error = next((r.get("error") for r in results if not r.get("ok")), "Unknown QA save error")
                logger.error(f"[save_lead_qa] Some Q&A items failed to save: {first_error}")
                return {"ok": False, "error": f"Some Q&A items failed to save: {first_error}"}

        except Exception as e:
            logger.error(f"[save_lead_qa] Error saving Q&A for session {session_id}: {e}")
            return {"ok": False, "error": f"Failed to save Q&A: {str(e)}"}

# --- Export an instance for easy access ---
# This allows importing the instance directly and calling its methods
# e.g., from agents.intake_agent import intake_agent_instance; await intake_agent_instance.get_practice_area_questions(...)
intake_agent_instance = IntakeAgent()

# --- Export specific coroutines bound to the instance for FUNCTION_MAP ---
# This allows FUNCTION_MAP to map string keys directly to these coroutines
# e.g., FUNCTION_MAP["get_practice_area_questions"] = get_practice_area_questions_coro
# These are partial applications or bindings of the instance methods
# get_practice_area_questions_coro = intake_agent_instance.get_practice_area_questions.__func__
# upsert_lead_information_coro = intake_agent_instance.upsert_lead_information.__func__
# save_lead_qa_coro = intake_agent_instance.save_lead_qa.__func__

# However, a cleaner way is to export the instance methods directly.
# The FUNCTION_MAP can then access them like: intake_agent_instance.get_practice_area_questions
# See law_functions.py update below.
