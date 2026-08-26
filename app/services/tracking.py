import os
import csv
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.config.settings import get_settings
from app.database.repository import Repository
from app.database.models import Submission
from app.utils.logger import setup_logger

logger = setup_logger("services.tracking")

CSV_HEADERS = [
    "candidate",
    "recruiter_email",
    "company",
    "job_title",
    "linkedin_url",
    "submission_date",
    "submission_time",
    "status",
    "match_score",
    "resume_filename",
    "error_message",
]


class TrackingService:
    def __init__(self, repository: Repository):
        self.repo = repository
        self.settings = get_settings()
        self.csv_path = os.path.join(
            self.settings.BASE_DIR, self.settings.SUBMISSIONS_DIR, "submissions.csv"
        )
        self._ensure_csv_file()

    def _ensure_csv_file(self):
        """Ensures the submissions CSV file exists with proper headers."""
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)

    def record_submission(
        self,
        candidate_name: str,
        recruiter_email: str,
        job_title: str,
        linkedin_post_url: str,
        candidate_id: Optional[int] = None,
        job_id: Optional[int] = None,
        recruiter_name: Optional[str] = None,
        company: Optional[str] = None,
        job_location: Optional[str] = None,
        status: str = "discovered",
        resume_filename: Optional[str] = None,
        match_score: Optional[float] = None,
        email_subject: Optional[str] = None,
        email_body: Optional[str] = None,
        error_message: Optional[str] = None,
        is_duplicate: bool = False,
    ) -> Submission:
        """Stores submission record in database and appends to CSV log."""
        # 1. Store in Database
        submission = self.repo.create_submission(
            candidate_id=candidate_id,
            job_id=job_id,
            candidate_name=candidate_name,
            recruiter_name=recruiter_name,
            recruiter_email=recruiter_email,
            company=company,
            job_title=job_title,
            job_location=job_location,
            linkedin_post_url=linkedin_post_url,
            email_status=status,
            resume_filename=resume_filename,
            match_score=match_score,
            email_subject=email_subject,
            email_body=email_body,
            error_message=error_message,
            is_duplicate=is_duplicate,
        )

        # 2. Append to CSV
        try:
            with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    candidate_name,
                    recruiter_email,
                    company or "N/A",
                    job_title,
                    linkedin_post_url,
                    submission.submission_date,
                    submission.submission_time,
                    status,
                    f"{match_score:.1f}%" if match_score is not None else "N/A",
                    resume_filename or "N/A",
                    error_message or "",
                ])
            logger.info(f"Recorded submission in DB (ID: {submission.id}) and CSV ({self.csv_path}) with status '{status}'")
        except Exception as e:
            logger.error(f"Failed to append to CSV: {e}")

        return submission
