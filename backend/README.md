# CampusOps Backend — $0 Gemini Mode

## Quick start (no Google APIs needed for first run)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set GEMINI_API_KEY and set MOCK_MODE=true for testing without Google
# get key: https://aistudio.google.com/apikey
uvicorn app.main:app --reload --port 8000
```

Test:
```bash
curl http://localhost:8000/
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"MACS wants to conduct a Python workshop for 80 students next Saturday"}'
```

## With real Google APIs
1. Google Cloud Console -> New Project -> Enable Gmail API, Forms API, Sheets API
2. OAuth consent -> Create OAuth Client ID (Desktop) -> Download credentials.json to backend/credentials.json
3. python scripts/auth_google.py  # opens browser, generates token.json
4. Set MOCK_MODE=false in .env, restart server.

## Endpoints
- GET / 
- POST /chat
- GET /events, GET /events/{id}
- POST /events/{id}/approve
