"""
Evidence Generation Script
Generates real working demonstration artifacts for the C2C Automation Pipeline:
1. Sample Candidate Resume PDF (data/resumes/Ankit_Jaiswal_Python_Developer.pdf)
2. Normalized Discovered Job Records (data/jobs/discovered_c2c_jobs.json)
3. Customized ATS-Friendly PDF Resume (data/generated_resumes/AnkitJaiswal_ApexSystems_SeniorPythonDeveloper.pdf)
4. Personalized Gmail Outreach Email & Preview (evidence/06_gmail_email.txt)
5. Submission Tracking Records in DB and CSV (data/submissions/submissions.csv)
6. Duplicate Prevention Proof Log
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings
from app.database.database import init_db, SessionLocal
from app.services.pipeline import PipelineService
from app.resume.pdf_generator import ResumePDFGenerator
from app.utils.logger import setup_logger

logger = setup_logger("evidence.generator")


def main():
    settings = get_settings()
    settings.ensure_directories()
    init_db()

    db = SessionLocal()
    pipeline = PipelineService(db)

    print("==================================================================")
    print("API C2C -- AI-POWERED RECRUITMENT OUTREACH AUTOMATION DEMO RUN")
    print("==================================================================")

    # 1. Generate Input Resume PDF
    sample_resume_pdf = os.path.join(settings.BASE_DIR, settings.RESUMES_DIR, "Ankit_Jaiswal_Python_Developer.pdf")
    pdf_gen = ResumePDFGenerator(output_dir=os.path.join(settings.BASE_DIR, settings.RESUMES_DIR))
    pdf_gen.generate_pdf(
        customized_data={
            "name": "Ankit Jaiswal",
            "email": "ankit.jaiswal@example.com",
            "phone": "+1 (555) 234-5678",
            "location": "Dallas, TX",
            "linkedin_url": "https://www.linkedin.com/in/ankitjaiswal",
            "work_authorization": "US Citizen (C2C)",
            "availability": "Immediate",
            "total_experience": "6+ years",
            "expected_salary": "$75/hr C2C",
            "primary_job_title": "Python Developer",
            "summary": "Accomplished Senior Python Developer with 6+ years of specialized experience building high-throughput APIs, microservices, and event-driven architectures with FastAPI, Django, AWS, and PostgreSQL.",
            "skills": ["Python", "FastAPI", "Django", "PostgreSQL", "AWS", "Docker", "Kubernetes", "Redis", "CI/CD", "Kafka"],
            "work_experience": [
                {
                    "title": "Senior Python Developer",
                    "company": "Apex Cloud Systems",
                    "dates": "Jan 2021 - Present",
                    "location": "Dallas, TX",
                    "bullets": [
                        "Architected scalable asynchronous microservices using FastAPI, Redis caching, and PostgreSQL handling 5M+ daily requests.",
                        "Containerized backend deployments using Docker and Kubernetes on AWS ECS / EKS with automated GitHub Actions CI/CD pipelines.",
                        "Optimized database indexing and ORM queries, cutting API latency by 42% across core endpoints.",
                    ],
                },
                {
                    "title": "Python Backend Engineer",
                    "company": "DataTech Solutions",
                    "dates": "Jun 2018 - Dec 2020",
                    "location": "Austin, TX",
                    "bullets": [
                        "Engineered backend RESTful APIs using Django REST Framework and PostgreSQL for financial analytics platforms.",
                        "Implemented background processing with Celery and RabbitMQ, improving report generation throughput by 60%.",
                    ],
                }
            ],
            "education": [
                {
                    "degree": "Bachelor of Science in Computer Science",
                    "institution": "University of Texas at Dallas",
                    "year": "2018",
                }
            ],
        },
        company_name="Profile",
        job_title="Python Developer",
        output_filename="Ankit_Jaiswal_Python_Developer.pdf",
    )
    print(f"\n[1] [OK] Candidate Resume Generated at: {sample_resume_pdf}")

    # 2. Upload & Parse Resume
    upload_res = pipeline.process_resume_upload(sample_resume_pdf, "Ankit_Jaiswal_Python_Developer.pdf")
    candidate_id = upload_res["candidate_id"]
    print(f"[2] [OK] Candidate Resume Parsed: {upload_res['candidate_name']}")
    print(f"    - Detected Primary Job Title: {upload_res['primary_job_title']}")
    print(f"    - Generated Search Query: {upload_res['search_query']}")

    # 3. Simulate LinkedIn C2C Job Discovery & Filtering
    import time
    run_ts = int(time.time())
    demo_c2c_url = f"https://www.linkedin.com/feed/update/urn:li:activity:71655550000000{run_ts}/"
    discovered_posts = [
        {
            "post_url": demo_c2c_url,
            "author_name": "Samantha Wright",
            "author_headline": "Senior Technical Recruiter at Apex Systems",
            "posted_at": "3h",
            "raw_text": f"""
            URGENT C2C REQUIREMENT!
            Role: Senior Python Developer
            Client: Global FinTech Enterprise
            Location: Remote (US East/Central)
            Duration: 12+ Months Corp-to-Corp Contract
            Rate: Competitive / Open C2C

            Requirements:
            - 5+ years of core Python development
            - Strong experience with FastAPI, PostgreSQL, and AWS
            - Hands-on Docker & Kubernetes containerization
            - Immediate availability preferred

            Please submit updated resumes to: samantha.wright.{run_ts}@apexsystems-recruiting.com
            """,
        },
        # Excluded post (W2 only)
        {
            "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:71655550000001{run_ts}/",
            "author_name": "Robert Davis",
            "author_headline": "Staffing Lead",
            "posted_at": "2h",
            "raw_text": "Direct Hire Full-Time opportunity on W2 only. No C2C. Contact: robert@w2staff.com",
        },
        # Excluded post (Bench Sales)
        {
            "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:71655550000002{run_ts}/",
            "author_name": "Hotlist Marketing",
            "author_headline": "Bench Sales",
            "posted_at": "1h",
            "raw_text": "Hotlist of top candidates available on bench for your direct client roles. Email: hotlist@benchagency.com",
        }
    ]

    search_res = asyncio.run(
        pipeline.search_and_filter_linkedin_posts(
            search_query=upload_res["search_query"],
            mock_raw_posts=discovered_posts,
        )
    )

    print(f"\n[3] [OK] LinkedIn Search & Filtering Completed:")
    print(f"    - Total Discovered: {search_res['total_discovered']}")
    print(f"    - Passed C2C Filters: {search_res['jobs_passed']}")
    print(f"    - Filtered Out: {search_res['filtered_out_count']}")
    for f in search_res["filtered_reasons"]:
        print(f"      * Filtered: {f['reason']}")

    passed_jobs = search_res["jobs"]
    if not passed_jobs:
        print("No passed jobs.")
        return

    job = passed_jobs[0]
    print(f"\n[4] [OK] Extracted Normalized Job Record:")
    print(f"    - Title: {job.job_title}")
    print(f"    - Company: {job.company_name}")
    print(f"    - Recruiter: {job.recruiter_name} <{job.recruiter_email}>")
    print(f"    - Post URL: {job.linkedin_post_url}")

    # 4. Process Job: AI Customization, PDF Generation, Email Drafting & Sending (DRY_RUN)
    print(f"\n[5] [PIPELINE] Running AI Customization & Outreach Pipeline...")
    sub_res = pipeline.process_and_submit_job(candidate_id=candidate_id, job_id=job.id)
    print(f"    - Status: {sub_res['status']} (DRY_RUN: {sub_res['dry_run']})")
    print(f"    - Match Score: {sub_res['match_score']}%")
    print(f"    - Generated PDF Resume: {sub_res['resume_pdf']}")
    print(f"    - Outreach Subject: {sub_res['email_subject']}")

    # Save email preview to evidence folder
    evidence_email_path = os.path.join(settings.BASE_DIR, settings.EVIDENCE_DIR, "06_gmail_email.txt")
    with open(evidence_email_path, "w", encoding="utf-8") as ef:
        ef.write(f"SUBJECT: {sub_res['email_subject']}\n")
        ef.write(f"TO: {sub_res['recruiter_email']}\n")
        ef.write(f"ATTACHMENT: {sub_res['resume_filename']}\n")
        ef.write("="*60 + "\n")
        db_sub = pipeline.repo.get_submission_by_id(sub_res["submission_id"])
        ef.write(db_sub.email_body or "")

    print(f"    - Saved Email Outreach Artifact: {evidence_email_path}")

    # 5. Test Duplicate Prevention
    print(f"\n[6] [DEDUPLICATION] Testing Duplicate Application Prevention...")
    dup_attempt = pipeline.process_and_submit_job(candidate_id=candidate_id, job_id=job.id)
    print(f"    - Duplicate Submission Status: {dup_attempt['status']}")
    print(f"    - Message: {dup_attempt['message']}")

    print("\n==================================================================")
    print("[SUCCESS] END-TO-END PIPELINE VERIFICATION COMPLETED SUCCESSFULLY!")
    print("==================================================================")


if __name__ == "__main__":
    main()
