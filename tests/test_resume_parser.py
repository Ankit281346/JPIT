import pytest
from app.resume.parser import ResumeParser, ParsedResume


def test_resume_parser_extracts_candidate_fields(sample_resume_text):
    parser = ResumeParser()
    parsed: ParsedResume = parser.parse(sample_resume_text, is_raw_text=True)

    assert parsed.name == "Ankit Jaiswal"
    assert parsed.email == "ankit.jaiswal@example.com"
    assert "555" in (parsed.phone or "")
    assert "linkedin.com/in/ankitjaiswal" in (parsed.linkedin_url or "")
    assert "Dallas" in (parsed.location or "")
    assert "US Citizen" in (parsed.work_authorization or "")
    assert "Immediate" in (parsed.availability or "")
    assert "6+" in (parsed.total_experience or "")

    # Check skills
    assert "Python" in parsed.skills
    assert "FastAPI" in parsed.skills
    assert "PostgreSQL" in parsed.skills
    assert "Docker" in parsed.skills

    # Check education
    assert len(parsed.education) >= 1
    assert "Computer Science" in parsed.education[0].degree

    # Check work experience
    assert len(parsed.work_experience) >= 2
    assert "Python" in parsed.work_experience[0].title
    assert len(parsed.work_experience[0].bullets) >= 1
