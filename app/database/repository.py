import json
import datetime
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database.models import Candidate, Job, Submission


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # ---------------- CANDIDATE OPERATIONS ----------------
    def create_candidate(
        self,
        name: str,
        primary_job_title: str,
        resume_filename: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        location: Optional[str] = None,
        work_authorization: Optional[str] = None,
        availability: Optional[str] = None,
        total_experience: Optional[str] = None,
        expected_salary: Optional[str] = None,
        skills: Optional[List[str]] = None,
        education: Optional[List[dict]] = None,
        work_experience: Optional[List[dict]] = None,
        raw_text: Optional[str] = None,
    ) -> Candidate:
        candidate = Candidate(
            name=name,
            email=email,
            phone=phone,
            linkedin_url=linkedin_url,
            location=location,
            work_authorization=work_authorization,
            availability=availability,
            total_experience=total_experience,
            expected_salary=expected_salary,
            skills=json.dumps(skills or []),
            education=json.dumps(education or []),
            work_experience=json.dumps(work_experience or []),
            primary_job_title=primary_job_title,
            raw_text=raw_text,
            resume_filename=resume_filename,
        )
        self.db.add(candidate)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    def get_candidate(self, candidate_id: int) -> Optional[Candidate]:
        return self.db.query(Candidate).filter(Candidate.id == candidate_id).first()

    def get_latest_candidate(self) -> Optional[Candidate]:
        return self.db.query(Candidate).order_by(Candidate.id.desc()).first()

    # ---------------- JOB OPERATIONS ----------------
    def create_job(
        self,
        linkedin_post_url: str,
        recruiter_email: str,
        job_title: str,
        job_description: str,
        recruiter_name: Optional[str] = None,
        company_name: Optional[str] = None,
        skills: Optional[List[str]] = None,
        experience_required: Optional[str] = None,
        location: Optional[str] = None,
        posted_at: Optional[str] = None,
        raw_post_text: Optional[str] = None,
        status: str = "discovered",
    ) -> Job:
        job = Job(
            linkedin_post_url=linkedin_post_url,
            recruiter_name=recruiter_name,
            recruiter_email=recruiter_email,
            company_name=company_name,
            job_title=job_title,
            job_description=job_description,
            skills=json.dumps(skills or []),
            experience_required=experience_required,
            location=location,
            posted_at=posted_at,
            raw_post_text=raw_post_text,
            status=status,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job_by_url(self, url: str) -> Optional[Job]:
        return self.db.query(Job).filter(Job.linkedin_post_url == url).first()

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        return self.db.query(Job).filter(Job.id == job_id).first()

    def get_job_by_recruiter_and_role(
        self, recruiter_email: str, job_title: str, company_name: Optional[str] = None
    ) -> Optional[Job]:
        query = self.db.query(Job).filter(
            Job.recruiter_email.ilike(recruiter_email.strip()),
            Job.job_title.ilike(job_title.strip()),
        )
        if company_name:
            query = query.filter(Job.company_name.ilike(company_name.strip()))
        return query.first()

    def is_job_duplicate(
        self,
        linkedin_post_url: str,
        recruiter_email: Optional[str] = None,
        job_title: Optional[str] = None,
        company_name: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        # 1. Check exact post URL
        if linkedin_post_url:
            existing_url = self.get_job_by_url(linkedin_post_url)
            if existing_url:
                return True, f"Job already exists with URL: {linkedin_post_url} (Job ID: {existing_url.id})"

        # 2. Check Recruiter Email + Job Title + Company
        if recruiter_email and job_title:
            existing_combo = self.get_job_by_recruiter_and_role(recruiter_email, job_title, company_name)
            if existing_combo:
                return True, f"Duplicate job found for recruiter {recruiter_email}, title '{job_title}', company '{company_name}' (Job ID: {existing_combo.id})"

        # 3. Check Submissions table for previous outreach
        if linkedin_post_url:
            sub = self.db.query(Submission).filter(Submission.linkedin_post_url == linkedin_post_url).first()
            if sub:
                return True, f"Already submitted to URL: {linkedin_post_url} (Submission ID: {sub.id})"

        if recruiter_email and job_title:
            sub_combo = self.db.query(Submission).filter(
                Submission.recruiter_email.ilike(recruiter_email.strip()),
                Submission.job_title.ilike(job_title.strip()),
            ).first()
            if sub_combo:
                return True, f"Already submitted to {recruiter_email} for '{job_title}' (Submission ID: {sub_combo.id})"

        return False, None

    def get_all_jobs(self, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> List[Job]:
        query = self.db.query(Job)
        if status:
            query = query.filter(Job.status == status)
        return query.order_by(Job.id.desc()).offset(skip).limit(limit).all()

    def update_job_status(self, job_id: int, status: str) -> Optional[Job]:
        job = self.get_job_by_id(job_id)
        if job:
            job.status = status
            self.db.commit()
            self.db.refresh(job)
        return job

    # ---------------- SUBMISSION OPERATIONS ----------------
    def create_submission(
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
        email_status: str = "discovered",
        resume_filename: Optional[str] = None,
        match_score: Optional[float] = None,
        email_subject: Optional[str] = None,
        email_body: Optional[str] = None,
        error_message: Optional[str] = None,
        is_duplicate: bool = False,
    ) -> Submission:
        now = datetime.datetime.now()
        submission = Submission(
            candidate_id=candidate_id,
            job_id=job_id,
            candidate_name=candidate_name,
            recruiter_name=recruiter_name,
            recruiter_email=recruiter_email,
            company=company,
            job_title=job_title,
            job_location=job_location,
            linkedin_post_url=linkedin_post_url,
            submission_date=now.strftime("%Y-%m-%d"),
            submission_time=now.strftime("%H:%M:%S"),
            email_status=email_status,
            resume_filename=resume_filename,
            match_score=match_score,
            email_subject=email_subject,
            email_body=email_body,
            error_message=error_message,
            is_duplicate=is_duplicate,
        )
        self.db.add(submission)
        self.db.commit()
        self.db.refresh(submission)
        return submission

    def get_all_submissions(self, skip: int = 0, limit: int = 100) -> List[Submission]:
        return self.db.query(Submission).order_by(Submission.id.desc()).offset(skip).limit(limit).all()

    def get_submission_by_id(self, submission_id: int) -> Optional[Submission]:
        return self.db.query(Submission).filter(Submission.id == submission_id).first()
