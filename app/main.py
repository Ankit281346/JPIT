import os
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import shutil
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, status, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.database import get_db, init_db
from app.database.repository import Repository
from app.database.models import Candidate, Job, Submission
from app.services.pipeline import PipelineService
from app.gmail.auth import GmailAuth
from app.utils.logger import setup_logger

logger = setup_logger("main")
settings = get_settings()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Initializing database schema and runtime storage directories...")
        init_db()
        settings.ensure_directories()
        logger.info("Application startup complete.")
    except Exception as e:
        logger.warning(f"Startup initialization note: {e}")
    yield
    logger.info("Application shutdown.")

# Initialize FastAPI application
app = FastAPI(
    title="API C2C - AI-Powered Recruitment Outreach Automation",
    description="Automates Candidate Resume Parsing, LinkedIn C2C Job Discovery, AI Resume Customization, ATS PDF Generation, and Gmail Outreach Tracking.",
    version="1.0.0",
    lifespan=lifespan,
)

from starlette.types import ASGIApp, Receive, Scope, Send

class VercelPathCorrectionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            for prefix in ("/api/index.py", "/api/index"):
                if path.startswith(prefix):
                    rem = path[len(prefix):]
                    scope["path"] = rem if (rem and rem.startswith("/")) else ("/" + rem if rem else "/")
                    break
            if scope.get("path") == "/api":
                scope["path"] = "/"
        await self.app(scope, receive, send)

