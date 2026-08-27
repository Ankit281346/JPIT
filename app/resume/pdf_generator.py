import os
import re
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    ListFlowable,
    ListItem,
    KeepTogether,
)
from app.config.settings import get_settings
from app.utils.logger import setup_logger

logger = setup_logger("resume.pdf_generator")


def sanitize_filename_part(text: str) -> str:
    """Removes special characters and spaces from text to produce safe filename parts."""
    if not text:
        return "Unknown"
    # Remove characters not alphanumeric
    cleaned = re.sub(r"[^\w\s-]", "", text).strip()
    # PascalCase or joined words
    words = cleaned.split()
    return "".join(w.capitalize() for w in words) if words else "Unknown"


class ResumePDFGenerator:
    def __init__(self, output_dir: Optional[str] = None):
        self.settings = get_settings()
        self.output_dir = output_dir or os.path.join(
            self.settings.BASE_DIR, self.settings.GENERATED_RESUMES_DIR
        )
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception:
            pass

    def generate_filename(self, candidate_name: str, company_name: str, job_title: str) -> str:
        """Generates sanitized filename: CandidateName_Company_JobTitle.pdf"""
        c_name = sanitize_filename_part(candidate_name)
        c_comp = sanitize_filename_part(company_name or "Company")
        c_title = sanitize_filename_part(job_title or "Role")
        return f"{c_name}_{c_comp}_{c_title}.pdf"

    def generate_pdf(
        self,
        customized_data: Dict[str, Any],
        company_name: Optional[str] = None,
        job_title: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """Generates an ATS-compliant PDF resume from customized data and returns the absolute filepath."""
        cand_name = customized_data.get("name", "Candidate")
        target_company = company_name or "TargetCompany"
        target_title = job_title or customized_data.get("primary_job_title", "Software Developer")

        if not output_filename:
            output_filename = self.generate_filename(cand_name, target_company, target_title)

        out_path = os.path.join(self.output_dir, output_filename)
        logger.info(f"Generating ATS PDF resume at: {out_path}")

        # Page setup: Standard Letter size with 0.5 inch margins (maximizing ATS readability)
        doc = SimpleDocTemplate(
            out_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()

        # Custom ATS Typography Styles
        name_style = ParagraphStyle(
            "ATS_Name",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=1,  # Center
            textColor=colors.HexColor("#1A202C"),
        )

        contact_style = ParagraphStyle(
            "ATS_Contact",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            alignment=1,  # Center
            textColor=colors.HexColor("#4A5568"),
        )

        section_heading_style = ParagraphStyle(
            "ATS_SectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=8,
            spaceAfter=3,
        )

        job_title_style = ParagraphStyle(
            "ATS_JobTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1E293B"),
        )

        company_style = ParagraphStyle(
            "ATS_Company",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#334155"),
        )

        body_style = ParagraphStyle(
            "ATS_Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1E293B"),
        )

        bullet_style = ParagraphStyle(
            "ATS_Bullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.8,
            textColor=colors.HexColor("#1E293B"),
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=2,
        )

        story = []

        # 1. CANDIDATE HEADER
        story.append(Paragraph(f"<b>{cand_name.upper()}</b>", name_style))
        story.append(Spacer(1, 3))

        contact_parts = []
        if customized_data.get("location"):
            contact_parts.append(customized_data["location"])
        if customized_data.get("phone"):
            contact_parts.append(customized_data["phone"])
        if customized_data.get("email"):
            contact_parts.append(customized_data["email"])
        if customized_data.get("linkedin_url"):
            contact_parts.append(customized_data["linkedin_url"])

        if contact_parts:
            story.append(Paragraph(" | ".join(contact_parts), contact_style))

        meta_parts = []
        if customized_data.get("work_authorization"):
            meta_parts.append(f"Work Auth: {customized_data['work_authorization']}")
        if customized_data.get("total_experience"):
            meta_parts.append(f"Experience: {customized_data['total_experience']}")

        if meta_parts:
            story.append(Paragraph(" | ".join(meta_parts), contact_style))

        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceBefore=2, spaceAfter=6))

        # 2. PROFESSIONAL SUMMARY
        summary_text = customized_data.get("customized_summary") or customized_data.get("summary")
        if summary_text:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceBefore=1, spaceAfter=4))
            story.append(Paragraph(summary_text, body_style))
            story.append(Spacer(1, 6))

        # 3. TECHNICAL SKILLS
        skills = customized_data.get("prioritized_skills") or customized_data.get("skills", [])
        if skills:
            story.append(Paragraph("TECHNICAL SKILLS", section_heading_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceBefore=1, spaceAfter=4))
            skills_str = ", ".join(skills)
            story.append(Paragraph(f"<b>Core Technologies:</b> {skills_str}", body_style))
            story.append(Spacer(1, 6))

        # 4. PROFESSIONAL EXPERIENCE
        work_exp = customized_data.get("customized_experience") or customized_data.get("work_experience", [])
        if work_exp:
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_heading_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceBefore=1, spaceAfter=4))

            for exp in work_exp:
                exp_elements = []
                title = exp.get("title", "Software Professional")
                company = exp.get("company", "")
                dates = exp.get("dates", "")
                location = exp.get("location", "")

                header_left = f"<b>{title}</b>"
                if company:
                    header_left += f" — <i>{company}</i>"
                if location:
                    header_left += f" ({location})"

                header_right = f"<i>{dates}</i>" if dates else ""
                header_full = f"{header_left} <font color='#64748B'>{header_right}</font>"

                exp_elements.append(Paragraph(header_full, job_title_style))
                exp_elements.append(Spacer(1, 2))

                bullets = exp.get("bullets", [])
                for b in bullets:
                    b_clean = b.lstrip("•-* ").strip()
                    if b_clean:
                        exp_elements.append(Paragraph(f"&bull; {b_clean}", bullet_style))

                exp_elements.append(Spacer(1, 4))
                story.append(KeepTogether(exp_elements))

            story.append(Spacer(1, 2))

        # 5. EDUCATION
        education = customized_data.get("education", [])
        if education:
            story.append(Paragraph("EDUCATION", section_heading_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceBefore=1, spaceAfter=4))
            for edu in education:
                degree = edu.get("degree", "Degree")
                institution = edu.get("institution", "")
                year = edu.get("year", "")

                edu_str = f"<b>{degree}</b>"
                if institution:
                    edu_str += f", {institution}"
                if year:
                    edu_str += f" ({year})"

                story.append(Paragraph(edu_str, body_style))
                story.append(Spacer(1, 2))

        # Build PDF document
        doc.build(story)
        logger.info(f"Successfully generated ATS-compliant PDF: {out_path} ({os.path.getsize(out_path)} bytes)")
        return out_path
