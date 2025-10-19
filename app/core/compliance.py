import re
from typing import Dict, List, Tuple, Set, Optional, Any
import logging
import os

logger = logging.getLogger(__name__)

# Import new BlocklistService
from app.services.compliance.blocklist_service import BlocklistService

class SensitiveDataDetector:
    """Detects sensitive data patterns in text"""
    PATTERNS = {
        "SSN": r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
        "CREDIT_CARD": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "DOB": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    }

    KEYWORDS = {
        "SSN": ["social security", "ssn", "social"],
        "CREDIT_CARD": ["credit card", "visa", "mastercard", "amex", "card number"],
        "DOB": ["date of birth", "dob", "born on", "birthday"],
        "PHI": ["diagnosis", "medical condition", "doctor", "prescription", "hospital", "treatment"]
    }

    @classmethod
    def detect_sensitive_data(cls, text: str) -> Dict[str, List[str]]:
        results: Dict[str, List[str]] = {}
        for data_type, pattern in cls.PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                results.setdefault(data_type, []).extend(matches)

        for data_type, keywords in cls.KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    results.setdefault(data_type, []).append("KEYWORD:" + keyword)

        return {k: v for k, v in results.items() if v}

    @classmethod
    def redact_sensitive_data(cls, text: str) -> Tuple[str, Dict[str, List[str]]]:
        detected = cls.detect_sensitive_data(text)
        redacted_text = text
        for data_type, pattern in cls.PATTERNS.items():
            replacement = f"[REDACTED {data_type}]"
            redacted_text = re.sub(pattern, replacement, redacted_text)
        return redacted_text, detected

def process_user_input(text: str, practice_area: Optional[str] = "general") -> Dict[str, Any]:
    """
    Process user input for compliance issues.
    Priority:
      1. Sensitive/emergency -> deflect immediately
      2. Off-script legal advice keywords -> transfer
      3. Blocklist phrases -> redact & flag
      4. Return processed_text safe to send to LLM/CallSession
    """
    result: Dict[str, Any] = {
        "original_text": text,
        "processed_text": text,
        "has_sensitive_data": False,
        "has_legal_advice_request": False,
        "has_phi": False,
        "is_blocked": False,
        "detected_issues": []
    }

    if not text:
        return result

    # 1) Sensitive data redaction (SSN/CC/DOB)
    redacted_text, sensitive_data = SensitiveDataDetector.redact_sensitive_data(text)
    if sensitive_data:
        result["has_sensitive_data"] = True
        result["processed_text"] = redacted_text
        result["detected_issues"].append({"type": "sensitive_data", "details": sensitive_data})
        # Immediately return processed (do not continue to blocklist to avoid double-processing)
        return result

    # 2) Legal advice / high-risk quick check
    legal_phrases = [
        "legal advice", "how much will i get", "settlement amount", "guarantee", "win my case",
        "what should i do", "should i sue", "what's my case worth"
    ]
    if any(p in text.lower() for p in legal_phrases):
        result["has_legal_advice_request"] = True
        result["detected_issues"].append({"type": "legal_advice_request", "details": []})
        # processed_text left as redacted_text or original, but caller will be transferred
        return result

    # 3) Blocklist checks (practice-specific + general)
    is_blocked, sanitized, matches = BlocklistService.check_and_sanitize(text, practice_area or "general")
    if is_blocked:
        result["is_blocked"] = True
        result["processed_text"] = sanitized
        result["detected_issues"].append({"type": "blocklist_match", "details": matches})
        # Keep sanitized text and flag for downstream handling (deflect or redact per flow)
        return result

    # 4) Normal path
    result["processed_text"] = text
    return result