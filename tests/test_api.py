import os
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.database import get_db, init_db, Base, engine
from app.resume.pdf_generator import ResumePDFGenerator

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_database(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.clear()


def test_api_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "api-c2c"


def test_api_web_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "API C2C Automation" in response.text


def test_api_resume_upload_and_pipeline_flow(tmp_path):
    # 1. Create candidate PDF in memory
    pdf_gen = ResumePDFGenerator(output_dir=str(tmp_path))
    pdf_path = pdf_gen.generate_pdf(
        customized_data={
            "name": "Jane Doe",
            "email": "jane.doe@example.com",
            "phone": "555-888-9999",
            "location": "New York, NY",
            "work_authorization": "Green Card",
            "availability": "Immediate",
            "total_experience": "7 years",
            "primary_job_title": "Java Developer",
            "skills": ["Java", "Spring Boot", "Microservices", "AWS", "MySQL"],
            "work_experience": [
                {
                    "title": "Senior Java Developer",
                    "company": "Enterprise Tech",
                    "dates": "2020 - Present",
                    "bullets": ["Developed Spring Boot microservices", "Configured AWS RDS"],
                }
            ],
            "education": [{"degree": "B.S. Software Engineering", "institution": "NYU", "year": "2017"}],
        },
        company_name="Sample",
        job_title="Java Developer",
        output_filename="Jane_Doe_Resume.pdf",
    )

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    # Upload resume
    upload_resp = client.post(
        "/resume/upload",
        files={"file": ("Jane_Doe_Resume.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert upload_resp.status_code == 200
    up_data = upload_resp.json()
    assert up_data["success"] is True
    cand_id = up_data["data"]["candidate_id"]

    # Search LinkedIn with mock posts
    search_payload = {
        "candidate_id": cand_id,
        "mock_posts": [
            {
                "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:9191919191/",
                "author_name": "David Recruiter",
                "author_headline": "Lead Recruiter at GlobalStaff",
                "posted_at": "4h",
                "raw_text": """
                Immediate C2C Opening!
                Position: Senior Java Developer
                Company: Global FinTech
                Location: Hybrid NYC
                Requirements: Java, Spring Boot, Microservices, AWS
                Email resumes: david@globalstaff.com
                """,
            }
        ],
    }
    search_resp = client.post("/linkedin/search", json=search_payload)
    assert search_resp.status_code == 200
    s_data = search_resp.json()
    assert s_data["summary"]["passed_filters"] == 1
    job_id = s_data["jobs"][0]["id"]

    # Get job details
    job_resp = client.get(f"/jobs/{job_id}")
    assert job_resp.status_code == 200
    assert job_resp.json()["recruiter_email"] == "david@globalstaff.com"

    # Process and Send outreach
    send_resp = client.post(f"/jobs/{job_id}/send", json={"candidate_id": cand_id})
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    assert send_data["status"] == "dry_run"

    # Verify submissions list
    subs_resp = client.get("/submissions")
    assert subs_resp.status_code == 200
    subs_data = subs_resp.json()
    assert subs_data["count"] >= 1
    assert any(s["recruiter_email"] == "david@globalstaff.com" for s in subs_data["submissions"])


def test_api_gmail_status_endpoint():
    resp = client.get("/gmail/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "authenticated" in data
    assert "dry_run" in data
    assert "credentials_configured" in data
