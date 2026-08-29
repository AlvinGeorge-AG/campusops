# Admin Login — Production Protocol

## Roles
- `admin` — full access: `POST /events/{id}/approve`, `POST /events/{id}/reset`, `GET /settings` (all), `POST /rooms/reset`, `GET /events?scope=all`.
- `club` — owner-only: `POST /chat`, `POST /events/{id}/send-permission-email` (own org), `PUT /settings/{org}` (own org), `GET /events?scope=mine|all` (all visible, mine filtered).
- `TEST_CLUB` (`is_sandbox=true`) — open, no password, same club permissions, for demos.

## Credentials (seeded)
```
admin@mec.ac.in / Admin@123
foss@mec.ac.in / Foss@123
macs@mec.ac.in / Macs@123
ieee@mec.ac.in / Ieee@123
testclub@mec.ac.in / test123 (also open via POST /auth/sandbox-login)
```
Change in production: `python -c "from app.state import create_user; from app.auth import hash_password; create_user('new@mec.ac.in','NEW CLUB','club',hash_password('Strong@123'))"`

## Flow
1. `POST /auth/login {email,password}` → `Set-Cookie: access_token=JWT HttpOnly; Path=/; Max-Age=3600` + `{access_token, user}`. Frontend stores `localStorage.access_token` fallback and `X-Org` header.
2. `GET /auth/me` validates JWT (`JWT_SECRET`, `JWT_ALGORITHM=HS256`, `JWT_EXP_MINUTES=60` in `backend/.env`). 401 → redirect `/login`.
3. `POST /auth/logout` clears cookie.
4. `POST /auth/google/init?org=FOSS%20MEC` (admin or owner) returns instructions to run `scripts/auth_google.py --org`.

## Per-Club Drive Isolation
- Each club runs `scripts/auth_google.py --org "CLUB"` once on server (needs `credentials.json`). Creates `backend/token_club.json` with `drive.file,forms.body,spreadsheets` scopes.
- `app/google/auth.py:get_credentials(org)` routes to `token_{slug}.json` via `app/config.py:google_token_path_for_org`.
- `app/tools/forms.py:265` uses club creds → files in club's Drive. Admin's `rooms_sheet` (`ROOM_SHEET_ID`) remains admin-owned, shared as `reader` to clubs.

## Security Checklist
- Rotate `JWT_SECRET` in `backend/.env` (32+ random chars), `BREVO_API_KEY`, `GEMINI_API_KEY` (were committed — rotate via Brevo/Gemini dashboards).
- `CORS` `FRONTEND_ORIGIN=http://localhost:5173` (comma separate prod origins), `allow_credentials=True`.
- Rate limit `slowapi` 10/min login, 20/min chat.
- `backend/.gitignore` ignores `token_*.json`, `events.db`, `.env`.
- Nightly `scripts/reset_rooms_sheet.py` cron `0 2 * * *` or in-app `_reset_loop` (24h) keeps `date >= today`.
