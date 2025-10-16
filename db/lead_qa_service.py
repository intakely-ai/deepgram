# db/lead_qa_service.py
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from .core import get_client
from .practice_area_service import practice_area_service

class LeadQAService:
    """Service for lead upserts and QA persistence."""

    def __init__(self):
        self.client = get_client()
        self.pa_service = practice_area_service # Dependency

    async def upsert_lead_new(self, lead_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Upsert a lead. If lead_data contains 'practice_area_code', map it to practice_area_id.
        Returns the upserted row dict or None.
        """
        try:
            # Map practice_area_code -> practice_area_id if present
            if "practice_area_code" in lead_data:
                pa_code = lead_data.pop("practice_area_code")
                pa = await self.pa_service.get_practice_area_by_code(pa_code)
                if not pa:
                    print(f"[upsert_lead_new] practice area code not found: {pa_code}")
                    return None
                lead_data["practice_area_id"] = pa["practice_area_id"]
                # Also set the VARCHAR practice_area column if needed by schema
                lead_data["practice_area"] = pa_code

            # Ensure required identifiers and timestamps
            lead_data.setdefault("session_id", str(uuid.uuid4()))
            # Ensure tenant_id is present if required by DB schema/RLS
            # lead_data.setdefault("tenant_id", "YOUR_DEFAULT_TENANT_ID") # Add if needed
            lead_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            # created_at handled by DB default or setdefault if needed
            # lead_data.setdefault("created_at", datetime.now(timezone.utc).isoformat())

            result = self.client.table("intake_leads").upsert(lead_data, on_conflict="caller_email,tenant_id").execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[upsert_lead_new] Error: {e}")
            return None

    async def save_lead_qa_response(
        self,
        session_id: str,
        question_id: Optional[str],
        state_name: Optional[str], # Subtype code/context
        question_text: str,
        answer_text: str,
        answer_metadata: Optional[Dict[str, Any]] = None,
        confidence_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Persist a Q&A response to intake_lead_qa.
        Returns a dict with operation result: {'ok': bool, 'data': row|None, 'error': str|None}
        """
        try:
            if not session_id:
                raise ValueError("session_id is required")

            qa_row = {
                "response_id": str(uuid.uuid4()),
                "session_id": session_id,
                "question_id": question_id,
                "state_name": state_name, # Store subtype/context if relevant
                "question_text": question_text,
                "answer_text": answer_text,
                "answer_metadata": answer_metadata or {},
                "confidence_score": confidence_score,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            result = self.client.table("intake_lead_qa").insert(qa_row).execute()
            if not result.data:
                return {"ok": False, "data": None, "error": "No data returned from insert"}
            return {"ok": True, "data": result.data[0], "error": None}
        except Exception as e:
            print(f"[save_lead_qa_response] Error: {e}")
            return {"ok": False, "data": None, "error": str(e)}

# Global instance for easy access
lead_qa_service = LeadQAService()
