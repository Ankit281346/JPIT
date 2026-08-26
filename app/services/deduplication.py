from typing import Tuple, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database.repository import Repository
from app.utils.logger import setup_logger

logger = setup_logger("services.deduplication")


class DeduplicationService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def is_duplicate(self, job_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Checks if a job or submission already exists in the system."""
        post_url = job_data.get("linkedin_post_url", "").strip()
        recruiter_email = job_data.get("recruiter_email", "").strip()
        job_title = job_data.get("job_title", "").strip()
        company_name = job_data.get("company_name", "").strip()

        is_dup, reason = self.repo.is_job_duplicate(
            linkedin_post_url=post_url,
            recruiter_email=recruiter_email,
            job_title=job_title,
            company_name=company_name,
        )

        if is_dup:
            logger.info(f"Duplicate detected: {reason}")
        return is_dup, reason
