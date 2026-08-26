# API C2C — AI-Powered Recruitment Outreach Automation

An end-to-end automated recruitment pipeline that parses candidate resumes, discovers relevant Corp-to-Corp (C2C) opportunities on LinkedIn, customizes the candidate's resume truthfully using AI, generates ATS-compliant PDF resumes, composes personalized Gmail outreach emails with attachments, validates and sends them, and tracks every submission while strictly preventing duplicates.

---

## Architecture & Pipeline Workflow

```text
               ┌────────────────────────┐
               │    Candidate Resume    │ (PDF)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │     Resume Parser      │ (pdfplumber + PyMuPDF)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │ Detect Primary Title   │ (e.g., "Python Developer")
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │ Generate Search Query  │ ("<Title>" C2C -W2 -Full-Time -Bench -Sales -Hotlist)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │ Search LinkedIn Posts  │ (Playwright Browser Automation)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │ Filter C2C Posts       │ (24h, C2C only, Exclude W2/Bench/Sales, Valid Email)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │ Extract Recruiter/Job  │ (Normalized Job Record)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │  Duplicate Prevention  │ (Post URL / Recruiter+Role+Company check)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │  AI Customization      │ (Google Gemini / OpenAI / Claude — Truthful, No Hallucinations)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │  Generate ATS PDF      │ (ReportLab: CandidateName_Company_JobTitle.pdf)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │  Personalized Gmail    │ (Structured Candidate Summary + Attached PDF)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │ Validate & Send Outreach│ (Safe Mode: DRY_RUN=true / Gmail API OAuth 2.0)
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │  Submission Tracking   │ (SQLite Database + data/submissions/submissions.csv)
               └────────────────────────┘
```

---

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy
- **Browser Automation**: Playwright (Chromium)
- **AI Engine**: Google Gemini (`google-generativeai`), OpenAI, Claude (configurable via `AI_PROVIDER`)
- **Resume Processing**: `pdfplumber` with `PyMuPDF` (`fitz`) fallback
- **PDF Generation**: `ReportLab` (ATS-compliant clean formatting)
- **Email Delivery**: Google Gmail API, OAuth 2.0 (`google-auth-oauthlib`)
- **Database & Storage**: SQLite (easily swappable with PostgreSQL via `DATABASE_URL`) + CSV export

---

## Directory Structure

```text
api-c2c/
├── app/
│   ├── main.py                     # FastAPI application & Web Dashboard
│   ├── config/
│   │   └── settings.py             # Pydantic Settings (.env configuration)
│   ├── linkedin/
│   │   ├── auth.py                 # Playwright persistent session management
│   │   ├── search.py               # LinkedIn posts search & dynamic query runner
│   │   ├── scraper.py              # Normalized recruiter/job extractor
│   │   └── filters.py              # 24-hour, C2C, W2/Bench/Hotlist filter rules
│   ├── resume/
│   │   ├── parser.py               # PDF parser (pdfplumber/PyMuPDF)
│   │   ├── analyzer.py             # Primary job title & query generation
│   │   ├── customizer.py           # Truthful AI customization orchestrator
│   │   └── pdf_generator.py        # ReportLab ATS PDF resume generator
│   ├── ai/
│   │   ├── client.py               # Configurable AI client (Gemini/OpenAI/Claude)
│   │   └── prompts.py              # Anti-hallucination prompts & match scoring
│   ├── gmail/
│   │   ├── auth.py                 # Gmail API OAuth 2.0 authorization
│   │   ├── drafts.py               # Dynamic email subject and body builder
│   │   └── sender.py               # Attachment validation, MIME builder & sender
│   ├── database/
│   │   ├── models.py               # SQLAlchemy models (Candidate, Job, Submission)
│   │   ├── database.py             # DB engine & session management
│   │   └── repository.py           # CRUD & duplicate check repository
│   ├── services/
│   │   ├── pipeline.py             # End-to-end orchestration workflow
│   │   ├── deduplication.py        # Duplicate prevention service
│   │   └── tracking.py             # Dual DB + CSV tracking service
│   └── utils/
│       └── logger.py               # Masked structured logging (no secrets in logs)
├── data/
│   ├── resumes/                    # Candidate input resumes
│   ├── generated_resumes/          # AI-tailored ATS PDF resumes
│   ├── jobs/                       # Discovered C2C jobs JSON dump
│   └── submissions/                # submissions.csv submission history
├── evidence/                       # Evidence cards, email preview, demo artifacts
├── scripts/
│   ├── generate_evidence.py        # Automated end-to-end demonstration script
│   └── capture_ui_screenshots.py   # Evidence visual cards generator
├── tests/                          # Complete pytest suite (32 unit/integration tests)
├── .env.example                    # Environment variable template
├── requirements.txt                # Python package dependencies
└── README.md
```

