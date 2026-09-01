# hi.myrepo — Internal Inventory

**Date:** 2026-09-01
**Commits:** 10 on `main`
**Tests:** 349 passing
**Working tree:** Clean

---

## Component Inventory

| Component | File(s) | State | Proven? | External Dep | Human Config | Risk |
|-----------|---------|-------|---------|--------------|--------------|------|
| Event Spine | `events/spine.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Fingerprinting | `events/fingerprinting.py` | IMPLEMENTED | ✅ TESTED | None | None | None |
| Incident Engine | `incidents/engine.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Council | `council/engine.py` | IMPLEMENTED | ✅ TESTED | None (deterministic) | None | No live AI |
| AI Gateway | `gateway/ai_gateway.py` | IMPLEMENTED | ✅ TESTED | Supabase + AI key | API_KEY | No live provider |
| Policy Engine | `policy/engine.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Runbook Engine | `runbooks/engine.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Verification | `verification/engine.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Memory | `memory/engine.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Auth | `security/auth.py` | IMPLEMENTED | ✅ TESTED | None | JWT_SECRET | None |
| SSRF | `security/ssrf.py` | IMPLEMENTED | ✅ TESTED | None | None | None |
| Telemetry | `telemetry/receiver.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Pipeline | `pipeline/orchestrator.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| API Routes (14) | `api/*.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Frontend (9 views) | `frontend/src/` | IMPLEMENTED | ✅ BUILD | Vercel | Deploy | None |
| Workers | `workers/` | IMPLEMENTED | ✅ TESTED | GitHub Actions | Secrets | None |
| Database | `database/models.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Migrations | `alembic/` | IMPLEMENTED | ✅ TESTED | Supabase | Run upgrade | None |
| Seeds | `database/seeds.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Config | `core/config.py` | IMPLEMENTED | ✅ TESTED | None | .env | None |
| Docker | `Dockerfile`, `docker-compose.yml` | IMPLEMENTED | ✅ BUILD | None | None | None |
| Health | `main.py /health` | IMPLEMENTED | ✅ TESTED | None | None | None |
| Readiness | `main.py /ready` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Auth UI | `views/Auth.jsx` | IMPLEMENTED | ✅ BUILD | Backend | Deploy | None |
| Webhooks | `api/webhooks.py` | IMPLEMENTED | ✅ TESTED | GitHub | WEBHOOK_SECRET | In-memory replay |
| Monitored Targets | `api/monitored_targets.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Deployments | `api/deployments.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Incident Detail | `api/incident_detail.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Audit | `api/audit.py` | IMPLEMENTED | ✅ TESTED | Supabase | DATABASE_URL | None |
| Self-Monitoring | — | NOT ACTIVE | ❌ | Supabase | Deploy + register | Requires deployment |

---

## External Dependencies

| Dependency | Purpose | Free Tier | Human Action |
|------------|---------|-----------|--------------|
| Supabase | PostgreSQL database | Yes (500MB) | Create project |
| Gemini/OpenAI/Groq | AI provider | Yes (limited) | Get API key |
| Vercel | Frontend hosting | Yes | Deploy |
| Render | Backend hosting | Yes | Deploy |
| GitHub Actions | Heartbeat worker | Yes (2000 min/mo) | Configure secrets |

---

## Known Limitations

1. **In-memory replay protection** — Webhook replay IDs stored in Python dict, lost on restart. Safe for single-instance. Would need Redis for multi-instance.
2. **In-memory rate limiting** — Telemetry rate limits per-process. Safe for single-instance.
3. **Council is deterministic** — No live AI provider calls. Operates on context data patterns.
4. **No Telegram notifications** — Architecture supports it, not implemented.
5. **No capability-scoped telemetry tokens** — Current auth is project-level.

---

## Human Configuration Required

| # | Action | Blocking? |
|---|--------|-----------|
| 1 | Create Supabase project | YES — nothing works without DB |
| 2 | Set DATABASE_URL in .env | YES — nothing works without DB |
| 3 | Generate JWT_SECRET | YES — auth fails with default |
| 4 | Generate APP_SECRET_KEY | YES — startup warning with default |
| 5 | Configure AI API key | NO — system works without AI |
| 6 | Run alembic upgrade head | YES — no tables without migration |
| 7 | Start backend | YES — can't verify without running |
| 8 | Register first user | YES — can't test auth without user |
| 9 | Create first project | YES — can't test without project |
| 10 | Deploy frontend | NO — dev mode works locally |
| 11 | Deploy backend | NO — local works for testing |
| 12 | Configure GitHub webhook | NO — optional for v1 |
| 13 | Register hi.myrepo as own project | NO — after deployment |
