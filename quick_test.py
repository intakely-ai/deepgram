from dotenv import load_dotenv
load_dotenv()

from law_functions import practice_area, contact_information, calendar_booking

print("practice_area:", practice_area("personal_injury"))
print("contact_information:", contact_information("John","Doe","john@example.com","+11234567890"))
print("calendar_booking:", calendar_booking("John Doe","2025-08-25T09:00:00-07:00",30,"John","Doe","john@example.com","+11234567890","in-person"))
