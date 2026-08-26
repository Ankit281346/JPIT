import os
import json
import pytest
from app.services.pipeline import PipelineService
from app.resume.pdf_generator import ResumePDFGenerator


def test_full_pipeline_minimum_acceptance_flow(db_session, tmp_path, sample_resume_text):
    # Step 0: Create a real PDF resume for candidate
    test_resume_path = str(tmp_path / "Ankit_Jaiswal_Resume.pdf")
    pdf_gen = ResumePDFGenerator(output_dir=str(tmp_path))
    pdf_gen.generate_pdf(
        customized_data={
            "name": "Ankit Jaiswal",
            "email": "ankit.jaiswal@example.com",
            "phone": "555-234-5678",
            "location": "Dallas, TX",
            "work_authorization": "US Citizen",
            "availability": "Immediate",
            "total_experience": "6+ years",
            "primary_job_title": "Python Developer",
            "skills": ["Python", "FastAPI", "Django", "PostgreSQL", "AWS", "Docker"],
            "work_experience": [
                {
                    "title": "Senior Python Developer",
                    "company": "Acme Cloud Solutions",
                    "dates": "Jan 2021 - Present",
                    "bullets": ["Architected REST APIs with FastAPI and PostgreSQL", "Deployed microservices on AWS with Docker"],
                }
            ],
            "education": [{"degree": "B.S. Computer Science", "institution": "UT Dallas", "year": "2018"}],
        },
        company_name="Original",
        job_title="Python Developer",
        output_filename="Ankit_Jaiswal_Resume.pdf",
    )

    pipeline = PipelineService(db_session)
    pipeline.pdf_generator = ResumePDFGenerator(output_dir=str(tmp_path / "generated_resumes"))
    pipeline.tracker.csv_path = str(tmp_path / "submissions.csv")
    pipeline.tracker._ensure_csv_file()

    # 1. Upload candidate resume & 2. Detect candidate job title & 3. Generate LinkedIn search query
    upload_res = pipeline.process_resume_upload(test_resume_path, "Ankit_Jaiswal_Resume.pdf")
    assert upload_res["candidate_id"] is not None
    assert upload_res["candidate_name"] == "Ankit Jaiswal"
    assert "Python" in upload_res["primary_job_title"]
    assert upload_res["search_query"] == f'"{upload_res["primary_job_title"]}" C2C -W2 -Full-Time -Bench -Sales -Hotlist'
    cand_id = upload_res["candidate_id"]

    # 4. Find relevant C2C post & 5. Extract recruiter + job details
    mock_c2c_posts = [
        {
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:7129999999999999999/",
            "author_name": "Sarah Miller",
            "author_headline": "Senior Technical Recruiter at TechStaff Solutions",
            "posted_at": "2h",
            "raw_text": """
            🚨 Urgent C2C Hiring!
            Role: Senior Python Developer
            Client: FinTech Global
            Location: Remote
            Experience: 5+ years
            Key Skills: Python, FastAPI, AWS, Docker, PostgreSQL
            Rate: Open / Market C2C

            Please send updated resumes to: sarah.miller@techstaffsolutions.com
            """,
        },
        # A post that should be filtered out (W2 only)
        {
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:8888888888888888888/",
            "author_name": "Mike Davis",
            "author_headline": "HR Manager",
            "posted_at": "1h",
            "raw_text": "Direct hire Python Engineer on W2 only. Full-time benefits. Email: mike@w2jobs.com",
        },
    ]

    import asyncio
    search_res = asyncio.run(
        pipeline.search_and_filter_linkedin_posts(
            search_query=upload_res["search_query"],
            mock_raw_posts=mock_c2c_posts,
        )
    )

    assert search_res["total_discovered"] == 2
    assert search_res["jobs_passed"] == 1
    assert search_res["filtered_out_count"] == 1
    assert len(search_res["jobs"]) == 1

    job = search_res["jobs"][0]
    assert job.recruiter_email == "sarah.miller@techstaffsolutions.com"
    assert "Python Developer" in job.job_title

    # 6. Check duplicate -> 7. Analyze resume vs job description -> 8. Generate truthful PDF -> 9. Draft email -> 10. Attach -> 11. Validate -> 12. Send (Dry run) -> 13. Save submission record
    sub_res = pipeline.process_and_submit_job(candidate_id=cand_id, job_id=job.id)

    assert sub_res["success"] is True
    assert sub_res["status"] == "dry_run"
    assert sub_res["recruiter_email"] == "sarah.miller@techstaffsolutions.com"
    assert sub_res["match_score"] >= 70.0
    assert os.path.exists(sub_res["resume_pdf"])
    assert "Submission for Senior Python Developer | C2C Consultant" in sub_res["email_subject"]

    # 14. Attempt same job again -> 15. System prevents duplicate (SKIPPED_DUPLICATE)
    dup_sub_res = pipeline.process_and_submit_job(candidate_id=cand_id, job_id=job.id)
    assert dup_sub_res["status"] == "skipped_duplicate"
    assert dup_sub_res["success"] is False
