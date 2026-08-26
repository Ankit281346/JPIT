import os
import json
from typing import Optional, Dict, Any, Tuple
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from app.config.settings import get_settings
from app.utils.logger import setup_logger

logger = setup_logger("gmail.auth")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


# In-memory storage for active OAuth flows (preserves PKCE code_verifier across redirect)
_pending_oauth_flows: Dict[str, Any] = {}


class GmailAuth:
    def __init__(self):
        self.settings = get_settings()
        self.token_path = os.path.join(self.settings.BASE_DIR, self.settings.GMAIL_TOKEN_PATH)
        self.credentials_path = os.path.join(self.settings.BASE_DIR, self.settings.GMAIL_CREDENTIALS_PATH)
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)

    def has_credentials_config(self) -> bool:
        """Checks if GCP OAuth client configuration is provided via file or environment variables."""
        if os.path.exists(self.credentials_path):
            return True
        if self.settings.GOOGLE_CLIENT_ID and self.settings.GOOGLE_CLIENT_SECRET:
            return True
        return False

    def is_authenticated(self) -> bool:
        """Returns True if a valid or successfully refreshed OAuth credential exists."""
        creds = self.get_credentials(interactive=False)
        return creds is not None and creds.valid

    def get_user_email(self) -> Optional[str]:
        """Retrieves the authenticated Gmail user's email address."""
        try:
            service = self.get_service(interactive=False)
            if not service:
                return None
            profile = service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception as e:
            logger.warning(f"Could not retrieve Gmail user profile: {e}")
            return None

    def get_credentials(self, interactive: bool = False) -> Optional[Credentials]:
        """Loads, refreshes, or initiates OAuth 2.0 flow to obtain valid Google credentials."""
        creds = None

        # 1. Check existing saved token
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                logger.debug(f"Loaded existing Gmail token from {self.token_path}")
            except Exception as e:
                logger.warning(f"Failed to read existing Gmail token: {e}")
                creds = None

        # 2. Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired Gmail access token...")
                creds.refresh(Request())
                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
                logger.info("Refreshed and saved Gmail token.")
                return creds
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}. Need re-authentication.")
                creds = None

        # 3. If valid, return
        if creds and creds.valid:
            return creds

        # 4. If non-interactive mode and no valid creds, stop here
        if not interactive:
            return None

        # 5. Interactive authorization flow
        return self.start_interactive_auth()

    def start_interactive_auth(self) -> Optional[Credentials]:
        """Runs the OAuth 2.0 InstalledAppFlow to obtain user consent via browser."""
        flow = None
        if os.path.exists(self.credentials_path):
            logger.info(f"Using client secrets file: {self.credentials_path}")
            try:
                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "web" in data:
                    logger.info("Detected 'web' OAuth client config. Adapting flow for desktop/local server authorization...")
                    web_info = data["web"]
                    installed_config = {
                        "installed": {
                            "client_id": web_info.get("client_id"),
                            "client_secret": web_info.get("client_secret"),
                            "auth_uri": web_info.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                            "token_uri": web_info.get("token_uri", "https://oauth2.googleapis.com/token"),
                            "redirect_uris": web_info.get("redirect_uris") or ["http://localhost:8080/", "http://127.0.0.1:8080/"],
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(installed_config, SCOPES)
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            except Exception as e:
                logger.warning(f"Could not parse credentials file: {e}. Falling back to default loader.")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
        elif self.settings.GOOGLE_CLIENT_ID and self.settings.GOOGLE_CLIENT_SECRET:
            logger.info("Using OAuth credentials from environment variables.")
            client_config = {
                "installed": {
                    "client_id": self.settings.GOOGLE_CLIENT_ID,
                    "client_secret": self.settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost:8080/"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        else:
            logger.warning(
                "No Gmail OAuth client credentials configured (credentials.json or GOOGLE_CLIENT_ID/SECRET missing)."
            )
            return None

        try:
            logger.info("Opening browser for Google OAuth authorization...")
            # Use port=0 so the OS automatically picks an available free port and avoids port collision errors (WinError 10048)
            creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info(f"Successfully authenticated and saved Gmail token to {self.token_path}")
            return creds
        except Exception as e:
            logger.error(f"Google OAuth authorization flow failed: {e}")
            return None

    def get_authorization_url(self, redirect_uri: str) -> Tuple[str, str]:
        """Generates Google OAuth URL for browser redirect flow and stores flow state for PKCE verifier matching."""
        if os.path.exists(self.credentials_path):
            try:
                flow = Flow.from_client_secrets_file(self.credentials_path, scopes=SCOPES, redirect_uri=redirect_uri)
            except Exception:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                flow.redirect_uri = redirect_uri
        elif self.settings.GOOGLE_CLIENT_ID and self.settings.GOOGLE_CLIENT_SECRET:
            client_config = {
                "web": {
                    "client_id": self.settings.GOOGLE_CLIENT_ID,
                    "client_secret": self.settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            }
            flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
        else:
            raise ValueError("No OAuth client credentials configured.")

        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        _pending_oauth_flows[state] = flow
        return authorization_url, state

    def fetch_token_from_code(self, code: str, redirect_uri: str, state: Optional[str] = None) -> Credentials:
        """Exchanges authorization code from redirect callback using preserved PKCE flow state."""
        flow = None
        if state and state in _pending_oauth_flows:
            flow = _pending_oauth_flows.pop(state)
            flow.redirect_uri = redirect_uri
        elif os.path.exists(self.credentials_path):
            try:
                flow = Flow.from_client_secrets_file(self.credentials_path, scopes=SCOPES, redirect_uri=redirect_uri)
            except Exception:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                flow.redirect_uri = redirect_uri
        elif self.settings.GOOGLE_CLIENT_ID and self.settings.GOOGLE_CLIENT_SECRET:
            client_config = {
                "web": {
                    "client_id": self.settings.GOOGLE_CLIENT_ID,
                    "client_secret": self.settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            }
            flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
        else:
            raise ValueError("No OAuth client credentials configured.")

        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(self.token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
        logger.info(f"Successfully saved Gmail OAuth token to {self.token_path}")
        return creds

    def get_service(self, interactive: bool = False) -> Optional[Resource]:
        """Returns initialized Gmail API client resource."""
        creds = self.get_credentials(interactive=interactive)
        if not creds or not creds.valid:
            return None
        try:
            service = build("gmail", "v1", credentials=creds)
            return service
        except Exception as e:
            logger.error(f"Failed to build Gmail service: {e}")
            return None
