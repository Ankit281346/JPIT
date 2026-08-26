import re
from typing import Dict, Any, List, Optional
from app.linkedin.filters import PostFilter, EMAIL_REGEX
from app.utils.logger import setup_logger

logger = setup_logger("linkedin.scraper")

COMMON_SKILLS = [
    "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "Spring", "Hibernate",
    "JavaScript", "TypeScript", "React", "React.js", "Angular", "Vue.js", "Node.js",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "CI/CD", "Kafka",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQL", ".NET", "C#",
    "Microservices", "REST API", "GraphQL", "Snowflake", "Databricks", "Airflow", "Spark",
]


class PostScraper:
    def __init__(self):
        self.filter = PostFilter()

    def parse_raw_post(
        self, raw_post: Dict[str, Any], default_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extracts and normalizes job and recruiter information from a post."""
        text = raw_post.get("raw_text", "")
        author_name = raw_post.get("author_name", "")
        author_headline = raw_post.get("author_headline", "")
        post_url = raw_post.get("post_url", "")
        posted_at = raw_post.get("posted_at", "1h")

        # 1. Recruiter Name
        recruiter_name = self._extract_recruiter_name(author_name, text)

        # 2. Recruiter Email
        recruiter_email = self.filter.extract_email(text) or ""

        # 3. Company Name
        company_name = self._extract_company(author_headline, text)

        # 4. Job Title
        job_title = self._extract_job_title(text, default_title)

        # 5. Skills
        skills = self._extract_skills(text)

        # 6. Experience Required
        exp_req = self._extract_experience_required(text)

        # 7. Location
        location = self._extract_location(text)

        normalized = {
            "recruiter_name": recruiter_name,
            "recruiter_email": recruiter_email,
            "company_name": company_name,
            "job_title": job_title,
            "job_description": self._clean_job_description(text),
            "skills": skills,
            "experience_required": exp_req,
            "location": location,
            "linkedin_post_url": post_url,
            "posted_at": posted_at,
            "raw_post_text": text.strip(),
        }

        return normalized

    def _clean_job_description(self, text: str) -> str:
        if not text:
            return ""
        lines = text.split('\n')
        
        ui_patterns_top = [
            r'^\s*Feed\s*post\s*$',
            r'^\s*[\w\s.-]*\s*(?:3rd\+|2nd|1st)\s*$', 
            r'^\s*Follow\s*$',
            r'^\s*Join\s*$',
            r'^\s*\d+[smhdw]\s*(?:•|.)?\s*(?:Edited)?\s*(?:•|.)?\s*$', 
            r'^\s*(?:Technical\s+)?Recruiter.*$',
        ]
        
        start_idx = 0
        last_match_idx = -1
        for i in range(min(20, len(lines))):
            line = lines[i].strip()
            if not line:
                continue
            matched = False
            for p in ui_patterns_top:
                if re.match(p, line, re.IGNORECASE):
                    matched = True
                    break
            if matched:
                last_match_idx = i
                
        if last_match_idx != -1:
            start_idx = last_match_idx + 1

        ui_patterns_bottom = [
            r'^\s*Like\s*$',
            r'^\s*Comment\s*$',
            r'^\s*Share\s*$',
            r'^\s*Send\s*$',
            r'^\s*Message\s*$',
            r'^\s*\d+\s+comments?\s*$',
            r'^\s*\d+\s+reposts?\s*$',
            r'^\s*\d+\s+likes?\s*$',
            r'^\s*Repost\s*$',
            r'^\s*Reactions\s*$',
            r'^\s*Follow\s*$',
            r'^\s*reply\s*$',
            r'^\s*(?:…|\.\.\.)\s*more\s*$',
        ]
        
        end_idx = len(lines)
        first_match_idx = -1
        for i in range(len(lines)-1, max(-1, len(lines)-20), -1):
            line = lines[i].strip()
            if not line:
                continue
            matched = False
            for p in ui_patterns_bottom:
                if re.match(p, line, re.IGNORECASE):
                    matched = True
                    break
            if matched:
                first_match_idx = i
                
        if first_match_idx != -1:
            end_idx = first_match_idx
            
        return '\n'.join(lines[start_idx:end_idx]).strip()

    def _extract_recruiter_name(self, author_name: str, text: str) -> str:
        if author_name and author_name != "Recruiter" and len(author_name.split()) <= 4:
            # Clean author name (remove emojis, credentials like ', CIR', etc.)
            clean = re.sub(r"[^\w\s.-]", "", author_name).strip()
            if clean:
                return clean

        # Check post signature: "Thanks & Regards, John Smith" or "Best, Jane Doe"
        sig_match = re.search(
            r"(?:Thanks\s*(?:&|and)\s*Regards|Best\s*Regards|Regards|Thanks)\s*,?\s*\n+([A-Za-z\s.'-]+)",
            text,
            re.IGNORECASE,
        )
        if sig_match:
            name = sig_match.group(1).strip()
            if len(name.split()) in [2, 3] and len(name) < 30:
                return name

        return "Hiring Team"

    def _extract_company(self, headline: str, text: str) -> str:
        # Check author headline: "Technical Recruiter at Apex Systems"
        if headline:
            match = re.search(r"\bat\s+([A-Za-z0-9\s&.,-]+?)(?:\s*\||\s*•|\s*-|\s*,|\Z)", headline, re.IGNORECASE)
            if match:
                comp = match.group(1).strip()
                if len(comp) > 2 and len(comp) < 40:
                    return comp

        # Check post text: "Client: Acme Inc" or "Company: Acme Inc"
        comp_match = re.search(
            r"(?:Client|Company|Organization|End Client)\s*:\s*([A-Za-z0-9\s&.,-]+?)(?:\n|\r|,|;|\Z)",
            text,
            re.IGNORECASE,
        )
        if comp_match:
            return comp_match.group(1).strip()

        return "Client"

    def _extract_job_title(self, text: str, default_title: Optional[str] = None) -> str:
        # Look for explicit labels: "Role: ...", "Position: ...", "Title: ..."
        title_match = re.search(
            r"(?:Role|Position|Title|Job\s*Title|Looking\s*for)\s*:\s*([^\n\r,;|]+)",
            text,
            re.IGNORECASE,
        )
        if title_match:
            cand = title_match.group(1).strip()
            if len(cand) > 3 and len(cand) < 60:
                return cand

        # Look for common developer titles in text
        patterns = [
            r"\b(Senior\s+Python\s+Developer|Python\s+Developer|Python\s+Backend\s+Engineer)\b",
            r"\b(Senior\s+Java\s+Developer|Java\s+Developer|Java\s+Full\s*Stack\s+Developer)\b",
            r"\b(React\s+Developer|Frontend\s+Developer|Senior\s+React\s+Developer)\b",
            r"\b(Full\s*Stack\s+Developer|DevOps\s+Engineer|Data\s+Engineer|Cloud\s+Architect)\b",
            r"\b(\.NET\s+Developer|C#\s+Developer|Node\.js\s+Developer)\b",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(0).strip()

        return default_title or "Software Developer"

    def _extract_skills(self, text: str) -> List[str]:
        found = []
        for s in COMMON_SKILLS:
            if re.search(rf"\b{re.escape(s)}\b", text, re.IGNORECASE):
                found.append(s)
        return found

    def _extract_experience_required(self, text: str) -> str:
        match = re.search(
            r"(\d+\+?\s*(?:-\s*\d+)?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp))",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return "5+ years"

    def _extract_location(self, text: str) -> str:
        if re.search(r"\b(remote|work\s+from\s+home|wfh)\b", text, re.IGNORECASE):
            return "Remote"
        loc_match = re.search(r"(?:Location|Job\s*Location)\s*:\s*([^\n\r;|]+)", text, re.IGNORECASE)
        if loc_match:
            return loc_match.group(1).strip()
        city_match = re.search(r"\b([A-Z][a-zA-Z\s]+),\s*([A-Z]{2})\b", text)
        if city_match:
            return f"{city_match.group(1).strip()}, {city_match.group(2)}"
        return "Remote / Hybrid"
