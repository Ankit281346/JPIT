import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI Configuration
    AI_PROVIDER: str = Field(default="gemini", description="AI provider: gemini, openai, claude")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API Key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic Claude API Key")

    # LinkedIn Configuration
    LINKEDIN_SESSION_PATH: str = Field(default="data/linkedin_session.json", description="Path to save/load Playwright storage state")
    LINKEDIN_HEADLESS: bool = Field(default=False, description="Run Playwright browser headlessly or with UI")

    # Google / Gmail API OAuth Configuration
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, description="Google Cloud OAuth Client ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, description="Google Cloud OAuth Client Secret")
    GMAIL_TOKEN_PATH: str = Field(default="data/gmail_token.json", description="Path to save Gmail OAuth token")
    GMAIL_CREDENTIALS_PATH: str = Field(default="credentials.json", description="Path to client_secrets.json from GCP")

    # Database Configuration
    DATABASE_URL: str = Field(default="sqlite:///./data/api_c2c.db", description="Database connection URL")

    # Pipeline & Safety
    DRY_RUN: bool = Field(default=True, description="When true, emails are drafted and validated but not actually sent")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR")

    @field_validator("LINKEDIN_HEADLESS", mode="before")
    @classmethod
    def parse_linkedin_headless(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return False
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "t", "yes", "y")
        return bool(v)

    @field_validator("DRY_RUN", mode="before")
    @classmethod
    def parse_dry_run(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return True
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "t", "yes", "y")
        return bool(v)

    @field_validator("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", mode="before")
    @classmethod
    def parse_empty_strings(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # Directories
    BASE_DIR: Path = Path("/tmp") if os.environ.get("VERCEL") else Path(__file__).resolve().parent.parent.parent
    RESUMES_DIR: str = Field(default="data/resumes")
    GENERATED_RESUMES_DIR: str = Field(default="data/generated_resumes")
    JOBS_DIR: str = Field(default="data/jobs")
    SUBMISSIONS_DIR: str = Field(default="data/submissions")
    SCREENSHOTS_DIR: str = Field(default="screenshots")
    EVIDENCE_DIR: str = Field(default="evidence")

    @property
    def database_url_resolved(self) -> str:
        if os.environ.get("VERCEL") and "sqlite" in self.DATABASE_URL:
            return "sqlite:////tmp/api_c2c.db"
        return self.DATABASE_URL

    def ensure_directories(self) -> None:
        """Ensure all required runtime data directories exist."""
        dirs = [
            self.RESUMES_DIR,
            self.GENERATED_RESUMES_DIR,
            self.JOBS_DIR,
            self.SUBMISSIONS_DIR,
            self.SCREENSHOTS_DIR,
            self.EVIDENCE_DIR,
            os.path.dirname(self.LINKEDIN_SESSION_PATH),
            os.path.dirname(self.GMAIL_TOKEN_PATH),
        ]
        for d in dirs:
            if d:
                try:
                    os.makedirs(os.path.join(self.BASE_DIR, d), exist_ok=True)
                except Exception:
                    pass


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
