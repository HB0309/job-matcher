"""Run this once to authorize Gmail access.

Steps:
  1. Place your downloaded OAuth credentials file at backend/gmail_credentials.json
  2. Run: python gmail_auth_setup.py
  3. A browser opens — sign in and click Allow
  4. gmail_token.json is saved — that's all you need going forward
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDS_FILE = Path(__file__).parent / "gmail_credentials.json"
TOKEN_FILE = Path(__file__).parent / "gmail_token.json"

if not CREDS_FILE.exists():
    print(f"ERROR: {CREDS_FILE} not found.")
    print("Download it from Google Cloud Console → APIs & Services → Credentials → your OAuth client → Download JSON")
    raise SystemExit(1)

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
creds = flow.run_local_server(port=0)
TOKEN_FILE.write_text(creds.to_json())
print(f"Done! Token saved to {TOKEN_FILE}")
print("You can now use Gmail API for OTP reading — no password needed.")
