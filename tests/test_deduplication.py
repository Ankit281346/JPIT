import pytest
from app.database.repository import Repository
from app.services.deduplication import DeduplicationService


def test_deduplication_by_post_url(db_session):
    repo = Repository(db_session)
    dedup = DeduplicationService(repo)

    # 1. First time creation
    repo.create_job(
        linkedin_post_url="https://www.linkedin.com/feed/update/urn:li:activity:71234567890/",
        recruiter_email="sarah.recruiter@apex.com",
        job_title="Python Developer",
        job_description="C2C Python role with FastAPI and AWS",
        company_name="Apex Systems",
    )

    # 2. Duplicate check with same post URL
    job_data_dup = {
        "linkedin_post_url": "https://www.linkedin.com/feed/update/urn:li:activity:71234567890/",
        "recruiter_email": "another@company.com",
        "job_title": "Different Title",
        "company_name": "Different Company",
    }

    is_dup, reason = dedup.is_duplicate(job_data_dup)
    assert is_dup is True
    assert "already exists" in reason.lower() or "job id" in reason.lower()


def test_deduplication_by_recruiter_and_role(db_session):
    repo = Repository(db_session)
    dedup = DeduplicationService(repo)

    repo.create_job(
        linkedin_post_url="https://www.linkedin.com/feed/update/urn:li:activity:11111/",
        recruiter_email="john.smith@techcorp.com",
        job_title="Java Developer",
        company_name="TechCorp",
        job_description="C2C Java Developer",
    )

    # New URL but same recruiter email, job title, and company
    job_data_dup = {
        "linkedin_post_url": "https://www.linkedin.com/feed/update/urn:li:activity:22222/",
        "recruiter_email": "john.smith@techcorp.com",
        "job_title": "Java Developer",
        "company_name": "TechCorp",
    }

    is_dup, reason = dedup.is_duplicate(job_data_dup)
    assert is_dup is True
    assert "duplicate job found" in reason.lower() or "john.smith" in reason.lower()


def test_deduplication_allows_unique_jobs(db_session):
    repo = Repository(db_session)
    dedup = DeduplicationService(repo)

    repo.create_job(
        linkedin_post_url="https://www.linkedin.com/feed/update/urn:li:activity:33333/",
        recruiter_email="recruiter1@domain.com",
        job_title="DevOps Engineer",
        company_name="Cloud Solutions",
        job_description="AWS DevOps C2C role",
    )

    new_job = {
        "linkedin_post_url": "https://www.linkedin.com/feed/update/urn:li:activity:44444/",
        "recruiter_email": "recruiter2@domain.com",
        "job_title": "Python Developer",
        "company_name": "Data Analytics Corp",
    }

    is_dup, reason = dedup.is_duplicate(new_job)
    assert is_dup is False
    assert reason is None
