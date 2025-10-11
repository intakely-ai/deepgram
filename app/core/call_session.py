from typing import Dict, Any, List, Optional
import json
import logging
import asyncio
from datetime import datetime
import uuid

from app.core.llm_service import get_llm_service
from app.core.prompt_templates import get_intake_system_prompt, get_question_bank
from app.core.compliance import process_user_input, LegalAdviceBlocklist
from db.session_manager import create_session_clock, upsert_ephemeral_log

logger = logging.getLogger(__name__)

class CallSession:
    """
    Manages a call session with history tracking and LLM interactions
    """
    
    def __init__(self, call_sid: str, phone_number: str, firm_id: str = "default_firm"):
        self.call_sid = call_sid
        self.phone_number = phone_number
        self.firm_id = firm_id
        self.session_id = f"call-{uuid.uuid4().hex}"
        self.history: List[Dict[str, str]] = []
        self.extracted_data: Dict[str, Any] = {
            "name": None,
            "email": None,
            "case_type": None,
            "sms_consent": False,
            "phone": phone_number
        }
        self.llm_service = get_llm_service()
        self.question_bank = get_question_bank()
        self.current_question = "greeting"
        self.practice_area = None
        self.created_at = datetime.utcnow().isoformat()
        self.off_script_count = 0
        self.max_off_script = 3  # Max number of off-script questions before transfer
        
    async def initialize(self) -> Dict[str, Any]:
        """Initialize the session in the database"""
        session_data = await create_session_clock(
            unique_caller_id=self.phone_number,
            firm_id=self.firm_id,
            session_id=self.session_id,
            ttl_seconds=86400  # 24 hours
        )
        
        # Log session creation
        await upsert_ephemeral_log(
            self.session_id, 
            {
                "type": "session_created",
                "call_sid": self.call_sid,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return session_data
    
    async def handle_input(self, user_input: str = "") -> Dict[str, Any]:
        """
        Process user input and generate response
        
        Args:
            user_input: Transcribed text from the user
            
        Returns:
            Dictionary with response information
        """
        # For first turn (empty input), send greeting
        if not user_input and not self.history:
            greeting = self.question_bank["greeting"]
            self.history.append({"role": "assistant", "content": greeting})
            await self._log_interaction("", greeting)
            return {
                "response": greeting,
                "next_action": "gather",
                "extracted_data": self.extracted_data
            }
        
        # Process input for compliance issues
        processed = process_user_input(user_input)
        
        # If legal advice requested or off-script, handle accordingly
        if processed["has_legal_advice_request"] or self._is_off_script(processed["processed_text"]):
            self.off_script_count += 1
            await self._log_high_risk_event("off_script", [{"details": "Off-script question"}])
            
            if self.off_script_count >= self.max_off_script:
                # If too many off-script questions, transfer
                transfer_msg = self.question_bank["transfer"]
                self.history.append({"role": "user", "content": processed["processed_text"]})
                self.history.append({"role": "assistant", "content": transfer_msg})
                
                await self._log_interaction(processed["processed_text"], transfer_msg)
                
                return {
                    "response": transfer_msg,
                    "next_action": "transfer",
                    "extracted_data": self.extracted_data
                }
            else:
                # Otherwise use off_script response
                off_script_msg = self.question_bank["off_script"]
                self.history.append({"role": "user", "content": processed["processed_text"]})
                self.history.append({"role": "assistant", "content": off_script_msg})
                
                await self._log_interaction(processed["processed_text"], off_script_msg)
                
                # Return to script with original question
                next_question = self.question_bank[self.current_question]
                self.history.append({"role": "assistant", "content": next_question})
                
                return {
                    "response": f"{off_script_msg} {next_question}",
                    "next_action": "gather",
                    "extracted_data": self.extracted_data
                }
        
        # If sensitive data detected, log it
        if processed["has_sensitive_data"] or processed["has_phi"]:
            await self._log_high_risk_event("sensitive_data", processed["detected_issues"])
            sensitive_msg = self.question_bank["sensitive_data"]
            
            # Add to response but continue script
            processed["processed_text"] += f" [SENSITIVE DATA REDACTED]"
        
        # Add user input to history
        self.history.append({"role": "user", "content": processed["processed_text"]})
        
        # Extract data based on current question
        self._extract_data_from_input(self.current_question, processed["processed_text"])
        
        # Determine next question
        next_question_key = self._determine_next_question()
        next_question = self.question_bank[next_question_key]
        self.current_question = next_question_key
        
        # Add question to history
        self.history.append({"role": "assistant", "content": next_question})
        
        # Log interaction
        await self._log_interaction(processed["processed_text"], next_question)
        
        # Update session data
        await self._update_session_data()
        
        # Handle sensitive data warning if needed
        if processed["has_sensitive_data"] or processed["has_phi"]:
            sensitive_msg = self.question_bank["sensitive_data"]
            return {
                "response": f"{sensitive_msg} {next_question}",
                "next_action": "gather",
                "extracted_data": self.extracted_data
            }
        
        return {
            "response": next_question,
            "next_action": "gather" if next_question_key != "goodbye" else "goodbye",
            "extracted_data": self.extracted_data
        }
    
    def _is_off_script(self, text: str) -> bool:
        """
        Determine if user input is off-script (a question rather than an answer)
        """
        # Simple heuristic: if the input ends with a question mark or starts with common question words
        question_starters = ["what", "how", "when", "why", "where", "can", "could", "will", "would", "should"]
        text_lower = text.lower()
        
        if text.strip().endswith("?"):
            return True
            
        for starter in question_starters:
            if text_lower.startswith(f"{starter} "):
                return True
                
        return False
    
    def _extract_data_from_input(self, current_question: str, user_input: str) -> None:
        """
        Extract relevant data from user input based on current question
        """
        if current_question == "name":
            self.extracted_data["name"] = user_input.strip()
        elif current_question == "email":
            self.extracted_data["email"] = user_input.strip()
        elif current_question == "case_type":
            self.extracted_data["case_type"] = user_input.strip()
            self.practice_area = self._map_case_type_to_practice_area(user_input)
        elif current_question == "sms_consent":
            # Check for affirmative response
            affirmative = ["yes", "yeah", "sure", "ok", "okay", "fine", "yep", "yup"]
            self.extracted_data["sms_consent"] = any(word in user_input.lower().split() for word in affirmative)
    
    def _determine_next_question(self) -> str:
        """
        Determine the next question to ask based on current state
        """
        question_flow = {
            "greeting": "name",
            "name": "case_type",
            "case_type": "email",
            "email": "sms_consent",
            "sms_consent": "schedule",
            "schedule": "goodbye"
        }
        
        return question_flow.get(self.current_question, "goodbye")
    
    def _map_case_type_to_practice_area(self, case_type: str) -> Optional[str]:
        """Map case type to practice area"""
        case_type_lower = case_type.lower()
        
        if any(x in case_type_lower for x in ["accident", "injury", "car", "slip", "fall"]):
            return "personal_injury"
        elif any(x in case_type_lower for x in ["divorce", "custody", "family"]):
            return "family_law"
        elif any(x in case_type_lower for x in ["lemon", "car problem", "vehicle"]):
            return "lemon_law"
        
        return None
    
    async def _log_interaction(self, user_input: str, response: str, error: str = None) -> None:
        """Log interaction to session log"""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "conversation_turn",
            "user_input_preview": user_input[:50] + ("..." if len(user_input) > 50 else ""),
            "response_preview": response[:50] + ("..." if len(response) > 50 else ""),
        }
        
        if error:
            event["error"] = error
            
        await upsert_ephemeral_log(
            self.session_id,
            event,
            extend_ttl_seconds=3600  # extend TTL by 1 hour
        )
    
    async def _log_high_risk_event(self, risk_type: str, details: List[Dict[str, Any]]) -> None:
        """Log high risk event"""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "high_risk_detection",
            "risk_type": risk_type,
            "flag": f"{risk_type.upper()}_DETECTED"
        }
        
        await upsert_ephemeral_log(self.session_id, event)
    
    async def _update_session_data(self) -> None:
        """Update session data in database"""
        update = {
            "lead_data": self.extracted_data,
            "conversation_turns": len(self.history) // 2,  # user + assistant = 1 turn
            "last_updated": datetime.utcnow().isoformat()
        }
        
        if self.practice_area:
            update["practice_area"] = self.practice_area
            
        await upsert_ephemeral_log(self.session_id, update)