import pytest
from importlib import import_module

blocklist = import_module("db.blocklist")

def test_compile_and_detect_simple_phrase():
    rows = [
        {"block_key": "pi_alcohol_admission", "phrase": "was drinking", "regex_pattern": r"was drinking", "severity":"high", "default_action":"redact"},
        {"block_key": "pi_admission_fault", "phrase": "my fault", "regex_pattern": r"my fault", "severity":"high", "default_action":"redact"},
    ]
    compiled = blocklist.compile_blocklist(rows)
    assert isinstance(compiled, list) and len(compiled) == 2

    text = "I was drinking and it was my fault."
    matches = blocklist.detect_high_risk(text, compiled)
    assert "pi_alcohol_admission" in matches
    assert "pi_admission_fault" in matches

def test_anonymized_event_record_shape():
    ev = blocklist.anonymized_event_record("pi_alcohol_admission", "personal_injury")
    assert ev["event"] == "HIGH_RISK_DETECTED"
    assert ev["category"] == "personal_injury"
    assert ev["flag"] == "pi_alcohol_admission"
    assert "timestamp" in ev