app.add_middleware(VercelPathCorrectionMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------- REQUEST / RESPONSE MODELS -------------------
class SearchRequest(BaseModel):
    query: Optional[str] = Field(default=None, description="Custom LinkedIn search query. If omitted, uses latest candidate's primary job title query.")
    candidate_id: Optional[int] = Field(default=None, description="Candidate ID to associate with search")
    max_results: int = Field(default=15, description="Maximum number of posts to fetch")
    mock_posts: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional raw posts list for offline testing")


class IngestPostRequest(BaseModel):
    raw_text: str = Field(..., description="Raw text of the LinkedIn post to ingest")
    post_url: Optional[str] = Field(default=None, description="LinkedIn post URL")
    author_name: Optional[str] = Field(default=None, description="Author or recruiter name")


class ProcessJobRequest(BaseModel):
    candidate_id: Optional[int] = Field(default=None, description="Candidate ID. If omitted, uses latest candidate.")


# ------------------- API ENDPOINTS -------------------

@app.get("/health", tags=["System"])
def health_check():
    """System health check endpoint."""
    return {
        "status": "ok",
        "service": "api-c2c",
        "version": "1.0.0",
        "ai_provider": settings.AI_PROVIDER,
        "dry_run": settings.DRY_RUN,
        "database": settings.DATABASE_URL.split("///")[-1] if "///" in settings.DATABASE_URL else "configured",
    }


@app.get("/gmail/status", tags=["Gmail"])
def get_gmail_status():
    """Returns current Gmail OAuth authentication status and authenticated user email."""
    auth = GmailAuth()
    is_auth = auth.is_authenticated()
    email = auth.get_user_email() if is_auth else None
    has_config = auth.has_credentials_config()
    return {
        "authenticated": is_auth,
        "email": email,
        "dry_run": settings.DRY_RUN,
        "credentials_configured": has_config,
    }


@app.post("/gmail/toggle-dry-run", tags=["Gmail"])
def toggle_dry_run():
    """Toggles between Safe Mode (DRY RUN) and Live Sending Mode."""
    settings.DRY_RUN = not settings.DRY_RUN
    mode = "Safe Mode (DRY RUN)" if settings.DRY_RUN else "Live Sending Mode"
    return {"success": True, "dry_run": settings.DRY_RUN, "mode": mode}


def _get_redirect_uri(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    
    # If on any Vercel deployment (*.vercel.app), use the fixed production domain
    # so Google Cloud Console only needs one registered URI: https://jpit.vercel.app/oauth2callback
    if host.endswith(".vercel.app"):
        return "https://jpit.vercel.app/oauth2callback"

    if not host.startswith("localhost") and not host.startswith("127.0.0.1"):
        proto = "https"
    return f"{proto}://{host}/oauth2callback"


@app.get("/gmail/auth/url", tags=["Gmail"])
def get_gmail_auth_url(request: Request):
    """Returns Google OAuth authorization URL for browser redirect."""
    auth = GmailAuth()
    if not auth.has_credentials_config():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OAuth credentials found. Please place 'credentials.json' in the project root or configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )
    redirect_uri = _get_redirect_uri(request)
    try:
        auth_url, state = auth.get_authorization_url(redirect_uri)
        return {"auth_url": auth_url, "redirect_uri": redirect_uri, "state": state}
    except Exception as e:
        logger.error(f"Failed to generate OAuth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/oauth2callback", tags=["Gmail"])
def oauth2callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handles OAuth 2.0 redirect callback from Google with PKCE state matching."""
    if error:
        return HTMLResponse(f"""
        <html><head><title>Gmail Auth Error</title></head>
        <body style="font-family:system-ui; text-align:center; padding:50px;">
          <h2 style="color:#ef4444;">❌ Google Authentication Error</h2>
          <p>{error}</p>
          <a href="/" style="display:inline-block; margin-top:20px; padding:10px 20px; background:#0f172a; color:white; border-radius:6px; text-decoration:none;">Return to Dashboard</a>
        </body></html>
        """)

    if not code:
        return HTMLResponse(f"""
        <html><head><title>Gmail Auth Error</title></head>
        <body style="font-family:system-ui; text-align:center; padding:50px;">
          <h2 style="color:#ef4444;">❌ Missing Authorization Code</h2>
          <a href="/" style="display:inline-block; margin-top:20px; padding:10px 20px; background:#0f172a; color:white; border-radius:6px; text-decoration:none;">Return to Dashboard</a>
        </body></html>
        """)

    redirect_uri = _get_redirect_uri(request)
    auth = GmailAuth()
    try:
        auth.fetch_token_from_code(code=code, redirect_uri=redirect_uri, state=state)
        email = auth.get_user_email()
        return HTMLResponse(f"""
        <html><head><title>Gmail Connected</title></head>
        <body style="font-family:system-ui; text-align:center; padding:50px; background:#f8fafc;">
          <h2 style="color:#10b981;">✅ Gmail Connected Successfully!</h2>
          <p>Authorized account: <strong>{email or 'Connected'}</strong></p>
          <p>Redirecting back to dashboard in 2 seconds...</p>
          <script>setTimeout(function() {{ window.location.href = '/'; }}, 2000);</script>
        </body></html>
        """)
    except Exception as e:
        logger.error(f"OAuth token exchange failed: {e}")
        return HTMLResponse(f"""
        <html><head><title>Gmail Auth Failed</title></head>
        <body style="font-family:system-ui; text-align:center; padding:50px;">
          <h2 style="color:#ef4444;">❌ Authentication Failed</h2>
          <p>{str(e)}</p>
          <a href="/" style="display:inline-block; margin-top:20px; padding:10px 20px; background:#0f172a; color:white; border-radius:6px; text-decoration:none;">Return to Dashboard</a>
        </body></html>
        """)


@app.post("/gmail/auth/login", tags=["Gmail"])
def initiate_gmail_login():
    """Initiates interactive Google OAuth 2.0 authorization flow to connect a Gmail account."""
    auth = GmailAuth()
    if not auth.has_credentials_config():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OAuth credentials found. Please place 'credentials.json' in the project root or configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )
    creds = auth.start_interactive_auth()
    if not creds or not creds.valid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth authorization failed or was cancelled.",
        )
    email = auth.get_user_email()
    return {
        "success": True,
        "authenticated": True,
        "email": email,
        "message": f"Successfully authenticated Gmail account: {email or 'Authorized'}",
    }


@app.post("/resume/upload", tags=["Resume"])
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a candidate resume PDF, parse details, detect primary title, and generate search query."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF resume files are supported.",
        )

    # Save uploaded file
    resumes_dir = os.path.join(settings.BASE_DIR, settings.RESUMES_DIR)
    os.makedirs(resumes_dir, exist_ok=True)
    saved_path = os.path.join(resumes_dir, file.filename)

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info(f"Resume uploaded and saved to: {saved_path}")

    pipeline = PipelineService(db)
    try:
        result = pipeline.process_resume_upload(saved_path, file.filename)
        return {
            "success": True,
            "message": "Resume uploaded and parsed successfully.",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Failed to parse uploaded resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse resume: {str(e)}",
        )


@app.post("/linkedin/search", tags=["LinkedIn"])
async def search_linkedin(
    request: SearchRequest = None,
    db: Session = Depends(get_db),
):
    """Search LinkedIn posts for C2C opportunities using primary title or custom query."""
    req = request or SearchRequest()
    repo = Repository(db)
    pipeline = PipelineService(db)

    search_query = req.query
    if not search_query:
        candidate = repo.get_candidate(req.candidate_id) if req.candidate_id else repo.get_latest_candidate()
        if candidate:
            search_query = pipeline.analyzer.generate_search_query(candidate.primary_job_title)
        else:
            search_query = '"Python Developer" C2C -W2 -Full-Time -Bench -Sales -Hotlist'

    try:
        search_result = await pipeline.search_and_filter_linkedin_posts(
            search_query=search_query,
            max_posts=req.max_results,
            mock_raw_posts=req.mock_posts,
        )
        return {
            "success": True,
            "query": search_query,
            "summary": {
                "total_discovered": search_result["total_discovered"],
                "passed_filters": search_result["jobs_passed"],
                "filtered_out": search_result["filtered_out_count"],
                "duplicates_skipped": search_result["duplicates_skipped_count"],
            },
            "jobs": [
                {
                    "id": j.id,
                    "job_title": j.job_title,
                    "company_name": j.company_name,
                    "recruiter_name": j.recruiter_name,
                    "recruiter_email": j.recruiter_email,
                    "location": j.location,
                    "experience_required": j.experience_required,
                    "skills": json.loads(j.skills) if j.skills else [],
                    "linkedin_post_url": j.linkedin_post_url,
                    "status": j.status,
                }
                for j in search_result["jobs"]
            ],
            "filtered_reasons": search_result["filtered_reasons"],
            "duplicates": search_result["duplicates"],
        }
    except Exception as e:
        logger.error(f"Error executing LinkedIn search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/jobs/ingest-post", tags=["Jobs"])
def ingest_custom_post(
    request: IngestPostRequest,
    db: Session = Depends(get_db),
):
    """Ingest a custom or pasted LinkedIn post directly, extracting recruiter, role and company."""
    import time
    pipeline = PipelineService(db)
    ts = int(time.time())
    post_url = request.post_url or f"https://www.linkedin.com/feed/update/urn:li:activity:custom_{ts}/"
    raw_dict = {
        "raw_text": request.raw_text,
        "post_url": post_url,
        "author_name": request.author_name or "",
        "author_headline": "",
        "posted_at": "1h",
    }
    normalized = pipeline.scraper.parse_raw_post(raw_dict)
    is_valid, reject_reason = pipeline.post_filter.validate_post(normalized)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Post rejected by C2C filter: {reject_reason}",
        )

    is_dup, dup_reason = pipeline.dedup.is_duplicate(normalized)
    if is_dup:
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate post: {dup_reason}",
        )

    saved_job = pipeline.repo.create_job(
        linkedin_post_url=normalized["linkedin_post_url"],
        recruiter_email=normalized["recruiter_email"],
        job_title=normalized["job_title"],
        job_description=normalized["job_description"],
        recruiter_name=normalized.get("recruiter_name"),
        company_name=normalized.get("company_name"),
        skills=normalized.get("skills", []),
        experience_required=normalized.get("experience_required"),
        location=normalized.get("location"),
        posted_at=normalized.get("posted_at"),
        raw_post_text=normalized.get("raw_post_text"),
        status="discovered",
    )
    return {
        "success": True,
        "message": "Custom LinkedIn post ingested successfully.",
        "job": {
            "id": saved_job.id,
            "job_title": saved_job.job_title,
            "company_name": saved_job.company_name,
            "recruiter_name": saved_job.recruiter_name,
            "recruiter_email": saved_job.recruiter_email,
            "location": saved_job.location,
            "status": saved_job.status,
        }
    }


@app.get("/jobs", tags=["Jobs"])
def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all extracted jobs."""
    repo = Repository(db)
    jobs = repo.get_all_jobs(skip=skip, limit=limit, status=status)
    return {
        "count": len(jobs),
        "jobs": [
            {
                "id": j.id,
                "job_title": j.job_title,
                "company_name": j.company_name,
                "recruiter_name": j.recruiter_name,
                "recruiter_email": j.recruiter_email,
                "location": j.location,
                "experience_required": j.experience_required,
                "skills": json.loads(j.skills) if j.skills else [],
                "linkedin_post_url": j.linkedin_post_url,
                "status": j.status,
                "posted_at": j.posted_at,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ],
    }


@app.get("/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a specific job."""
    repo = Repository(db)
    job = repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "job_title": job.job_title,
        "company_name": job.company_name,
        "recruiter_name": job.recruiter_name,
        "recruiter_email": job.recruiter_email,
        "location": job.location,
        "experience_required": job.experience_required,
        "skills": json.loads(job.skills) if job.skills else [],
        "job_description": job.job_description,
        "linkedin_post_url": job.linkedin_post_url,
        "status": job.status,
        "posted_at": job.posted_at,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@app.post("/jobs/{job_id}/process", tags=["Pipeline"])
def process_job(
    job_id: int,
    request: ProcessJobRequest = None,
    db: Session = Depends(get_db),
):
    """Customizes candidate resume for this job and generates an ATS-friendly PDF."""
    repo = Repository(db)
    req = request or ProcessJobRequest()
    candidate = repo.get_candidate(req.candidate_id) if req.candidate_id else repo.get_latest_candidate()

    if not candidate:
        raise HTTPException(status_code=400, detail="No candidate found. Please upload a resume first.")

    pipeline = PipelineService(db)
    result = pipeline.process_and_submit_job(candidate_id=candidate.id, job_id=job_id)
    return result


@app.post("/jobs/{job_id}/send", tags=["Pipeline"])
def send_job_application(
    job_id: int,
    request: ProcessJobRequest = None,
    db: Session = Depends(get_db),
):
    """Validates, prepares attachment, and sends outreach email (or dry-run logs) for a specific job."""
    repo = Repository(db)
    req = request or ProcessJobRequest()
    candidate = repo.get_candidate(req.candidate_id) if req.candidate_id else repo.get_latest_candidate()

    if not candidate:
        raise HTTPException(status_code=400, detail="No candidate found. Please upload a resume first.")

    pipeline = PipelineService(db)
    result = pipeline.process_and_submit_job(candidate_id=candidate.id, job_id=job_id)
    return result


@app.post("/jobs/submit-all", tags=["Pipeline"])
async def submit_all_jobs(
    request: ProcessJobRequest = None,
    db: Session = Depends(get_db),
):
    """Processes and submits outreach emails for all discovered jobs concurrently with limits."""
    repo = Repository(db)
    req = request or ProcessJobRequest()
    candidate = repo.get_candidate(req.candidate_id) if req.candidate_id else repo.get_latest_candidate()

    if not candidate:
        raise HTTPException(status_code=400, detail="No candidate found. Please upload a resume first.")

    jobs = repo.get_all_jobs(status="discovered")
    if not jobs:
        return {"success": True, "message": "No newly discovered jobs to process.", "processed": 0}

    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent email generations/sends
    pipeline = PipelineService(db)

    async def process_job_concurrent(job_id: int):
        async with semaphore:
            try:
                # Use to_thread since process_and_submit_job is synchronous
                return await asyncio.to_thread(pipeline.process_and_submit_job, candidate.id, job_id)
            except Exception as e:
                logger.error(f"Failed to process job {job_id}: {e}")
                return {"success": False, "job_id": job_id, "error": str(e)}

    tasks = [process_job_concurrent(job.id) for job in jobs]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": True,
        "message": f"Processed {len(jobs)} jobs. Successful submissions: {success_count}.",
        "processed": len(jobs),
        "success_count": success_count,
        "results": results
    }


@app.get("/submissions", tags=["Tracking"])
def list_submissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lists all outreach submission records."""
    repo = Repository(db)
    submissions = repo.get_all_submissions(skip=skip, limit=limit)
    return {
        "count": len(submissions),
        "submissions": [
            {
                "id": s.id,
                "candidate_name": s.candidate_name,
                "recruiter_email": s.recruiter_email,
                "recruiter_name": s.recruiter_name,
                "company": s.company,
                "job_title": s.job_title,
                "job_location": s.job_location,
                "linkedin_post_url": s.linkedin_post_url,
                "submission_date": s.submission_date,
                "submission_time": s.submission_time,
                "email_status": s.email_status,
                "resume_filename": s.resume_filename,
                "match_score": s.match_score,
                "email_subject": s.email_subject,
                "email_body": s.email_body,
                "error_message": s.error_message,
                "is_duplicate": s.is_duplicate,
            }
            for s in submissions
        ],
    }


@app.get("/download/resume/{filename}", tags=["Resume"])
def download_resume(filename: str):
    """Download a master or generated PDF resume."""
    res_dir = os.path.join(settings.BASE_DIR, settings.RESUMES_DIR)
    gen_dir = os.path.join(settings.BASE_DIR, settings.GENERATED_RESUMES_DIR)
    file_path = os.path.join(res_dir, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(gen_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/pdf", filename=filename)


@app.post("/system/reset", tags=["System"])
def reset_system_data(db: Session = Depends(get_db)):
    """Clear all discovered jobs and outreach submissions history."""
    db.query(Submission).delete()
    db.query(Job).delete()
    db.commit()

    csv_path = os.path.join(settings.BASE_DIR, settings.SUBMISSIONS_DIR, "submissions.csv")
    if os.path.exists(csv_path):
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("candidate,recruiter_email,company,job_title,linkedin_url,submission_date,submission_time,status,match_score,resume_filename,error_message\n")

    jobs_json = os.path.join(settings.BASE_DIR, settings.JOBS_DIR, "latest_jobs.json")
    if os.path.exists(jobs_json):
        with open(jobs_json, "w", encoding="utf-8") as f:
            f.write("[]")

    return {"success": True, "message": "All jobs and outreach submissions history cleared successfully."}


# ------------------- INTERACTIVE WEB DASHBOARD -------------------
@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
@app.get("/api", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api/index", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api/index.py", response_class=HTMLResponse, include_in_schema=False)
def web_dashboard():
    """Interactive visual dashboard for testing and observing the full pipeline."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API C2C - AI Recruitment Outreach Automation</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    body { background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; }
    .card { border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
    .header-bar { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 24px 0; }
    .badge-sent { background-color: #10b981; color: white; font-weight: 600; padding: 6px 10px; border-radius: 6px; }
    .badge-dryrun { background-color: #f59e0b; color: #000; font-weight: 600; padding: 6px 10px; border-radius: 6px; }
    .badge-failed { background-color: #ef4444; color: white; font-weight: 600; padding: 6px 10px; border-radius: 6px; }
    .badge-duplicate { background-color: #64748b; color: white; font-weight: 600; padding: 6px 10px; border-radius: 6px; }
    .badge-discovered { background-color: #0284c7; color: white; font-weight: 600; padding: 6px 10px; border-radius: 6px; }
    .auth-card { background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 8px; padding: 10px 16px; }
  </style>
</head>
<body>
  <div class="header-bar mb-4">
    <div class="container">
      <div class="row align-items-center">
        <div class="col-lg-6">
          <h2 class="fw-bold mb-1">🚀 API C2C Automation</h2>
          <p class="mb-0 text-slate-300 opacity-75 small">Resume Parsing → LinkedIn C2C Discovery → Master Resume Outreach → Real Gmail Delivery</p>
        </div>
        <div class="col-lg-6 mt-3 mt-lg-0 text-lg-end">
          <div class="d-inline-flex align-items-center gap-2 auth-card text-start">
            <div>
              <div class="small fw-semibold" id="modeStatus"><span class="spinner-border spinner-border-sm text-light"></span> Loading mode...</div>
              <div class="small" id="gmailStatusText"><span class="spinner-border spinner-border-sm text-light"></span> Checking Gmail...</div>
            </div>
            <button class="btn btn-sm btn-light fw-semibold ms-2" id="authGmailBtn" onclick="connectGmail()">
              <i class="bi bi-google"></i> Connect Gmail
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="container mb-5">
    <div class="row g-4">
      <!-- Step 1: Resume Upload -->
      <div class="col-md-5">
        <div class="card p-4 h-100">
          <h5 class="fw-bold text-primary mb-3"><i class="bi bi-file-earmark-person"></i> 1. Candidate Resume Upload</h5>
          <form id="uploadForm" enctype="multipart/form-data">
            <div class="mb-3">
              <label class="form-label">Upload Resume (PDF)</label>
              <input type="file" id="resumeFile" name="file" class="form-control" accept=".pdf" required>
            </div>
            <button type="submit" class="btn btn-primary w-100" id="uploadBtn">Upload & Parse Resume</button>
          </form>

          <div id="candidateInfo" class="mt-4 d-none">
            <h6 class="fw-bold text-success"><i class="bi bi-check-circle"></i> Parsed Candidate Profile</h6>
            <ul class="list-group list-group-flush small">
              <li class="list-group-item"><strong>Name:</strong> <span id="candName"></span></li>
              <li class="list-group-item"><strong>Primary Title:</strong> <span class="badge bg-dark" id="candTitle"></span></li>
              <li class="list-group-item"><strong>Generated Query:</strong> <br><code id="candQuery"></code></li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Step 2: LinkedIn Search & Manual Ingest -->
      <div class="col-md-7">
        <div class="card p-4 h-100">
          <h5 class="fw-bold text-primary mb-3"><i class="bi bi-search"></i> 2. LinkedIn C2C Job Discovery</h5>
          <div class="mb-3">
            <label class="form-label">Dynamic Search Query</label>
            <input type="text" id="searchQueryInput" class="form-control" placeholder='"Python Developer" C2C -W2 -Full-Time -Bench -Sales -Hotlist'>
          </div>
          <div class="d-flex gap-2 mb-3">
            <button class="btn btn-dark flex-grow-1" id="searchBtn">Discover & Filter LinkedIn C2C Posts</button>
            <button class="btn btn-outline-primary" data-bs-toggle="modal" data-bs-target="#pastePostModal">+ Paste Post Text</button>
          </div>
          <div id="searchSummary" class="alert alert-info py-2 small d-none"></div>
        </div>
      </div>
    </div>

    <!-- Modal for Pasting Custom LinkedIn Post -->
    <div class="modal fade" id="pastePostModal" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Paste LinkedIn Post Text</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">Post Description / Content</label>
              <textarea id="customPostText" class="form-control" rows="6" placeholder="Urgent C2C role! Position: Full Stack Developer. Email resume to: recruiter@techagency.com..."></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">Post URL (Optional)</label>
              <input type="text" id="customPostUrl" class="form-control" placeholder="https://www.linkedin.com/posts/...">
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-primary" id="submitCustomPostBtn">Ingest & Add to Jobs</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Jobs Table -->
    <div class="row mt-4">
      <div class="col-12">
        <div class="card p-4">
          <div class="d-flex justify-content-between align-items-center mb-3">
            <h5 class="fw-bold text-primary mb-0"><i class="bi bi-briefcase"></i> 3. Discovered C2C Opportunities</h5>
            <div class="d-flex gap-2">
              <button class="btn btn-primary fw-bold" id="submitAllBtn"><i class="bi bi-send-fill"></i> 🚀 Send All Outreach</button>
              <button class="btn btn-outline-secondary btn-sm" id="refreshJobsBtn">Refresh Jobs</button>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table table-hover align-middle">
              <thead class="table-light">
                <tr>
                  <th>ID</th>
                  <th>Job Title</th>
                  <th>Company</th>
                  <th>Recruiter</th>
                  <th>Recruiter Email</th>
                  <th>Location</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody id="jobsTableBody">
                <tr><td colspan="8" class="text-center text-muted py-4">No jobs discovered yet. Upload a resume and run discovery!</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 4: Submission Records -->
    <div class="row mt-4">
      <div class="col-12">
        <div class="card p-4">
          <div class="d-flex justify-content-between align-items-center mb-3">
            <h5 class="fw-bold text-primary mb-0"><i class="bi bi-send-check"></i> 4. Outreach Submissions & Deduplication Log</h5>
            <div class="d-flex gap-2">
              <button class="btn btn-outline-danger btn-sm" onclick="clearAllData()"><i class="bi bi-trash"></i> Clear All Data</button>
              <button class="btn btn-outline-secondary btn-sm" id="refreshSubsBtn">Refresh Submissions</button>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table table-hover align-middle">
              <thead class="table-light">
                <tr>
                  <th>ID</th>
                  <th>Candidate</th>
                  <th>Recruiter Email</th>
                  <th>Job Title</th>
                  <th>Match Score</th>
                  <th>Delivery Status</th>
                  <th>Resume PDF</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody id="subsTableBody">
                <tr><td colspan="8" class="text-center text-muted py-4">No submissions recorded yet.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let activeCandidateId = null;
    let isDryRunMode = true;
    let isGmailAuthed = false;

    async function checkGmailStatus() {
      try {
        const res = await fetch('/gmail/status');
        const data = await res.json();
        isDryRunMode = data.dry_run;
        isGmailAuthed = data.authenticated;

        const modeBadge = isDryRunMode 
          ? '<span class="badge bg-warning text-dark" onclick="toggleDryRun()" style="cursor:pointer;" title="Click to switch to Live Sending Mode"><i class="bi bi-shield-lock"></i> Mode: DRY RUN (Click to Switch to Live)</span>'
          : '<span class="badge bg-success text-white" onclick="toggleDryRun()" style="cursor:pointer;" title="Click to switch to Safe Mode"><i class="bi bi-send-fill"></i> Mode: LIVE SENDING (Active)</span>';
        document.getElementById('modeStatus').innerHTML = modeBadge;

        const authBtn = document.getElementById('authGmailBtn');
        if (data.authenticated && data.email) {
          document.getElementById('gmailStatusText').innerHTML = `🟢 Gmail: <strong>${data.email}</strong>`;
          authBtn.innerText = 'Re-Authenticate';
          authBtn.className = 'btn btn-sm btn-outline-light ms-2';
        } else if (data.authenticated) {
          document.getElementById('gmailStatusText').innerHTML = '🟢 Gmail: <strong>Connected</strong>';
          authBtn.innerText = 'Re-Authenticate';
          authBtn.className = 'btn btn-sm btn-outline-light ms-2';
        } else {
          document.getElementById('gmailStatusText').innerHTML = '🔴 Gmail: <strong>Not Connected</strong>';
          authBtn.innerHTML = '<i class="bi bi-google"></i> Connect Gmail';
          authBtn.className = 'btn btn-sm btn-light fw-bold ms-2';
        }
      } catch (e) {
        console.error('Failed to load Gmail status:', e);
      }
    }

    async function toggleDryRun() {
      try {
        const res = await fetch('/gmail/toggle-dry-run', { method: 'POST' });
        const data = await res.json();
        alert('Switched to: ' + data.mode + (data.dry_run ? '\n(Emails will be validated & drafted without sending)' : '\n(Live sending enabled: emails will be delivered directly from your connected Gmail)'));
        checkGmailStatus();
      } catch (err) {
        alert('Could not toggle mode: ' + err.message);
      }
    }

    async function connectGmail() {
      const btn = document.getElementById('authGmailBtn');
      const originalText = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Opening Google Login...';
      btn.disabled = true;

      try {
        const res = await fetch('/gmail/auth/url');
        const data = await res.json();
        if (res.ok && data.auth_url) {
          // Direct browser navigation to Google sign-in
          window.location.href = data.auth_url;
          return;
        }
        
        // Fallback to local server flow if URL generator cannot be used
        const resFallback = await fetch('/gmail/auth/login', { method: 'POST' });
        const dataFallback = await resFallback.json();
        if (resFallback.ok && dataFallback.success) {
          alert('✅ ' + dataFallback.message);
        } else {
          alert('❌ Authentication failed: ' + (dataFallback.detail || data.detail || 'Could not authenticate. Check credentials.json or .env.'));
        }
      } catch (err) {
        alert('❌ Error: ' + err.message);
      } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
        checkGmailStatus();
      }
    }

    function renderStatusBadge(status) {
      if (status === 'sent') {
        return '<span class="badge-sent"><i class="bi bi-check-all"></i> SENT - Gmail API confirmed</span>';
      } else if (status === 'dry_run') {
        return '<span class="badge-dryrun"><i class="bi bi-shield-check"></i> DRY RUN - not sent</span>';
      } else if (status === 'failed') {
        return '<span class="badge-failed"><i class="bi bi-x-circle"></i> FAILED - email not sent</span>';
      } else if (status === 'skipped_duplicate') {
        return '<span class="badge-duplicate"><i class="bi bi-copy"></i> Skipped (Duplicate)</span>';
      } else {
        return `<span class="badge-discovered">${status}</span>`;
      }
    }

    document.getElementById('uploadForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById('resumeFile');
      if (!fileInput.files[0]) return;

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);

      const btn = document.getElementById('uploadBtn');
      btn.innerText = 'Parsing Resume...';
      btn.disabled = true;

      try {
        const res = await fetch('/resume/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
          activeCandidateId = data.data.candidate_id;
          document.getElementById('candName').innerText = data.data.candidate_name;
          document.getElementById('candTitle').innerText = data.data.primary_job_title;
          document.getElementById('candQuery').innerText = data.data.search_query;
          document.getElementById('searchQueryInput').value = data.data.search_query;
          document.getElementById('candidateInfo').classList.remove('d-none');
        } else {
          alert('Upload failed: ' + data.detail);
        }
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        btn.innerText = 'Upload & Parse Resume';
        btn.disabled = false;
      }
    });

    document.getElementById('submitCustomPostBtn').addEventListener('click', async () => {
      const text = document.getElementById('customPostText').value.trim();
      const url = document.getElementById('customPostUrl').value.trim();
      if (!text) {
        alert('Please paste the LinkedIn post text.');
        return;
      }
      const btn = document.getElementById('submitCustomPostBtn');
      btn.innerText = 'Ingesting...';
      btn.disabled = true;

      try {
        const res = await fetch('/jobs/ingest-post', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ raw_text: text, post_url: url || undefined })
        });
        const data = await res.json();
        if (res.ok) {
          alert('Success! Custom post ingested: ' + data.job.job_title + ' at ' + (data.job.company_name || 'Client'));
          document.getElementById('customPostText').value = '';
          document.getElementById('customPostUrl').value = '';
          const modalElem = document.getElementById('pastePostModal');
          const modal = bootstrap.Modal.getInstance(modalElem);
          if (modal) modal.hide();
          loadJobs();
        } else {
          alert('Ingestion failed: ' + (data.detail || 'Unknown error'));
        }
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        btn.innerText = 'Ingest & Add to Jobs';
        btn.disabled = false;
      }
    });

    document.getElementById('searchBtn').addEventListener('click', async () => {
      const btn = document.getElementById('searchBtn');
      const query = document.getElementById('searchQueryInput').value.trim();

      if (query) {
        // Open live LinkedIn 24h posts in a new tab
        const linkedInUrl = 'https://www.linkedin.com/search/results/content/?keywords=' + encodeURIComponent(query) + '&sortBy=%22date_posted%22&f_TPR=r86400';
        window.open(linkedInUrl, '_blank');
      }

      btn.innerText = 'Discovering & Filtering...';
      btn.disabled = true;

      try {
        const res = await fetch('/linkedin/search', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ query: query, candidate_id: activeCandidateId, max_results: 15 })
        });
        const data = await res.json();
        if (data.success) {
          const s = data.summary;
          const sumBox = document.getElementById('searchSummary');
          sumBox.innerHTML = `Discovered: <strong>${s.total_discovered}</strong> | Passed C2C Filters (24h): <strong>${s.passed_filters}</strong> | Filtered Out: <strong>${s.filtered_out}</strong> | Duplicates Skipped: <strong>${s.duplicates_skipped}</strong>`;
          sumBox.classList.remove('d-none');
          loadJobs();
        } else {
          alert('❌ ' + (data.detail || 'Search failed'));
        }
      } catch (err) {
        alert('❌ Error: ' + err.message);
      } finally {
        btn.innerText = 'Discover & Filter LinkedIn C2C Posts';
        btn.disabled = false;
      }
    });

    async function loadJobs() {
      const res = await fetch('/jobs');
      const data = await res.json();
      const tbody = document.getElementById('jobsTableBody');
      if (data.jobs && data.jobs.length > 0) {
        tbody.innerHTML = data.jobs.map(j => `
          <tr>
            <td>${j.id}</td>
            <td class="fw-bold">${j.job_title}</td>
            <td>${j.company_name || 'Client'}</td>
            <td>${j.recruiter_name || 'Hiring Team'}</td>
            <td><code>${j.recruiter_email}</code></td>
            <td>${j.location || 'Remote'}</td>
            <td>${renderStatusBadge(j.status)}</td>
            <td>
              <a href="${j.linkedin_post_url}" target="_blank" class="btn btn-sm btn-outline-secondary"><i class="bi bi-link-45deg"></i> Source</a>
            </td>
          </tr>
        `).join('');
      } else {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No jobs discovered yet.</td></tr>';
      }
    }

    async function processJob(jobId) {
      const res = await fetch(`/jobs/${jobId}/send`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ candidate_id: activeCandidateId })
      });
      const data = await res.json();
      if (data.status === 'sent') {
        alert(`✅ SENT - Gmail API confirmed!\n\nEmail successfully delivered to: ${data.recruiter_email}\nJob: ${data.job_title}\nMatch Score: ${data.match_score}%\nGmail Message ID: ${data.message_id || 'Confirmed'}`);
      } else if (data.status === 'dry_run') {
        alert(`🟡 DRY RUN - not sent (DRY_RUN=true)\n\nEmail drafted and validated for: ${data.recruiter_email}\nPDF Attachment: ${data.resume_filename}\nMatch Score: ${data.match_score}%\n\nTo send real emails, connect Gmail and set DRY_RUN=false in .env.`);
      } else if (data.status === 'skipped_duplicate') {
        alert(`⚠️ Duplicate Skipped:\n\n${data.message}`);
      } else {
        alert(`❌ FAILED - email not sent:\n\n${data.error || data.message || 'Unknown error'}`);
      }
      loadJobs();
      loadSubmissions();
    }

    async function loadSubmissions() {
      const res = await fetch('/submissions');
      const data = await res.json();
      const tbody = document.getElementById('subsTableBody');
      if (data.submissions && data.submissions.length > 0) {
        tbody.innerHTML = data.submissions.map(s => {
          let pdfLink = s.resume_filename ? `<a href="/download/resume/${s.resume_filename}" target="_blank" class="btn btn-outline-dark btn-sm"><i class="bi bi-file-earmark-pdf"></i> PDF</a>` : 'N/A';
          return `
            <tr>
              <td>${s.id}</td>
              <td>${s.candidate_name}</td>
              <td><code>${s.recruiter_email}</code></td>
              <td>${s.job_title}</td>
              <td><strong>${s.match_score ? s.match_score + '%' : 'N/A'}</strong></td>
              <td>${renderStatusBadge(s.email_status)}</td>
              <td>${pdfLink}</td>
              <td><small>${s.submission_date} ${s.submission_time}</small></td>
            </tr>
          `;
        }).join('');
      } else {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No submissions recorded yet.</td></tr>';
      }
    }

    async function clearAllData() {
      if (!confirm('Are you sure you want to clear all discovered jobs and outreach submissions?')) return;
      try {
        const res = await fetch('/system/reset', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          alert('✅ ' + data.message);
          loadJobs();
          loadSubmissions();
        }
      } catch (err) {
        alert('❌ Error: ' + err.message);
      }
    }

    document.getElementById('refreshJobsBtn').addEventListener('click', loadJobs);
    document.getElementById('refreshSubsBtn').addEventListener('click', loadSubmissions);
    
    document.getElementById('submitAllBtn').addEventListener('click', async () => {
      const btn = document.getElementById('submitAllBtn');
      if (!confirm('This will concurrently send outreach emails for all discovered jobs. Proceed?')) return;
      
      btn.innerText = 'Sending...';
      btn.disabled = true;
      try {
        const res = await fetch('/jobs/submit-all', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ candidate_id: activeCandidateId })
        });
        const data = await res.json();
        if (data.success) {
          alert('✅ ' + data.message);
          loadJobs();
          loadSubmissions();
        } else {
          alert('❌ Error: ' + data.detail);
        }
      } catch (err) {
        alert('❌ Error: ' + err.message);
      } finally {
        btn.innerHTML = '<i class="bi bi-send-fill"></i> Send All Outreach';
        btn.disabled = false;
      }
    });
    
    // Initialize dashboard data
    checkGmailStatus();
    loadJobs();
    loadSubmissions();
  </script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
