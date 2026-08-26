from typing import Dict, Any, Optional
from app.utils.logger import setup_logger

logger = setup_logger("gmail.drafts")


class EmailDraftBuilder:
    def __init__(self):
        pass

    def build_subject(self, job_title: str) -> str:
        """Generates outreach email subject line."""
        title = job_title.strip() if job_title else "Software Developer"
        return f"Submission for {title} | C2C Consultant"

    def build_body(
        self,
        candidate_data: Dict[str, Any],
        job_data: Dict[str, Any],
    ) -> str:
        """Constructs strictly formatted personalized outreach email body."""
        # 1. Recruiter Greeting
        recruiter_name = job_data.get("recruiter_name")
        if recruiter_name and recruiter_name not in ["Hiring Team", "Recruiter", ""]:
            # Use first name or full name if short
            first_name = recruiter_name.split()[0]
            greeting = f"Dear {first_name},"
        else:
            greeting = "Dear Hiring Team,"

        job_title = job_data.get("job_title", "Software Developer")
        cand_name = candidate_data.get("name", "Candidate")
        email = candidate_data.get("email", "")
        phone = candidate_data.get("phone", "")
        linkedin = candidate_data.get("linkedin_url", "")
        location = candidate_data.get("location", "")
        work_auth = candidate_data.get("work_authorization", "Authorized to work in US")
        avail = candidate_data.get("availability", "Immediate")
        total_exp = candidate_data.get("total_experience", "")
        expected_salary = candidate_data.get("expected_salary", "Open / Market Rate (C2C)")

        job_url = job_data.get("linkedin_post_url", "")
        raw_job_desc = job_data.get("job_description", "")

        from app.linkedin.scraper import PostScraper
        cleaner = PostScraper()
        job_desc = cleaner._clean_job_description(raw_job_desc)

        # Format body according to exact specification in Section 14
        body = f"""{greeting}


I hope this email finds you well.


I came across your recent LinkedIn hiring post regarding the {job_title} opportunity and would like to submit my application.


Please find my resume attached for your review.


Candidate Summary


Candidate Name: {cand_name}
Email: {email}
Phone: {phone}
LinkedIn Profile: {linkedin}
Current Location: {location}
Work Authorization: {work_auth}
Availability: {avail}
Total Experience: {total_exp}
Expected Salary: {expected_salary}


LinkedIn Job Post


Post URL:
{job_url}


Job Description:
{job_desc}


I believe my experience aligns well with your requirements and would appreciate the opportunity to discuss the role further.


Thank you for your time and consideration.


Best Regards,


{cand_name}"""

        return body
