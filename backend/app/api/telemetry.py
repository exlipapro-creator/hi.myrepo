"""
hi.myrepo - Telemetry API

Zero-SDK telemetry ingestion via navigator.sendBeacon().
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import Project
from app.security.auth import TokenData, get_current_user
from app.telemetry.receiver import TelemetryBatch, TelemetryPayload, telemetry_receiver

router = APIRouter()


@router.post("/ingest", status_code=202)
async def ingest_telemetry(
    batch: TelemetryBatch,
    user: TokenData = Depends(get_current_user),
):
    """Ingest a batch of telemetry events from clients.

    Designed for navigator.sendBeacon() — fire-and-forget semantics.
    Returns 202 Accepted immediately.
    """
    # Verify project exists
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == batch.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    # Process the batch with database session for persistence
    async with db_manager.get_session() as session:
        summary = await telemetry_receiver.receive_batch(batch, session=session)

    return {
        "status": "accepted",
        "processed": summary["processed"],
        "errors": summary["errors"],
    }


@router.post("/error", status_code=202)
async def ingest_error(
    error: TelemetryPayload,
    project_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Ingest a single error telemetry event."""
    batch = TelemetryBatch(
        events=[error],
        project_id=project_id,
    )
    async with db_manager.get_session() as session:
        summary = await telemetry_receiver.receive_batch(batch, session=session)
    return {
        "status": "accepted",
        "processed": summary["processed"],
    }
