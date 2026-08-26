import pytest
from app.resume.parser import ResumeParser, ParsedResume
from app.resume.customizer import ResumeCustomizer
from app.ai.client import AIClient


def test_ai_customizer_prioritizes_truthful_skills(sample_resume_text):
    parser = ResumeParser()
    parsed: ParsedResume = parser.parse(sample_resume_text, is_raw_text=True)
    parsed.primary_job_title = "Python Developer"

    customizer = ResumeCustomizer(ai_client=AIClient(provider="offline_truthful"))

    job_dict = {
        "job_title": "Python Developer",
        "company_name": "CloudScale Inc",
        "job_description": "Seeking Python Developer with strong FastAPI, Docker, and PostgreSQL experience for a C2C role.",
        "skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
    }

    result = customizer.customize(parsed, job_dict)

    assert result["name"] == "Ankit Jaiswal"
    assert "Python" in result["prioritized_skills"]
    assert "FastAPI" in result["prioritized_skills"]
    assert "match_score" in result
    assert result["match_score"] >= 70.0
    assert result["match_score"] <= 100.0

    # Verify no fabricated company injected
    companies = [exp.get("company") for exp in result.get("customized_experience", [])]
    assert "Acme Cloud Solutions" in companies or "Tech Innovators LLC" in companies
    assert "Fake Hallucinated Company" not in companies
