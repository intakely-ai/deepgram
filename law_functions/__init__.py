# law_functions/law_functions.py (or __init__.py if applicable)
# This file re-exports functions from the modularized files to maintain the original FUNCTION_MAP interface.

# Import functions from their new locations
from .agents.intake_agent import (
    practice_area,
    create_or_get_caller_id,
    upsert_lead_information,
    save_lead_qa,
    get_practice_area_questions,
)
from .utils.datetime_helpers import get_current_datetime
from .booking.booking_functions import (
    save_lead_booking_sync,
    get_calendar_id_by_practice_area,
)
from .calendar.availability import (
    get_next_available_slots_sync,
    check_slot_and_alternatives_sync,
    get_slots_for_dates,
)
from .crm.crm_functions import (
    get_booking_info_by_email,
    update_client_practice_area,
)
from .crm.rechedule_functions import reschedule_lead_booking
from .utils.email_helpers import (
    terms_of_engagement_letter,
    send_email
)

# Define the function map using the imported functions
FUNCTION_MAP = {
    "practice_area": practice_area,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,
    # Intake Agent core
    "create_or_get_caller_id": create_or_get_caller_id,
    "get_current_datetime": get_current_datetime,
    "upsert_lead_information": upsert_lead_information,
    "get_practice_area_questions": get_practice_area_questions,
    "save_lead_qa": save_lead_qa,
    # Booking
    "get_calendar_id_by_practice_area": get_calendar_id_by_practice_area,
    "get_next_available_slots": get_next_available_slots_sync,
    "check_slot_and_alternatives": check_slot_and_alternatives_sync,
    "get_slots_for_dates": get_slots_for_dates,
    "save_lead_booking": save_lead_booking_sync,
    "reschedule_lead_booking": reschedule_lead_booking,
    # CRM / returning client
    "get_booking_info_by_email": get_booking_info_by_email,
    "update_client_practice_area": update_client_practice_area,
}

# Optional: Make these functions available at the package level if this is __init__.py
# __all__ = list(FUNCTION_MAP.keys())