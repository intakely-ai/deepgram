import os
import json
import sys
import pathlib
from datetime import datetime

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# Load .env into this process
env_path = pathlib.Path(__file__).parent.parent / ".env"
if env_path.exists():
    print(f"Loading environment from {env_path}")
    for ln in env_path.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Import our modules
import calcom_integration
from law_functions import get_next_available_slots, save_lead_booking_sync

def test_calcom_availability():
    """Test getting available slots from Cal.com"""
    print("\n--- Testing Cal.com Availability ---")
    
    # Set attorney calendar type for this test
    os.environ["ATTORNEY_CALENDAR_TYPE"] = "cal.com"
    
    result = get_next_available_slots(
        count=5,
        slot_minutes=30,
        horizon_days=14
    )
    
    print(json.dumps(result, indent=2))
    return result

def test_calcom_booking(slot=None):
    """Test creating a booking in Cal.com"""
    print("\n--- Testing Cal.com Booking ---")
    
    if not slot and not isinstance(slot, dict):
        # Use the first available slot or a fixed time for testing
        slots = test_calcom_availability()
        if slots.get("ok") and slots.get("slots"):
            slot = slots["slots"][0]
        else:
            # Use a fixed time for testing - REPLACE WITH APPROPRIATE FUTURE TIME
            slot = {
                "start_iso": (datetime.now().replace(hour=14, minute=0) + 
                             datetime.timedelta(days=1)).isoformat()
            }
    
    # Set attorney calendar type for this test
    os.environ["ATTORNEY_CALENDAR_TYPE"] = "cal.com"
    
    result = save_lead_booking_sync(
        unique_caller_id="test-" + datetime.now().strftime("%Y%m%d%H%M%S"),
        email="test@example.com",
        appointment_datetime=slot["start_iso"],
        timezone="America/Los_Angeles",
        platform="video",
        phone_number="1234567890",
        booking_notes="Test booking from API"
    )
    
    print(json.dumps(result, indent=2))
    return result

def test_google_calendar_fallback():
    """Test falling back to Google Calendar"""
    print("\n--- Testing Google Calendar Fallback ---")
    
    # Set attorney calendar type for this test
    os.environ["ATTORNEY_CALENDAR_TYPE"] = "google"
    
    # Get available slots using Google Calendar
    slots_result = get_next_available_slots(
        count=3,
        slot_minutes=30,
        horizon_days=14
    )
    print("Google Calendar Slots:")
    print(json.dumps(slots_result, indent=2))
    
    # Test booking if slots available
    if slots_result.get("ok") and slots_result.get("slots"):
        slot = slots_result["slots"][0]
        booking_result = save_lead_booking_sync(
            unique_caller_id="test-google-" + datetime.now().strftime("%Y%m%d%H%M%S"),
            email="test@example.com",
            appointment_datetime=slot["start_iso"],
            timezone="America/Los_Angeles",
            platform="video",
            booking_notes="Test Google Calendar booking"
        )
        print("Google Calendar Booking:")
        print(json.dumps(booking_result, indent=2))
        return booking_result
    
    return None

if __name__ == "__main__":
    print("Cal.com API Key:", "✓ Set" if os.getenv("CALCOM_API_KEY") else "❌ Missing")
    print("Cal.com Event Type ID:", "✓ Set" if os.getenv("CALCOM_EVENT_TYPE_ID") else "❌ Missing")
    print("Attorney Calendar Type:", os.getenv("ATTORNEY_CALENDAR_TYPE", "google"))
    
    # Test functions
    test_calcom_availability()
    test_calcom_booking()
    test_google_calendar_fallback()