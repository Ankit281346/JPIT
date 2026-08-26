import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.gmail.auth import GmailAuth
from app.linkedin.auth import LinkedInAuth
from app.linkedin.search import LinkedInSearcher
from app.linkedin.scraper import PostScraper


def test_gmail_auth_methods(tmp_path):
    auth = GmailAuth()
    auth.token_path = str(tmp_path / "token.json")
    auth.credentials_path = str(tmp_path / "creds.json")

    # With no credentials file, get_credentials returns None
    creds = auth.get_credentials()
    assert creds is None

    # get_service returns None safely
    assert auth.get_service() is None


def test_linkedin_auth_has_session(tmp_path):
    session_file = tmp_path / "linkedin_session.json"
    auth = LinkedInAuth(session_path=str(session_file))
    assert auth.has_saved_session() is False

    # Create dummy session
    with open(session_file, "w") as f:
        f.write('{"cookies": [{"name": "li_at", "value": "dummy"}]}')

    assert auth.has_saved_session() is True


def test_linkedin_searcher_mock():
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_elem = MagicMock()
    mock_text_elem = MagicMock()
    sample_text = "Urgent Python Developer role C2C. Contact: rec@apex.com"
    mock_text_elem.inner_text.return_value = sample_text
    mock_elem.inner_text.return_value = sample_text
    mock_elem.inner_html.return_value = f"<div>{sample_text}</div>"
    mock_elem.query_selector.side_effect = lambda sel: mock_text_elem if "text" in sel or "desc" in sel else None
    mock_elem.get_attribute.return_value = "urn:li:activity:12345"

    mock_page.query_selector_all.return_value = [mock_elem]

    searcher = LinkedInSearcher(mock_context)
    results = searcher.search_posts('"Python Developer"', max_results=1)

    assert len(results) >= 1
    assert "urn:li:activity:12345" in results[0]["post_url"]


def test_scraper_fallback_heuristics():
    scraper = PostScraper()
    raw = {
        "raw_text": """
        We have a new contract position.
        Role: Senior Cloud Architect
        Client: Enterprise Systems Inc
        Location: Austin, TX
        Years of experience: 8+ years of experience
        Technologies: AWS, Kubernetes, Terraform, Docker
        Regards,
        Jessica Taylor
        Email: jessica.taylor@enterpriserecruiting.com
        """,
        "author_name": "Jessica Taylor",
        "author_headline": "Senior Talent Partner",
        "post_url": "https://linkedin.com/feed/update/123",
        "posted_at": "5h",
    }

    job = scraper.parse_raw_post(raw)
    assert job["recruiter_name"] == "Jessica Taylor"
    assert job["recruiter_email"] == "jessica.taylor@enterpriserecruiting.com"
    assert job["company_name"] == "Enterprise Systems Inc"
    assert job["job_title"] == "Senior Cloud Architect"
    assert job["location"] == "Austin, TX"
    assert job["experience_required"] == "8+ years of experience"
    assert "AWS" in job["skills"]
    assert "Terraform" in job["skills"]
