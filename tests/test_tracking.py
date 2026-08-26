import os
import csv
import pytest
from app.database.repository import Repository
from app.services.tracking import TrackingService


def test_tracking_service_records_in_db_and_csv(db_session, tmp_path):
    repo = Repository(db_session)
    tracker = TrackingService(repo)
    tracker.csv_path = str(tmp_path / "test_submissions.csv")
    tracker._ensure_csv_file()

    sub = tracker.record_submission(
        candidate_name="Ankit Jaiswal",
        recruiter_email="john@example.com",
        recruiter_name="John Smith",
        company="Example Corp",
        job_title="Python Developer",
        job_location="Remote",
        linkedin_post_url="https://linkedin.com/feed/update/123",
        status="sent",
        resume_filename="AnkitJaiswal_ExampleCorp_PythonDeveloper.pdf",
        match_score=89.5,
        email_subject="Submission for Python Developer | C2C Consultant",
    )

    assert sub.id is not None
    assert sub.candidate_name == "Ankit Jaiswal"
    assert sub.email_status == "sent"

    # Verify CSV content
    assert os.path.exists(tracker.csv_path)
    with open(tracker.csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) >= 2  # Header + 1 row
        headers = reader[0]
        assert "candidate" in headers
        assert "recruiter_email" in headers

        row = reader[1]
        assert row[0] == "Ankit Jaiswal"
        assert row[1] == "john@example.com"
        assert row[2] == "Example Corp"
        assert row[3] == "Python Developer"
        assert row[7] == "sent"
        assert "89.5%" in row[8]
