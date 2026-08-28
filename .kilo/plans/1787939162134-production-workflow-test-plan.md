# Production Workflow Test Plan

## Objective
Run the full CampusOps backend workflow in production mode (`MOCK_MODE=false`) with real Google/Gemini APIs. Identify and fix any production issues.

## Prerequisites Verified
- `backend/.env`: exists, `MOCK_MODE=false`, `POLLER_ENABLED=true`, real `GEMINI_API_KEY`, `FACULTY_EMAIL=alvingeorge_@outlook.com`
- `backend/credentials.json`: exists (Google OAuth client)
- `backend/token.json`: exists (Google OAuth token)
- `backend/requirements.txt`: dependencies listed
- No `.venv` found at expected paths — must create or locate before running

## Step 1: Environment Setup
1. Locate or create Python virtual environment:
   - If `.venv` exists elsewhere, note its path
   - Otherwise create: `python3 -m venv .venv`
2. Activate and install deps:
   - `.venv/bin/pip install -r requirements.txt`
3. Verify `uvicorn` is installed and runnable

## Step 2: Server Startup
1. Start backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
2. Confirm health: `curl http://localhost:8000/`
3. Expected: `{"status":"ok","service":"CampusOps Backend","mock_mode":"false"}`

## Step 3: Full Workflow Test via `/chat`
Run the complete 1-chat workflow with a real event request.

### Test A: New Event Request
**POST** `/chat` with body:
```json
{
  "message": "FOSS MEC wants to conduct a Python Workshop for 50 students on 2026-09-20 from 3:30 PM to 5:00 PM in LH-302. Speaker is Dr. John Doe (Alumni, Google). Purpose: introduce Python fundamentals. Chairperson: Arthana Sreekesh. Staff: Aysha Fymin Majeed. Need on-foot publicity.",
  "start_time": "3:30 PM",
  "end_time": "5:00 PM",
  "speaker": "Dr. John Doe (Alumni, Google)",
  "purpose": "Introduce students to Python programming fundamentals and practical applications in data science.",
  "chairperson": "Arthana Sreekesh",
  "staff_in_charge": "Aysha Fymin Majeed",
  "need_onfoot": true
}
```

**Validate response contains:**
- `event_id` (non-null)
- `status` (should be `pending_approval`)
- `permission_letter` (non-empty, detailed)
- `onfoot_letter` (non-empty, since `need_onfoot=true`)
- `announcement_draft` (non-empty)

**Validate backend logs show:**
- Room check called (real or mock fallback)
- Room booking attempted
- Letters generated
- Event persisted to SQLite

### Test B: Form Creation with File Upload
**POST** `/events/{event_id}/form` with body:
```json
{
  "fields": [
    {"title": "Full Name", "type": "text", "required": true},
    {"title": "Email", "type": "text", "required": true},
    {"title": "Year", "type": "multiple_choice", "options": ["1st", "2nd", "3rd", "4th"], "required": true},
    {"title": "Resume", "type": "file_upload", "required": false},
    {"title": "Expectations", "type": "paragraph", "required": false}
  ]
}
```

**Validate response contains:**
- `form_link` (real Google Form URL, not mock)
- `sheet_link` (real Google Sheet URL)
- `upload_folder_link` (non-empty, Google Drive folder)

**Validate:**
- Form is actually accessible in browser
- Sheet exists and has headers

## Step 4: Direct Endpoint Tests

### Test C: Send Permission Email
**POST** `/events/{event_id}/send-permission-email` with empty body `{}`

**Validate response contains:**
- `sent: true`
- `message_id` (Gmail message ID)
- Email arrives at `alvingeorge_@outlook.com`

### Test D: Approve Event
**POST** `/events/{event_id}/approve` with body `{"approved": true}`

**Validate response:**
- Auto-resumes and creates form + announcement
- `event.status` becomes `live`
- `form_id` and `form_link` are set
- `announcement_sent` is true

### Test E: Registration Count
**GET** `/events/{event_id}/registrations`

**Validate response:**
- Returns count (may be 0 initially)
- `source` field present
- No errors

### Test F: Test Endpoints
**POST** `/test/email` — validate email draft with all metadata
**POST** `/test/form` — validate form with file_upload creates Drive folder
**POST** `/test/letter` — validate permission letter + announcement

## Step 5: Edge Cases
1. **Duplicate event creation**: POST `/chat` twice without `event_id` — should create separate events
2. **Edit and resend**: POST `/events/{id}/send-permission-email` with `edited_email` text
3. **Regenerate instruction**: POST with `regenerate_instruction: "make more formal"`
4. **Reset and retry**: POST `/events/{id}/reset` then re-approve
5. **Missing fields**: Form creation with empty `fields` array (should use defaults)

## Step 6: Production Issues to Watch For
1. **Google Forms API 400 on file_upload** — should now fallback to Drive folder + text field
2. **Gemini rate limit (15 req/min)** — if hit, wait 60s before retry
3. **OAuth token expiry** — if `token.json` is stale, flow will prompt for local server auth
4. **Sheet creation quota** — creating linked sheets costs API calls
5. **Announcement reuse** — after approval, announcement should reuse the draft with real form link

## Step 7: Bug Fix Protocol
If any test fails:
1. Capture full error from response + server logs
2. Fix the code in-place
3. Re-run the failing test
4. Re-run all subsequent tests to verify no regression

## Success Criteria
- All 6 main tests pass
- Real emails arrive at `alvingeorge_@outlook.com`
- Real Google Form + Sheet are created
- Drive folder created for file upload
- No unhandled exceptions in server logs
- Announcement correctly reuses draft with form link after approval
