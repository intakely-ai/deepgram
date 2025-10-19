import requests
import os
from dotenv import load_dotenv

# load .env in project root
load_dotenv()

# Prefer Cal.com-specific env var names; fall back to a generic one if needed
API_KEY = os.getenv("CALCOM_API_KEY") or os.getenv("CAL_API_KEY")
if not API_KEY:
    raise SystemExit("CALCOM_API_KEY or CAL_API_KEY not set in environment or .env")

# Allow overriding the base URL (useful for staging or if the env provides it)
BASE_URL = os.getenv("CALCOM_BASE_URL", "https://api.cal.com").rstrip('/')

# Cal.com API endpoint to list event types
url = f"{BASE_URL}/v1/event-types"

# Headers with API key for authentication (include both common headers)
headers = {
    'Authorization': f'Bearer {API_KEY}',
    'x-api-key': API_KEY,
    'Content-Type': 'application/json',
}

# Small diagnostic helper (does NOT print the key)
def _diag():
    print(f"Using Cal.com base URL: {BASE_URL}")
    # Show which env var supplied the key (don't print the key itself)
    supplied = 'CALCOM_API_KEY' if os.getenv('CALCOM_API_KEY') else 'CAL_API_KEY'
    print(f"Using API key from env variable: {supplied}")

    # Masked preview and basic sanity checks to help debug common .env issues
    try:
        key_preview = API_KEY[:8] + '...' + API_KEY[-4:]
        print(f"API key preview: {key_preview} (length={len(API_KEY)})")
    except Exception:
        print("API key preview: <unable to preview>")

    problems = []
    if API_KEY.count('cal_live_') > 1:
        problems.append('appears to contain a duplicated token (looks like the key is concatenated)')
    if any(ch.isspace() for ch in API_KEY):
        problems.append('contains whitespace characters')
    if problems:
        print("API key sanity checks: ")
        for p in problems:
            print(" -", p)


def get_event_types():
    _diag()
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        print("Request failed:", str(e))
        return
    if response.status_code == 200:
        try:
            body = response.json()
        except ValueError:
            print("Received non-JSON response")
            print(response.text)
            return

        # API may return a list or a dict with a 'data' list — handle both
        items = body.get('data') if isinstance(body, dict) and 'data' in body else body
        if not items:
            print("No event types returned:", body)
            return

        for event_type in items:
            print(f"Event Type ID: {event_type.get('id')}, Name: {event_type.get('name', 'No Name')}")
    else:
        print(f"Failed to retrieve event types. Status Code: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    get_event_types()
