"""Run once to generate token.json via OAuth. Use --org 'CLUB NAME' for per-club isolated tokens."""
import os
import sys
import argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.google.auth import get_credentials
from app.config import google_token_path_for_org

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Google OAuth token (per-club isolated)")
    parser.add_argument("--org", type=str, default=None, help='Club name e.g. "FOSS MEC" (creates token_{slug}.json). Omit for default token.json')
    args = parser.parse_args()
    os.environ["ALLOW_INTERACTIVE_AUTH"] = "true"
    org = args.org
    creds = get_credentials(org)
    token_path = google_token_path_for_org(org) if org else os.getenv("GOOGLE_TOKEN_PATH", "token.json")
    if creds:
        print(f"✓ token generated successfully at {token_path} for org={org or 'default'}")
        print(f"  Token file: {token_path}")
        if org:
            print(f"  This club's Forms/Sheets will be created in its own Drive ({org}).")
            print(f"  Rooms sheet remains admin-owned (global) — ensure it is shared as reader to this account.")
        print("You can now call Gmail/Forms/Sheets APIs.")
    else:
        print("✗ Failed. Make sure credentials.json exists at", os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
