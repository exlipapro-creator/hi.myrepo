#!/bin/bash
# ============================================================================
# hi.myrepo — Frontend Vercel Deployment Script
# ============================================================================
# Prerequisites:
#   1. Vercel CLI installed: npm install -g vercel
#   2. Logged in to Vercel: vercel login
#   3. Backend deployed and verified at Railway
#
# Usage:
#   cd frontend
#   bash ../scripts/deploy-frontend.sh
# ============================================================================

set -e

echo "============================================"
echo "hi.myrepo Frontend Deployment to Vercel"
echo "============================================"

# Check prerequisites
if ! command -v vercel &> /dev/null; then
    echo "ERROR: Vercel CLI not found. Install: npm install -g vercel"
    exit 1
fi

# Navigate to frontend directory
cd "$(dirname "$0")/../frontend" || exit 1

echo ""
echo "Step 1: Setting VITE_API_BASE_URL..."
echo "Backend URL: https://hi-myrepo-backend-production.up.railway.app"
echo ""

# Deploy to Vercel with environment variable
echo "Step 2: Deploying to Vercel (production)..."
vercel --prod \
  -e VITE_API_BASE_URL=https://hi-myrepo-backend-production.up.railway.app \
  --yes

echo ""
echo "============================================"
echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Note the Vercel URL from the output above"
echo "2. Set FRONTEND_ORIGIN in Railway to the Vercel URL"
echo "3. Verify CORS: curl -I https://<vercel-url> from the frontend"
echo "============================================"
