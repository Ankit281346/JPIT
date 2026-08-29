import re
from typing import Dict, Any, Optional, List
from app.utils.logger import setup_logger

logger = setup_logger("gmail.drafts")


class EmailDraftBuilder:
    def __init__(self):
        pass

    def build_subject(self, job_title: str) -> str:
        """Generates outreach email subject line."""
        title = job_title.strip() if job_title else "AI Engineer"
        return f"Submission : {title} - Open for relocation"

    def extract_matched_skills_text(
        self, candidate_skills: List[str], job_text: str, default_skills: Optional[List[str]] = None
    ) -> str:
        """Extracts genuine matching skills between candidate and job description."""
        cand_skills = candidate_skills or default_skills or ["Python", "AWS", "Databricks"]
        job_lower = (job_text or "").lower()

        matched = []
        for s in cand_skills:
            if s and re.search(rf"\b{re.escape(s.lower())}\b", job_lower):
                matched.append(s)

        if not matched:
            matched = cand_skills[:3] if cand_skills else ["Python", "AWS", "Databricks"]

        if len(matched) == 1:
            return matched[0]
        elif len(matched) == 2:
            return f"{matched[0]} and {matched[1]}"
        else:
            return f"{', '.join(matched[:3][:-1])}, and {matched[:3][-1]}"

    def build_body(
        self,
        candidate_data: Dict[str, Any],
        job_data: Dict[str, Any],
    ) -> str:
        """Constructs strictly formatted personalized outreach email body adhering to the exact template."""
        # 1. Recruiter Greeting
        recruiter_name = (job_data.get("recruiter_name") or "").strip()
        if not recruiter_name or recruiter_name.lower() in [
            "hiring team", "recruiter", "hiring manager", "undefined", "null", "none", "client", ""
        ]:
            greeting = "Dear Hiring Team,"
        else:
            greeting = f"Dear {recruiter_name},"

        job_title = job_data.get("job_title") or "AI Engineer"
        cand_name = candidate_data.get("name") or "Arbaz Baig"
        email = candidate_data.get("email") or "Baigarabz27@gmail.com"
        phone = candidate_data.get("phone") or "3122628530"
        linkedin = candidate_data.get("linkedin_url") or "https://www.linkedin.com/in/arbazbaig"
        location = candidate_data.get("location") or "Chicago, IL"
        relocation = candidate_data.get("relocation") or "Open for relocation"
        work_auth = candidate_data.get("work_authorization") or "Initial OPT"
        avail = candidate_data.get("availability") or "Immediate"
        total_exp = candidate_data.get("total_experience") or "4+ Years"
        rate = candidate_data.get("expected_salary") or "Negotiable"

        # Matched Skills
        cand_skills = candidate_data.get("skills") or ["Python", "AWS", "Databricks", "SQL", "FastAPI"]
        job_desc_raw = job_data.get("job_description") or job_data.get("raw_post_text") or ""
        matched_skills_str = self.extract_matched_skills_text(cand_skills, f"{job_title} {job_desc_raw}")
        if not matched_skills_str:
            matched_skills_str = "Python, AWS, and Databricks"

        # Snippet and Source URL
        from app.linkedin.scraper import PostScraper
        cleaner = PostScraper()
        job_desc_snippet = cleaner._clean_job_description(job_desc_raw)
        source_url = job_data.get("linkedin_post_url") or job_data.get("source_url") or ""

        # Exact requested email body
        body = f"""{greeting}

I came across your posting for a {job_title} position. My hands-on experience with {matched_skills_str} maps directly to what you are looking for, and I would welcome the opportunity to be considered.

Please find my submission details below for your review:

--- SUBMISSION DETAILS ---
• Candidate Name: {cand_name}
• Applied Role: {job_title}
• Total Experience: {total_exp}
• Phone / Contact: {phone}
• Email Address: {email}
• Current Location: {location}
• Relocation: {relocation}
• Work Authorization: {work_auth}
• Availability: {avail}
• Rate / Compensation: {rate}
• LinkedIn Profile: {linkedin}

I have attached my updated resume for your review. Are you available for a brief call sometime this week to discuss this position? Thank you for your time and consideration; I look forward to hearing from you.

Best regards,
{cand_name}
Phone: {phone} | Email: {email}
LinkedIn: {linkedin}

-----------------------------------------
Referenced Job Description / Snippet:
{job_desc_snippet}

Role Reference:
- LinkedIn Post URL: {source_url}"""

        return body
