#!/bin/bash
# ============================================================================
# Railway Deployment Verification Script
# ============================================================================
# Usage: ./scripts/verify-railway.sh https://your-app.up.railway.app
# ============================================================================

set -e

RAILWAY_URL="${1:?Usage: $0 <railway-url>}"
PASS=0
FAIL=0

echo "========================================================"
echo "RAILWAY DEPLOYMENT VERIFICATION"
echo "========================================================"
echo "Target: $RAILWAY_URL"
echo "Timestamp: $(date -u '+%Y-%m-%dT%H:%M:%S UTC')"
echo ""

# Test 1: Health check
echo "--- Test 1: GET /health ---"
RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 15 "$RAILWAY_URL/health" 2>&1)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)
if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✅ HTTP $HTTP_CODE"
    echo "  Body: $BODY"
    PASS=$((PASS + 1))
else
    echo "  ❌ HTTP $HTTP_CODE (expected 200)"
    echo "  Body: $BODY"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 2: Root endpoint
echo "--- Test 2: GET / ---"
RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 15 "$RAILWAY_URL/" 2>&1)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)
if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✅ HTTP $HTTP_CODE"
    echo "  Body: $BODY"
    PASS=$((PASS + 1))
else
    echo "  ❌ HTTP $HTTP_CODE (expected 200)"
    echo "  Body: $BODY"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 3: Readiness check
echo "--- Test 3: GET /ready ---"
RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 15 "$RAILWAY_URL/ready" 2>&1)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)
if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✅ HTTP $HTTP_CODE"
    echo "  Body: $BODY"
    PASS=$((PASS + 1))
else
    echo "  ❌ HTTP $HTTP_CODE (expected 200)"
    echo "  Body: $BODY"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 4: HTTPS certificate
echo "--- Test 4: HTTPS certificate ---"
CERT_INFO=$(curl -s -I --connect-timeout 10 --max-time 15 "$RAILWAY_URL/health" 2>&1 | head -1)
if echo "$CERT_INFO" | grep -q "200"; then
    echo "  ✅ HTTPS certificate valid"
    PASS=$((PASS + 1))
else
    echo "  ❌ HTTPS certificate issue: $CERT_INFO"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 5: Authentication required
echo "--- Test 5: GET /api/v1/events (should require auth) ---"
RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 15 "$RAILWAY_URL/api/v1/events" 2>&1)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "403" ]; then
    echo "  ✅ HTTP $HTTP_CODE (auth required)"
    PASS=$((PASS + 1))
else
    echo "  ❌ HTTP $HTTP_CODE (expected 401/403)"
    FAIL=$((FAIL + 1))
fi
echo ""

# Summary
echo "========================================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================================"

if [ $FAIL -eq 0 ]; then
    echo "✅ All checks passed!"
    exit 0
else
    echo "❌ Some checks failed"
    exit 1
fi
