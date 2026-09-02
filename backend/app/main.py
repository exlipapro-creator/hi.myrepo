"""
hi.myrepo - FastAPI Application Entry Point

The control plane for developer operations.
Event-driven architecture — the UI does not own system state.
"""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.database.connection import db_manager

logger = structlog.get_logger()
settings = get_settings()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info(
        "hi.myrepo starting",
        env=settings.app_env.value,
        debug=settings.app_debug,
    )
    # Startup: verify database connectivity
    healthy = await db_manager.health_check()
    if healthy:
        logger.info("Database connection established")
        # Seed default data (runbooks, policies, providers)
        try:
            from app.database.seeds import run_all_seeds
            async with db_manager.get_session() as session:
                await run_all_seeds(session)
        except Exception as e:
            logger.warning("seed_error", error=str(e))
    else:
        logger.warning(
            "Database not available — running in degraded mode",
            hint="Set DATABASE_URL in .env",
        )

    # Validate configuration
    config_issues = _validate_config()
    if config_issues:
        for issue in config_issues:
            logger.warning("config_issue", issue=issue)
    else:
        logger.info("configuration_valid")

    # Warn about known limitations
    if settings.is_production:
        logger.warning(
            "known_limitation",
            component="webhook_replay",
            limitation="In-memory replay protection is lost on process restart",
            impact="Duplicate webhook delivery possible within 5-minute window after restart",
            mitigation="Safe for single-instance deployment. For multi-instance, use Redis.",
            documented_at="docs/audits/production-readiness.md",
        )

    yield
    # Shutdown: close connections
    await db_manager.close()
    logger.info("hi.myrepo shutting down")


