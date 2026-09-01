"""
hi.myrepo - AI Gateway API

OpenAI-compatible interface: /v1/chat/completions
Provider health, routing, and observability.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import AIProvider
from app.gateway.ai_gateway import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ai_gateway,
)
from app.security.auth import TokenData, get_current_user

router = APIRouter()


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    user: TokenData = Depends(get_current_user),
):
    """OpenAI-compatible chat completion endpoint with provider routing."""
    async with db_manager.get_session() as session:
        try:
            response = await ai_gateway.chat_completions(request, session)
            return response
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))


@router.get("/providers")
async def list_providers(
    user: TokenData = Depends(get_current_user),
):
    """Get AI provider health and status. Gracefully degrades if DB unavailable."""
    try:
        async with db_manager.get_session() as session:
            result = await session.execute(select(AIProvider))
            providers = result.scalars().all()

            return [
                {
                    "name": p.name,
                    "status": p.status,
                    "circuit_state": p.circuit_state,
                    "success_rate": p.success_rate,
                    "failure_rate": p.failure_rate,
                    "avg_latency_ms": p.avg_latency_ms,
                    "total_requests": p.total_requests,
                    "total_failures": p.total_failures,
                    "recent_429_count": p.recent_429_count,
                    "recent_timeout_count": p.recent_timeout_count,
                    "cooldown_until": p.cooldown_until.isoformat() if p.cooldown_until else None,
                    "capabilities": p.capabilities or [],
                    "models_available": p.models_available or [],
                }
                for p in providers
            ]
    except Exception:
        return []
