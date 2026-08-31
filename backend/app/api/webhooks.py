"""
hi.myrepo - Webhook Ingestion

Hardened webhook endpoints for external service integration.

Requirements:
- Signature verification where supported
- Replay protection via idempotency keys
- Payload normalization into the event spine
- Project association
- Audit logging

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

# Replay protection: store recent webhook IDs in memory
# In production, use Redis or a database table
_seen_webhook_ids: dict[str, datetime] = {}
_MAX_SEEN_IDS = 10_000
_REPLAY_WINDOW_SECONDS = 300  # 5 minutes


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
    """
    # Read body for signature verification
    body = await request.body()

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
    """
    body = await request.body()

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
    """
    body = await request.body()

    # Replay protection using content hash
    content_hash = hashlib.sha256(body).hexdigest()[:16]
    delivery_id = f"custom:{project_slug}:{content_hash}"

    if _check_replay(delivery_id):
        return {"status": "ignored", "reason": "duplicate_delivery"}

    # Verify custom webhook secret if configured
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

    # Resolve project by slug
    project_id = await _resolve_project_from_name(project_slug)

    if not project_id:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    # Allow caller to specify event type, default to ERROR_DETECTED
    event_type = payload.pop("event_type", "ERROR_DETECTED")
    severity = payload.pop("severity", "medium")

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
