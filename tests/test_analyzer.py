import pytest
from app.resume.parser import ResumeParser, ParsedResume
from app.resume.analyzer import ResumeAnalyzer


def test_resume_analyzer_detects_primary_job_title(sample_resume_text):
    parser = ResumeParser()
    parsed: ParsedResume = parser.parse(sample_resume_text, is_raw_text=True)

    analyzer = ResumeAnalyzer()
    title = analyzer.determine_primary_job_title(parsed)

    assert "Python" in title
    assert "Developer" in title or "Engineer" in title


def test_search_query_generation():
    analyzer = ResumeAnalyzer()
    query = analyzer.generate_search_query("Python Developer")
    assert query == '"Python Developer" C2C -W2 -Full-Time -Bench -Sales -Hotlist'

    query_java = analyzer.generate_search_query("Java Developer")
    assert query_java == '"Java Developer" C2C -W2 -Full-Time -Bench -Sales -Hotlist'

    query_react = analyzer.generate_search_query("React Developer")
    assert query_react == '"React Developer" C2C -W2 -Full-Time -Bench -Sales -Hotlist'
