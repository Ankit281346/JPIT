from typing import Dict, Any, Optional
from app.ai.client import AIClient
from app.resume.parser import ParsedResume
from app.utils.logger import setup_logger

logger = setup_logger("resume.customizer")


class ResumeCustomizer:
    def __init__(self, ai_client: Optional[AIClient] = None):
        self.ai_client = ai_client or AIClient()

    def customize(self, resume: ParsedResume, job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Customizes the candidate's resume against the specific job description."""
        logger.info(f"Customizing resume for candidate '{resume.name}' for job '{job_dict.get('job_title')}' at '{job_dict.get('company_name', 'Client')}'")

        candidate_dict = {
            "name": resume.name,
            "email": resume.email,
            "phone": resume.phone,
            "linkedin_url": resume.linkedin_url,
            "location": resume.location,
            "work_authorization": resume.work_authorization,
            "availability": resume.availability,
            "total_experience": resume.total_experience,
            "expected_salary": resume.expected_salary,
            "summary": resume.summary,
            "primary_job_title": resume.primary_job_title or "Software Developer",
            "skills": resume.skills,
            "education": [e.model_dump() if hasattr(e, "model_dump") else (e.dict() if hasattr(e, "dict") else e) for e in resume.education],
            "work_experience": [w.model_dump() if hasattr(w, "model_dump") else (w.dict() if hasattr(w, "dict") else w) for w in resume.work_experience],
        }

        customized_payload = self.ai_client.customize_resume(candidate_dict, job_dict)

        # Merge candidate contact information for complete resume generation
        customized_payload["name"] = resume.name
        customized_payload["email"] = resume.email
        customized_payload["phone"] = resume.phone
        customized_payload["linkedin_url"] = resume.linkedin_url
        customized_payload["location"] = resume.location
        customized_payload["work_authorization"] = resume.work_authorization
        customized_payload["total_experience"] = resume.total_experience
        customized_payload["primary_job_title"] = resume.primary_job_title

        logger.info(f"Resume customization complete. Match score: {customized_payload.get('match_score')}%")
        return customized_payload
