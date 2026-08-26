import os
import json
import time
from typing import Optional, Any
try:
    from playwright.sync_api import sync_playwright, BrowserContext, Page
except ImportError:
    sync_playwright = None
    BrowserContext = Any
    Page = Any
from app.config.settings import get_settings
from app.utils.logger import setup_logger

logger = setup_logger("linkedin.auth")


class LinkedInAuth:
    def __init__(self, session_path: Optional[str] = None):
        self.settings = get_settings()
        self.session_path = session_path or os.path.join(
            self.settings.BASE_DIR, self.settings.LINKEDIN_SESSION_PATH
        )
        os.makedirs(os.path.dirname(self.session_path), exist_ok=True)

    def has_saved_session(self) -> bool:
        """Check if a session storage file already exists."""
        return os.path.exists(self.session_path) and os.path.getsize(self.session_path) > 10

    def get_authenticated_context(self, p, headless: Optional[bool] = None) -> Optional[BrowserContext]:
        """Launches browser and creates an authenticated context, prompting login if needed."""
        is_headless = headless if headless is not None else self.settings.LINKEDIN_HEADLESS

        # Launch Chromium
        browser = p.chromium.launch(
            headless=is_headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        if self.has_saved_session():
            logger.info(f"Loading existing LinkedIn session from: {self.session_path}")
            try:
                context = browser.new_context(
                    storage_state=self.session_path,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                # Verify session validity by checking feed
                page = context.new_page()
                page.goto("https://www.linkedin.com/feed/", timeout=30000, wait_until="domcontentloaded")
                
                if "feed" in page.url or "mynetwork" in page.url or "messaging" in page.url:
                    logger.info("LinkedIn session validated successfully.")
                    page.close()
                    return context
                else:
                    logger.warning("Existing session expired or invalid. Manual login required.")
                    page.close()
                    context.close()
            except Exception as e:
                logger.warning(f"Failed to reuse session: {e}. Re-authenticating...")

        # If we need fresh authentication
        logger.info("Starting interactive LinkedIn authentication flow...")
        if is_headless:
            browser.close()
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
            page.goto("https://www.linkedin.com/login", timeout=45000)
            logger.info("Please log in to LinkedIn in the opened browser window (including solving any MFA/CAPTCHA)...")

            # Wait until user lands on the feed or main home page
            page.wait_for_url(lambda url: "feed" in url or "mynetwork" in url, timeout=60000)
            logger.info("Login detected! Saving session storage state...")
            context.storage_state(path=self.session_path)
            logger.info(f"Saved authenticated session to {self.session_path}")
            page.close()
            return context
        except Exception as e:
            logger.warning(f"LinkedIn authentication prompt ended or timed out: {e}")
            page.close()
            context.close()
            browser.close()
            return None
