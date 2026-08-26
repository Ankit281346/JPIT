import os
import io
import json
import pytest
from app.database.repository import Repository
from app.resume.analyzer import ResumeAnalyzer
from app.resume.parser import ParsedResume, WorkExperience, Education
from app.ai.client import AIClient
from app.ai.prompts import build_customization_prompt
from app.gmail.auth import GmailAuth
from app.gmail.sender import EmailSender
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_analyzer_various_tech_stacks():
    analyzer = ResumeAnalyzer()

    # React Developer
    resume_react = ParsedResume(
        name="Alex River",
        skills=["React", "TypeScript", "Redux", "HTML", "CSS", "Next.js"],
        raw_text="Experienced in React, Next.js and frontend architecture.",
    )
    assert "React" in analyzer.determine_primary_job_title(resume_react)

    # DevOps Engineer
    resume_devops = ParsedResume(
        name="Sam Cloud",
        skills=["AWS", "Kubernetes", "Docker", "Terraform", "CI/CD"],
        raw_text="DevOps and Cloud Infrastructure specialist.",
    )
    assert "DevOps" in analyzer.determine_primary_job_title(resume_devops)

    # Data Engineer
    resume_data = ParsedResume(
        name="Jordan Data",
        skills=["Python", "Spark", "Snowflake", "Airflow", "Databricks"],
        raw_text="Data Engineer with strong Big Data pipeline skills.",
    )
    assert "Data" in analyzer.determine_primary_job_title(resume_data)

    # .NET Developer
    resume_dotnet = ParsedResume(
        name="Chris Dotnet",
        skills=["C#", ".NET Core", "ASP.NET", "SQL Server"],
        raw_text=".NET Developer building enterprise software.",
    )
    assert ".NET" in analyzer.determine_primary_job_title(resume_dotnet)

    # Ambiguous fallback
    resume_generic = ParsedResume(
        name="Generic Person",
        skills=[],
        raw_text="I like working on computer stuff.",
    )
    assert "Software Engineer" in analyzer.determine_primary_job_title(resume_generic)


def test_ai_client_json_extraction_and_sanitization():
    ai_client = AIClient(provider="offline_truthful")

    # 1. Plain json
    raw1 = '{"match_score": 90, "prioritized_skills": ["Python", "FastAPI"]}'
    assert ai_client._extract_json(raw1)["match_score"] == 90

    # 2. Markdown fenced json
    raw2 = '```json\n{"match_score": 85, "prioritized_skills": ["Python"]}\n```'
    assert ai_client._extract_json(raw2)["match_score"] == 85

    # 3. Embedded json in text
    raw3 = 'Here is the response:\n{"match_score": 92, "prioritized_skills": ["AWS"]}\nHope this helps!'
    assert ai_client._extract_json(raw3)["match_score"] == 92

    # 4. Invalid json
    assert ai_client._extract_json("not json at all") is None

    # Test sanitization
    orig = {
        "skills": ["Python", "Django", "PostgreSQL"],
        "work_experience": [{"company": "Tech Corp", "title": "Developer"}],
    }
    ai_output = {
        "match_score": 105.0,  # over 100
        "prioritized_skills": ["Python", "Django", "Hallucinated Skill 123"],
    }
    sanitized = ai_client._validate_and_sanitize(ai_output, orig)
    assert sanitized["match_score"] == 100.0
    assert "Python" in sanitized["prioritized_skills"]
    assert "Django" in sanitized["prioritized_skills"]
    assert "Hallucinated Skill 123" not in sanitized["prioritized_skills"]


def test_build_customization_prompt():
    cand = {
        "name": "Ankit Jaiswal",
        "primary_job_title": "Python Developer",
        "skills": ["Python", "FastAPI"],
        "work_experience": [],
        "education": [],
    }
    job = {
        "job_title": "Senior Python Developer",
        "company_name": "Acme Inc",
        "skills": ["Python", "FastAPI", "AWS"],
        "job_description": "We need Python expert.",
    }
    prompt = build_customization_prompt(cand, job)
    assert "TARGET JOB DESCRIPTION" in prompt
    assert "Senior Python Developer" in prompt
    assert "Ankit Jaiswal" in prompt


def test_repository_crud_methods(db_session):
    repo = Repository(db_session)

    # Create candidate
    cand = repo.create_candidate(
        name="Test Candidate",
        primary_job_title="Python Developer",
        resume_filename="test.pdf",
        email="test@example.com",
    )
    assert cand.id is not None
    assert repo.get_candidate(cand.id).name == "Test Candidate"
    assert repo.get_latest_candidate().id == cand.id

    # Create job
    job = repo.create_job(
        linkedin_post_url="https://linkedin.com/feed/update/test-url-123",
        recruiter_email="test.recruiter@example.com",
        job_title="Python Developer",
        job_description="Sample C2C job description",
    )
    assert job.id is not None
    assert repo.get_job_by_url("https://linkedin.com/feed/update/test-url-123").id == job.id
    assert repo.get_job_by_id(job.id).job_title == "Python Developer"

    # Update job status
    updated_job = repo.update_job_status(job.id, "processed")
    assert updated_job.status == "processed"

    # List all jobs
    jobs = repo.get_all_jobs()
    assert len(jobs) >= 1

    # Create and fetch submission
    sub = repo.create_submission(
        candidate_name="Test Candidate",
        recruiter_email="test.recruiter@example.com",
        job_title="Python Developer",
        linkedin_post_url="https://linkedin.com/feed/update/test-url-123",
        candidate_id=cand.id,
        job_id=job.id,
        email_status="sent",
    )
    assert sub.id is not None
    assert repo.get_submission_by_id(sub.id).email_status == "sent"
    assert len(repo.get_all_submissions()) >= 1


def test_api_edge_cases(tmp_path, db_session):
    # Test non-pdf upload rejected
    bad_upload = client.post(
        "/resume/upload",
        files={"file": ("resume.txt", io.BytesIO(b"Just text"), "text/plain")},
    )
    assert bad_upload.status_code == 400

    # Test job not found
    res = client.get("/jobs/999999")
    assert res.status_code == 404

    # Test download non-existent resume
    res_dl = client.get("/download/resume/non_existent.pdf")
    assert res_dl.status_code == 404
