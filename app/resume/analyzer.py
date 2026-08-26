import re
from collections import Counter
from typing import List, Optional
from app.resume.parser import ParsedResume
from app.utils.logger import setup_logger

logger = setup_logger("resume.analyzer")

# Mapping of tech stack keywords to representative job titles
TITLE_TECH_PATTERNS = [
    (r"\b(python|django|fastapi|flask|pandas|numpy)\b", "Python Developer"),
    (r"\b(java|spring\s*boot|spring|hibernate|jvm)\b", "Java Developer"),
    (r"\b(react|react\.js|redux|next\.js|javascript|frontend)\b", "React Developer"),
    (r"\b(angular|angularjs|typescript)\b", "Angular Developer"),
    (r"\b(node|node\.js|express|nest\.js)\b", "Node.js Developer"),
    (r"\b(\.net|\.net\s*core|c#|asp\.net)\b", ".NET Developer"),
    (r"\b(aws|devops|kubernetes|docker|terraform|ci/cd|ansible)\b", "DevOps Engineer"),
    (r"\b(data\s+engineer|spark|hadoop|pyspark|snowflake|airflow|databricks)\b", "Data Engineer"),
    (r"\b(data\s+scientist|machine\s+learning|deep\s+learning|tensorflow|pytorch)\b", "Data Scientist"),
    (r"\b(salesforce|apex|visualforce|lightning)\b", "Salesforce Developer"),
    (r"\b(golang|go\s+developer)\b", "Golang Developer"),
    (r"\b(qa|automation\s+test|selenium|cypress|playwright\s+test)\b", "QA Automation Engineer"),
    (r"\b(cloud\s+architect|solutions\s+architect)\b", "Cloud Architect"),
    (r"\b(ios|swift|swiftui)\b", "iOS Developer"),
    (r"\b(android|kotlin)\b", "Android Developer"),
    (r"\b(full\s*stack|fullstack)\b", "Full Stack Developer"),
]

KNOWN_TITLES = [
    "Python Developer", "Senior Python Developer", "Lead Python Developer",
    "Java Developer", "Senior Java Developer", "Java Full Stack Developer",
    "React Developer", "Front End Developer", "Frontend Developer",
    "Full Stack Developer", "Senior Full Stack Developer",
    "DevOps Engineer", "Cloud DevOps Engineer", "Site Reliability Engineer",
    "Data Engineer", "Senior Data Engineer", "Big Data Engineer",
    "Data Scientist", "Machine Learning Engineer", "AI Engineer",
    ".NET Developer", "C# Developer", ".NET Core Developer",
    "Node.js Developer", "Backend Developer", "Software Engineer",
    "Senior Software Engineer", "Solutions Architect", "Cloud Architect",
    "QA Automation Engineer", "SDET", "Salesforce Developer"
]


class ResumeAnalyzer:
    def __init__(self):
        pass

    def determine_primary_job_title(self, resume: ParsedResume) -> str:
        """Intelligently detects primary job title from resume text, experiences, and skills."""
        raw = resume.raw_text

        # 1. Check explicit title or headline in the resume (top lines or summary)
        headline_match = re.search(
            r"^(?:Senior\s+|Lead\s+|Principal\s+)?(Python|Java|React|Node\.js|Full\s*Stack|DevOps|Data|Cloud|\.NET|Software)\s+(Developer|Engineer|Architect|Consultant)\b",
            raw,
            re.MULTILINE | re.IGNORECASE,
        )
        if headline_match:
            candidate_title = headline_match.group(0).strip()
            # Clean up casing
            for kt in KNOWN_TITLES:
                if candidate_title.lower() == kt.lower():
                    logger.info(f"Detected primary job title from headline: {kt}")
                    return kt
            return candidate_title.title()

        # 2. Check title from most recent work experience
        if resume.work_experience:
            for exp in resume.work_experience:
                if exp.title and exp.title != "Software Professional":
                    clean_title = re.sub(r"^(Senior|Lead|Junior|Staff|Principal)\s+", "", exp.title, flags=re.IGNORECASE).strip()
                    for kt in KNOWN_TITLES:
                        if clean_title.lower() in kt.lower() or kt.lower() in exp.title.lower():
                            logger.info(f"Detected primary job title from work history: {kt}")
                            return kt

        # 3. Analyze skill frequencies and tech patterns
        text_lower = raw.lower()
        score_counter = Counter()

        for pattern, title in TITLE_TECH_PATTERNS:
            matches = re.findall(pattern, text_lower)
            if matches:
                score_counter[title] += len(matches)

        if score_counter:
            best_title, count = score_counter.most_common(1)[0]
            logger.info(f"Determined primary job title from skill density: {best_title} (score: {count})")
            return best_title

        # Default fallback if ambiguous
        logger.info("Defaulting primary job title to Software Engineer")
        return "Software Engineer"

    def generate_search_query(self, job_title: str) -> str:
        """Generates dynamic LinkedIn search query based on primary job title."""
        clean_title = job_title.strip().strip('"')
        query = f'"{clean_title}" C2C -W2 -Full-Time -Bench -Sales -Hotlist'
        logger.info(f"Generated LinkedIn search query: {query}")
        return query
