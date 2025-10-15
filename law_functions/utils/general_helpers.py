# utils/general_helpers.py
import uuid

# ---------------- ID helpers ----------------
def normalize_caller_id(candidate):
    """Normalize a caller ID candidate into a valid UUID string."""
    value = (candidate or "").strip()
    if value.lower() in {"", "undefined", "null", "none", "unique_caller_id"}:
        return str(uuid.uuid4())
    try:
        uuid.UUID(value)
        return value
    except Exception:
        return str(uuid.uuid4())

# Add other general-purpose if any emerges