---

## Quick Start & Setup

### 1. Clone & Install Dependencies

```bash
# Clone the repository
git clone <repo_url>
cd api-c2c

# Install Python packages
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# AI Provider: gemini, openai, claude
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here

# LinkedIn Session
LINKEDIN_SESSION_PATH=data/linkedin_session.json
LINKEDIN_HEADLESS=false

# Google Cloud OAuth 2.0 (Gmail API)
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GMAIL_TOKEN_PATH=data/gmail_token.json

# Database
DATABASE_URL=sqlite:///./data/api_c2c.db

# Safe Mode: when true, validates & logs emails without sending live
DRY_RUN=true
```

---

## Step-by-Step Google Cloud & Gmail API Setup

Follow these steps to configure Gmail OAuth 2.0 and enable real outreach delivery:

### 1. Configure Google Cloud Project
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. `api-c2c-recruitment`).
3. In the left sidebar, navigate to **APIs & Services > Library**.
4. Search for **Gmail API** and click **Enable**.

### 2. Configure OAuth Consent Screen
1. Navigate to **APIs & Services > OAuth consent screen**.
2. Select **External** and click **Create**.
3. Enter:
   - **App Name**: `API C2C Automation`
   - **User Support Email**: Your Gmail address
   - **Developer Contact Email**: Your Gmail address
4. Under **Scopes**, add `https://www.googleapis.com/auth/gmail.send`, `https://www.googleapis.com/auth/gmail.compose`, and `https://www.googleapis.com/auth/gmail.readonly`.
5. Under **Test Users**, click **Add Users** and add your Gmail address (required while the app is in testing mode).
6. Save and complete the wizard.

