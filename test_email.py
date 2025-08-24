# test_email.py
from lawfirm_functions import send_email

def test_email():
    result = send_email(
        "test@example.com", 
        "Test Email from Oakwood Law", 
        "This is a test email from our AI phone system."
    )
    print(f"Email test result: {result}")

if __name__ == "__main__":
    test_email()