"""
hi.myrepo - AI Gateway

OpenAI-compatible interface with capability routing, provider state tracking,
circuit breakers, and cost/quotawareness.

Application → hi.myrepo AI Gateway → Capability Router → Provider Pool
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import AIProvider, AIProviderEvent, ProviderStatus


# ============================================================================
# Request/Response Models (OpenAI-compatible)
# ============================================================================

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "gemini-2.0-flash"
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024
    top_p: Optional[float] = None
    stream: bool = False
    # Custom extensions for capability routing
    required_capabilities: list[str] = Field(default_factory=lambda: ["text"])
    priority: str = "normal"  # low, normal, high, critical


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: Optional[dict] = None
    # Gateway extensions
    provider: Optional[str] = None
    latency_ms: Optional[float] = None
    cascade_count: Optional[int] = None


# ============================================================================
# Circuit Breaker
# ============================================================================

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider circuit breaker."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._success_count = 0
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False


# ============================================================================
# Provider Configuration
# ============================================================================

class ProviderConfig:
    """Configuration for a single AI provider."""

    PROVIDERS = {
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key_env": "gemini_api_key",
            "models": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash"],
            "capabilities": ["text", "vision", "reasoning", "code", "long_context"],
            "timeout": 30,
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "openai_api_key",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "capabilities": ["text", "vision", "reasoning", "code", "structured_output"],
            "timeout": 30,
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "groq_api_key",
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
            "capabilities": ["text", "speed", "code"],
            "timeout": 15,
        },
    }

    @classmethod
    def get_config(cls, provider_name: str) -> Optional[dict]:
        return cls.PROVIDERS.get(provider_name)

    @classmethod
    def get_all_providers(cls) -> dict:
        return cls.PROVIDERS


# ============================================================================
# Failure Classification
# ============================================================================

class FailureType(str, Enum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    POLICY = "policy"


def classify_failure(status_code: int, error_message: str) -> FailureType:
    """Classify an AI provider failure."""
    error_lower = error_message.lower()

    # Policy failures (check message keywords first — takes precedence)
    # e.g., 403 "Provider disabled" is a policy issue, not an auth error
    if "quota" in error_lower:
        return FailureType.POLICY
    if "disabled" in error_lower:
        return FailureType.POLICY
    if "limit" in error_lower and status_code != 429:
        return FailureType.POLICY

    # Non-retryable: authentication/request errors
    non_retryable_codes = {400, 401, 403, 404, 422}
    if status_code in non_retryable_codes:
        return FailureType.NON_RETRYABLE

    # Retryable: transient errors
    retryable_codes = {408, 429, 500, 502, 503, 504}
    if status_code in retryable_codes:
        return FailureType.RETRYABLE

    return FailureType.RETRYABLE


# ============================================================================
# AI Gateway
# ============================================================================

class AIGateway:
    """
    OpenAI-compatible AI gateway with provider routing and circuit breakers.

    Architecture:
        Application → AI Gateway → Capability Router → Provider Pool
    """

    def __init__(self):
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    def _get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self._circuit_breakers:
            self._circuit_breakers[provider] = CircuitBreaker()
        return self._circuit_breakers[provider]

    async def chat_completions(
        self,
        request: ChatCompletionRequest,
        session: AsyncSession,
    ) -> ChatCompletionResponse:
        """
        Process a chat completion request with provider routing and failover.
        """
        settings = self._settings
        cascade_count = 0

        # Determine provider order based on capabilities and health
        provider_order = await self._select_providers(
            request.required_capabilities, session
        )

        if not provider_order:
            raise ValueError("No healthy AI providers available")

        last_error = None
        for provider_name in provider_order:
            config = ProviderConfig.get_config(provider_name)
            if not config:
                continue

            # Get API key
            api_key = getattr(settings, config["api_key_env"], "")
            if not api_key:
                continue

            # Check circuit breaker
            cb = self._get_circuit_breaker(provider_name)
            if not cb.can_execute():
                cascade_count += 1
                continue

            # Try the provider
            try:
                start_time = time.time()
                response = await self._call_provider(
                    provider_name, config, api_key, request
                )
                latency_ms = (time.time() - start_time) * 1000

                cb.record_success()

                # Record success event
                await self._record_provider_event(
                    provider_name=provider_name,
                    request_type="chat_completion",
                    model_used=request.model,
                    latency_ms=latency_ms,
                    success=True,
                    session=session,
                )

                return ChatCompletionResponse(
                    id=response.get("id", ""),
                    model=response.get("model", request.model),
                    choices=response.get("choices", []),
                    usage=response.get("usage"),
                    provider=provider_name,
                    latency_ms=latency_ms,
                    cascade_count=cascade_count,
                )

            except httpx.HTTPStatusError as e:
                failure_type = classify_failure(e.response.status_code, str(e))
                cb.record_failure()

                await self._record_provider_event(
                    provider_name=provider_name,
                    request_type="chat_completion",
                    model_used=request.model,
                    latency_ms=0,
                    success=False,
                    error_message=str(e),
                    error_classification=failure_type.value,
                    session=session,
                )

                if failure_type == FailureType.NON_RETRYABLE:
                    # Don't try other providers for auth errors
                    raise ValueError(
                        f"Provider '{provider_name}' authentication failed: {e}"
                    )

                last_error = e
                cascade_count += 1
                continue

            except Exception as e:
                cb.record_failure()
                last_error = e
                cascade_count += 1
                continue

        # All providers failed
        raise ValueError(
            f"All AI providers failed after {cascade_count} cascades. "
            f"Last error: {last_error}"
        )

    async def _select_providers(
        self,
        required_capabilities: list[str],
        session: AsyncSession,
    ) -> list[str]:
        """
        Select providers based on capabilities, health, and policy.
        Not merely: Gemini → OpenAI → Groq.
        The ordering is policy/configuration, not hardcoded doctrine.
        """
        # Get provider states from database
        result = await session.execute(select(AIProvider))
        providers = {p.name: p for p in result.scalars().all()}

        settings = self._settings
        candidates = []

        for name in ProviderConfig.get_all_providers():
            # Check if API key is configured
            config = ProviderConfig.get_config(name)
            if not config:
                continue
            api_key = getattr(settings, config["api_key_env"], "")
            if not api_key:
                continue

            # Check capabilities
            if required_capabilities:
                provider_caps = set(config.get("capabilities", []))
                required = set(required_capabilities)
                if not required.issubset(provider_caps):
                    continue

            # Check health from database state
            db_provider = providers.get(name)
            if db_provider:
                if db_provider.status == ProviderStatus.DISABLED:
                    continue
                if db_provider.status == ProviderStatus.COOLDOWN:
                    if db_provider.cooldown_until and db_provider.cooldown_until > datetime.now(timezone.utc):
                        continue

            # Check circuit breaker
            cb = self._get_circuit_breaker(name)
            if not cb.can_execute():
                continue

            # Score the provider (lower is better)
            score = 0
            if db_provider:
                # Prefer healthy providers
                if db_provider.status == ProviderStatus.HEALTHY:
                    score -= 10
                # Prefer low latency
                score += db_provider.avg_latency_ms / 1000
                # Prefer high success rate
                score += (1 - db_provider.success_rate) * 50

            candidates.append((name, score))

        # Sort by score (best first)
        candidates.sort(key=lambda x: x[1])
        return [name for name, _ in candidates]

    async def _call_provider(
        self,
        provider_name: str,
        config: dict,
        api_key: str,
        request: ChatCompletionRequest,
    ) -> dict:
        """Make the actual API call to a provider."""
        client = await self._get_client()

        # Convert to provider-specific format
        headers, payload, url = self._build_request(
            provider_name, config, api_key, request
        )

        response = await client.post(
            url,
            json=payload,
            headers=headers,
            timeout=config.get("timeout", 30),
        )
        response.raise_for_status()
        return response.json()

    def _build_request(
        self,
        provider_name: str,
        config: dict,
        api_key: str,
        request: ChatCompletionRequest,
    ) -> tuple[dict, dict, str]:
        """Build provider-specific request format."""
        base_url = config["base_url"]

        if provider_name == "gemini":
            # Gemini uses different format
            url = f"{base_url}/models/{request.model}:generateContent?key={api_key}"
            # Convert messages to Gemini format
            contents = []
            for msg in request.messages:
                role = "user" if msg.role in ("user", "system") else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_tokens,
                },
            }
            headers = {"Content-Type": "application/json"}
        else:
            # OpenAI-compatible format (OpenAI, Groq)
            url = f"{base_url}/chat/completions"
            payload = {
                "model": request.model,
                "messages": [m.model_dump() for m in request.messages],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
            if request.top_p is not None:
                payload["top_p"] = request.top_p
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

        return headers, payload, url

    async def _record_provider_event(
        self,
        provider_name: str,
        request_type: str,
        model_used: str,
        latency_ms: float,
        success: bool,
        session: AsyncSession,
        error_message: Optional[str] = None,
        error_classification: Optional[str] = None,
    ):
        """Record a provider event for observability."""
        # Get provider ID
        result = await session.execute(
            select(AIProvider).where(AIProvider.name == provider_name)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            return

        event = AIProviderEvent(
            provider_id=provider.id,
            request_type=request_type,
            model_used=model_used,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            error_classification=error_classification,
        )
        session.add(event)

        # Update provider stats
        provider.total_requests += 1
        if not success:
            provider.total_failures += 1
            provider.recent_429_count += 1 if error_classification == "retryable" else 0

        # Update success rate
        if provider.total_requests > 0:
            provider.success_rate = 1 - (provider.total_failures / provider.total_requests)
            provider.failure_rate = provider.total_failures / provider.total_requests

        # Update avg latency
        if provider.total_requests == 1:
            provider.avg_latency_ms = latency_ms
        else:
            provider.avg_latency_ms = (
                (provider.avg_latency_ms * (provider.total_requests - 1) + latency_ms)
                / provider.total_requests
            )

        provider.updated_at = datetime.now(timezone.utc)
        await session.flush()

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Global AI gateway singleton
ai_gateway = AIGateway()
