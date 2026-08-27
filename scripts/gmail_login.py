"""
Interactive Gmail Authentication Script
Run this script to authenticate your Gmail account with Google OAuth 2.0.
Saves the token to data/gmail_token.json.
"""

import os
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from app.gmail.auth import GmailAuth, SCOPES
from google_auth_oauthlib.flow import InstalledAppFlow, Flow

def main():
    settings = get_settings()
    auth = GmailAuth()
    
    print("=" * 66)
    print("🔐 GMAIL INTERACTIVE OAUTH 2.0 AUTHENTICATION")
    print("=" * 66)
    
    if not auth.has_credentials_config():
        print("\n❌ Error: credentials.json not found in project root and GOOGLE_CLIENT_ID not in .env")
        print("Please ensure credentials.json is present in d:\\Projects\\Jpittt\\credentials.json")
        return

    token_path = auth.token_path
    print(f"Token will be saved to: {token_path}")
    print(f"Credentials source: {auth.credentials_path}")

    # Check if existing token is valid
    if auth.is_authenticated():
        email = auth.get_user_email()
        print(f"\n✅ Already authenticated as: {email}")
        choice = input("\nDo you want to re-authenticate with a different account? (y/N): ").strip().lower()
        if choice != 'y':
            print("Keeping existing credentials.")
            return

    print("\nStarting authentication flow...")
    print("If your browser opens to Google Consent screen:")
    print("  1. Select your Google / Gmail account (ensure it's added as a Test User in GCP Console)")
    print("  2. If you see 'Google hasn't verified this app', click 'Advanced' -> 'Go to <App Name> (unsafe)'")
    print("  3. Click 'Continue' to grant Gmail send/compose permissions.\n")

    try:
        with open(auth.credentials_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        is_web = "web" in data
        client_info = data.get("web") or data.get("installed")
        
        # Try local server flow on standard ports
        redirect_uris = client_info.get("redirect_uris", [])
        port = 8080
        
        # Check if port 8080 or port 8000 is in redirect_uris
        found_port = None
        for uri in redirect_uris:
            if "localhost:" in uri or "127.0.0.1:" in uri:
                try:
                    parts = uri.split(":")
                    p = int(parts[2].split("/")[0])
                    found_port = p
                    break
                except Exception:
                    pass
        
        if found_port:
            port = found_port

        installed_config = {
            "installed": {
                "client_id": client_info.get("client_id"),
                "client_secret": client_info.get("client_secret"),
                "auth_uri": client_info.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                "token_uri": client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
                "redirect_uris": [f"http://localhost:{port}/", f"http://127.0.0.1:{port}/", "urn:ietf:wg:oauth:2.0:oob"],
            }
        }

        flow = InstalledAppFlow.from_client_config(installed_config, SCOPES)
        try:
            creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")
        except Exception as local_err:
            print(f"\n⚠️ Local server flow notice: {local_err}")
            print("Falling back to manual authorization URL / code entry...")
            
            # Fallback to manual flow
            flow = InstalledAppFlow.from_client_config(installed_config, SCOPES)
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print(f"\n👉 Open this URL in your browser:\n\n{auth_url}\n")
            code = input("👉 Enter the authorization code: ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials

        # Save credentials
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        # Test verification
        auth_verify = GmailAuth()
        email = auth_verify.get_user_email()
        print("\n" + "=" * 66)
        print(f"🎉 SUCCESS! Connected Gmail Account: {email or 'Authenticated'}")
        print(f"Token saved to: {token_path}")
        print("=" * 66)

    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        print("\nCommon fixes:")
        print("1. Google Cloud Console > APIs & Services > Credentials > Edit OAuth 2.0 Client ID")
        print(f"   Add to Authorized redirect URIs: http://localhost:8080/ and http://localhost:8000/oauth2callback")
        print("2. Google Cloud Console > OAuth consent screen > Test users")
        print("   Ensure the Gmail address you are logging in with is added to the Test users list.")

if __name__ == "__main__":
    main()
