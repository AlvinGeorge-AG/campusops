# CampusOps — AI Event Operations Agent

> **Describe your event. CampusOps runs the ops — you just decide.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](backend/requirements.txt)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688.svg)](https://fastapi.tiangolo.com)
[![Strands Agents](https://img.shields.io/badge/Strands%20Agents-1.53.0-orange.svg)](https://github.com/strands-agents/sdk-python)
[![Track: Everyday Agents](https://img.shields.io/badge/Track-Everyday%20Agents-purple.svg)](HACKATHON-README.md)

CampusOps is an **AI event operations agent** built with the **Strands Agents SDK** and **Gemini**. It turns a natural-language request like *"FOSS MEC wants a GIT workshop for 80 students next Saturday 2pm–4pm"* into a complete operational workflow — room discovery, permission letters, registration forms, announcements and monitoring — while keeping humans in control of approvals.

*Built for the [AWS Agents for Humans Hackathon](HACKATHON-README.md) — **Everyday Agents** track.*

---

## ✨ Demo

- **Video (5 min max):** `https://youtu.be/LRXyYXjvQ48`
- **Live demo:** *Not yet deployed — runs locally. Planned: Bedrock AgentCore + Vercel/Render.*
- **Slides / Story:** See [`CampsOps-System-Design.md`](CampsOps-System-Design.md)

---

## 🎯 Problem & Solution

Organizing a campus event takes **3–5 hours** of fragmented work: check rooms, write permission emails, create Google Forms/Sheets, send announcements, track registrations, send reminders.

**Traditional:** organizer manually coordinates Gmail + Forms + Sheets + room ledger.
**CampusOps:** organizer sends one sentence → agent does the work → human approves only when authorization is required.

```
User: "MACS Python workshop for 80 next Saturday 2pm-4pm"
  ↓
CampusOps Agent
  ├── check_room_availability  → Google Sheets (Bookings ledger)
  ├── book_room_slot           → atomic lock (DB + Sheet)
  ├── generate_permission_letter + generate_onfoot_letter → PDF + draft
  ├── [human: edit & send to Principal]
  ├── [human: Principal approves]
  ├── create_registration_form → Google Forms + linked Sheet
  ├── send_announcement        → Gmail/Brevo
  └── get_registration_count   → polling every 60s
```

Design principle: **The agent should do the work, not merely explain how to do the work.**

---

## 🚀 Features

- **Natural-language intake** with date/time resolution (`next Saturday` → `YYYY-MM-DD` via `TODAY`)
- **Time-aware room booking** — `Room | Date | Start | End` ledger with overlap detection, atomic `book_room_slot`, alternatives on conflict
- **High-quality letters** — institution-aware templates per `OrgSettings` (Principal + On-foot), editable before sending
- **Human-in-the-loop** — `DRAFT → PENDING_APPROVAL → LIVE → CLOSED` state machine; drafts never auto-send
- **Dynamic Google Forms** — `text | paragraph | multiple_choice | checkbox | file_upload` fields, linked response Sheet with headers, Drive folder for uploads
- **Announcements** — via Gmail/Brevo to configured recipients after approval
- **Proactive monitoring** — `R_current / R_expected < 0.4 && T < 2d → propose reminder draft`
- **Deterministic fast-path** — if `date + start + end` provided, bypass LLM for <500ms room+letter path
- **Multi-tenant** — per-club `OrgSettings` + per-club `token_{org}.json` Drive isolation or central Drive mode

---

## 🏗️ Architecture

```
                         User (Event Organizer)
                                   │
                                   ▼
                         CampusOps Agent
                      (Strands Agents SDK + Gemini 3.5 Flash Lite)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        Room Tools         Registration Tools     Communication Tools
   check_room_availability  create_registration_form  draft_permission_email
   book_room_slot           get_registration_count     send_announcement
              │                    │                    │
              ▼                    ▼                    ▼
       Google Sheets          Google Forms           Gmail / Brevo
       (RoomInventory +       (Form + linked         (permission PDFs,
        Bookings ledger)       response Sheet)         announcements)
              │                    │
              └─────────┬──────────┘
                        ▼
                   Event State (SQLite)
                   id, org, title, date, room, status,
                   form_id, sheet_id, registrant_count
                        │
                        ▼
                   Human Approval Boundary
              (club edits → principal approves)
```

- **Current:** Single flat agent (intentionally — lower complexity, easier debugging, faster demo)
- **Planned:** `AgentCore Runtime + Memory` for deployed persistence; future multi-agent (`Event | Communication | Logistics`)

See [`CampsOps-System-Design.md`](CampsOps-System-Design.md) for full 50-section design doc and [`docs/`](docs/) for admin/club guides.

---

## 🧰 Tech Stack

| Layer | Tech |
|-------|------|
| Agent | `strands-agents==1.53.0`, `strands-agents-tools==0.8.6`, `Gemini 3.5 Flash Lite` (`google-genai`) |
| Backend | `FastAPI==0.141.1`, `uvicorn==0.52.4`, `pydantic==2.13.4` |
| Auth | `python-jose`, `passlib[bcrypt]`, `slowapi` (rate limit) |
| Google | `google-api-python-client`, `google-auth-oauthlib`, Sheets/Forms/Gmail/Drive |
| Email | `sib-api-v3-sdk` (Brevo) |
| PDF | `reportlab` |
| DB | SQLite (WAL) — `events`, `org_settings`, `users`, `room_bookings` |
| Docs | `CampsOps-System-Design.md`, `docs/CLUB_GUIDE.md`, `docs/ADMIN_LOGIN.md`, `docs/SECURITY.md` |

---

## 📁 Project Structure

```
CampsOps/
├── backend/
│   ├── app/
│   │   ├── agent.py          # Strands agent + system prompt
│   │   ├── main.py           # FastAPI, /chat, /approve, auth, polling
│   │   ├── models.py         # Event, OrgSettings, FieldModel
│   │   ├── state.py          # SQLite CRUD + room_bookings ledger
│   │   ├── config.py         # env / CENTRAL_DRIVE / per-org token paths
│   │   ├── pdf.py            # permission PDF generation
│   │   ├── google/auth.py    # per-org OAuth credentials
│   │   └── tools/
│   │       ├── room.py       # check + book (2-sheet format)
│   │       ├── letters.py    # permission / onfoot templates
│   │       ├── forms.py      # dynamic Forms + Sheet + Drive folder
│   │       ├── announcement.py
│   │       └── registrations.py
│   ├── scripts/
│   │   ├── auth_google.py
│   │   ├── create_room_sheet.py
│   │   └── reset_rooms_sheet.py
│   ├── data/rooms_production.csv
│   ├── requirements.txt
│   └── .env.example
├── docs/
│   ├── CLUB_GUIDE.md
│   ├── ADMIN_LOGIN.md
│   └── SECURITY.md
├── CampsOps-System-Design.md
├── LICENSE (MIT)
└── README.md
```

---

## ⚡ Quick Start

### 1. Prerequisites

- Python 3.12+, `pip`
- Gemini API key — https://aistudio.google.com/apikey
- (Optional for real Google) Google Cloud project with **Gmail API, Forms API, Sheets API, Drive API** enabled

### 2. Local mock run (no Google OAuth needed)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env:
# GEMINI_API_KEY=your_key_here
# MOCK_MODE=true
uvicorn app.main:app --reload --port 8000
```

Test:

```bash
curl http://localhost:8000/
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT>" \
  -d '{"message":"FOSS MEC wants to conduct a GIT workshop for 50 students","date":"2026-09-06","start_time":"15:30","end_time":"16:30"}'
```

Login first: `POST /auth/login` or `POST /auth/sandbox-login` (TEST_CLUB, no password). Use returned `access_token`.

### 3. With real Google APIs

```bash
# 1. Google Cloud Console → New Project → Enable Gmail, Forms, Sheets, Drive APIs
# 2. OAuth consent → Create OAuth Client (Desktop) → Download credentials.json → backend/credentials.json
python scripts/auth_google.py          # opens browser, writes token.json
# or per-club: python scripts/auth_google.py --org "FOSS MEC" → token_foss_mec.json

# 3. Create room sheet (optional, for live ledger)
python scripts/create_room_sheet.py

# 4. .env: set MOCK_MODE=false, ROOM_SHEET_ID=<sheet_id>, restart
uvicorn app.main:app --reload --port 8000
```

---

## 🔧 Configuration

Copy `backend/.env.example` → `backend/.env`:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL_ID=gemini-3.5-flash-lite
GEMINI_TIMEOUT_MS=45000

GOOGLE_CREDENTIALS_PATH=./credentials.json
GOOGLE_TOKEN_PATH=./token.json
MOCK_MODE=false
ROOM_SHEET_ID=
FORM_HEADER_IMAGE_URL=

POLLER_ENABLED=true
POLL_INTERVAL_SECONDS=60

JWT_SECRET=change-me-to-32-random-chars
SANDBOX_ORG=TEST_CLUB
FRONTEND_ORIGIN=http://localhost:5173

# Per-org overrides live in Settings UI (institution_name, faculty_email, etc.)
FACULTY_EMAIL=faculty@example.com
ANNOUNCEMENT_RECIPIENTS=students@example.com
```

Per-club settings are stored in `org_settings` table and edited via `Settings` UI — env values are fallbacks only.

---

## 🔌 API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/` | — | Health |
| `POST` | `/auth/login` | — | `{email,password}` → JWT |
| `POST` | `/auth/sandbox-login` | — | TEST_CLUB open login |
| `GET` | `/auth/me` | JWT | Current user |
| `POST` | `/chat` | club | Create/continue event (1-chat heart) |
| `GET` | `/events` | JWT | `?scope=all|mine` |
| `GET` | `/events/{id}` | JWT | Single event |
| `POST` | `/events/{id}/send-permission-email` | club (owner) | Send draft to principal |
| `POST` | `/events/{id}/approve` | admin | Approve → creates Form + announcement |
| `GET` | `/rooms/availability` | JWT | `?date=&capacity=&start_time=&end_time=` |
| `GET` | `/auth/google/status?org=` | JWT | Drive connection status |
| `GET` | `/auth/google/url?org=` | JWT | OAuth URL |

Rate limits: `10/min` login, `20/min` chat, `100/min` global.

---

## 🧪 Testing

```bash
# Unit: tools in isolation
python -m pytest  # (add tests under backend/tests/)

# Integration: chat → tool → Google API → state
curl -X POST http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"Create a Python workshop for 80","date":"2026-09-12","start_time":"14:00","end_time":"16:00"}'

# Failure cases
# - No room: capacity 2000 on booked date → 409 with alternatives
# - Missing date → agent asks for date
# - Invalid time → 400 invalid_time_range
```

---

## 🔒 Security

- JWT (`HS256`, `JWT_SECRET` rotate in prod), `bcrypt` passwords, `HttpOnly` cookie + `Authorization` header
- RBAC: `admin` vs `club` vs `TEST_CLUB` sandbox (open, isolated)
- Per-club Drive isolation via `token_{org}.json` (`drive.file` + `forms.body` + `spreadsheets`)
- `CENTRAL_DRIVE=true` default — admin owns central Drive, shares per-club folders `writer` to club Gmail
- `slowapi` rate limiting, strict Pydantic validators, CORS allowlist
- Secrets are **never committed** — see [`.gitignore`](.gitignore) (`credentials.json`, `token*.json`, `.env`, `*.db`)

See [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 🗺️ Roadmap

- [x] Natural-language intake + time-aware room ledger
- [x] Permission + on-foot letters with PDFs
- [x] Dynamic Forms + linked Sheets + announcements
- [x] Human approval boundary + state machine
- [ ] Deploy to **Bedrock AgentCore** (Runtime + Memory)
- [ ] Slack/Discord + Calendar + PDF summary reports
- [ ] Multi-agent (Event / Comms / Logistics) via agent-as-tool

---

## 📄 License

MIT — see [LICENSE](LICENSE). Required for hackathon submission (MIT or Apache).

---

## 🙏 Acknowledgments

- [Strands Agents SDK](https://github.com/strands-agents/sdk-python) — AWS
- Govt. Model Engineering College — clubs FOSS MEC, MACS, IEEE
- Gemini via Google AI Studio

---

**CampusOps — From one sentence to event-ready.** *You describe it, CampusOps does the ops.*
