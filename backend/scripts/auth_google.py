"""Run once to generate token.json via OAuth."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.google.auth import get_credentials

if __name__ == "__main__":
    creds = get_credentials()
    if creds:
        print("✓ token.json generated successfully at", os.getenv("GOOGLE_TOKEN_PATH", "token.json"))
        print("You can now call Gmail/Forms/Sheets APIs.")
    else:
        print("✗ Failed. Make sure credentials.json exists at", os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
