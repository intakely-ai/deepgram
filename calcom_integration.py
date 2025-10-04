import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger("calcom_integration")

# Load Cal.com config from environment
CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
CALCOM_BASE_URL = os.getenv("CALCOM_BASE_URL", "https://api.cal.com").rstrip("/")
CALCOM_EVENT_TYPE_ID = os.getenv("CALCOM_EVENT_TYPE_ID", "")  # Default event type

def get_available_slots(
    event_type_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    duration: int = 30
) -> Dict[str, Any]:
    """
    Get available slots from Cal.com for the given event type and date range.
    
    Args:
        event_type_id: Cal.com event type ID (from CALCOM_EVENT_TYPE_ID env var if not specified)
        start_date: Start date in ISO format (defaults to today)
        end_date: End date in ISO format (defaults to 14 days from start)
        duration: Duration in minutes (defaults to 30)
        
    Returns:
        Dict with 'ok' status and 'slots' list or 'error' message
    """
    if not CALCOM_API_KEY:
        return {"ok": False, "error": "Cal.com API key not configured"}
    
    event_type = event_type_id or CALCOM_EVENT_TYPE_ID
    if not event_type:
        return {"ok": False, "error": "No Cal.com event type ID provided"}
    
    # Default date range if not provided
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")
    if not end_date:
        end_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CALCOM_API_KEY}"
    }
    
    try:
        url = f"{CALCOM_BASE_URL}/v1/availabilities"
        params = {
            "eventTypeId": event_type,
            "startTime": start_date,
            "endTime": end_date,
            "duration": duration
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Cal.com API error: {response.status_code} - {response.text}")
            return {"ok": False, "error": f"Cal.com API error: {response.status_code}"}
        
        data = response.json()
        slots = []
        
        # Process the available slots
        for slot in data.get("slots", []):
            start_time = slot.get("startTime")
            end_time = slot.get("endTime")
            if start_time and end_time:
                # Format the slot for our system
                formatted_slot = {
                    "start_iso": start_time,
                    "end_iso": end_time,
                    "label": _format_slot_label(start_time)
                }
                slots.append(formatted_slot)
        
        return {"ok": True, "slots": slots}
    
    except Exception as e:
        logger.exception(f"Error getting Cal.com availability: {e}")
        return {"ok": False, "error": f"Failed to get Cal.com availability: {e}"}

def create_booking(
    email: str,
    name: str,
    start_time: str,
    event_type_id: Optional[str] = None,
    notes: Optional[str] = None,
    phone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a booking in Cal.com
    
    Args:
        email: Attendee email
        name: Attendee name
        start_time: Booking start time in ISO format
        event_type_id: Cal.com event type ID
        notes: Additional booking notes
        phone: Attendee phone number
        
    Returns:
        Dict with booking details or error
    """
    if not CALCOM_API_KEY:
        return {"ok": False, "error": "Cal.com API key not configured"}
    
    event_type = event_type_id or CALCOM_EVENT_TYPE_ID
    if not event_type:
        return {"ok": False, "error": "No Cal.com event type ID provided"}
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CALCOM_API_KEY}"
    }
    
    try:
        url = f"{CALCOM_BASE_URL}/v1/bookings"
        payload = {
            "eventTypeId": event_type,
            "startTime": start_time,
            "attendees": [
                {
                    "email": email,
                    "name": name
                }
            ]
        }
        
        if notes:
            payload["notes"] = notes
        
        if phone:
            payload["attendees"][0]["phone"] = phone
        
        response = requests.post(
            url, 
            headers=headers, 
            json=payload,
            timeout=15
        )
        
        if response.status_code not in (200, 201):
            logger.error(f"Cal.com booking error: {response.status_code} - {response.text}")
            return {"ok": False, "error": f"Cal.com booking error: {response.status_code}"}
        
        booking_data = response.json()
        return {
            "ok": True, 
            "booking": booking_data,
            "meeting_link": booking_data.get("meetingUrl") or booking_data.get("location"),
            "booking_id": booking_data.get("id")
        }
    
    except Exception as e:
        logger.exception(f"Error creating Cal.com booking: {e}")
        return {"ok": False, "error": f"Failed to create Cal.com booking: {e}"}

def reschedule_booking(
    booking_id: str,
    new_start_time: str
) -> Dict[str, Any]:
    """
    Reschedule an existing booking in Cal.com
    
    Args:
        booking_id: Cal.com booking ID
        new_start_time: New start time in ISO format
        
    Returns:
        Dict with updated booking details or error
    """
    if not CALCOM_API_KEY:
        return {"ok": False, "error": "Cal.com API key not configured"}
    
    if not booking_id:
        return {"ok": False, "error": "No booking ID provided"}
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CALCOM_API_KEY}"
    }
    
    try:
        url = f"{CALCOM_BASE_URL}/v1/bookings/{booking_id}"
        payload = {
            "startTime": new_start_time
        }
        
        response = requests.patch(
            url, 
            headers=headers, 
            json=payload,
            timeout=15
        )
        
        if response.status_code != 200:
            logger.error(f"Cal.com reschedule error: {response.status_code} - {response.text}")
            return {"ok": False, "error": f"Cal.com reschedule error: {response.status_code}"}
        
        booking_data = response.json()
        return {
            "ok": True, 
            "booking": booking_data,
            "meeting_link": booking_data.get("meetingUrl") or booking_data.get("location")
        }
    
    except Exception as e:
        logger.exception(f"Error rescheduling Cal.com booking: {e}")
        return {"ok": False, "error": f"Failed to reschedule Cal.com booking: {e}"}

def _format_slot_label(iso_time: str) -> str:
    """Format ISO time string into human-readable label"""
    try:
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        return dt.strftime("%A, %B %d, %Y at %I:%M %p").lstrip("0")
    except Exception:
        return iso_time