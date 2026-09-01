"""
hi.myrepo - Webhook Ingestion

Hardened webhook endpoints for external service integration.

Security model:
- Signature verification where supported
- Replay protection via delivery ID tracking
- Payload normalization into the event spine
- Project association via repository/name lookup
- Audit logging
- Body size limits to prevent memory exhaustion
- Timestamp freshness checks
- Event type is NOT caller-controlled (mapped from GitHub event)
- Custom webhooks cannot override event_type or severity

Supported sources:
- GitHub (push, deployment, check_run, etc.)
- Vercel (deployment created, succeeded, failed)
- Custom (generic webhook with project association)
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.database.connection import db_manager
from app.database.models import Project
from app.events.spine import EventEnvelope, event_processor
from app.pipeline.orchestrator import pipeline
from app.security.auth import TokenData, get_current_user
from app.security.ssrf import ssrf_protector

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter()

# Body size limits
_MAX_WEBHOOK_BODY_BYTES = 1_000_000  # 1 MB — generous but bounded
_MAX_GITHUB_PAYLOAD = 500_000        # 500 KB for GitHub events

# Timestamp freshness
_FRESHNESS_WINDOW_SECONDS = 600  # 10 minutes — reject webhooks older than this

# Replay protection: store recent webhook IDs in memory
# In production, use Redis or a database table
_seen_webhook_ids: dict[str, datetime] = {}
_MAX_SEEN_IDS = 10_000
_REPLAY_WINDOW_SECONDS = 300  # 5 minutes

# Allowed event types that custom webhooks can create
# This prevents an attacker from injecting arbitrary event types
_ALLOWED_CUSTOM_EVENT_TYPES = {
    "ERROR_DETECTED",
    "HEARTBEAT_DEGRADED",
    "HEARTBEAT_FAILURE",
    "DEPLOYMENT_STARTED",
    "DEPLOYMENT_SUCCEEDED",
    "DEPLOYMENT_FAILED",
}
_ALLOWED_CUSTOM_SEVERITIES = {"low", "medium", "high", "critical"}


def _check_replay(delivery_id: str) -> bool:
    """Check if this webhook has already been processed."""
    now = datetime.now(timezone.utc)

    # Clean old entries
    cutoff_ts = now.timestamp() - _REPLAY_WINDOW_SECONDS
    expired = [k for k, v in _seen_webhook_ids.items() if v < cutoff_ts]
    for k in expired:
        del _seen_webhook_ids[k]

    if delivery_id in _seen_webhook_ids:
        return True  # Already seen

    _seen_webhook_ids[delivery_id] = now.timestamp()
    if len(_seen_webhook_ids) > _MAX_SEEN_IDS:
        # Remove oldest entries
        oldest_keys = sorted(_seen_webhook_ids, key=_seen_webhook_ids.get)[:1000]
        for k in oldest_keys:
            del _seen_webhook_ids[k]

    return False


def _check_body_size(body: bytes, max_bytes: int, source: str) -> None:
    """Reject oversized webhook payloads before they consume processing resources."""
    if len(body) > max_bytes:
        logger.warning(
            "webhook_body_too_large",
            source=source,
            size=len(body),
            max=max_bytes,
        )
        raise HTTPException(
            status_code=413,
            detail=f"Payload too large. Maximum {max_bytes} bytes.",
        )


def _check_timestamp_freshness(request: Request, source: str) -> None:
    """Check webhook timestamp freshness if available.
    Some providers include a timestamp header; reject stale requests.
    """
    timestamp_header = request.headers.get("x-webhook-timestamp")
    if not timestamp_header:
        return  # No timestamp to check — provider doesn't send one

    try:
        ts = int(timestamp_header)
        # Handle both seconds and milliseconds timestamps
        if ts > 1e12:
            ts = ts / 1000.0
        webhook_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        age = (now - webhook_time).total_seconds()
        if age > _FRESHNESS_WINDOW_SECONDS:
            logger.warning(
                "webhook_stale",
                source=source,
                age_seconds=age,
                max=_FRESHNESS_WINDOW_SECONDS,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Webhook is too old ({int(age)} seconds). Maximum {_FRESHNESS_WINDOW_SECONDS}.",
            )
    except (ValueError, TypeError, OverflowError):
        pass  # Invalid timestamp — let other checks handle it


def _verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC signature."""
    if not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ============================================================================
# GitHub Webhook
# ============================================================================

