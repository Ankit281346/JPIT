import os
import pytest
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base
from app.config.settings import Settings, get_settings

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(autouse=True)
def enforce_test_env(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory):
    temp_dir = tmp_path_factory.mktemp("c2c_test_data")
    settings = Settings(
        DATABASE_URL=TEST_DB_URL,
        RESUMES_DIR=str(temp_dir / "resumes"),
        GENERATED_RESUMES_DIR=str(temp_dir / "generated_resumes"),
        JOBS_DIR=str(temp_dir / "jobs"),
        SUBMISSIONS_DIR=str(temp_dir / "submissions"),
        SCREENSHOTS_DIR=str(temp_dir / "screenshots"),
        EVIDENCE_DIR=str(temp_dir / "evidence"),
        DRY_RUN=True,
    )
    settings.ensure_directories()
    return settings


from sqlalchemy.pool import StaticPool

@pytest.fixture
def db_session():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_resume_text():
    return """
Ankit Jaiswal
Email: ankit.jaiswal@example.com | Phone: (555) 234-5678 | Location: Dallas, TX
LinkedIn: https://www.linkedin.com/in/ankitjaiswal
Work Authorization: US Citizen | Availability: Immediate | Total Experience: 6+ years

PROFESSIONAL SUMMARY
Results-driven Python Developer with 6+ years of experience designing, developing, and deploying scalable web services, microservices, and REST APIs using Python, Django, FastAPI, AWS, and PostgreSQL.

TECHNICAL SKILLS
Languages: Python, JavaScript, SQL, Bash
Frameworks: FastAPI, Django, Flask, SQLAlchemy
Cloud & DevOps: AWS (EC2, S3, RDS, Lambda), Docker, Kubernetes, CI/CD
Databases: PostgreSQL, MySQL, Redis, MongoDB

PROFESSIONAL EXPERIENCE
Senior Python Developer | Acme Cloud Solutions | Jan 2021 - Present | Dallas, TX
• Architected and maintained high-throughput REST APIs and microservices using FastAPI and PostgreSQL.
• Containerized backend applications using Docker and orchestrated deployments on AWS ECS and Kubernetes.
• Optimized database queries and caching layers with Redis, reducing API response times by 35%.

Python Software Engineer | Tech Innovators LLC | Jun 2018 - Dec 2020 | Austin, TX
• Developed and scaled web applications using Django, Celery, and PostgreSQL.
• Implemented automated CI/CD deployment pipelines using GitHub Actions and AWS CloudFormation.
• Integrated third-party payment gateways and external partner RESTful APIs.

EDUCATION
Bachelor of Science in Computer Science | University of Texas at Dallas | 2018
"""
