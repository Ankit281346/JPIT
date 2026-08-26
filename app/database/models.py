import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def get_utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(100), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)
    work_authorization = Column(String(255), nullable=True)
    availability = Column(String(255), nullable=True)
    total_experience = Column(String(100), nullable=True)
    expected_salary = Column(String(100), nullable=True)
    skills = Column(Text, nullable=True)  # JSON-serialized list
    education = Column(Text, nullable=True)  # JSON-serialized list
    work_experience = Column(Text, nullable=True)  # JSON-serialized list
    primary_job_title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=True)
    resume_filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    submissions = relationship("Submission", back_populates="candidate", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    linkedin_post_url = Column(String(1000), unique=True, nullable=False, index=True)
    recruiter_name = Column(String(255), nullable=True)
    recruiter_email = Column(String(255), nullable=False, index=True)
    company_name = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=False)
    job_description = Column(Text, nullable=False)
    skills = Column(Text, nullable=True)  # JSON-serialized list
    experience_required = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    posted_at = Column(String(100), nullable=True)
    raw_post_text = Column(Text, nullable=True)
    status = Column(String(50), default="discovered")  # discovered, filtered, processed, resume_generated, email_drafted, sent, failed, skipped_duplicate
    created_at = Column(DateTime, default=get_utc_now)

    __table_args__ = (
        UniqueConstraint("recruiter_email", "job_title", "company_name", name="uq_recruiter_job_company"),
    )

    submissions = relationship("Submission", back_populates="job", cascade="all, delete-orphan")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    candidate_name = Column(String(255), nullable=False)
    recruiter_name = Column(String(255), nullable=True)
    recruiter_email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=False)
    job_location = Column(String(255), nullable=True)
    linkedin_post_url = Column(String(1000), nullable=False)
    submission_date = Column(String(50), nullable=False)
    submission_time = Column(String(50), nullable=False)
    email_status = Column(String(50), nullable=False, default="discovered")
    resume_filename = Column(String(255), nullable=True)
    match_score = Column(Float, nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    is_duplicate = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_utc_now)

    candidate = relationship("Candidate", back_populates="submissions")
    job = relationship("Job", back_populates="submissions")

