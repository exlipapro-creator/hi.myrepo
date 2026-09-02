# hi.myrepo — Vercel Frontend Deployment Guide

## Prerequisites

- [Vercel account](https://vercel.com) (free tier works)
- Vercel CLI installed: `npm install -g vercel`
- Backend deployed and verified at Railway

## Step 1: Login to Vercel

```bash
vercel login
```

Follow the browser prompt to authenticate.

## Step 2: Deploy to Vercel

From the repository root:

```bash
cd frontend
vercel --prod \
  -e VITE_API_BASE_URL=https://hi-myrepo-backend-production.up.railway.app
```

When prompted:
- **Set up and deploy?** → Yes
- **Which scope?** → Your personal account
- **Link to existing project?** → No (create new)
- **Project name?** → `hi-myrepo-frontend` (or your preference)
- **Directory where code is located?** → `.` (current directory)

## Step 3: Note Your Vercel URL

After deployment, Vercel will output a URL like:
```
https://hi-myrepo-frontend.vercel.app
```

## Step 4: Configure CORS on Railway

Go to **Railway Dashboard → hi-myrepo-backend → Variables** and set:

```
FRONTEND_ORIGIN=https://hi-myrepo-frontend.vercel.app
```

This tells the backend to accept CORS requests from your Vercel frontend.

## Step 5: Verify

1. Open your Vercel URL in a browser
2. You should see the login/register page
3. Register a test account
4. Login — you should see the dashboard
5. Check browser DevTools → Network tab — API requests should go to `https://hi-myrepo-backend-production.up.railway.app`

## Environment Variables Summary

| Variable | Where | Value |
|----------|-------|-------|
| `VITE_API_BASE_URL` | Vercel | `https://hi-myrepo-backend-production.up.railway.app` |
| `FRONTEND_ORIGIN` | Railway | `https://<your-vercel-url>` |

## Troubleshooting

### CORS errors
- Ensure `FRONTEND_ORIGIN` is set in Railway to your exact Vercel URL
- No trailing slash
- Must match exactly (including `https://`)

### Blank page
- Check Vercel build logs for errors
- Ensure `VITE_API_BASE_URL` is set in Vercel environment variables

### API requests failing
- Open browser DevTools → Network tab
- Check if requests are going to the correct Railway URL
- Check for mixed-content errors (HTTP vs HTTPS)