### 3. Create OAuth 2.0 Credentials
1. Navigate to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth client ID**.
3. Select Application type: **Desktop App**.
4. Set Name: `API C2C Client`.
5. Click **Create**, then click **Download JSON**.
6. Save the downloaded file as **`credentials.json`** in the root directory of this project (`d:/Projects/1/credentials.json`).
   *(Alternatively, copy `client_id` and `client_secret` from the JSON and paste them into your `.env` file as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`).*

---

## Authenticating & Sending Live Emails

### 1. Start the Server
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Open the Dashboard at: [http://localhost:8000](http://localhost:8000)

### 2. Connect Your Gmail Account
1. Look at the top right of the Web Dashboard header banner.
2. Click the **"Connect Gmail"** button.
3. A Google sign-in window will open in your browser. Log in with your Gmail account and click **Allow / Continue** to grant permission.
4. Once completed, the dashboard header will display `🟢 Gmail: your-email@gmail.com`.
5. Your local OAuth token is securely saved to `data/gmail_token.json` (gitignored).

### 3. Enable Live Sending (`DRY_RUN=false`)
1. By default, `DRY_RUN=true` is enabled for safe demonstration without sending actual emails.
2. To send real emails, edit your `.env` file:
   ```env
   DRY_RUN=false
   ```
3. Restart or reload the application. The header badge will now show `🟢 DRY_RUN=false (LIVE SENDING)`.

### 4. Send an Application & Verify Delivery
1. In the Web Dashboard, upload a candidate resume PDF (e.g. `data/resumes/Ankit_Jaiswal_Python_Developer.pdf`).
2. Click **"Discover & Filter LinkedIn C2C Posts"** or paste a custom LinkedIn post.
3. On any job in the table, click **"Customise & Send"**:
   - The application truthful AI customizer tailors the resume.
   - An ATS-compliant PDF resume is compiled with ReportLab.
   - A personalized outreach email is drafted and the PDF is attached.
   - When `DRY_RUN=false`, the email is delivered through your Gmail account.
   - You will see a confirmation alert: `✅ SENT - Gmail API confirmed! (Message ID: ...)`
4. **Verify in Gmail**:
   - Open your browser and go to [Gmail](https://mail.google.com).
   - Check your **Sent** folder (`Gmail > Sent`).
   - You will see the outreach email sent to the recruiter with the generated PDF resume attached!

---

## Status Lifecycle & UI Indicators

The application strictly tracks every submission and prevents duplicate outreach:
- `🟢 SENT - Gmail API confirmed`: Successfully delivered via Gmail API with confirmed message ID.
- `🟡 DRY RUN - not sent`: Validated and drafted in safe mode (`DRY_RUN=true`); email was not sent.
- `🔴 FAILED - email not sent`: Submission failed (e.g. Gmail unauthenticated, invalid email, or API error).
- `⚪ Skipped (Duplicate)`: Deduplication engine prevented re-applying to an already contacted recruiter/job.

---

## Running the Automated Demonstration Script

To execute the complete pipeline non-interactively:

```bash
python scripts/generate_evidence.py
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web User Dashboard |
| `GET` | `/health` | Service health status and environment check |
| `POST` | `/resume/upload` | Uploads PDF resume, parses candidate, detects title, generates query |
| `POST` | `/linkedin/search` | Discovers & filters past 24h C2C LinkedIn posts |
| `GET` | `/jobs` | Lists all discovered & normalized jobs |
| `GET` | `/jobs/{id}` | Retrieves specific job record details |
| `POST` | `/jobs/{id}/process` | Runs AI resume customization & PDF generation |
| `POST` | `/jobs/{id}/send` | Validates, attaches resume, and sends outreach email |
| `GET` | `/submissions` | Lists all submission tracking records |
| `GET` | `/download/resume/{filename}` | Downloads generated ATS PDF resume |

---

## Automated Test Suite

Run unit and integration tests with coverage:

```bash
pytest -v --cov=app --cov-report=term-missing
```

### Coverage Report Summary

```text
Name                            Stmts   Miss  Cover
---------------------------------------------------
app/config/settings.py             38      0   100%
app/database/models.py             68      0   100%
app/database/repository.py         75      3    96%
app/gmail/drafts.py                29      1    97%
app/linkedin/filters.py            60     10    83%
app/linkedin/scraper.py            79      8    90%
app/linkedin/search.py             60     10    83%
app/main.py                       119     26    78%
app/resume/analyzer.py             46      8    83%
app/resume/customizer.py           22      0   100%
app/resume/parser.py              244     39    84%
app/resume/pdf_generator.py       125      3    98%
app/services/deduplication.py      17      0   100%
app/services/pipeline.py          120     18    85%
app/services/tracking.py           33      2    94%
app/utils/logger.py                35      4    89%
---------------------------------------------------
TOTAL                            1551    270    83%
======================= 32 passed in 8.32s ========================
```

---

## Evidence Artifacts

The system includes complete verifiable evidence cards in the `evidence/` directory:

1. `evidence/01_resume_upload.png` — Resume upload, parsing, primary title detection
2. `evidence/02_linkedin_search.png` — LinkedIn search execution and 24h C2C filtering
3. `evidence/03_extracted_job.png` — Normalized job & recruiter record
4. `evidence/04_ai_resume.png` — Truthful AI customization & match scoring
5. `evidence/05_generated_pdf.png` — ATS PDF resume generation (ReportLab)
6. `evidence/06_gmail_email.png` & `06_gmail_email.txt` — Structured Gmail email body
7. `evidence/07_submission_tracking.png` — Dual database & CSV tracking with duplicate prevention

---

## Security & Reliability Guardrails

- **Zero-Hallucination AI**: The customizer strictly preserves original experience, companies, degrees, and dates.
- **Safe Mode (`DRY_RUN=true`)**: Real emails are never sent during testing/development unless explicitly disabled.
- **Credential Protection**: Tokens and passwords are never logged; `.env` and session tokens are strictly git-ignored.
- **Isolated Browser Sessions**: Playwright session cookies persist in `data/linkedin_session.json` without hardcoded credentials.
- **Fault-Tolerant Execution**: A single failed job does not halt the pipeline; detailed error reasons are recorded in both SQLite and CSV logs.
