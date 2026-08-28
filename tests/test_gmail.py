import os
import pytest
from app.gmail.drafts import EmailDraftBuilder
from app.gmail.sender import EmailSender


def test_email_draft_builder_subject_and_body():
    builder = EmailDraftBuilder()
    subject = builder.build_subject("AI Engineer")
    assert subject == "Application — AI Engineer"

    candidate_data = {
        "name": "Arbaz Baig",
        "email": "Baigarabz27@gmail.com",
        "phone": "3122628530",
        "linkedin_url": "https://www.linkedin.com/in/arbazbaig",
        "location": "Chicago, IL",
        "work_authorization": "Initial OPT",
        "availability": "Immediate",
        "total_experience": "4+ Years",
        "expected_salary": "Negotiable",
        "skills": ["Python", "AWS", "Databricks", "SQL"],
    }

    job_data = {
        "job_title": "AI Engineer",
        "recruiter_name": "Raunak Gupta",
        "recruiter_email": "raunak@jgoldmead.com",
        "linkedin_post_url": "https://lnkd.in/p/d_r_DFeV",
        "job_description": "We are looking for an AI Engineer with expertise in Python, AWS, and Databricks.",
    }

    body = builder.build_body(candidate_data, job_data)

    assert "Dear Raunak Gupta," in body
    assert "Application — AI Engineer" == subject
    assert "--- SUBMISSION DETAILS ---" in body
    assert "• Candidate Name: Arbaz Baig" in body
    assert "• Applied Role: AI Engineer" in body
    assert "• Total Experience: 4+ Years" in body
    assert "• Phone / Contact: 3122628530" in body
    assert "• Email Address: Baigarabz27@gmail.com" in body
    assert "• Current Location: Chicago, IL" in body
    assert "• Relocation: Open for relocation" in body
    assert "• Work Authorization: Initial OPT" in body
    assert "• Availability: Immediate" in body
    assert "• Rate / Compensation: Negotiable" in body
    assert "• LinkedIn Profile: https://www.linkedin.com/in/arbazbaig" in body
    assert "Best regards,\nArbaz Baig" in body
    assert "LinkedIn Post URL: https://lnkd.in/p/d_r_DFeV" in body


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

    assert "Application — Python Developer" == result["subject"]
    assert "ankit@example.com" in result["cc"]
    assert "quinn@jpitstaffing.com" in result["cc"]
    assert "kim@jpitstaffing.com" in result["bcc"]

    # Verify MIME headers
    mime_msg = sender.build_mime_message(
        to_email=job_data["recruiter_email"],
        subject=result["subject"],
        body=result["body"],
        pdf_path=str(dummy_pdf),
        cc_emails=result["cc"],
        bcc_emails=result["bcc"],
    )
    assert mime_msg["To"] == "recruiter@hiringagency.com"
    assert "quinn@jpitstaffing.com" in mime_msg["Cc"]
    assert "ankit@example.com" in mime_msg["Cc"]
    assert mime_msg["Bcc"] == "kim@jpitstaffing.com"


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
