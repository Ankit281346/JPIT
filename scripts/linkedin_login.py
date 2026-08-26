"""
Interactive LinkedIn Authentication Script
Run this script to log in to LinkedIn once.
It will open a browser, wait for you to log in (and solve any CAPTCHA/2FA),
and save the authenticated session storage state to data/linkedin_session.json.
"""

import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from app.utils.logger import setup_logger

logger = setup_logger("linkedin.login")


def login():
    settings = get_settings()
    session_path = os.path.join(settings.BASE_DIR, settings.LINKEDIN_SESSION_PATH)
    os.makedirs(os.path.dirname(session_path), exist_ok=True)

    print("==================================================================")
    print("🔐 LINKEDIN INTERACTIVE AUTHENTICATION")
    print("==================================================================")
    print(f"Session will be saved to: {session_path}")
    print("Opening Chromium browser window for LinkedIn login...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            page.goto("https://www.linkedin.com/login", timeout=60000)
            print("\n👉 Please enter your LinkedIn credentials in the opened browser window.")
            print("👉 Complete any Two-Factor Authentication (2FA) or Security Verification (CAPTCHA).")
            print("👉 Waiting for you to reach your LinkedIn Feed...\n")

            # Wait until user reaches feed or network
            page.wait_for_url(
                lambda url: "feed" in url or "mynetwork" in url or "messaging" in url,
                timeout=300000,  # 5 minutes
            )

            print("\n[OK] Login detected successfully!")
            context.storage_state(path=session_path)
            print(f"[OK] Authenticated session saved to: {session_path}")
            print("You can now run searches without logging in again!")

        except Exception as e:
            print(f"\n[ERROR] Authentication failed or timed out: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    login()
