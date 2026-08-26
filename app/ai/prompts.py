import json
from typing import Dict, Any

RESUME_CUSTOMIZATION_SYSTEM_PROMPT = """You are an expert ATS Resume Customizer and Recruitment Specialist.

CRITICAL INTEGRITY RULES (MANDATORY):
1. You MUST NEVER invent or hallucinate any work experience, companies, job titles, certifications, degrees, skills, projects, years of experience, work authorization, or client experience.
2. ONLY information actually present in the original candidate resume may be used.
3. You may reorder, emphasize, and optimize wording/phrasing of EXISTING skills and achievements to highlight relevance to the target job description.
4. Calculate a realistic and transparent match_score (between 0.0 and 100.0) based strictly on matching qualifications between the resume and job requirements.
5. Return ONLY a valid JSON object matching the requested schema. Do NOT include markdown code blocks (```json), commentary, or extra text.
"""

RESUME_CUSTOMIZATION_USER_TEMPLATE = """TARGET JOB DESCRIPTION:
-----------------------
Job Title: {job_title}
Company: {company_name}
Required Skills / Requirements: {job_skills}
Job Description:
{job_description}

CANDIDATE ORIGINAL RESUME:
-------------------------
Name: {candidate_name}
Summary: {candidate_summary}
Primary Title: {candidate_title}
Work Authorization: {work_authorization}
Total Experience: {total_experience}
Location: {location}
Skills: {candidate_skills}
Work Experience:
{work_experience_json}
Education:
{education_json}

INSTRUCTIONS:
1. Analyze the job requirements against the candidate's existing background.
2. Select and prioritize the candidate's actual skills that match the job.
3. Refine the summary and bullet points from existing work history for ATS alignment without adding unstated claims.
4. Calculate a match_score (0-100).
5. Output JSON structure:
{{
  "match_score": 88.5,
  "match_reasons": ["Demonstrated 5+ years with Python & FastAPI", "Strong SQL & AWS background matching requirements"],
  "missing_skills": ["Kafka (if required by job but absent in candidate resume)"],
  "customized_summary": "Tailored summary strictly based on candidate's real background...",
  "prioritized_skills": ["Python", "FastAPI", "PostgreSQL", "AWS", ...],
  "customized_experience": [
    {{
      "title": "Senior Python Developer",
      "company": "Company Name",
      "dates": "Jan 2021 - Present",
      "location": "Dallas, TX",
      "bullets": [
        "ATS-enhanced truthful bullet 1...",
        "ATS-enhanced truthful bullet 2..."
      ]
    }}
  ],
  "education": [
    {{
      "degree": "Bachelor of Science in Computer Science",
      "institution": "University Name",
      "year": "2018"
    }}
  ]
}}
"""


def build_customization_prompt(
    candidate_dict: Dict[str, Any],
    job_dict: Dict[str, Any]
) -> str:
    """Builds formatted prompt for AI customization."""
    return RESUME_CUSTOMIZATION_USER_TEMPLATE.format(
        job_title=job_dict.get("job_title", "Software Developer"),
        company_name=job_dict.get("company_name", "Hiring Company"),
        job_skills=", ".join(job_dict.get("skills", [])) if isinstance(job_dict.get("skills"), list) else str(job_dict.get("skills", "")),
        job_description=job_dict.get("job_description", ""),
        candidate_name=candidate_dict.get("name", "Candidate"),
        candidate_summary=candidate_dict.get("summary", ""),
        candidate_title=candidate_dict.get("primary_job_title", "Developer"),
        work_authorization=candidate_dict.get("work_authorization", "Authorized to work in US"),
        total_experience=candidate_dict.get("total_experience", ""),
        location=candidate_dict.get("location", ""),
        candidate_skills=", ".join(candidate_dict.get("skills", [])) if isinstance(candidate_dict.get("skills"), list) else str(candidate_dict.get("skills", "")),
        work_experience_json=json.dumps(candidate_dict.get("work_experience", []), indent=2),
        education_json=json.dumps(candidate_dict.get("education", []), indent=2),
    )