def _validate_config() -> list[str]:
    """Validate required configuration. Returns list of issues (empty = valid)."""
    issues = []

    # JWT secret must not be default
    if settings.jwt_secret == "change-me":
        issues.append("JWT_SECRET is default value — generate a secure random string")

    # App secret key must not be default
    if settings.app_secret_key == "change-me":
        issues.append("APP_SECRET_KEY is default value — generate a secure random string")

    # Database URL should be set
    if not settings.database_url:
        issues.append("DATABASE_URL not configured")

    # In production, require at least one AI provider
    if settings.is_production and not settings.available_ai_providers:
        issues.append("No AI providers configured — set GEMINI_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY")

    # In production, CORS should not be wildcard
    if settings.is_production and not os.environ.get("FRONTEND_ORIGIN"):
        issues.append("FRONTEND_ORIGIN not set — CORS will default to https://hi.myrepo.vercel.app")

    return issues


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="hi.myrepo",
        description="Developer Operations Control Plane — Event-driven, AI-augmented incident management",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
    )

    # ── Middleware ────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS — strict in production, permissive in development
    if settings.app_debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        frontend_origin = os.environ.get("FRONTEND_ORIGIN", "")
        allowed_origins = [o.strip() for o in frontend_origin.split(",") if o.strip()]
        if not allowed_origins:
            allowed_origins = ["https://hi.myrepo.vercel.app"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    # Rate limiting middleware for API routes
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Apply rate limiting to API routes (not health/root/webhooks)
        path = request.url.path
        # Apply rate limiting to all API routes including AI gateway
        # Exempt: health (/health, /ready), root (/), webhooks (/webhooks)
        if path.startswith("/api/v1/") or path.startswith("/v1/"):
            key = f"{get_remote_address(request)}:{path.split('/')[3] if len(path.split('/')) > 3 else 'default'}"
            # Simple in-memory rate limiter (single-instance)
            import time
            now = time.time()
            window = 60  # 1-minute window
            max_requests = settings.rate_limit_per_minute
            
            # Initialize or clean up the rate limit store
            if not hasattr(app.state, "_rate_limits"):
                app.state._rate_limits = {}
            
            store = app.state._rate_limits
            # Clean old entries
            expired = [k for k, v in store.items() if now - v[0] > window]
            for k in expired:
                del store[k]
            
            if key in store:
                timestamps = store[key]
                # Remove entries outside the window
                timestamps = [t for t in timestamps if now - t < window]
                if len(timestamps) >= max_requests:
                    return JSONResponse(
                        status_code=429,
                        content={"error": "rate_limit_exceeded", "message": "Too many requests"},
                        headers={"Retry-After": str(window)},
                    )
                timestamps.append(now)
                store[key] = timestamps
            else:
                store[key] = [now]
        
        return await call_next(request)

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Security headers middleware
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    # Structured logging middleware
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        start = datetime.now(timezone.utc)
        response = await call_next(request)
        duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            request_id=getattr(request.state, "request_id", None),
        )
        return response

    # ── Global error handlers ────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    # ── Routes ───────────────────────────────────────────────────────────

    # ── Health endpoints (unauthenticated) ──────────────────────────────

    @app.get("/health")
    @limiter.exempt
    async def health_check():
        """Liveness probe — is the process alive?"""
        return {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "0.1.0",
        }

    @app.get("/ready")
    @limiter.exempt
    async def readiness_check():
        """Readiness probe — can the system serve traffic?"""
        checks = {}
        overall = "ready"

        # Database
        db_healthy = await db_manager.health_check()
        checks["database"] = "connected" if db_healthy else "disconnected"
        if not db_healthy:
            overall = "not_ready"

        # Configuration
        config_issues = _validate_config()
        checks["configuration"] = config_issues if config_issues else "valid"
        if config_issues:
            overall = "not_ready"

        # AI providers
        available_providers = settings.available_ai_providers
        checks["ai_providers"] = available_providers if available_providers else ["none_configured"]

        status_code = 200 if overall == "ready" else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": checks,
                "version": "0.1.0",
            },
        )

    @app.get("/")
    @limiter.exempt
    async def root():
        return {
            "name": "hi.myrepo",
            "description": "Developer Operations Control Plane",
            "version": "0.1.0",
            "docs": "/docs" if settings.app_debug else None,
        }

    # Register API routers
    from app.api.events import router as events_router
    from app.api.incidents import router as incidents_router
    from app.api.projects import router as projects_router
    from app.api.auth import router as auth_router
    from app.api.gateway import router as gateway_router
    from app.api.runbooks import router as runbooks_router
    from app.api.telemetry import router as telemetry_router
    from app.api.audit import router as audit_router
    from app.api.memory import router as memory_router
    from app.api.providers import router as providers_router

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(projects_router, prefix="/api/v1/projects", tags=["Projects"])
    app.include_router(events_router, prefix="/api/v1/events", tags=["Events"])
    app.include_router(incidents_router, prefix="/api/v1/incidents", tags=["Incidents"])
    app.include_router(gateway_router, prefix="/v1", tags=["AI Gateway"])
    app.include_router(providers_router, prefix="/api/v1/providers", tags=["AI Providers"])
    app.include_router(runbooks_router, prefix="/api/v1/runbooks", tags=["Runbooks"])
    app.include_router(telemetry_router, prefix="/api/v1/telemetry", tags=["Telemetry"])
    app.include_router(audit_router, prefix="/api/v1/audit", tags=["Audit Logs"])
    app.include_router(memory_router, prefix="/api/v1/memory", tags=["Memory"])

    # New routes
    from app.api.webhooks import router as webhooks_router
    from app.api.monitored_targets import router as targets_router
    from app.api.deployments import router as deployments_router
    from app.api.incident_detail import router as incident_detail_router

    app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(targets_router, prefix="/api/v1/monitored-targets", tags=["Monitored Targets"])
    app.include_router(deployments_router, prefix="/api/v1/deployments", tags=["Deployments"])
    app.include_router(incident_detail_router, prefix="/api/v1/incidents", tags=["Incident Detail"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
