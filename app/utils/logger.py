import logging
import sys
import re
from typing import Optional
from app.config.settings import get_settings

# Sensitive patterns to scrub from logs
SENSITIVE_PATTERNS = [
    re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', re.IGNORECASE),
    re.compile(r'(secret["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', re.IGNORECASE),
    re.compile(r'(token["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', re.IGNORECASE),
    re.compile(r'(password["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', re.IGNORECASE),
    re.compile(r'(bearer\s+)([^"\'\s]+)', re.IGNORECASE),
]


class SensitiveDataFilter(logging.Filter):
    """Filter that masks sensitive tokens/keys from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.mask_sensitive(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.mask_sensitive(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.mask_sensitive(str(arg)) for arg in record.args)
        return True

    @staticmethod
    def mask_sensitive(text: str) -> str:
        masked = text
        for pattern in SENSITIVE_PATTERNS:
            masked = pattern.sub(r'\1***REDACTED***', masked)
        return masked


def setup_logger(name: str = "api_c2c") -> logging.Logger:
    """Configures and returns a logger instance with formatting and security filtering."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

    return logger
