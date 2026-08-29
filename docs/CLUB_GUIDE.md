# CampusOps — Club Admin Guide (External)

Welcome, Club Admin! This guide is for **FOSS MEC, MACS MEC, IEEE MEC** (and `TEST_CLUB` sandbox). No dev jargon.

## 1) First Time Setup (Once per club)

1. **Get credentials from Admin:** `email` + `password` (e.g. `foss@mec.ac.in / Foss@123`). `TEST_CLUB` needs no password — click **Use TEST_CLUB sandbox**.
2. **Set your club details:** `Login → Settings` — institution, principal email, announcement recipients (comma-separated), chairperson & staff. Save. **No Drive setup needed** — central Drive creates per-club folders (`CampusOps/FOSS MEC/`) and shares to your club Gmail. `TEST_CLUB` works instantly.
3. **(Optional) Per-club Drive isolation:** If you want data in *your* Drive instead of central, ask Admin to run `python scripts/auth_google.py --org "YOUR CLUB"` and then `Settings → Connect Drive` via Google OAuth. Otherwise central Drive is default.

## 2) Create an Event (2 minutes)

1. `Dashboard → + New Event`
2. **Pick Date & Time** via date picker (required — prevents double-bookings) + `Start / End` time (24h). Also write a short sentence: *“FOSS MEC wants Java workshop for 50 students”* — headcount is extracted.
3. **Add form fields** (Name, Email, Year…), set `Speaker`, `Purpose`, toggle `Need on-foot letter?`
4. **Click Create → Show Draft Letter** — if the slot conflicts you’ll see a **clear error**: *“Elga booked 16:30-17:30 by MACS MEC — Try SDPK 17:30-18:30”* plus alternatives. Change date/time and retry — no silent fail.
5. **Review → Edit permission letter → Send to Principal (with PDFs)**. Check Inbox/Spam for principal.

## 3) After Principal Approves

- Admin clicks **Approve** in `Admin Queue`. The system:
  - Creates **Google Form + linked Sheet** in central Drive per-club folder and shares to your Gmail (link appears on event page)
  - Sends the **announcement** via Brevo to your recipient list after approval.
- **Registrations sync every 60s** to your Sheet; `Dashboard` count updates.

## 4) View Events

- `Dashboard` toggle: **All Events** (every club, MEC single-college) vs **My Events** (yours only). Admin sees all.
- Past bookings are auto-cleared daily at 02:00 — future events are kept.

## 5) Troubleshooting

- **“Invalid date”** — use the picker, format `YYYY-MM-DD`.
- **No email?** Check principal email in `Settings`, Spam, and Brevo sender verification.
- **Drive permission error?** Central Drive is default — no per-club Drive needed. If you use per-club isolation, re-run `python scripts/auth_google.py --org "YOUR CLUB"` or `Settings → Connect Drive`.

## 6) Security

- Central Drive per-club folders — admin owns Drive, shares per-club folders `writer` to your Gmail. Admin sees event metadata + folder ACLs, not your private files. Revoke via `myaccount.google.com/permissions` if per-club mode.
- `TEST_CLUB` is open for demos — don’t use it for real events.

Questions? Contact `admin@mec.ac.in`.
