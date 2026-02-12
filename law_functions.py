# law_functions.py
import os, json, uuid, requests, asyncio, importlib, logging, re
from datetime import datetime as dt, timedelta
from datetime import timezone as _tz
from zoneinfo import ZoneInfo  # Python 3.9+
from dateutil import parser as dtp  # parse ISO datetimes

# Move FUNCTION_MAP inside __init__.py instead
from .law_functions import practice_area, terms_of_engagement_letter, send_email
from .law_functions.agents.intake_agent import IntakeAgent, create_or_get_caller_id, get_practice_area_questions, save_lead_qa, upsert_lead_information
from .law_functions.booking.booking_functions import BookingManager, save_lead_booking, save_lead_booking_sync, get_calendar_id_by_practice_area
from .law_functions.calendar.availability import get_next_available_slots_sync, check_slot_and_alternatives_sync, get_slots_for_dates
from .law_functions.crm.crm_functions import get_booking_info_by_email, update_client_practice_area
from .law_functions.crm.crm_functions import reschedule_lead_booking
from .law_functions.utils.email_sender import terms_of_engagement_letter, send_email
from .law_functions.utils.datetime_helpers import get_current_datetime

# Initialize services
intake_agent = IntakeAgent()
booking_manager = BookingManager()

# ---------------- Function map ----------------
FUNCTION_MAP = {
    "practice_area": practice_area,
    "terms_of_engagement_letter": terms_of_engagement_letter,
    "send_email": send_email,
    # Intake Agent core
    "create_or_get_caller_id": create_or_get_caller_id,
    "get_current_datetime": get_current_datetime,
    "upsert_lead_information": intake_agent.upsert_lead_information,
    "get_practice_area_questions": intake_agent.get_practice_area_questions,
    "save_lead_qa": intake_agent.save_lead_qa,
    "get_booking_info": intake_agent.get_booking_info,
    "save_booking": intake_agent.save_booking,
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
    "get_practice_area_questions": get_practice_area_questions, # Points to updated version
    "upsert_lead_information": upsert_lead_information, # Points to updated version
    "save_lead_qa": save_lead_qa, # Points to updated version
    "save_lead_booking": save_lead_booking,
}