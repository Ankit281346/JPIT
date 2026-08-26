import os
import pytest
from app.gmail.drafts import EmailDraftBuilder
from app.gmail.sender import EmailSender


def test_email_draft_builder_subject_and_body():
    builder = EmailDraftBuilder()
    subject = builder.build_subject("Python Developer")
    assert subject == "Submission for Python Developer | C2C Consultant"

    candidate_data = {
        "name": "Ankit Jaiswal",
        "email": "ankit@example.com",
        "phone": "555-0199",
        "linkedin_url": "https://linkedin.com/in/ankitjaiswal",
        "location": "Dallas, TX",
        "work_authorization": "US Citizen",
        "availability": "Immediate",
        "total_experience": "6+ years",
        "expected_salary": "$75/hr C2C",
    }

    job_data = {
        "job_title": "Python Developer",
        "recruiter_name": "John Smith",
        "recruiter_email": "john.smith@techrecruiting.com",
        "linkedin_post_url": "https://linkedin.com/feed/update/urn:li:activity:99999",
        "job_description": "We are seeking a Python Developer with FastAPI and PostgreSQL experience for a C2C client project.",
    }

    body = builder.build_body(candidate_data, job_data)

    assert "Dear John," in body
    assert "Submission for Python Developer" in subject
    assert "Candidate Summary" in body
    assert "Candidate Name: Ankit Jaiswal" in body
    assert "Email: ankit@example.com" in body
    assert "Phone: 555-0199" in body
    assert "LinkedIn Profile: https://linkedin.com/in/ankitjaiswal" in body
    assert "Work Authorization: US Citizen" in body
    assert "Post URL:\nhttps://linkedin.com/feed/update/urn:li:activity:99999" in body
    assert "Job Description:\nWe are seeking a Python Developer" in body
    assert "Best Regards,\n\n\nAnkit Jaiswal" in body


def test_email_validation_rules(tmp_path):
    sender = EmailSender()

    # Create dummy PDF
    dummy_pdf = tmp_path / "valid.pdf"
    with open(dummy_pdf, "wb") as f:
        f.write(b"%PDF-1.4 dummy valid content for testing purposes " + b"x" * 200)

    # 1. Valid data
    valid, err = sender.validate_submission_prerequisites(
        recruiter_email="valid.recruiter@company.com",
        pdf_path=str(dummy_pdf),
        candidate_name="Ankit Jaiswal",
        job_title="Python Developer",
    )
    assert valid is True
    assert err is None

    # 2. Invalid email format
    valid, err = sender.validate_submission_prerequisites(
        recruiter_email="invalid_email_at_nowhere",
        pdf_path=str(dummy_pdf),
        candidate_name="Ankit",
        job_title="Python Developer",
    )
    assert valid is False
    assert "invalid recruiter email" in err.lower()

    # 3. Missing PDF file
    valid, err = sender.validate_submission_prerequisites(
        recruiter_email="recruiter@company.com",
        pdf_path=str(tmp_path / "non_existent.pdf"),
        candidate_name="Ankit",
        job_title="Python Developer",
    )
    assert valid is False
    assert "does not exist" in err.lower()


def test_dry_run_email_send(tmp_path):
    sender = EmailSender()
    sender.settings.DRY_RUN = True

    dummy_pdf = tmp_path / "test_resume.pdf"
    with open(dummy_pdf, "wb") as f:
        f.write(b"%PDF-1.4 sample content for dry run testing " + b"0" * 200)

    candidate_data = {
        "name": "Ankit Jaiswal",
        "email": "ankit@example.com",
        "phone": "555-1234",
        "linkedin_url": "https://linkedin.com/in/ankitjaiswal",
        "location": "Dallas, TX",
        "work_authorization": "US Citizen",
        "availability": "Immediate",
        "total_experience": "6 years",
    }
    job_data = {
        "job_title": "Python Developer",
        "recruiter_email": "recruiter@hiringagency.com",
        "recruiter_name": "Sarah",
        "linkedin_post_url": "https://linkedin.com/feed/update/123",
        "job_description": "C2C Python Role",
    }

    result = sender.send_outreach_email(candidate_data, job_data, str(dummy_pdf))

    assert result["success"] is True
    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    assert "DRY RUN" in result["message"]
    assert "Submission for Python Developer | C2C Consultant" == result["subject"]


def test_real_send_unauthenticated_fails(tmp_path):
    from unittest.mock import MagicMock
    from app.config.settings import Settings
    test_settings = Settings(DRY_RUN=False)
    sender = EmailSender(settings=test_settings)
    sender.auth.is_authenticated = MagicMock(return_value=False)

    dummy_pdf = tmp_path / "test_resume.pdf"
    with open(dummy_pdf, "wb") as f:
        f.write(b"%PDF-1.4 sample content for testing " + b"0" * 200)

    candidate_data = {"name": "Ankit Jaiswal"}
    job_data = {
        "job_title": "Python Developer",
        "recruiter_email": "recruiter@hiringagency.com",
        "recruiter_name": "Sarah",
        "linkedin_post_url": "https://linkedin.com/feed/update/123",
        "job_description": "C2C Python Role",
    }

    result = sender.send_outreach_email(candidate_data, job_data, str(dummy_pdf))

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "Gmail is not authenticated" in result["error"]


def test_real_send_authenticated_success(tmp_path):
    from unittest.mock import MagicMock
    from app.config.settings import Settings
    test_settings = Settings(DRY_RUN=False)
    sender = EmailSender(settings=test_settings)

    # Mock authenticated Gmail API service
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "gmail_msg_abc123", "threadId": "thread_xyz"}
    mock_messages.send.return_value = mock_send
    mock_service.users.return_value.messages.return_value = mock_messages

    sender.auth.is_authenticated = MagicMock(return_value=True)
    sender.auth.get_service = MagicMock(return_value=mock_service)

    dummy_pdf = tmp_path / "test_resume.pdf"
    with open(dummy_pdf, "wb") as f:
        f.write(b"%PDF-1.4 sample content for testing " + b"0" * 200)

    candidate_data = {"name": "Ankit Jaiswal"}
    job_data = {
        "job_title": "Python Developer",
        "recruiter_email": "recruiter@hiringagency.com",
        "recruiter_name": "Sarah",
        "linkedin_post_url": "https://linkedin.com/feed/update/123",
        "job_description": "C2C Python Role",
    }

    result = sender.send_outreach_email(candidate_data, job_data, str(dummy_pdf))

    assert result["success"] is True
    assert result["status"] == "sent"
    assert result["dry_run"] is False
    assert result["message_id"] == "gmail_msg_abc123"


def test_gmail_auth_status_methods():
    from app.gmail.auth import GmailAuth
    auth = GmailAuth()
    # Test checking config and auth methods without crashing
    assert isinstance(auth.has_credentials_config(), bool)
    assert isinstance(auth.is_authenticated(), bool)
