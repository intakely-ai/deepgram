import re
from typing import Tuple, List, Set

class BlocklistService:
    """
    Detects and sanitizes high-risk phrases that could harm a client's case.
    Run this BEFORE any storage/logging. Returns (is_blocked, sanitized_text, matches).
    """

    # Minimal representative blocklists — expand with your full FSM lists.
    PIGENERALBLOCKLIST: Set[str] = {
        "texting while driving", "ran a red light", "was at fault", "i caused the crash",
        "i was drunk", "i was on drugs", "i hit the other car", "i rear-ended someone"
    }

    CARACCIDENTBLOCKLIST: Set[str] = {
        "texting while driving", "running a red light", "speeding", "driving under the influence"
    }

    WORKERSCOMP_BLOCKLIST: Set[str] = {
        "working while injured", "on the clock", "employer's fault"
    }

    # Combined quick access mapping (practice_area => set)
    BLOCKLIST_MAP = {
        "general": PIGENERALBLOCKLIST,
        "car": CARACCIDENTBLOCKLIST,
        "workers_comp": WORKERSCOMP_BLOCKLIST,
    }

    @classmethod
    def _compile_patterns(cls, phrases: Set[str]) -> List[re.Pattern]:
        return [re.compile(re.escape(p), flags=re.IGNORECASE) for p in phrases]

    @classmethod
    def check_and_sanitize(cls, user_input: str, practice_area: str = "general") -> Tuple[bool, str, List[str]]:
        """
        Check input against blocklists and return sanitized text plus detected matches.

        Returns:
            (is_blocked, sanitized_text, matches)
        """
        if not user_input:
            return False, user_input, []

        # Choose blocklist
        phrases = set()
        phrases.update(cls.BLOCKLIST_MAP.get("general", set()))
        # include practice-specific if present
        if practice_area and practice_area in cls.BLOCKLIST_MAP:
            phrases.update(cls.BLOCKLIST_MAP[practice_area])

        patterns = cls._compile_patterns(phrases)
        matches: List[str] = []

        sanitized = user_input
        for pat in patterns:
            found = pat.findall(sanitized)
            if found:
                matches.extend(found)
                sanitized = pat.sub("[REDACTED]", sanitized)

        is_blocked = len(matches) > 0
        # Normalize whitespace
        sanitized = re.sub(r"\s{2,}", " ", sanitized).strip()
        return is_blocked, sanitized, matches