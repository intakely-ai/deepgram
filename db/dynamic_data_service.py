# db/dynamic_data_service.py
# This file acts as a facade, importing and exposing methods from individual services.
# It keeps the original DynamicDataService class concept for easy replacement.

from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, List
from .core import get_client

class DynamicDataService:
    """
    Facade class providing access to various data services.
    Delegates to individual service modules.
    """
    def __init__(self):
        self.client = get_client()

    async def get_practice_area_by_code(self, area_code: str) -> Optional[Dict]:
        try:
            result = self.client.table("practice_areas").select("*").eq("area_code", area_code).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[get_practice_area_by_code] Error: {e}")
            return None

    async def get_questions_for_practice_area_subtype(
        self, 
        practice_area_code: str,
        subtype_code: Optional[str] = None
    ) -> List[Dict]:
        try:
            query = self.client.table("intake_questions").select("*").eq("practice_area", practice_area_code)
            if subtype_code:
                query = query.eq("state_name", subtype_code)
            result = query.order("display_order").execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"[get_questions] Error: {e}")
            return []

    async def save_lead_qa_response(
        self,
        session_id: str,
        question_id: str,
        answer: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        try:
            data = {
                "response_id": str(uuid4()),
                "session_id": session_id,
                "question_id": question_id,
                "answer_text": answer,
                "answer_metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            result = self.client.table("intake_lead_qa").insert(data).execute()
            return {"ok": True, "data": result.data[0]} if result.data else {"ok": False, "error": "Insert failed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def upsert_lead_new(self, lead_data: Dict) -> Optional[Dict]:
        try:
            # Handle practice_area_code mapping
            if "practice_area_code" in lead_data:
                lead_data["practice_area"] = lead_data.pop("practice_area_code")
            
            lead_data.update({
                "session_id": lead_data.get("session_id", str(uuid4())),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            
            result = self.client.table("intake_leads").upsert(
                lead_data,
                on_conflict="caller_email,tenant_id"
            ).execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[upsert_lead_new] Error: {e}")
            return None

# Maintain the singleton access pattern if desired
# _instance = None
# def get_instance():
#     global _instance
#     if _instance is None:
#         _instance = DynamicDataService()
#     return _instance
dynamic_data_service = DynamicDataService()