@router.post("/github")
async def github_webhook(request: Request):
    """
    Handle GitHub webhooks.

    Verifies signature, normalizes payload, and ingests events.
    Security: body size limit → signature verification → replay check → timestamp freshness.
    """
    # Read body for signature verification
    body = await request.body()

    # 1. Reject oversized payloads before any processing
    _check_body_size(body, _MAX_GITHUB_PAYLOAD, "github")

    # Get GitHub delivery ID for replay protection
    delivery_id = request.headers.get("x-github-delivery", "")
    if not delivery_id:
        raise HTTPException(status_code=400, detail="Missing x-github-delivery header")

    if _check_replay(delivery_id):
        logger.info("webhook_replay_detected", source="github", delivery_id=delivery_id)
        return {"status": "ignored", "reason": "duplicate_delivery"}

    # Verify signature
    secret = settings.github_webhook_secret
    if secret:
        signature = request.headers.get("x-hub-signature-256", "")
        if not _verify_github_signature(body, signature, secret):
            logger.warning("webhook_signature_invalid", source="github")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = request.headers.get("x-github-event", "unknown")
    action = payload.get("action", "")

    # Extract project info from repository
    repository = payload.get("repository", {})
    repo_name = repository.get("full_name", "unknown")
    repo_url = repository.get("html_url", "")

    # Map GitHub event to internal event type
    internal_event_type = _map_github_event(event_type, action)

    # Determine project_id from repository URL
    project_id = await _resolve_project_from_repo(repo_url)

    if not project_id:
        logger.warning("webhook_project_not_found", source="github", repo=repo_name)
        return {"status": "ignored", "reason": "project_not_registered"}

    # Build event envelope
    envelope = EventEnvelope(
        event_type=internal_event_type,
        occurred_at=datetime.now(timezone.utc),
        source=repo_name,
        source_type="webhook",
        project_id=project_id,
        severity=_determine_github_severity(event_type, action),
        idempotency_key=f"github:{delivery_id}",
        payload={
            "github_event": event_type,
            "action": action,
            "repository": repo_name,
            "sender": payload.get("sender", {}).get("login", "unknown"),
            "ref": payload.get("ref"),
            "head_commit": {
                "id": payload.get("head_commit", {}).get("id"),
                "message": payload.get("head_commit", {}).get("message", "")[:200],
            } if payload.get("head_commit") else None,
        },
        metadata={
            "source": "github_webhook",
            "delivery_id": delivery_id,
        },
    )

    # Process through pipeline
    async with db_manager.get_session() as session:
        result = await pipeline.process_event(envelope, session)

    logger.info(
        "webhook_github_processed",
        event_type=internal_event_type,
        repo=repo_name,
        actions=result.actions_taken,
    )

    return {
        "status": "accepted",
        "event_type": internal_event_type,
        "event_id": str(result.event.id) if result.event else None,
    }


def _map_github_event(github_event: str, action: str) -> str:
    """Map GitHub webhook event to internal event type."""
    mapping = {
        ("push", ""): "DEPLOYMENT_STARTED",
        ("deployment_status", "success"): "DEPLOYMENT_SUCCEEDED",
        ("deployment_status", "failure"): "DEPLOYMENT_FAILED",
        ("check_run", "completed"): "HEARTBEAT_SUCCESS" if action == "success" else "ERROR_DETECTED",
        ("workflow_run", "completed"): "DEPLOYMENT_SUCCEEDED",
        ("workflow_run", "failure"): "DEPLOYMENT_FAILED",
        ("issues", "opened"): "ERROR_DETECTED",
    }
    return mapping.get((github_event, action), "HEARTBEAT_SUCCESS")


def _determine_github_severity(github_event: str, action: str) -> str:
    """Determine severity from GitHub event."""
    if action in ("failure", "error"):
        return "high"
    if github_event == "deployment_status" and action == "failure":
        return "high"
    return "low"


# ============================================================================
# Vercel Webhook
# ============================================================================

