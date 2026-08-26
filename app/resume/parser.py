import os
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.utils.logger import setup_logger

logger = setup_logger("resume.parser")

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class WorkExperience(BaseModel):
    title: str = ""
    company: str = ""
    location: Optional[str] = None
    dates: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


class Education(BaseModel):
    degree: str = ""
    institution: str = ""
    location: Optional[str] = None
    year: Optional[str] = None


class ParsedResume(BaseModel):
    name: str = "Candidate"
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    work_authorization: Optional[str] = None
    availability: Optional[str] = None
    total_experience: Optional[str] = None
    expected_salary: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    raw_text: str = ""
    primary_job_title: Optional[str] = None


class ResumeParser:
    def __init__(self):
        pass

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract plain text from PDF using pdfplumber with PyMuPDF fallback."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Resume PDF file not found at: {pdf_path}")

        text = ""
        # 1. Primary extractor: pdfplumber
        if pdfplumber is not None:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            pages_text.append(page_text)
                    text = "\n".join(pages_text).strip()
                if text:
                    logger.debug("Successfully extracted text using pdfplumber.")
                    return text
            except Exception as e:
                logger.warning(f"pdfplumber extraction encountered error: {e}. Falling back to PyMuPDF.")

        # 2. Fallback extractor: PyMuPDF (fitz)
        if fitz is not None:
            try:
                doc = fitz.open(pdf_path)
                pages_text = []
                for page in doc:
                    pages_text.append(page.get_text())
                text = "\n".join(pages_text).strip()
                if text:
                    logger.debug("Successfully extracted text using PyMuPDF.")
                    return text
            except Exception as e:
                logger.error(f"PyMuPDF extraction failed: {e}")

        if not text:
            raise ValueError(f"Could not extract readable text from PDF: {pdf_path}")
        return text

    def parse(self, pdf_path_or_text: str, is_raw_text: bool = False) -> ParsedResume:
        """Parse resume from PDF path or raw text and return structured ParsedResume."""
        if is_raw_text:
            raw_text = pdf_path_or_text
        else:
            raw_text = self.extract_text_from_pdf(pdf_path_or_text)

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        name = self._extract_name(lines, raw_text)
        email = self._extract_email(raw_text)
        phone = self._extract_phone(raw_text)
        linkedin_url = self._extract_linkedin(raw_text)
        location = self._extract_location(raw_text, lines)
        work_auth = self._extract_work_authorization(raw_text)
        availability = self._extract_availability(raw_text)
        total_exp = self._extract_total_experience(raw_text)
        expected_salary = self._extract_expected_salary(raw_text)
        skills = self._extract_skills(raw_text)
        education = self._extract_education(raw_text)
        work_experience = self._extract_work_experience(raw_text)
        summary = self._extract_summary(raw_text)

        return ParsedResume(
            name=name,
            email=email,
            phone=phone,
            linkedin_url=linkedin_url,
            location=location,
            work_authorization=work_auth,
            availability=availability,
            total_experience=total_exp,
            expected_salary=expected_salary,
            summary=summary,
            skills=skills,
            education=education,
            work_experience=work_experience,
            raw_text=raw_text,
        )

    def _extract_email(self, text: str) -> Optional[str]:
        pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        match = re.search(pattern, text)
        return match.group(0).strip() if match else None

    def _extract_phone(self, text: str) -> Optional[str]:
        pattern = r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})"
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip()
        # Fallback simpler phone regex
        match2 = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
        return match2.group(0).strip() if match2 else None

    def _extract_linkedin(self, text: str) -> Optional[str]:
        pattern = r"(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(0).strip()
            if not url.startswith("http"):
                url = "https://" + url
            return url
        return None

    def _extract_name(self, lines: List[str], text: str) -> str:
        # Check explicit label first: Name: John Doe
        label_match = re.search(r"^(?:Candidate\s+)?Name\s*:\s*([A-Za-z\s.'-]+)$", text, re.MULTILINE | re.IGNORECASE)
        if label_match:
            return label_match.group(1).strip()

        # Usually candidate name is on the first or second non-empty line
        for line in lines[:5]:
            clean = line.strip()
            # If line is not an email, not a phone, not a URL, not a heading
            if "@" in clean or "http" in clean or "linkedin" in clean:
                continue
            if re.search(r"\d{3}", clean):
                continue
            if len(clean.split()) in [2, 3, 4] and len(clean) < 40:
                # Check that words look like names
                words = clean.split()
                if all(w.replace(".", "").replace("-", "").isalpha() for w in words):
                    return clean.title() if clean.isupper() else clean
        return "Candidate"

    def _extract_location(self, text: str, lines: List[str]) -> Optional[str]:
        # Check explicit label
        match = re.search(r"(?:Current\s+)?Location\s*:\s*([^\n\r,]+(?:,\s*[A-Z]{2}|[^\n\r]+)?)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Check City, ST patterns (e.g. Austin, TX or Chicago, IL)
        loc_pattern = r"\b([A-Z][a-zA-Z\s]+),\s*([A-Z]{2})\b"
        loc_match = re.search(loc_pattern, text)
        if loc_match:
            return f"{loc_match.group(1).strip()}, {loc_match.group(2)}"
        return None

    def _extract_work_authorization(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:Work\s+Authorization|Visa\s+Status|Work\s+Status|Legal\s+Status)\s*:\s*([^\n\r]+)",
            r"\b(US\s+Citizen|Green\s+Card|GC-EAD|H1B|OPT|CPT|TN\s+Visa|Authorized\s+to\s+work\s+in\s+(?:the\s+)?US|Permanent\s+Resident)\b",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Authorized to work in US (C2C)"

    def _extract_availability(self, text: str) -> Optional[str]:
        patterns = [
            r"Availability\s*:\s*([^\n\r]+)",
            r"Notice\s+Period\s*:\s*([^\n\r]+)",
            r"\b(Immediate(?:ly)?|2\s+weeks(?:\s+notice)?|1\s+week|Available\s+Immediately)\b",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Immediate"

    def _extract_total_experience(self, text: str) -> Optional[str]:
        patterns = [
            r"Total\s+Experience\s*:\s*([^\n\r]+)",
            r"(\d+(?:\.\d+)?\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:total\s+)?experience)",
            r"(\d+\+?\s*(?:years?|yrs?)\s+in\s+[a-zA-Z\s]+)",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_expected_salary(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:Expected\s+Salary|Expected\s+Rate|Hourly\s+Rate|Target\s+Rate|Rate)\s*:\s*([^\n\r]+)",
            r"(\$\s*\d+(?:,\d{3})*(?:\s*-\s*\$\s*\d+)?\s*(?:/\s*(?:hr|hour|yr|year|annum))?)",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Open / Market Rate (C2C)"

    def _extract_summary(self, text: str) -> Optional[str]:
        match = re.search(
            r"(?:PROFESSIONAL\s+SUMMARY|SUMMARY|PROFILE|ABOUT\s+ME)\s*[:\n\r]+(.*?)(?=\n\s*(?:TECHNICAL\s+SKILLS|SKILLS|EXPERIENCE|WORK\s+EXPERIENCE|EDUCATION|PROJECTS)\b|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return " ".join(match.group(1).strip().split())
        return None

    def _extract_skills(self, text: str) -> List[str]:
        skills_set = set()
        # Look for skills section
        match = re.search(
            r"(?:TECHNICAL\s+SKILLS|SKILLS|CORE\s+COMPETENCIES|TECHNOLOGIES)\s*[:\n\r]+(.*?)(?=\n\s*(?:EXPERIENCE|WORK\s+EXPERIENCE|EMPLOYMENT|EDUCATION|CERTIFICATIONS|PROJECTS)\b|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        skills_text = match.group(1) if match else text

        # Split on commas, bullets, colons, newlines, pipes
        items = re.split(r"[,;•|/·\n\r\t]+", skills_text)
        for item in items:
            cleaned = item.strip()
            # Remove categories like "Languages:", "Frameworks:"
            cleaned = re.sub(r"^[A-Za-z\s]+:\s*", "", cleaned)
            cleaned = cleaned.strip(" -:*•")
            if cleaned and 1 <= len(cleaned.split()) <= 4 and len(cleaned) <= 35:
                # Exclude common non-skill words
                if not re.match(r"^(and|the|with|for|such|as|years|experience|responsible|using)$", cleaned, re.IGNORECASE):
                    skills_set.add(cleaned)

        # Well-known tech keywords search across text
        common_tech = [
            "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "Spring", "Hibernate",
            "JavaScript", "TypeScript", "React", "React.js", "Angular", "Vue.js", "Node.js", "Express",
            "C#", ".NET", ".NET Core", "ASP.NET", "C++", "Golang", "Rust", "PHP", "Ruby on Rails",
            "SQL", "PostgreSQL", "MySQL", "Oracle", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
            "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "CI/CD", "Jenkins", "Git",
            "GraphQL", "REST API", "Microservices", "Kafka", "RabbitMQ", "Spark", "Hadoop", "Pandas",
            "NumPy", "TensorFlow", "PyTorch", "Airflow", "Snowflake", "Databricks", "Tableau", "Power BI"
        ]
        for tech in common_tech:
            if re.search(rf"\b{re.escape(tech)}\b", text, re.IGNORECASE):
                skills_set.add(tech)

        return sorted(list(skills_set))

    def _extract_education(self, text: str) -> List[Education]:
        education_list = []
        match = re.search(
            r"(?:EDUCATION|ACADEMIC\s+BACKGROUND|DEGREES)\s*[:\n\r]+(.*?)(?=\n\s*(?:SKILLS|EXPERIENCE|CERTIFICATIONS|PROJECTS)\b|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        edu_text = match.group(1) if match else ""
        if edu_text:
            lines = [l.strip() for l in edu_text.splitlines() if l.strip()]
            current_degree = ""
            current_inst = ""
            for line in lines:
                if re.search(r"\b(Bachelor|Master|B\.S\.|M\.S\.|B\.Tech|M\.Tech|Ph\.D\.|Associate|Degree)\b", line, re.IGNORECASE):
                    if current_degree:
                        education_list.append(Education(degree=current_degree, institution=current_inst))
                    current_degree = line
                    current_inst = ""
                elif re.search(r"\b(University|College|Institute|School|Academy)\b", line, re.IGNORECASE):
                    current_inst = line
                elif current_degree and not current_inst:
                    current_inst = line
            if current_degree:
                education_list.append(Education(degree=current_degree, institution=current_inst))

        if not education_list:
            # Fallback scan in whole text
            edu_pattern = r"(Bachelor(?:'s)?|Master(?:'s)?|B\.S\.|M\.S\.|B\.Tech|M\.Tech)\s+(?:of|in)?\s+([A-Za-z\s]+)(?:from|at|,)?\s+([A-Za-z\s]+(?:University|College|Institute))?"
            for m in re.finditer(edu_pattern, text, re.IGNORECASE):
                degree = f"{m.group(1)} in {m.group(2).strip()}"
                inst = m.group(3).strip() if m.group(3) else "Accredited University"
                education_list.append(Education(degree=degree, institution=inst))

        return education_list

    def _extract_work_experience(self, text: str) -> List[WorkExperience]:
        experiences = []
        match = re.search(
            r"(?:PROFESSIONAL\s+EXPERIENCE|WORK\s+EXPERIENCE|EXPERIENCE|EMPLOYMENT\s+HISTORY)\s*[:\n\r]+(.*?)(?=\n\s*(?:EDUCATION|ACADEMIC|SKILLS|CERTIFICATIONS|PROJECTS)\b|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        exp_text = match.group(1) if match else text
        lines = [l.strip() for l in exp_text.splitlines() if l.strip()]

        current_exp: Optional[WorkExperience] = None

        for line in lines:
            # Detect title/company header line (e.g. Senior Python Developer | Acme Corp | 2020 - Present)
            # or (Python Developer at Google, Jan 2021 - Present)
            date_match = re.search(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December|\d{4})\s*[\d-]*\s*(?:-|–|to)\s*(?:Present|Current|Now|\d{4}))\b", line, re.IGNORECASE)
            
            if date_match or (line.startswith("Role:") or line.startswith("Title:") or " - " in line and ("Developer" in line or "Engineer" in line or "Architect" in line or "Lead" in line or "Manager" in line or "Consultant" in line)):
                if current_exp and (current_exp.title or current_exp.company):
                    experiences.append(current_exp)
                
                dates = date_match.group(0) if date_match else None
                clean_line = line
                if dates:
                    clean_line = line.replace(dates, "").strip(" |,-")
                
                parts = [p.strip() for p in re.split(r"[|–—\-,]", clean_line) if p.strip()]
                title = parts[0] if len(parts) > 0 else "Software Professional"
                company = parts[1] if len(parts) > 1 else ""
                
                current_exp = WorkExperience(
                    title=title,
                    company=company,
                    dates=dates,
                    bullets=[]
                )
            elif line.startswith("•") or line.startswith("-") or line.startswith("*") or (current_exp and len(line) > 20):
                bullet = line.lstrip("•-* ").strip()
                if current_exp:
                    current_exp.bullets.append(bullet)
                else:
                    current_exp = WorkExperience(
                        title="Software Professional",
                        company="",
                        bullets=[bullet]
                    )

        if current_exp and (current_exp.title or current_exp.bullets):
            experiences.append(current_exp)

        return experiences
