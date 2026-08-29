import os
import re
import random
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, Tuple, Optional, List
from app.config.settings import get_settings
from app.gmail.auth import GmailAuth
from app.gmail.drafts import EmailDraftBuilder
from app.utils.logger import setup_logger

logger = setup_logger("gmail.sender")

EMAIL_FORMAT_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class EmailSender:
    def __init__(self, gmail_auth: Optional[GmailAuth] = None, settings=None):
        self.settings = settings or get_settings()
        self.auth = gmail_auth or GmailAuth()
        self.draft_builder = EmailDraftBuilder()

    def validate_submission_prerequisites(
        self,
        recruiter_email: str,
        pdf_path: str,
        candidate_name: str,
        job_title: str,
    ) -> Tuple[bool, Optional[str]]:
        """Validates all email delivery prerequisites."""
        # 1. Recruiter email existence and format
        if not recruiter_email or not recruiter_email.strip():
            return False, "Recruiter email is missing or empty"

        cleaned_email = recruiter_email.strip().rstrip(".,;:!?)>\"'")
        if not EMAIL_FORMAT_REGEX.match(cleaned_email):
            return False, f"Invalid recruiter email format: {cleaned_email}"

        # 2. Resume PDF existence and readability
        if not pdf_path or not os.path.exists(pdf_path):
            return False, f"Resume PDF file does not exist at: {pdf_path}"

        try:
            file_size = os.path.getsize(pdf_path)
            if file_size < 100:
                return False, f"Resume PDF file is empty or corrupted ({file_size} bytes)"
            with open(pdf_path, "rb") as f:
                header = f.read(5)
                if not header.startswith(b"%PDF-"):
                    return False, f"Attachment file is not a valid PDF: {pdf_path}"
        except Exception as e:
            return False, f"Failed to read resume PDF: {e}"

        # 3. Basic metadata
        if not candidate_name or not candidate_name.strip():
            return False, "Candidate name is missing"
        if not job_title or not job_title.strip():
            return False, "Job title is missing"

        return True, None

    def build_mime_message(
        self,
        to_email: str,
        subject: str,
        body: str,
        pdf_path: str,
        sender_email: str = "me",
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
        attachment_filename: Optional[str] = None,
    ) -> MIMEMultipart:
        """Constructs a standard MIME multipart email message with PDF attachment, CC, and BCC."""
        msg = MIMEMultipart()
        msg["To"] = to_email
        msg["From"] = sender_email
        msg["Subject"] = subject

        if cc_emails:
            clean_cc = [e.strip() for e in cc_emails if e and e.strip()]
            if clean_cc:
                msg["Cc"] = ", ".join(clean_cc)

        if bcc_emails:
            clean_bcc = [e.strip() for e in bcc_emails if e and e.strip()]
            if clean_bcc:
                msg["Bcc"] = ", ".join(clean_bcc)

        # Attach text body
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach PDF with randomized anti-spam filename
        filename = attachment_filename or os.path.basename(pdf_path)
        with open(pdf_path, "rb") as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
            pdf_attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename,
            )
            msg.attach(pdf_attachment)

        return msg

    def send_outreach_email(
        self,
        candidate_data: Dict[str, Any],
        job_data: Dict[str, Any],
        pdf_path: str,
    ) -> Dict[str, Any]:
        """Validates, constructs, and sends (or dry-run logs) outreach email with required CC/BCC."""
        recruiter_email = job_data.get("recruiter_email", "").strip()
        job_title = job_data.get("job_title", "Software Developer")
        cand_name = candidate_data.get("name", "Candidate")

        logger.info(f"Preparing outreach email to '{recruiter_email}' for '{job_title}'")

        # 1. Validate prerequisites
        is_valid, error_msg = self.validate_submission_prerequisites(
            recruiter_email=recruiter_email,
            pdf_path=pdf_path,
            candidate_name=cand_name,
            job_title=job_title,
        )

        if not is_valid:
            logger.error(f"Email validation failed: {error_msg}")
            return {
                "success": False,
                "status": "failed",
                "error": error_msg,
                "subject": None,
                "body": None,
                "recruiter_email": recruiter_email,
            }

        # 2. Build email content & recipient routing (CC & BCC)
        subject = self.draft_builder.build_subject(job_title)
        body = self.draft_builder.build_body(candidate_data, job_data)

        # CC routing: candidate email + mandatory quinn@jpitstaffing.com
        cc_list: List[str] = []
        cand_email = candidate_data.get("email")
        if cand_email and isinstance(cand_email, str) and cand_email.strip() and EMAIL_FORMAT_REGEX.match(cand_email.strip()):
            cc_list.append(cand_email.strip())

        agency_cc = "quinn@jpitstaffing.com"
        if agency_cc not in cc_list:
            cc_list.append(agency_cc)

        # BCC routing: mandatory kim@jpitstaffing.com
        bcc_list: List[str] = ["kim@jpitstaffing.com"]

        # Anti-spam randomized attachment filename: <Candidate_Name>_Resume_<4digit>.pdf
        cand_name_for_file = re.sub(r"[^\w\s-]", "", cand_name or "Candidate").strip()
        cand_name_for_file = re.sub(r"[\s-]+", "_", cand_name_for_file) or "Candidate"
        rand_suffix = random.randint(1000, 9999)
        unique_attachment_filename = f"{cand_name_for_file}_Resume_{rand_suffix}.pdf"

        mime_msg = self.build_mime_message(
            to_email=recruiter_email,
            subject=subject,
            body=body,
            pdf_path=pdf_path,
            cc_emails=cc_list,
            bcc_emails=bcc_list,
            attachment_filename=unique_attachment_filename,
        )

        # 3. Dry Run Check
        if self.settings.DRY_RUN:
            logger.info("[DRY_RUN=True] Safe Mode Active: Email validated, drafted and logged without sending.")
            logger.info(
                f"--- [DRY_RUN EMAIL PREVIEW] ---\n"
                f"To: {recruiter_email}\n"
                f"Cc: {', '.join(cc_list)}\n"
                f"Bcc: {', '.join(bcc_list)}\n"
                f"Subject: {subject}\n"
                f"Attachment: {pdf_path} (filename: {unique_attachment_filename})\n\n"
                f"{body}\n"
                f"-------------------------------"
            )
            return {
                "success": True,
                "status": "dry_run",
                "dry_run": True,
                "message": "DRY RUN - email not actually sent",
                "message_id": f"dry_run_{int(os.path.getmtime(pdf_path))}",
                "subject": subject,
                "body": body,
                "recruiter_email": recruiter_email,
                "cc": cc_list,
                "bcc": bcc_list,
                "pdf_path": pdf_path,
                "resume_filename": unique_attachment_filename,
            }

        # 4. Actual Gmail API sending (when DRY_RUN=false)
        try:
            if not self.auth.is_authenticated():
                error_detail = (
                    "Gmail is not authenticated. Please authenticate your Gmail account "
                    "via the web dashboard or configure OAuth credentials in .env/credentials.json."
                )
                logger.error(error_detail)
                return {
                    "success": False,
                    "status": "failed",
                    "error": error_detail,
                    "subject": subject,
                    "body": body,
                    "recruiter_email": recruiter_email,
                    "resume_filename": unique_attachment_filename,
                }

            service = self.auth.get_service()
            if not service:
                raise RuntimeError("Gmail service unavailable. Please check OAuth credentials.")

            raw_encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
            send_response = service.users().messages().send(
                userId="me",
                body={"raw": raw_encoded}
            ).execute()

            msg_id = send_response.get("id", "sent_unknown_id")
            logger.info(f"Gmail email sent successfully to {recruiter_email}! (Attachment: {unique_attachment_filename}, Message ID: {msg_id})")
            return {
                "success": True,
                "status": "sent",
                "dry_run": False,
                "message_id": msg_id,
                "subject": subject,
                "body": body,
                "recruiter_email": recruiter_email,
                "cc": cc_list,
                "bcc": bcc_list,
                "pdf_path": pdf_path,
                "resume_filename": unique_attachment_filename,
            }
        except Exception as e:
            logger.error(f"Failed to send email via Gmail API: {e}")
            return {
                "success": False,
                "status": "failed",
                "error": str(e),
                "subject": subject,
                "body": body,
                "recruiter_email": recruiter_email,
            }
