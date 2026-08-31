import re
from typing import Dict, Any, Tuple, Optional, List
from app.utils.logger import setup_logger

logger = setup_logger("linkedin.filters")

# Strict exclusion terms for C2C pipeline (specifically non-C2C and bench sales)
EXCLUDED_KEYWORDS = [
    r"\bw2\s+only\b",
    r"\bonly\s+w2\b",
    r"\bno\s+c2c\b",
    r"\bc2c\s+not\s+(?:allowed|accepted|entertained)\b",
    r"\bno\s+corp[- ]to[- ]corp\b",
    r"\blooking for bench\b",
    r"\bcandidate available\b",
    r"\breverse marketing\b",
    r"\bbench\s+sales\b",
    r"\bhotlist\b",
]

# Required C2C confirmation terms
C2C_KEYWORDS = [
    r"\bc2c\b",
    r"\bcorp[- ]to[- ]corp\b",
    r"\bcorp2corp\b",
    r"\b1099\b",
    r"\bc-2-c\b",
    r"\bcontract[- ]to[- ]hire\b",
    r"\bcontract\b",
    r"\bcontractor\b",
    r"\bsubcontract\b",
    r"\bb2b\b",
    r"\bcorp\b",
    r"\bc2h\b",
]

# Recruiter / hiring indicators
HIRING_INDICATORS = [
    r"\bhiring\b",
    r"\burgent requirement\b",
    r"\bjob opening\b",
    r"\bimmediate opening\b",
    r"\blooking for\b",
    r"\bposition\b",
    r"\brole\b",
    r"\bclient requirement\b",
    r"\bopportunity\b",
    r"\bopenings?\b",
    r"\bshare (?:cv|profile|resume|resumes|profiles)\b",
    r"\bsend (?:cv|profile|resume|resumes|profiles)\b",
    r"\breach me\b",
    r"\bemail me\b",
    r"\bneed\b",
    r"\brequirement\b",
]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


class PostFilter:
    def __init__(self):
        pass

    def extract_email(self, text: str) -> Optional[str]:
        """Extracts the first valid professional recruiter email from post text."""
        if not text:
            return None
        
        # Normalize obfuscated emails e.g. "name [at] company.com", "name @ company.com", "name(at)company.com"
        normalized_text = re.sub(r'[\(\[\{]\s*(?:at|@)\s*[\)\]\}]', '@', text, flags=re.IGNORECASE)
        normalized_text = re.sub(r'\s+@\s+', '@', normalized_text)
        normalized_text = re.sub(r'[\(\[\{]\s*(?:dot|\.)\s*[\)\]\}]', '.', normalized_text, flags=re.IGNORECASE)

        matches = EMAIL_REGEX.findall(normalized_text)
        for m in matches:
            clean = m.strip().lower().rstrip(".,;:!?)>\"'")
            # Filter out non-email garbage or image/domain extensions
            if clean.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                continue
            if "example.com" in clean or "linkedin.com" in clean:
                continue
            return clean
        return None

    def is_within_24_hours(self, posted_at_str: str) -> bool:
        """Determines if the post was created within the last 24 hours based on LinkedIn time strings."""
        if not posted_at_str:
            return True  # If ambiguous or live search, allow
        lower = posted_at_str.lower()
        # LinkedIn formats: "1h", "2h", "23h", "10m", "5m", "1d", "just now", "1 day ago", "yesterday"
        if re.search(r"\b(\d+m|\d+h|just now|\d+\s*minutes?|\d+\s*hours?|yesterday|1d|1\s*day)\b", lower):
            return True
        if re.search(r"\b(\d+d|\d+\s*days?|\d+w|\d+\s*weeks?|\d+mo|\d+\s*months?|\d+y|\d+\s*years?)\b", lower):
            # If 2d or more, it's older than 24 hours
            match_days = re.search(r"(\d+)\s*d", lower)
            if match_days and int(match_days.group(1)) <= 1:
                return True
            return False
        return True

    def validate_post(self, post_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates all required C2C post constraints."""
        text = post_data.get("raw_post_text") or post_data.get("job_description") or ""
        text_lower = text.lower()
        title_lower = (post_data.get("job_title") or "").lower()
        full_text = f"{title_lower} {text_lower}"

        # 1. 24-hour check bypassed for mass mailing (all posts allowed)
        # posted_at = post_data.get("posted_at", "")

        # 2. Exclusions Check (W2, Full-Time, Bench, Sales, Hotlist)
        for excl in EXCLUDED_KEYWORDS:
            if re.search(excl, full_text):
                # Check if it explicitly says "No W2" or "Not W2"
                if "no w2" in full_text or "not w2" in full_text:
                    continue
                return False, f"Matched exclusion keyword: {excl}"

        # 3. C2C Opportunity Check
        has_c2c = any(re.search(c2c, full_text) for c2c in C2C_KEYWORDS)
        if not has_c2c:
            return False, "Post does not contain C2C / Corp-to-Corp / Contract keywords"

        # 4. Recruiter / Job-related Post Check
        is_job_related = any(re.search(ind, full_text) for ind in HIRING_INDICATORS)
        if not is_job_related and len(text) < 100:
            return False, "Post is not recognizably job/hiring-related"

        # 5. Recruiter Email Availability Check
        email = post_data.get("recruiter_email") or self.extract_email(text)
        if not email:
            return False, "No valid recruiter email found in post"

        # 6. Valid Job Description Check
        cleaned_text = post_data.get("job_description") or post_data.get("raw_post_text") or ""
        if len(cleaned_text.strip()) < 50:
            return False, "Job description is too short or consists entirely of UI metadata"

        return True, None
