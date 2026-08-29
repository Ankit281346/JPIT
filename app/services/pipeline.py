import os
import shutil
import json
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from app.config.settings import get_settings
from app.database.repository import Repository
from app.database.models import Candidate, Job, Submission
from app.resume.parser import ResumeParser, ParsedResume
from app.resume.analyzer import ResumeAnalyzer
from app.resume.customizer import ResumeCustomizer
from app.resume.pdf_generator import ResumePDFGenerator
from app.linkedin.auth import LinkedInAuth
from app.linkedin.search import LinkedInSearcher
from app.linkedin.scraper import PostScraper
from app.linkedin.filters import PostFilter
from app.gmail.sender import EmailSender
from app.services.deduplication import DeduplicationService
from app.services.tracking import TrackingService
from app.utils.logger import setup_logger

logger = setup_logger("services.pipeline")


class PipelineService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = Repository(db)
        self.settings = get_settings()
        self.parser = ResumeParser()
        self.analyzer = ResumeAnalyzer()
        self.customizer = ResumeCustomizer()
        self.pdf_generator = ResumePDFGenerator()
        self.post_filter = PostFilter()
        self.scraper = PostScraper()
        self.email_sender = EmailSender()
        self.dedup = DeduplicationService(self.repo)
        self.tracker = TrackingService(self.repo)

    def process_resume_upload(self, pdf_path: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """Parses an uploaded resume PDF, detects primary job title, saves candidate, and generates query."""
        logger.info(f"[Step 1] Parsing uploaded resume: {pdf_path}")
        parsed_resume: ParsedResume = self.parser.parse(pdf_path)

        # Detect primary job title
        primary_title = self.analyzer.determine_primary_job_title(parsed_resume)
        parsed_resume.primary_job_title = primary_title
        logger.info(f"[Step 2] Detected candidate primary job title: {primary_title}")

        # Generate search query
        search_query = self.analyzer.generate_search_query(primary_title)
        logger.info(f"[Step 3] Generated LinkedIn search query: {search_query}")

        # Save candidate in database
        saved_filename = filename or os.path.basename(pdf_path)
        dest_dir = os.path.join(self.settings.BASE_DIR, self.settings.RESUMES_DIR)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, saved_filename)
        if os.path.abspath(pdf_path) != os.path.abspath(dest_path) and os.path.exists(pdf_path):
            shutil.copy2(pdf_path, dest_path)

        candidate = self.repo.create_candidate(
            name=parsed_resume.name,
            email=parsed_resume.email,
            phone=parsed_resume.phone,
            linkedin_url=parsed_resume.linkedin_url,
            location=parsed_resume.location,
            work_authorization=parsed_resume.work_authorization,
            availability=parsed_resume.availability,
            total_experience=parsed_resume.total_experience,
            expected_salary=parsed_resume.expected_salary,
            skills=parsed_resume.skills,
            education=[e.model_dump() if hasattr(e, "model_dump") else e.dict() for e in parsed_resume.education],
            work_experience=[w.model_dump() if hasattr(w, "model_dump") else w.dict() for w in parsed_resume.work_experience],
            primary_job_title=primary_title,
            raw_text=parsed_resume.raw_text,
            resume_filename=saved_filename,
        )

        logger.info(f"Saved candidate record in database (ID: {candidate.id})")

        return {
            "candidate_id": candidate.id,
            "candidate_name": candidate.name,
            "primary_job_title": primary_title,
            "search_query": search_query,
            "skills_count": len(parsed_resume.skills),
            "experience_count": len(parsed_resume.work_experience),
        }

    def _run_linkedin_search_sync(self, search_query: str, max_posts: int) -> List[Dict[str, Any]]:
        """Synchronous LinkedIn search runner executed safely in worker thread."""
        auth = LinkedInAuth()
        if not auth.has_saved_session():
            raise RuntimeError(
                "LinkedIn session not found. Please log in first by running 'python scripts/linkedin_login.py' in your terminal."
            )
        with sync_playwright() as p:
            context = auth.get_authenticated_context(p)
            if context is None:
                raise RuntimeError(
                    "LinkedIn session is expired or invalid. Please re-run 'python scripts/linkedin_login.py' to log in."
                )
            try:
                searcher = LinkedInSearcher(context)
                raw_posts = searcher.search_posts(search_query, max_results=max_posts)
                return raw_posts
            finally:
                context.close()

    async def search_and_filter_linkedin_posts(
        self,
        search_query: str,
        max_posts: int = 80,
        mock_raw_posts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Performs LinkedIn post discovery, filtering, deduplication, and stores valid jobs."""
        logger.info(f"[Step 4] Starting LinkedIn search for query: {search_query}")
        raw_posts: List[Dict[str, Any]] = []

        if mock_raw_posts is not None:
            raw_posts = mock_raw_posts
            logger.info(f"Using {len(raw_posts)} provided search posts.")
        else:
            raw_posts = await asyncio.to_thread(self._run_linkedin_search_sync, search_query, max_posts)

        logger.info(f"Discovered {len(raw_posts)} raw LinkedIn posts")

        discovered_jobs = []
        filtered_out = []
        duplicates_skipped = []

        for post in raw_posts:
            normalized_job = self.scraper.parse_raw_post(post)

            # Check filtering rules (24h, C2C, no W2/Bench/Sales/Hotlist, email present)
            is_valid, reject_reason = self.post_filter.validate_post(normalized_job)
            if not is_valid:
                logger.info(f"Filtered out post '{normalized_job.get('job_title')}': {reject_reason}")
                filtered_out.append({"post_url": normalized_job.get("linkedin_post_url"), "reason": reject_reason})
                continue

            # Check duplicate rules
            is_dup, dup_reason = self.dedup.is_duplicate(normalized_job)
            if is_dup:
                logger.info(f"Skipping duplicate post: {dup_reason}")
                duplicates_skipped.append({"post_url": normalized_job.get("linkedin_post_url"), "reason": dup_reason})
                continue

            # Save valid job in database
            saved_job = self.repo.create_job(
                linkedin_post_url=normalized_job["linkedin_post_url"],
                recruiter_email=normalized_job["recruiter_email"],
                job_title=normalized_job["job_title"],
                job_description=normalized_job["job_description"],
                recruiter_name=normalized_job.get("recruiter_name"),
                company_name=normalized_job.get("company_name"),
                skills=normalized_job.get("skills", []),
                experience_required=normalized_job.get("experience_required"),
                location=normalized_job.get("location"),
                posted_at=normalized_job.get("posted_at"),
                raw_post_text=normalized_job.get("raw_post_text"),
                status="discovered",
            )
            discovered_jobs.append(saved_job)

        # Dump extracted jobs to data/jobs/
        jobs_dump_path = os.path.join(self.settings.BASE_DIR, self.settings.JOBS_DIR, "latest_jobs.json")
        try:
            with open(jobs_dump_path, "w", encoding="utf-8") as jf:
                json.dump([
                    {
                        "id": j.id,
                        "title": j.job_title,
                        "company": j.company_name,
                        "recruiter": j.recruiter_name,
                        "email": j.recruiter_email,
                        "url": j.linkedin_post_url,
                        "skills": json.loads(j.skills) if j.skills else [],
                    }
                    for j in discovered_jobs
                ], jf, indent=2)
        except Exception as e:
            logger.warning(f"Could not dump jobs JSON: {e}")

        logger.info(
            f"Search Complete -> Discovered: {len(raw_posts)} | Passed: {len(discovered_jobs)} | "
            f"Filtered: {len(filtered_out)} | Duplicates Skipped: {len(duplicates_skipped)}"
        )

        return {
            "total_discovered": len(raw_posts),
            "jobs_passed": len(discovered_jobs),
            "filtered_out_count": len(filtered_out),
            "duplicates_skipped_count": len(duplicates_skipped),
            "jobs": discovered_jobs,
            "filtered_reasons": filtered_out,
            "duplicates": duplicates_skipped,
        }

    def process_and_submit_job(
        self,
        candidate_id: int,
        job_id: int,
    ) -> Dict[str, Any]:
        """Customizes resume, generates PDF, drafts email, validates and sends outreach for a single job."""
        candidate = self.repo.get_candidate(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate ID {candidate_id} not found.")

        job = self.repo.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job ID {job_id} not found.")

        logger.info(f"Processing candidate '{candidate.name}' for Job ID {job.id} ('{job.job_title}' at '{job.company_name}')")

        # 1. Deduplication check prior to processing
        is_dup, dup_reason = self.repo.is_job_duplicate(
            linkedin_post_url=job.linkedin_post_url,
            recruiter_email=job.recruiter_email,
            job_title=job.job_title,
            company_name=job.company_name,
        )
        if is_dup and job.status in ["sent", "dry_run", "email_drafted", "processed"]:
            logger.warning(f"Job #{job.id} is already processed/submitted. Duplicate skip.")
            self.tracker.record_submission(
                candidate_id=candidate.id,
                job_id=job.id,
                candidate_name=candidate.name,
                recruiter_name=job.recruiter_name,
                recruiter_email=job.recruiter_email,
                company=job.company_name,
                job_title=job.job_title,
                job_location=job.location,
                linkedin_post_url=job.linkedin_post_url,
                status="skipped_duplicate",
                error_message=dup_reason,
                is_duplicate=True,
            )
            return {
                "success": False,
                "status": "skipped_duplicate",
                "message": f"Skipped duplicate submission: {dup_reason}",
                "job_id": job.id,
            }

        try:
            self.repo.update_job_status(job.id, "processed")
            job_dict = {
                "job_title": job.job_title,
                "company_name": job.company_name,
                "job_description": job.job_description,
                "skills": json.loads(job.skills) if job.skills else [],
                "recruiter_name": job.recruiter_name,
                "recruiter_email": job.recruiter_email,
                "linkedin_post_url": job.linkedin_post_url,
            }

            # 2. Calculate Match Score (Candidate Profile vs Target Job)
            cand_skills = set(s.lower() for s in (json.loads(candidate.skills) if candidate.skills else []))
            job_skills = set(s.lower() for s in (json.loads(job.skills) if job.skills else []))
            if job_skills and cand_skills:
                overlap = len(cand_skills.intersection(job_skills))
                match_score = round(min(100.0, max(60.0, (overlap / len(job_skills)) * 100.0)), 1)
            else:
                match_score = 85.0

            # 3. Locate Master Resume PDF (One master resume sent to all)
            master_pdf_path = os.path.join(self.settings.BASE_DIR, self.settings.RESUMES_DIR, candidate.resume_filename)
            if not os.path.exists(master_pdf_path):
                if os.path.exists(candidate.resume_filename):
                    master_pdf_path = candidate.resume_filename
                else:
                    # Fallback generation if original file was removed from disk
                    master_pdf_path = self.pdf_generator.generate_pdf(
                        customized_data={
                            "name": candidate.name,
                            "email": candidate.email,
                            "phone": candidate.phone,
                            "linkedin_url": candidate.linkedin_url,
                            "location": candidate.location,
                            "work_authorization": candidate.work_authorization,
                            "availability": candidate.availability,
                            "total_experience": candidate.total_experience,
                            "primary_job_title": candidate.primary_job_title,
                            "skills": json.loads(candidate.skills) if candidate.skills else [],
                            "education": json.loads(candidate.education) if candidate.education else [],
                            "work_experience": json.loads(candidate.work_experience) if candidate.work_experience else [],
                            "summary": candidate.raw_text[:200] if candidate.raw_text else "",
                        },
                        company_name="Master",
                        job_title=candidate.primary_job_title,
                        output_filename=candidate.resume_filename,
                    )

            pdf_path = master_pdf_path
            resume_filename = os.path.basename(pdf_path)
            self.repo.update_job_status(job.id, "resume_ready")

            # 4. Email Drafting, Validation & Sending
            cand_dict = {
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "linkedin_url": candidate.linkedin_url,
                "location": candidate.location,
                "work_authorization": candidate.work_authorization,
                "availability": candidate.availability,
                "total_experience": candidate.total_experience,
                "expected_salary": candidate.expected_salary,
            }

            send_result = self.email_sender.send_outreach_email(
                candidate_data=cand_dict,
                job_data=job_dict,
                pdf_path=pdf_path,
            )

            final_status = send_result.get("status", "failed")
            error_msg = send_result.get("error")

            # 5. Record Submission Tracking in SQLite and CSV
            submission = self.tracker.record_submission(
                candidate_id=candidate.id,
                job_id=job.id,
                candidate_name=candidate.name,
                recruiter_name=job.recruiter_name,
                recruiter_email=job.recruiter_email,
                company=job.company_name,
                job_title=job.job_title,
                job_location=job.location,
                linkedin_post_url=job.linkedin_post_url,
                status=final_status,
                resume_filename=resume_filename,
                match_score=match_score,
                email_subject=send_result.get("subject"),
                email_body=send_result.get("body"),
                error_message=error_msg,
                is_duplicate=False,
            )

            self.repo.update_job_status(job.id, final_status)

            return {
                "success": send_result.get("success", False),
                "status": final_status,
                "job_id": job.id,
                "submission_id": submission.id,
                "candidate_name": candidate.name,
                "recruiter_email": job.recruiter_email,
                "company_name": job.company_name,
                "job_title": job.job_title,
                "match_score": match_score,
                "resume_pdf": pdf_path,
                "resume_filename": resume_filename,
                "email_subject": send_result.get("subject"),
                "dry_run": send_result.get("dry_run", self.settings.DRY_RUN),
                "message_id": send_result.get("message_id"),
                "error": error_msg,
            }

        except Exception as e:
            logger.error(f"Error processing job #{job.id}: {e}")
            self.repo.update_job_status(job.id, "failed")
            self.tracker.record_submission(
                candidate_id=candidate.id,
                job_id=job.id,
                candidate_name=candidate.name,
                recruiter_name=job.recruiter_name,
                recruiter_email=job.recruiter_email,
                company=job.company_name,
                job_title=job.job_title,
                job_location=job.location,
                linkedin_post_url=job.linkedin_post_url,
                status="failed",
                error_message=str(e),
                is_duplicate=False,
            )
            return {
                "success": False,
                "status": "failed",
                "job_id": job.id,
                "error": str(e),
            }
