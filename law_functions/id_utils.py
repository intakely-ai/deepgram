# id_utils.py
import uuid

def _normalize_caller_id(candidate):
    value = (candidate or "").strip()
    if value.lower() in {"", "undefined", "null", "none", "unique_caller_id"}:
        return str(uuid.uuid4())
    try:
        uuid.UUID(value)
        return value
    except Exception:
        return str(uuid.uuid4())