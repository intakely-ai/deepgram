import os

# Import modular function implementations
from functions.practice_area import practice_area
from functions.contact_information import contact_information
from functions.calendar_booking import calendar_booking
from functions.save_lead_booking import save_lead_booking
from functions.get_booking_info_by_email import get_booking_info_by_email
from functions.reschedule_calendar_booking import reschedule_calendar_booking

# Re-export any helpers or constants as needed
BUSINESS_TZ = os.getenv("BUSINESS_TZ", "America/Los_Angeles")

# Map names to callables expected by the agent
FUNCTION_MAP = {
    "practice_area": practice_area,
    "contact_information": contact_information,
    "calendar_booking": calendar_booking,
    "save_lead_booking": save_lead_booking,
    "get_booking_info_by_email": get_booking_info_by_email,
    "reschedule_calendar_booking": reschedule_calendar_booking,
}