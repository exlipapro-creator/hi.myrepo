"""
hi.myrepo - AI Provider Management API

Admin-only CRUD for AI provider configuration.
API keys are encrypted at rest and never returned in responses.

Security:
- Only admins can manage providers
- API keys are encrypted before persistence
- GET endpoints return safe metadata only
- Audit events are created for all mutations
- No secret leakage in responses, logs, or exceptions
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import AIProvider, AuditLog, ProviderStatus
from app.security.auth import (
    TokenData,
    get_current_user,
    require_role,
)
from app.security.encryption import (
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
    mask_secret,
)

router = APIRouter()

# Provider registry — supported providers and their required fields
PROVIDER_REGISTRY = {
    "gemini": {
        "name": "gemini",
        "display_name": "Google Gemini",
        "capabilities": ["text", "vision", "reasoning", "code", "long_context"],
        "models": [
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
        ],
        "env_var": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
    },
    "openai": {
        "name": "openai",
        "display_name": "OpenAI",
        "capabilities": ["text", "vision", "reasoning", "code", "structured_output"],
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "env_var": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
    },
    "groq": {
        "name": "groq",
        "display_name": "Groq",
        "capabilities": ["text", "speed", "code"],
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "env_var": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
    },
}


# ── Response Models ────────────────────────────────────────────────────

class ProviderResponse(BaseModel):
    """Safe provider metadata — never includes API keys."""
    id: str
    name: str
    display_name: str
    status: str
    is_configured: bool
    configured_at: Optional[str] = None
    key_last_four: Optional[str] = None
    capabilities: list[str]
    models_available: list[str]
    success_rate: float
    failure_rate: float
    avg_latency_ms: float
    total_requests: int
    total_failures: int
    circuit_state: str
    recent_429_count: int
    recent_timeout_count: int
    cooldown_until: Optional[str] = None
    base_url: Optional[str] = None


class ProviderCreate(BaseModel):
    """Request to add/update a provider configuration."""
    name: str = Field(..., description="Provider name (gemini, openai, groq)")
    api_key: str = Field(..., min_length=8, description="API key for the provider")
    models: Optional[list[str]] = Field(None, description="Override default model list")
    base_url: Optional[str] = Field(None, description="Override API base URL")


class ProviderUpdate(BaseModel):
    """Request to update provider configuration."""
    api_key: Optional[str] = Field(None, min_length=8, description="New API key (replaces existing)")
    models: Optional[list[str]] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None


# ── Helpers ────────────────────────────────────────────────────────────

def _provider_to_response(p: AIProvider, registry_entry: dict = None) -> ProviderResponse:
    """Convert a database AIProvider to a safe response model."""
    reg = registry_entry or PROVIDER_REGISTRY.get(p.name, {})

    # Check if API key exists (encrypted or from env)
    is_configured = bool(p.api_key_encrypted) if hasattr(p, 'api_key_encrypted') and p.api_key_encrypted else False
    key_last_four = None
    configured_at = None

    if is_configured and hasattr(p, 'api_key_encrypted') and p.api_key_encrypted:
        try:
            decrypted = decrypt_secret(p.api_key_encrypted)
            key_last_four = mask_secret(decrypted, visible_chars=4)[-4:] if decrypted else None
        except Exception:
            pass
        if hasattr(p, 'configured_at') and p.configured_at:
            configured_at = p.configured_at.isoformat()

    return ProviderResponse(
        id=str(p.id),
        name=p.name,
        display_name=reg.get("display_name", p.name.title()),
        status=p.status,
        is_configured=is_configured,
        configured_at=configured_at,
        key_last_four=key_last_four,
        capabilities=p.capabilities or [],
        models_available=p.models_available or [],
        success_rate=p.success_rate,
        failure_rate=p.failure_rate,
        avg_latency_ms=p.avg_latency_ms,
        total_requests=p.total_requests,
        total_failures=p.total_failures,
        circuit_state=p.circuit_state,
        recent_429_count=p.recent_429_count,
        recent_timeout_count=p.recent_timeout_count,
        cooldown_until=p.cooldown_until.isoformat() if p.cooldown_until else None,
        base_url=reg.get("base_url"),
    )


def _write_audit_log(
    session, action: str, user: TokenData,
    resource_id: str, details: dict, outcome: str = "success",
):
    """Write an audit log entry for provider mutations."""
    audit = AuditLog(
        id=uuid.uuid4(),
        action=action,
        actor_type="user",
        actor_id=user.user_id,
        resource_type="ai_provider",
        resource_id=resource_id,
        details={k: v for k, v in details.items() if k not in ("api_key", "secret")},
        outcome=outcome,
    )
    session.add(audit)


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    user: TokenData = Depends(get_current_user),
):
    """List all AI providers with safe metadata. No API keys returned."""
    async with db_manager.get_session() as session:
        result = await session.execute(select(AIProvider))
        providers = result.scalars().all()

        return [_provider_to_response(p) for p in providers]


@router.get("/{provider_name}", response_model=ProviderResponse)
async def get_provider(
    provider_name: str,
    user: TokenData = Depends(get_current_user),
):
    """Get a single provider's safe metadata."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(AIProvider).where(AIProvider.name == provider_name)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        return _provider_to_response(provider)


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_or_update_provider(
    req: ProviderCreate,
    user: TokenData = Depends(require_role("admin")),
):
    """Create or update an AI provider configuration. Admin only.

    API key is encrypted before persistence and never returned.
    """
    # Validate provider name against registry
    registry_entry = PROVIDER_REGISTRY.get(req.name.lower())
    if not registry_entry:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{req.name}'. Supported: {list(PROVIDER_REGISTRY.keys())}",
        )

    encrypted_key = encrypt_secret(req.api_key)

    async with db_manager.get_session() as session:
        # Check if provider already exists
        result = await session.execute(
            select(AIProvider).where(AIProvider.name == req.name.lower())
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing provider
            existing.api_key_encrypted = encrypted_key
            existing.configured_at = datetime.now(timezone.utc)
            if req.models:
                existing.models_available = req.models
            existing.status = ProviderStatus.HEALTHY
            provider = existing
            action = "provider_updated"
        else:
            # Create new provider
            provider = AIProvider(
                id=uuid.uuid4(),
                name=req.name.lower(),
                status=ProviderStatus.HEALTHY,
                api_key_encrypted=encrypted_key,
                configured_at=datetime.now(timezone.utc),
                capabilities=registry_entry["capabilities"],
                models_available=req.models or registry_entry["models"],
                circuit_state="closed",
                success_rate=1.0,
                failure_rate=0.0,
                avg_latency_ms=0.0,
                total_requests=0,
                total_failures=0,
                recent_429_count=0,
                recent_timeout_count=0,
            )
            session.add(provider)
            action = "provider_created"

        # Audit log — NEVER include the API key
        _write_audit_log(
            session, action, user,
            resource_id=str(provider.id),
            details={
                "provider_name": req.name,
                "has_api_key": True,
                "models": req.models or registry_entry["models"],
            },
        )

        await session.flush()
        return _provider_to_response(provider, registry_entry)


@router.patch("/{provider_name}", response_model=ProviderResponse)
async def update_provider(
    provider_name: str,
    req: ProviderUpdate,
    user: TokenData = Depends(require_role("admin")),
):
    """Update provider configuration. Admin only."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(AIProvider).where(AIProvider.name == provider_name.lower())
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        changes = {}

        if req.api_key is not None:
            provider.api_key_encrypted = encrypt_secret(req.api_key)
            provider.configured_at = datetime.now(timezone.utc)
            provider.status = ProviderStatus.HEALTHY
            changes["api_key_updated"] = True

        if req.models is not None:
            provider.models_available = req.models
            changes["models"] = req.models

        if req.base_url is not None:
            changes["base_url"] = req.base_url

        if req.is_active is not None:
            if req.is_active:
                provider.status = ProviderStatus.HEALTHY
                provider.circuit_state = "closed"
                provider.cooldown_until = None
            else:
                provider.status = ProviderStatus.DISABLED
            changes["active"] = req.is_active

        if not changes:
            raise HTTPException(status_code=400, detail="No changes specified")

        _write_audit_log(
            session, "provider_updated", user,
            resource_id=str(provider.id),
            details={"provider_name": provider_name, **changes},
        )

        await session.flush()
        registry_entry = PROVIDER_REGISTRY.get(provider.name, {})
        return _provider_to_response(provider, registry_entry)


@router.delete("/{provider_name}", status_code=204)
async def delete_provider(
    provider_name: str,
    user: TokenData = Depends(require_role("admin")),
):
    """Delete a provider configuration. Admin only.

    This removes the encrypted API key and disables the provider.
    """
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(AIProvider).where(AIProvider.name == provider_name.lower())
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        # Clear the API key but keep the provider record for statistics
        provider.api_key_encrypted = None
        provider.status = ProviderStatus.DISABLED
        provider.configured_at = None

        _write_audit_log(
            session, "provider_deleted", user,
            resource_id=str(provider.id),
            details={
                "provider_name": provider_name,
                "action": "api_key_cleared",
            },
        )

        await session.flush()


@router.post("/{provider_name}/test")
async def test_provider(
    provider_name: str,
    user: TokenData = Depends(require_role("admin")),
):
    """Test provider connectivity. Admin only.

    Decrypts the API key and makes a minimal test call.
    Never returns the API key.
    """
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(AIProvider).where(AIProvider.name == provider_name.lower())
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        if not provider.api_key_encrypted:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider_name}' has no API key configured",
            )

        try:
            api_key = decrypt_secret(provider.api_key_encrypted)
        except ValueError:
            raise HTTPException(
                status_code=500,
                detail="Failed to decrypt API key",
            )

        # Test connectivity based on provider type
        import httpx
        test_result = {"provider": provider_name, "success": False, "error": None}

        try:
            if provider_name == "gemini":
                resp = await httpx.AsyncClient().get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    test_result["success"] = True
                    models = resp.json().get("models", [])
                    test_result["models_available"] = len(models)
                else:
                    test_result["error"] = f"HTTP {resp.status_code}"

            elif provider_name == "openai":
                resp = await httpx.AsyncClient().get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    test_result["success"] = True
                else:
                    test_result["error"] = f"HTTP {resp.status_code}"

            elif provider_name == "groq":
                resp = await httpx.AsyncClient().get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    test_result["success"] = True
                else:
                    test_result["error"] = f"HTTP {resp.status_code}"

            else:
                test_result["error"] = "Unknown provider type"

        except httpx.TimeoutException:
            test_result["error"] = "Connection timeout"
        except Exception as e:
            test_result["error"] = str(e)[:200]

        # Update provider status based on test
        if test_result["success"]:
            provider.status = ProviderStatus.HEALTHY
            provider.circuit_state = "closed"
            provider.cooldown_until = None
        else:
            provider.status = ProviderStatus.DEGRADED

        _write_audit_log(
            session, "provider_connectivity_test", user,
            resource_id=str(provider.id),
            details={
                "provider_name": provider_name,
                "success": test_result["success"],
                "error": test_result.get("error"),
            },
            outcome="success" if test_result["success"] else "failure",
        )

        await session.flush()
        return test_result
