import pytest
from app.linkedin.filters import PostFilter


def test_filters_accept_valid_c2c_post():
    filter_service = PostFilter()
    valid_post = {
        "job_title": "Python Developer",
        "recruiter_email": "recruiter@apextech.com",
        "posted_at": "3h",
        "raw_post_text": """
        Urgent Requirement! Looking for Senior Python Developer for a Corp-to-Corp (C2C) contract role.
        Location: Remote / Dallas, TX
        Skills: Python, FastAPI, AWS, PostgreSQL
        Experience: 5+ years
        Send resume to: recruiter@apextech.com
        """,
    }

    is_valid, reason = filter_service.validate_post(valid_post)
    assert is_valid is True
    assert reason is None


def test_filters_reject_w2_post():
    filter_service = PostFilter()
    post = {
        "job_title": "Python Developer",
        "recruiter_email": "recruiter@apextech.com",
        "posted_at": "2h",
        "raw_post_text": "Hiring Python Developer on W2 only. No C2C. Contact: recruiter@apextech.com",
    }
    is_valid, reason = filter_service.validate_post(post)
    assert is_valid is False
    assert "exclusion" in reason.lower() or "w2" in reason.lower()


def test_filters_reject_full_time_post():
    filter_service = PostFilter()
    post = {
        "job_title": "Python Developer",
        "recruiter_email": "recruiter@apextech.com",
        "posted_at": "2h",
        "raw_post_text": "Direct hire Full-Time opportunity for Python Engineer. Email: recruiter@apextech.com",
    }
    is_valid, reason = filter_service.validate_post(post)
    assert is_valid is False


def test_filters_reject_bench_and_hotlist_posts():
    filter_service = PostFilter()
    bench_post = {
        "job_title": "Available Candidates",
        "recruiter_email": "sales@benchagency.com",
        "posted_at": "1h",
        "raw_post_text": "Hotlist of candidates on bench available for C2C requirements. Email: sales@benchagency.com",
    }
    is_valid, reason = filter_service.validate_post(bench_post)
    assert is_valid is False


def test_filters_reject_missing_recruiter_email():
    filter_service = PostFilter()
    no_email_post = {
        "job_title": "Python Developer",
        "recruiter_email": "",
        "posted_at": "1h",
        "raw_post_text": "Great C2C role for Python developer. DM me on LinkedIn to apply!",
    }
    is_valid, reason = filter_service.validate_post(no_email_post)
    assert is_valid is False
    assert "email" in reason.lower()


def test_filters_reject_older_than_24_hours():
    filter_service = PostFilter()
    old_post = {
        "job_title": "Python Developer",
        "recruiter_email": "john@example.com",
        "posted_at": "5d",
        "raw_post_text": "C2C opening for Python developer. Email john@example.com",
    }
    is_valid, reason = filter_service.validate_post(old_post)
    assert is_valid is False
    assert "24 hours" in reason.lower()