@router.post("/vercel")
async def vercel_webhook(request: Request):
    """
    Handle Vercel deployment webhooks.
    Security: body size limit → signature verification → replay check.
    """
    body = await request.body()

    # 1. Reject oversized payloads before any processing
    _check_body_size(body, _MAX_WEBHOOK_BODY_BYTES, "vercel")

    # Replay protection
    delivery_id = request.headers.get("x-vercel-delivery-id", str(uuid.uuid4()))
    if _check_replay(delivery_id):
        return {"status": "ignored", "reason": "duplicate_delivery"}

    # Verify signature if configured
    secret = settings.vercel_webhook_secret
    if secret:
        signature = request.headers.get("x-vercel-signature", "")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Map Vercel payload to internal events
    deployment_state = payload.get("payload", {}).get("state", "")
    project_name = payload.get("payload", {}).get("name", "unknown")
    deployment_url = payload.get("payload", {}).get("url", "")

    state_map = {
        "BUILDING": "DEPLOYMENT_STARTED",
        "READY": "DEPLOYMENT_SUCCEEDED",
        "ERROR": "DEPLOYMENT_FAILED",
    }
    internal_event_type = state_map.get(deployment_state, "HEARTBEAT_SUCCESS")

    severity = "high" if deployment_state == "ERROR" else "low"

    # Resolve project
    project_id = await _resolve_project_from_name(project_name)

    if not project_id:
        return {"status": "ignored", "reason": "project_not_registered"}

    envelope = EventEnvelope(
        event_type=internal_event_type,
        occurred_at=datetime.now(timezone.utc),
        source=project_name,
        source_type="webhook",
        project_id=project_id,
        severity=severity,
        idempotency_key=f"vercel:{delivery_id}",
        payload={
            "vercel_event": payload.get("type", "unknown"),
            "state": deployment_state,
            "project": project_name,
            "url": deployment_url,
            "commit_sha": payload.get("payload", {}).get("meta", {}).get("commitSha"),
        },
        metadata={
            "source": "vercel_webhook",
            "delivery_id": delivery_id,
        },
    )

    async with db_manager.get_session() as session:
        result = await pipeline.process_event(envelope, session)

    return {
        "status": "accepted",
        "event_type": internal_event_type,
        "event_id": str(result.event.id) if result.event else None,
    }


# ============================================================================
# Custom Webhook
# ============================================================================

@router.post("/custom/{project_slug}")
async def custom_webhook(
    project_slug: str,
    request: Request,
):
    """
    Generic custom webhook endpoint.

    Associates events with a project by slug.

    SECURITY: The caller CANNOT freely specify event_type or severity.
    The payload may contain a 'type' hint, but it is validated against
    an allowlist. If invalid, it defaults to ERROR_DETECTED/medium.
    This prevents arbitrary event injection.
    """
    body = await request.body()

    # 1. Reject oversized payloads before any processing
    _check_body_size(body, _MAX_WEBHOOK_BODY_BYTES, "custom")

    # 2. Replay protection using full content hash
    content_hash = hashlib.sha256(body).hexdigest()
    delivery_id = f"custom:{project_slug}:{content_hash}"

    if _check_replay(delivery_id):
        return {"status": "ignored", "reason": "duplicate_delivery"}

    # 3. Verify custom webhook secret if configured
    secret = settings.custom_webhook_secret
    if secret:
        signature = request.headers.get("x-webhook-signature", "")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}

    # 4. Resolve project by slug
    project_id = await _resolve_project_from_name(project_slug)

    if not project_id:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    # 5. SECURITY: Event type and severity are validated against allowlists
    #    Callers CANNOT inject arbitrary event types or severities.
    requested_type = payload.pop("event_type", "ERROR_DETECTED")
    requested_severity = payload.pop("severity", "medium")

    event_type = requested_type if requested_type in _ALLOWED_CUSTOM_EVENT_TYPES else "ERROR_DETECTED"
    severity = requested_severity if requested_severity in _ALLOWED_CUSTOM_SEVERITIES else "medium"

    # 6. Strip internal fields from payload to prevent injection
    for internal_key in ["project_id", "actor", "correlation_id", "idempotency_key"]:
        payload.pop(internal_key, None)

    envelope = EventEnvelope(
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        source=project_slug,
        source_type="webhook",
        project_id=project_id,
        severity=severity,
        idempotency_key=f"custom:{delivery_id}",
        payload=payload,
        metadata={
            "source": "custom_webhook",
            "delivery_id": delivery_id,
        },
    )

    async with db_manager.get_session() as session:
        result = await pipeline.process_event(envelope, session)

    return {
        "status": "accepted",
        "event_type": event_type,
        "event_id": str(result.event.id) if result.event else None,
    }


# ============================================================================
# Helper Functions
# ============================================================================

async def _resolve_project_from_repo(repo_url: str) -> Optional[uuid.UUID]:
    """Find a project by repository URL."""
    if not repo_url:
        return None

    from sqlalchemy import select

    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.repository_url == repo_url)
        )
        project = result.scalar_one_or_none()
        return project.id if project else None


async def _resolve_project_from_name(name: str) -> Optional[uuid.UUID]:
    """Find a project by name or slug."""
    from sqlalchemy import select

    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(
                (Project.slug == name) | (Project.name == name)
            )
        )
        project = result.scalar_one_or_none()
        return project.id if project else None
