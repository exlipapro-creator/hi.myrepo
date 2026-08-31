# hi.myrepo — Human Configuration Checklist

This document contains the exact steps a human must perform to configure hi.myrepo for production.
Every step that can be automated has been automated. These steps require external account access.

---

## STEP 1: Create Supabase Project

**WHERE:** https://supabase.com

**WHAT TO DO:**
1. Click "New Project"
2. Organization: Create new or select existing
3. Project name: `hi-myrepo`
4. Database password: Generate a strong password (save it)
5. Region: Choose closest to your users
6. Click "Create new project"
7. Wait for project to be ready (~2 minutes)

**HOW TO VERIFY:** Project dashboard shows "Healthy" status

**COMMON FAILURE:** Supabase free tier limit reached — use a different organization

---

## STEP 2: Get Database Credentials

**WHERE:** Supabase Dashboard → Project Settings → Database → Connection string

**WHAT TO DO:**
1. Go to Project Settings → Database
2. Under "Connection string", find "URI"
3. Copy the full connection string
4. It looks like: `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`

**WHERE TO PUT IT:** `.env` file as `DATABASE_URL`

**HOW TO VERIFY:**
```bash
cd backend
DATABASE_URL="your-connection-string" python -c "
import asyncio
from app.database.connection import db_manager
asyncio.run(db_manager.health_check())
print('Database OK')
"
```

**EXPECTED RESULT:** Prints "Database OK"

**COMMON FAILURE:** Wrong password — reset in Supabase dashboard

---

## STEP 3: Generate Secrets

**WHERE:** Your terminal

**WHAT TO DO:**
```bash
# Generate JWT secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate app secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**WHERE TO PUT IT:** `.env` file as `JWT_SECRET` and `APP_SECRET_KEY`

**COMMON FAILURE:** Using default "change-me" values — system will warn at startup

---

## STEP 4: Configure AI Provider

**WHERE:** At least one of:
- Google AI Studio: https://aistudio.google.com/apikey
- OpenAI: https://platform.openai.com/api-keys
- Groq: https://console.groq.com/keys

**WHAT TO DO (example for Gemini):**
1. Go to Google AI Studio
2. Click "Create API Key"
3. Copy the key

**WHERE TO PUT IT:** `.env` file as `GEMINI_API_KEY`

**HOW TO VERIFY:**
```bash
cd backend
GEMINI_API_KEY="your-key" python -c "
from app.core.config import get_settings
s = get_settings()
print('Available providers:', s.available_ai_providers)
"
```

**EXPECTED RESULT:** Shows `['gemini']`

**COMMON FAILURE:** API key not activated — wait 5 minutes after creation

---

## STEP 5: Run Database Migrations

**WHERE:** Backend directory

**WHAT TO DO:**
```bash
cd backend
alembic upgrade head
```

**HOW TO VERIFY:**
```bash
cd backend
alembic current
```

**EXPECTED RESULT:** Shows `32d24d105027 (head)`

**COMMON FAILURE:** Connection refused — check DATABASE_URL and Supabase IP allowlist

---

## STEP 6: Start Backend

**WHERE:** Backend directory

**WHAT TO DO:**
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**HOW TO VERIFY:**
```bash
curl http://localhost:8000/ready
```

**EXPECTED RESULT:**
```json
{
  "status": "ready",
  "checks": {
    "database": "connected",
    "configuration": "valid",
    "ai_providers": ["gemini"]
  }
}
```

**COMMON FAILURE:** "Database not available" — check DATABASE_URL format

---

## STEP 7: Register First User

**WHERE:** Backend API or Swagger UI

**WHAT TO DO:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "you@example.com",
    "password": "your-secure-password-123",
    "full_name": "Your Name",
    "organization_name": "My Organization"
  }'
```

**HOW TO VERIFY:** Response contains `access_token`

**COMMON FAILURE:** "User already exists" — use a different email

---

## STEP 8: Create First Project

**WHERE:** Backend API

**WHAT TO DO:**
```bash
# Use the token from Step 7
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hi.myrepo",
    "slug": "hi-myrepo",
    "description": "Self-monitoring control plane",
    "repository_url": "https://github.com/YOUR_USERNAME/hi.myrepo"
  }'
```

**HOW TO VERIFY:** Response contains project `id`

