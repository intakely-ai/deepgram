import os
from .calendar_booking import calendar_booking

def save_lead_booking(**kwargs):
    """
    Sync wrapper expected by agent. Accepts flexible kwargs from agent.
    Delegates to calendar_booking for the calendar create logic.
    """
    # Map common agent keys to calendar_booking signature
    cal_id = kwargs.get("calendar_id")  # optional
    appointment_datetime = kwargs.get("appointment_datetime") or kwargs.get("start_iso") or kwargs.get("appointment_date")
    slot_minutes = int(kwargs.get("slot_minutes", kwargs.get("duration_min", 30)))
    booked_with = kwargs.get("booked_with") or kwargs.get("attorney_name")
    # caller info
    first = kwargs.get("first_name") or kwargs.get("caller_first_name") or ""
    last = kwargs.get("last_name") or kwargs.get("caller_last_name") or ""
    email = kwargs.get("email")
    phone = kwargs.get("phone_number") or kwargs.get("cell_phone")

    # call calendar_booking (stub) — in full implementation call google_calendar.create_event
    result = calendar_booking(booked_with, appointment_datetime, slot_minutes, first, last, email, phone, kwargs.get("location"))
    # persist into Supabase in production
    return result