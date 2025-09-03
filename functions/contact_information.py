import os

def contact_information(first_name: str, last_name: str, email: str, phone: str):
    """
    Minimal contact info handler. Expand to validate and persist.
    """
    return {
        "ok": True,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone
    }