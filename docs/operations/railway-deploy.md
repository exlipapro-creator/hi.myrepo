# Railway Deployment Guide — hi.myrepo Backend

## Prerequisites

- GitHub account with access to `exlipapro-creator/hi.myrepo`
- Railway account (https://railway.app — free tier available)
- Supabase DATABASE_URL (already configured)
- GEMINI_API_KEY (already configured)

## Step 1: Create Railway Project

1. Go to https://railway.app/new
2. Click **"Deploy from GitHub repo"**
3. Authorize Railway to access your GitHub account
4. Select **`exlipapro-creator/hi.myrepo`**
5. Railway will detect the monorepo structure

## Step 2: Configure Service

1. Railway will create a service. Click on it.
2. Go to **Settings** tab
3. Under **Build**:
   - **Root Directory:** `backend`
   - **Dockerfile Path:** `Dockerfile`
4. Under **Deploy**:
   - Railway auto-detects the Dockerfile
   - No start command override needed (Dockerfile CMD handles it)

## Step 3: Set Environment Variables

Go to **Variables** tab and add these:

```
APP_ENV=production
APP_DEBUG=false
DATABASE_URL=<your Supabase connection string>
JWT_SECRET=<your production JWT secret>
APP_SECRET_KEY=<your production app secret key>
GEMINI_API_KEY=<your Gemini API key>
FRONTEND_ORIGIN=
APP_PORT=8000
```

**Important:**
- Copy the exact values from your existing `.env` file
- `DATABASE_URL` must use the pooler endpoint (port 6543) for external connections
- `FRONTEND_ORIGIN` can be left empty for now (CORS will default to `https://hi.myrepo.vercel.app`)

## Step 4: Deploy

1. Railway will automatically trigger a deployment after variable changes
2. Go to **Deployments** tab to watch the build
3. Wait for "Success" status

## Step 5: Get Public URL

1. Go to **Settings** tab
2. Under **Networking**, click **"Generate Domain"**
3. Railway will create a URL like: `hi-myrepo-backend.up.railway.app`
4. Copy this URL

## Step 6: Verify

Run these commands with your Railway URL:

```bash
# Health check
curl -i https://<your-railway-url>/health

# Root endpoint
curl -i https://<your-railway-url>/

# Ready check
curl -i https://<your-railway-url>/ready
```

Expected results:
- `/health` → 200 with `{"status": "alive", ...}`
- `/` → 200 with `{"name": "hi.myrepo", ...}`
- `/ready` → 200 with `{"status": "ready", "checks": {"database": "connected", ...}}`

## Step 7: Test Authentication

```bash
# Register
curl -X POST https://<your-railway-url>/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpassword123","name":"Test User"}'

# Login
curl -X POST https://<your-railway-url>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpassword123"}'
```

## Troubleshooting

### Build fails
- Check that `backend/` is set as the root directory
- Verify the Dockerfile path is correct

### Database connection fails
- Ensure DATABASE_URL uses the pooler endpoint (port 6543)
- Verify the Supabase project is not paused
- Check that the database is accessible from Railway's IP ranges

### Seed loading shows 0
- Verify `backend/database/seeds/default_runbooks.json` exists
- Check application logs for seed-related warnings

### Health check fails
- Check application logs for startup errors
- Verify all environment variables are set
