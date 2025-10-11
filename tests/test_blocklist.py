import pytest
from app.services.compliance.blocklist_service import BlocklistService

def test_blocklist_replaces_phrase_case_insensitive():
    text = "I was Texting While Driving when the crash happened."
    blocked, sanitized, matches = BlocklistService.check_and_sanitize(text, practice_area="car")
    assert blocked is True
    assert "[REDACTED]" in sanitized
    assert any("texting" in m.lower() for m in matches)

def test_blocklist_no_match_leaves_text():
    text = "I was stopped at a light and someone hit me."
    blocked, sanitized, matches = BlocklistService.check_and_sanitize(text, practice_area="car")
    assert blocked is False
    assert sanitized == text
    assert matches == []

if __name__ == "__main__":
    pytest.main(["-m", "pytest tests/test_blocklist.py"])