---

## STEP 9: Install Frontend Dependencies

**WHERE:** Frontend directory

**WHAT TO DO:**
```bash
cd frontend
npm install
```

**HOW TO VERIFY:**
```bash
ls node_modules/.package-lock.json
```

**EXPECTED RESULT:** File exists

---

## STEP 10: Start Frontend Dev Server

**WHERE:** Frontend directory

**WHAT TO DO:**
```bash
cd frontend
npm run dev
```

**HOW TO VERIFY:** Open http://localhost:3000 — should show login page

**EXPECTED RESULT:** Dark-themed login/register form

---

## STEP 11: Configure GitHub Webhook

**WHERE:** GitHub repo → Settings → Webhooks → Add webhook

**WHAT TO DO:**
1. Payload URL: `https://YOUR_BACKEND_URL/webhooks/github`
2. Content type: `application/json`
3. Secret: Set `GITHUB_WEBHOOK_SECRET` in `.env` to the same value
4. Events: Select "Deployments", "Push", "Check runs"
5. Click "Add webhook"

**HOW TO VERIFY:** Push a commit — should see events in the Event Explorer

**COMMON FAILURE:** Webhook URL unreachable — check backend deployment

---

## STEP 12: Deploy to Production

**WHERE:** Vercel (frontend) + Render (backend)

**WHAT TO DO:**

### Frontend (Vercel)
1. Push to GitHub
2. Go to vercel.com → New Project
3. Import your GitHub repo
4. Framework: Vite
5. Root directory: `frontend`
6. Deploy

### Backend (Render)
1. Go to render.com → New Web Service
2. Connect GitHub repo
3. Root directory: `backend`
4. Runtime: Python
5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
7. Add environment variables from `.env`
8. Deploy

**HOW TO VERIFY:**
- Frontend: Open Vercel URL → login page
- Backend: `curl https://YOUR_BACKEND_URL/ready`

---

## STEP 13: Configure Production Environment

**WHERE:** Render service → Environment

**WHAT TO DO:** Set these environment variables:
- `DATABASE_URL` — from Supabase
- `JWT_SECRET` — from Step 3
- `APP_SECRET_KEY` — from Step 3
- `GEMINI_API_KEY` (or OPENAI/GROQ)
- `APP_ENV=production`
- `APP_DEBUG=false`
- `FRONTEND_ORIGIN=https://YOUR_VERCEL_URL`

**HOW TO VERIFY:** `curl https://YOUR_BACKEND_URL/ready` returns `"status": "ready"`

---

## STEP 14: Register hi.myrepo as Its Own Project

**WHERE:** Backend API

**WHAT TO DO:** After deployment, register hi.myrepo to monitor itself:
```bash
curl -X POST https://YOUR_BACKEND_URL/api/v1/projects \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hi.myrepo",
    "slug": "hi-myrepo-self",
    "description": "Self-monitoring",
    "repository_url": "https://github.com/YOUR_USERNAME/hi.myrepo"
  }'
```

Then add monitored targets:
```bash
curl -X POST https://YOUR_BACKEND_URL/api/v1/monitored-targets \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJECT_ID_FROM_ABOVE",
    "name": "API Health",
    "url": "https://YOUR_BACKEND_URL/ready",
    "expected_status": 200,
    "interval_seconds": 900
  }'
```

**HOW TO VERIFY:** Heartbeat events appear in Event Explorer

---

## VERIFICATION CHECKLIST

After all steps, verify:

- [ ] `GET /ready` returns `"status": "ready"`
- [ ] Login works at frontend
- [ ] Projects list shows hi.myrepo
- [ ] Events API returns events
- [ ] Heartbeat worker runs (check GitHub Actions)
- [ ] Webhook receives GitHub events
- [ ] AI Gateway responds (if provider configured)

---

## COMMON ISSUES

| Issue | Cause | Fix |
|-------|-------|-----|
| "Database not available" | Wrong DATABASE_URL | Check Supabase connection string |
| "JWT_SECRET is default" | Using "change-me" | Generate new secret |
| 401 on all API calls | No auth token | Register a user first |
| Webhook not received | URL wrong or firewall | Check Render service URL |
| AI provider fails | No API key | Configure at least one provider |
| Frontend shows blank | Backend unreachable | Check CORS and backend URL |
