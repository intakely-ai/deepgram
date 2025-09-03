import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE")

def get_booking_info_by_email(email: str):
    """
    Query Supabase REST for the most recent booking by email.
    Returns {'ok': True/False, ...}
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "error": "Supabase credentials missing"}
    try:
        url = f"{SUPABASE_URL}/rest/v1/lead_booking?email=eq.{email}&order=created_at.desc&limit=1"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"ok": False, "error": f"Supabase error {r.status_code}: {r.text}"}
        data = r.json()
        if not data:
            return {"ok": False, "error": "No booking found for this email"}
        return {"ok": True, "booking": data[0]}
    except Exception as e:
        return {"ok": False, "error": str(e)}