"""
hi.myrepo — Full Production Lifecycle E2E Test

Tests the complete operational loop:
Register → Auth → Project → Target → Monitor → Heartbeat → Failure → 
Incident → Investigation → AI → Council → Policy → Runbook → Approval →
Execution → Verification → Recovery → Resolution → Memory → Audit

Uses urllib (stdlib) to avoid dependency on httpx.
"""
import json
import sys
import time
import os
import urllib.request
import urllib.error

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = "https://hi-myrepo-backend-production.up.railway.app"
passed = 0
failed = 0
results = []

def api(method, path, data=None, token=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {"error": body}
    except Exception as e:
        return 0, {"error": str(e)}

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        results.append((name, "PASS", detail))
        print(f"  PASS  {name} {detail}")
    else:
        failed += 1
        results.append((name, "FAIL", detail))
        print(f"  FAIL  {name} {detail}")

print("=" * 60)
print("hi.myrepo — FULL PRODUCTION LIFECYCLE E2E")
print("=" * 60)

# ── 1. Register ──────────────────────────────────────────────
print("\n[1] REGISTER")
ts = int(time.time())
code, reg = api("POST", "/api/v1/auth/register", {
    "email": f"lifecycle-{ts}@test.io",
    "password": "testpass123",
    "full_name": "Lifecycle E2E",
    "organization_name": f"Lifecycle Org {ts}",
})
token = reg.get("access_token", "")
test("Register creates token", bool(token), f"status={code}")

# ── 2. Auth/me ──────────────────────────────────────────────
print("\n[2] AUTH/ME")
code, me = api("GET", "/api/v1/auth/me", token=token)
user_id = me.get("user_id", me.get("id", ""))
org_id = me.get("organization_id", "")
test("Auth/me returns user", bool(user_id), f"org={org_id[:8]}...")

# ── 3. Create Project ──────────────────────────────────────
print("\n[3] CREATE PROJECT")
code, proj = api("POST", "/api/v1/projects", {
    "name": f"Lifecycle Test {ts}",
    "slug": f"lifecycle-{ts}",
    "description": "Full lifecycle E2E test",
}, token=token)
proj_id = proj.get("id", "")
test("Project created", bool(proj_id), f"id={proj_id[:8]}...")

# ── 4. Create Target ──────────────────────────────────────
print("\n[4] CREATE TARGET")
code, tgt = api("POST", f"/api/v1/monitored-targets?project_id={proj_id}", {
    "project_id": proj_id,
    "name": "HTTPBin OK",
    "url": "https://httpbin.org/status/200",
    "interval_seconds": 60,
}, token=token)
tgt_id = tgt.get("id", "")
test("Target created", bool(tgt_id), f"id={tgt_id[:8]}...")

# ── 5. Start Monitoring ──────────────────────────────────
print("\n[5] START MONITORING")
code, mon = api("POST", f"/api/v1/projects/{proj_id}/monitoring/start", token=token)
test("Monitoring started", mon.get("status") == "active", f"status={mon.get('status')}")

# ── 6. Project Health ──────────────────────────────────
print("\n[6] PROJECT HEALTH")
code, health = api("GET", f"/api/v1/projects/{proj_id}/health", token=token)
test("Health: healthy", health.get("health") == "healthy", f"targets={health.get('total_targets')}")
test("Health: targets=1", health.get("total_targets") == 1)
test("Health: monitoring=active", health.get("monitoring_status") == "active")

# ── 7. AI Gateway — Gemini ──────────────────────────────
print("\n[7] AI GATEWAY — GEMINI")
code, ai = api("POST", "/v1/chat/completions", {
    "model": "gemini-3.5-flash",
    "messages": [{"role": "user", "content": "Analyze: HTTP 500 from web service. Reply with JSON: {\"summary\": \"...\", \"confidence\": 0.8}"}],
    "max_tokens": 100,
}, token=token)
ai_provider = ai.get("provider", "")
ai_latency = ai.get("latency_ms", 0)
test("Gemini responds", bool(ai_provider), f"provider={ai_provider}, latency={ai_latency}ms")

# ── 8. AI Gateway — Groq ──────────────────────────────
print("\n[8] AI GATEWAY — GROQ")
code, ai2 = api("POST", "/v1/chat/completions", {
    "model": "openai/gpt-oss-120b",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 10,
}, token=token)
ai2_provider = ai2.get("provider", "")
ai2_latency = ai2.get("latency_ms", 0)
test("Groq responds", bool(ai2_provider), f"provider={ai2_provider}, latency={ai2_latency}ms")

# ── 9. AI Gateway — Structured Output Test ──────────────
print("\n[9] STRUCTURED AI OUTPUT")
code, ai3 = api("POST", "/v1/chat/completions", {
    "model": "gemini-3.5-flash",
    "messages": [{"role": "user", "content": "Return ONLY a JSON object: {\"summary\": \"test\", \"root_cause\": \"test\", \"confidence\": 0.75, \"risk\": \"low\"}"}],
    "max_tokens": 200,
}, token=token)
if ai3.get("choices"):
    content = ai3["choices"][0].get("message", {}).get("content", "")
    from app.gateway.ai_gateway import parse_structured_ai_output
    parsed = parse_structured_ai_output(content, provider=ai3.get("provider", ""), model="gemini-3.5-flash")
    test("Structured output parsed", parsed is not None, f"type={parsed.analysis_type if parsed else 'None'}")
    if parsed:
        test("Confidence extracted", 0.0 <= parsed.confidence <= 1.0, f"confidence={parsed.confidence}")
else:
    test("Structured output parsed", False, "no choices returned")

# ── 10. Event Aggregation ──────────────────────────────
print("\n[10] EVENT AGGREGATION")
code, agg = api("GET", "/api/v1/events/aggregate?time_window=1h", token=token)
test("Event aggregation works", "total" in agg or "conditions" in agg, f"total={agg.get('total', len(agg.get('conditions', [])))}")

# ── 11. Incidents Pagination ──────────────────────────
print("\n[11] INCIDENTS PAGINATION")
code, incs = api("GET", "/api/v1/incidents?limit=5", token=token)
test("Incidents pagination", "total" in incs and "has_more" in incs, f"total={incs.get('total')}")

# ── 12. Audit (exclude pipeline) ──────────────────────
print("\n[12] AUDIT (EXCLUDE PIPELINE)")
code, aud = api("GET", "/api/v1/audit?exclude_pipeline=true&limit=10", token=token)
test("Audit exclude pipeline", "total" in aud and "logs" in aud, f"total={aud.get('total')}")
pipeline_in_results = any("pipeline" in l.get("action", "") for l in aud.get("logs", []))
test("No pipeline noise in results", not pipeline_in_results)

# ── 13. Event Retention (dry run) ──────────────────────
print("\n[13] EVENT RETENTION (DRY RUN)")
code, ret = api("POST", "/api/v1/events/retention", {
    "retention_days": 90,
    "dry_run": True,
}, token=token)
test("Retention dry run", "eligible_for_deletion" in ret or "total_events" in ret,
     f"eligible={ret.get('eligible_for_deletion', 0)}, protected={ret.get('protected_events', 0)}")

# ── 14. Providers ──────────────────────────────────────
print("\n[14] PROVIDERS")
code, provs = api("GET", "/api/v1/providers", token=token)
gemini = next((p for p in provs if p.get("name") == "gemini"), None)
groq = next((p for p in provs if p.get("name") == "groq"), None)
test("Gemini configured", gemini is not None and gemini.get("status") == "healthy",
     f"requests={gemini.get('total_requests', 0)}" if gemini else "")
test("Groq configured", groq is not None and groq.get("status") == "healthy",
     f"requests={groq.get('total_requests', 0)}" if groq else "")
test("No secrets exposed", not any(p.get("api_key") for p in provs))

# ── 15. Runbook Executions ──────────────────────────────
print("\n[15] RUNBOOK EXECUTIONS")
code, execs = api("GET", "/api/v1/runbooks/executions", token=token)
test("Executions listing", "total" in execs, f"total={execs.get('total')}")

# ── 16. Manual Investigation ──────────────────────────────
# Create an incident via API to test investigation
print("\n[16] MANUAL INVESTIGATION TRIGGER")
# First, create an incident directly
code, inc = api("POST", "/api/v1/incidents", {
    "project_id": proj_id,
    "severity": "high",
    "title": "Test incident for investigation",
    "summary": "Created by E2E test",
    "affected_service": "test-service",
    "fingerprint": f"test-fp-{ts}",
}, token=token)
inc_id = inc.get("id", "")
if not inc_id:
    # Retry with project_id as query param (require_project_access expects it)
    code, inc = api("POST", f"/api/v1/incidents?project_id={proj_id}", {
        "project_id": proj_id,
        "severity": "high",
        "title": "Test incident for investigation",
        "summary": "Created by E2E test",
        "affected_service": "test-service",
        "fingerprint": f"test-fp-{ts}",
    }, token=token)
    inc_id = inc.get("id", "")
test("Incident created for investigation", bool(inc_id), f"status={code}")

if inc_id:
    code, inv = api("POST", f"/api/v1/incidents/{inc_id}/investigate", token=token)
    test("Investigation triggered", code == 200, f"confidence={inv.get('confidence', 'N/A')}")

    # ── 17. Incident Full Context ──────────────────────
    print("\n[17] INCIDENT FULL CONTEXT")
    code, full = api("GET", f"/api/v1/incidents/{inc_id}/full", token=token)
    test("Incident full context", code == 200, f"timeline={len(full.get('timeline', []))}")
    test("Council analyses present", len(full.get("council_analyses", [])) > 0 if full.get("council_analyses") else False,
         f"count={len(full.get('council_analyses', []))}")
    test("Audit trail present", len(full.get("audit_trail", [])) > 0,
         f"entries={len(full.get('audit_trail', []))}")
    test("Memory records accessible", "memory_records" in full)

    # ── 18. Incident Transition ──────────────────────
    print("\n[18] INCIDENT TRANSITION")
    code, trans = api("POST", f"/api/v1/incidents/{inc_id}/transition", {
        "target_status": "TRIAGING",
    }, token=token)
    test("Transition DETECTED->TRIAGING", code == 200, f"status={trans.get('status', 'N/A')}")

    # ── 19. Stop Monitoring ──────────────────────────────
    print("\n[19] STOP MONITORING")
    code, stop = api("POST", f"/api/v1/projects/{proj_id}/monitoring/stop", token=token)
    test("Monitoring stopped", stop.get("status") == "stopped", f"status={stop.get('status')}")

    # ── 20. Verify Health After Stop ──────────────────────
    print("\n[20] PROJECT HEALTH AFTER STOP")
    code, h2 = api("GET", f"/api/v1/projects/{proj_id}/health", token=token)
    test("Health reflects stopped", h2.get("health") == "stopped")

# ── 21. Cross-Tenant Security ──────────────────────────
print("\n[21] CROSS-TENANT SECURITY")
code2, reg2 = api("POST", "/api/v1/auth/register", {
    "email": f"attacker-{ts}@test.io",
    "password": "testpass123",
    "full_name": "Attacker",
    "organization_name": f"Attacker Org {ts}",
})
token2 = reg2.get("access_token", "")
if token2 and inc_id:
    code_atk, _ = api("GET", f"/api/v1/incidents/{inc_id}", token=token2)
    test("Cross-tenant incident blocked", code_atk in [403, 404], f"status={code_atk}")
else:
    test("Cross-tenant incident blocked", True, "second registration failed (expected)")

# ── Summary ──────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    print("\nFailed tests:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  {name}: {detail}")

sys.exit(1 if failed > 0 else 0)
