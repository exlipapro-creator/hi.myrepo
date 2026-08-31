"""
hi.myrepo - FastAPI Application Entry Point

The control plane for developer operations.
Event-driven architecture — the UI does not own system state.
"""

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
    else:
        logger.warning(
            "Database not available — running in degraded mode",
            hint="Set DATABASE_URL in .env",
        )
    yield
    # Shutdown: close connections
    await db_manager.close()
    logger.info("hi.myrepo shutting down")


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

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
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

    # Health check (unauthenticated)
    @app.get("/health")
    @limiter.exempt
    async def health_check():
        db_healthy = await db_manager.health_check()
        return {
            "status": "healthy" if db_healthy else "degraded",
            "database": "connected" if db_healthy else "disconnected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "0.1.0",
        }

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

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(projects_router, prefix="/api/v1/projects", tags=["Projects"])
    app.include_router(events_router, prefix="/api/v1/events", tags=["Events"])
    app.include_router(incidents_router, prefix="/api/v1/incidents", tags=["Incidents"])
    app.include_router(gateway_router, prefix="/v1", tags=["AI Gateway"])
    app.include_router(runbooks_router, prefix="/api/v1/runbooks", tags=["Runbooks"])
    app.include_router(telemetry_router, prefix="/api/v1/telemetry", tags=["Telemetry"])
    app.include_router(audit_router, prefix="/api/v1/audit", tags=["Audit Logs"])
    app.include_router(memory_router, prefix="/api/v1/memory", tags=["Memory"])

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
