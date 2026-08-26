import os
import pytest
from app.resume.pdf_generator import ResumePDFGenerator, sanitize_filename_part


def test_sanitize_filename_part():
    assert sanitize_filename_part("Ankit Jaiswal") == "AnkitJaiswal"
    assert sanitize_filename_part("Example Corp, Inc.") == "ExampleCorpInc"
    assert sanitize_filename_part("Senior Python / Backend Developer") == "SeniorPythonBackendDeveloper"


def test_resume_pdf_generation(tmp_path):
    pdf_gen = ResumePDFGenerator(output_dir=str(tmp_path))

    customized_data = {
        "name": "Ankit Jaiswal",
        "email": "ankit@example.com",
        "phone": "555-123-4567",
        "location": "Dallas, TX",
        "work_authorization": "US Citizen",
        "total_experience": "6+ years",
        "primary_job_title": "Python Developer",
        "customized_summary": "Experienced Python Developer with expertise in FastAPI and AWS.",
        "prioritized_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
        "customized_experience": [
            {
                "title": "Senior Python Developer",
                "company": "Acme Corp",
                "dates": "2021 - Present",
                "bullets": ["Developed APIs using FastAPI", "Deployed microservices on AWS"],
            }
        ],
        "education": [
            {
                "degree": "B.S. in Computer Science",
                "institution": "UT Dallas",
                "year": "2018",
            }
        ],
    }

    pdf_path = pdf_gen.generate_pdf(
        customized_data=customized_data,
        company_name="Example Corp",
        job_title="Python Developer",
    )

    assert os.path.exists(pdf_path)
    assert os.path.basename(pdf_path) == "AnkitJaiswal_ExampleCorp_PythonDeveloper.pdf"
    assert os.path.getsize(pdf_path) > 1000

    # Verify PDF signature header
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header.startswith(b"%PDF-")
