# Operations — Deployment Guide

## Zero-Budget Architecture

| Component | Hosting | Cost |
|-----------|---------|------|
| Frontend | Vercel (free tier) | $0 |
| Backend | Render (free tier) | $0 |
| Database | Supabase PostgreSQL (free tier) | $0 |
| Automation | GitHub Actions | $0 |

## Prerequisites

1. **Supabase Account** — Create at supabase.com
2. **GitHub Account** — For repository and Actions
3. **Vercel Account** — For frontend deployment
4. **Render Account** — For backend deployment

## Deployment Steps

### Step 1: Create Supabase Project

1. Go to supabase.com → New Project
2. Note the database connection string
3. Note the API URL and keys (anon + service role)

### Step 2: Configure Environment

Copy `.env.example` to `.env` and fill in:

```bash
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres
SUPABASE_URL=https://[REF].supabase.co
SUPABASE_ANON_KEY=[YOUR-ANON-KEY]
SUPABASE_SERVICE_ROLE_KEY=[YOUR-SERVICE-ROLE-KEY]
JWT_SECRET=[GENERATE-RANDOM-STRING]
APP_SECRET_KEY=[GENERATE-RANDOM-STRING]
```

### Step 3: Apply Database Migrations

```bash
cd backend
alembic upgrade head
```

### Step 4: Deploy Backend to Render

1. Connect GitHub repository to Render
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add all environment variables

### Step 5: Deploy Frontend to Vercel

1. Connect GitHub repository to Vercel
2. Set framework: Vite
3. Set root directory: `frontend`
4. Add environment variable: `VITE_API_URL=https://your-backend.onrender.com`

### Step 6: Configure GitHub Actions

Add secrets to your GitHub repository:
- `API_URL`: Your backend URL
- `API_TOKEN`: A valid auth token

## Self-Monitoring

hi.myrepo must monitor itself. Register hi.myrepo as one of its own projects:

1. Create a project via the API
2. Add monitored targets pointing to `/health`
3. The heartbeat worker will continuously check health
4. The control plane becomes its own first customer
