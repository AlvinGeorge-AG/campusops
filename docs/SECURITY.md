# Security — Decentralized Drive + Brevo

## Model
- **Rooms:** Single source `ROOM_SHEET_ID` (admin Google Sheet, `Rooms!A:H` `Room,Capacity,Date,Start,End,Available,Booked By`). Clubs have `reader` share, not owner. Daily reset keeps `date >= today`.
- **Forms/Sheets/Posters:** Per-club Drive isolation via `token_{org}.json`. Admin never reads club Drive files — only event metadata (`form_link/sheet_link` URLs) stored in `events.db` (`org` indexed). Revoke via `myaccount.google.com/permissions`.
- **Email:** Brevo `sib-api-v3-sdk` (`FROM_EMAIL` per club or env) — no Gmail send quota. Announcement now via Brevo (was Gmail `gmail.send`) for reliability.

## Secrets
- `backend/.env` contains `JWT_SECRET`, `BREVO_API_KEY`, `GEMINI_API_KEY`, `ROOM_SHEET_ID` — set `git rm --cached .env` and inject via Vault/SSM in prod.
- `backend/token_*.json` per club — `backend/.gitignore` covers.

## RBAC
- JWT `HttpOnly` cookie + `Authorization: Bearer` fallback, `exp` 60m, `role` claim. `require_role('admin')` on `approve/reset`. `TEST_CLUB` bypass via `is_sandbox`.
- `Dashboard` `GET /events?scope=all|mine` server-filtered (`app/state.py:list_events(org,scope_all)`).
