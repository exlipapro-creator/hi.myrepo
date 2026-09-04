"""
hi.myrepo - AI Gateway

OpenAI-compatible interface with capability routing, provider state tracking,
circuit breakers, and cost/quotawareness.

Application → hi.myrepo AI Gateway → Capability Router → Provider Pool
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import httpx
import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import AIProvider, AIProviderEvent, ProviderStatus

logger = structlog.get_logger()


# ============================================================================
# Request/Response Models (OpenAI-compatible)
# ============================================================================

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "gemini-3.5-flash"
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024
    top_p: Optional[float] = None
    stream: bool = False
    required_capabilities: list[str] = Field(default_factory=lambda: ["text"])
    priority: str = "normal"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: Optional[dict] = None
    provider: Optional[str] = None
    latency_ms: Optional[float] = None
    cascade_count: Optional[int] = None


# ============================================================================
# Structured AI Output Models
# ============================================================================

class AIAnalysisOutput(BaseModel):
    """Structured output from AI incident analysis.
    Distinguishes FACT / INFERENCE / HYPOTHESIS / UNKNOWN.
    """
    summary: str
    probable_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    risk: str = "unknown"  # low, medium, high, critical
    affected_components: list[str] = Field(default_factory=list)
    blast_radius: str = "unknown"  # low, medium, high, critical
    evidence_classification: dict = Field(default_factory=dict)  # fact/inference/hypothesis per item
    provider: Optional[str] = None
    model: Optional[str] = None
    analysis_type: str = "ai_analysis"


def parse_structured_ai_output(
    raw_content: str,
    provider: str = "unknown",
    model: str = "unknown",
) -> Optional[AIAnalysisOutput]:
    """Parse AI response into structured analysis output.
    
    Handles:
    1. Direct JSON response
    2. Markdown-wrapped JSON (```json ... ```)
    3. Plain text fallback (extract key fields)
    
    Returns None if parsing fails completely.
    """
    import json
    import re

    if not raw_content:
        return None

    content = raw_content.strip()

    # Strategy 1: Direct JSON parse
    try:
        data = json.loads(content)
        return _build_analysis_from_dict(data, provider, model)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Extract JSON from markdown code block
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return _build_analysis_from_dict(data, provider, model)
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: Find first { ... } block in content
    brace_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            return _build_analysis_from_dict(data, provider, model)
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Plain text fallback — extract structured fields from prose
    confidence = 0.5
    conf_match = re.search(r'confidence[:\s]*(\d+\.?\d*)%?', content, re.IGNORECASE)
    if conf_match:
        try:
            conf_val = float(conf_match.group(1))
            confidence = conf_val / 100 if conf_val > 1 else conf_val
        except ValueError:
            pass

    risk = "medium"
    if any(w in content.lower() for w in ["critical", "severe", "urgent"]):
        risk = "high"
    elif any(w in content.lower() for w in ["low risk", "minor", "transient"]):
        risk = "low"

    return AIAnalysisOutput(
        summary=content[:500],
        probable_root_cause="Unable to extract structured root cause from AI response",
        confidence=confidence,
        evidence=[content[:200]],
        risk=risk,
        provider=provider,
        model=model,
        analysis_type="ai_analysis_text_fallback",
    )


def _build_analysis_from_dict(data: dict, provider: str, model: str) -> AIAnalysisOutput:
    """Build AIAnalysisOutput from a parsed JSON dict with field normalization."""
    confidence = float(data.get("confidence", data.get("confidence_score", 0.5)))
    if confidence > 1:
        confidence = confidence / 100  # Normalize percentage to 0-1
    confidence = max(0.0, min(1.0, confidence))

    return AIAnalysisOutput(
        summary=str(data.get("summary", data.get("analysis", "No summary provided")))[:1000],
        probable_root_cause=str(data.get("probable_root_cause", data.get("root_cause", data.get("cause", "Unknown"))))[:500],
        confidence=confidence,
        evidence=data.get("evidence", data.get("supporting_evidence", [])) or [],
        alternative_hypotheses=data.get("alternative_hypotheses", data.get("alternatives", [])) or [],
        recommended_next_steps=data.get("recommended_next_steps", data.get("recommendations", data.get("next_steps", []))) or [],
        risk=str(data.get("risk", "medium")),
        affected_components=data.get("affected_components", data.get("components", [])) or [],
        blast_radius=str(data.get("blast_radius", "unknown")),
        evidence_classification=data.get("evidence_classification", {}),
        provider=provider,
        model=model,
        analysis_type="ai_analysis_structured",
    )


# ============================================================================
# Circuit Breaker
# ============================================================================

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider circuit breaker with asyncio-safe state transitions."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, half_open_max_calls: int = 3):
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
                    self._success_count = 0
        return self._state

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._half_open_calls = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._half_open_calls = 0
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
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
            "models": ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.7-flash"],
            "default_model": "gemini-3.5-flash",
            "capabilities": ["text", "vision", "reasoning", "code", "long_context"],
            "timeout": 30,
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "openai_api_key",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "default_model": "gpt-4o-mini",
            "capabilities": ["text", "vision", "reasoning", "code", "structured_output"],
            "timeout": 30,
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "groq_api_key",
            "models": ["openai/gpt-oss-120b", "qwen/qwen3.6-27b", "openai/gpt-oss-20b"],
            "default_model": "openai/gpt-oss-120b",
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

    @classmethod
    def get_default_model(cls, provider_name: str) -> str:
        config = cls.get_config(provider_name)
        return config.get("default_model", "") if config else ""


# ============================================================================
# Failure Classification
# ============================================================================

class FailureType(str, Enum):
    """Fine-grained failure classification for AI provider errors."""
    AUTHENTICATION_FAILURE = "authentication_failure"
    MODEL_NOT_FOUND = "model_not_found"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMIT = "rate_limit"
    POLICY = "policy"
    TRANSIENT_PROVIDER_FAILURE = "transient_provider_failure"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN = "unknown"


def classify_failure(status_code: int, error_message: str) -> FailureType:
    """Classify an AI provider failure with fine-grained categories."""
    error_lower = error_message.lower()
    if status_code == 429:
        return FailureType.RATE_LIMIT
    if status_code == 408:
        return FailureType.TIMEOUT
    if status_code >= 500:
        return FailureType.TRANSIENT_PROVIDER_FAILURE
    if "quota" in error_lower:
        return FailureType.POLICY
    if "disabled" in error_lower:
        return FailureType.POLICY
    if "blocked" in error_lower:
        return FailureType.POLICY
    if status_code == 401:
        return FailureType.AUTHENTICATION_FAILURE
    if status_code == 403:
        if "api key" in error_lower or "credential" in error_lower or "unauthorized" in error_lower:
            return FailureType.AUTHENTICATION_FAILURE
        return FailureType.POLICY
    if status_code == 404:
        if "model" in error_lower or "not found" in error_lower:
            return FailureType.MODEL_NOT_FOUND
        return FailureType.INVALID_REQUEST
    if status_code == 400:
        return FailureType.INVALID_REQUEST
    if status_code == 422:
        return FailureType.INVALID_REQUEST
    return FailureType.TRANSIENT_PROVIDER_FAILURE


def is_retryable(failure_type: FailureType) -> bool:
    """Determine if a failure type warrants cascading to another provider."""
    return failure_type in {FailureType.RATE_LIMIT, FailureType.TIMEOUT, FailureType.TRANSIENT_PROVIDER_FAILURE}


# ============================================================================
# Gemini Response Normalizer
# ============================================================================

class GeminiNormalizer:
    """
    Convert Gemini API responses to OpenAI-compatible format.

    Gemini returns: { candidates: [...], usageMetadata: {...}, modelVersion, responseId }
    We normalize to: { id, object, created, model, choices, usage }
    """

    FINISH_REASON_MAP = {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
        "FINISH_REASON_UNSPECIFIED": "stop",
    }

    @staticmethod
    def normalize_request_for_gemini(
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> dict:
        """Convert OpenAI-format messages to Gemini generateContent format."""
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.role.lower()
            if role == "system":
                if system_instruction is None:
                    system_instruction = msg.content
                else:
                    system_instruction += "\n" + msg.content
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": msg.content}]})

        payload: dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        gen_config: dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_tokens is not None:
            gen_config["maxOutputTokens"] = max_tokens
        if top_p is not None:
            gen_config["topP"] = top_p
        if gen_config:
            payload["generationConfig"] = gen_config

        return payload

    @staticmethod
    def normalize_response(
        gemini_response: dict,
        provider_name: str = "gemini",
        model_used: str = "",
    ) -> ChatCompletionResponse:
        """Convert Gemini response to OpenAI-compatible ChatCompletionResponse."""
        now = int(time.time())
        response_id = gemini_response.get("responseId") or f"chatcmpl-{uuid.uuid4().hex[:24]}"
        model_version = gemini_response.get("modelVersion", model_used)

        candidates = gemini_response.get("candidates", [])
        if not candidates:
            return ChatCompletionResponse(
                id=response_id, created=now, model=model_version,
                choices=[{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}],
                usage=GeminiNormalizer._normalize_usage(gemini_response.get("usageMetadata")),
                provider=provider_name,
            )

        candidate = candidates[0]
        finish_reason_raw = candidate.get("finishReason", "STOP")
        finish_reason = GeminiNormalizer.FINISH_REASON_MAP.get(finish_reason_raw, "stop")

        content = ""
        candidate_content = candidate.get("content", {})
        parts = candidate_content.get("parts", [])
        if parts:
            text_parts = [part["text"] for part in parts if "text" in part]
            content = "\n".join(text_parts)

        if not content and finish_reason_raw in ("SAFETY", "RECITATION"):
            content = "[Response blocked by safety filter]"

        return ChatCompletionResponse(
            id=response_id, created=now, model=model_version,
            choices=[{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
            usage=GeminiNormalizer._normalize_usage(gemini_response.get("usageMetadata")),
            provider=provider_name,
        )

    @staticmethod
    def _normalize_usage(usage_metadata: Optional[dict]) -> Optional[dict]:
        if not usage_metadata:
            return None
        return {
            "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
            "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
            "total_tokens": usage_metadata.get("totalTokenCount", 0),
        }


# ============================================================================
# AI Gateway
# ============================================================================

class AIGateway:
    """
    OpenAI-compatible AI gateway with provider routing and circuit breakers.
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
        """Process a chat completion request with provider routing and failover."""
        cascade_count = 0
        provider_order = await self._select_providers(request.required_capabilities, session)
        if not provider_order:
            raise ValueError("No healthy AI providers available")

        last_error = None
        for provider_name in provider_order:
            config = ProviderConfig.get_config(provider_name)
            if not config:
                continue
            # Try env var first, then fall back to encrypted DB key
            api_key = getattr(self._settings, config["api_key_env"], "")
            if not api_key:
                # Read from encrypted provider record in database
                try:
                    from app.database.connection import db_manager
                    async with db_manager.get_session() as db_session:
                        result = await db_session.execute(
                            select(AIProvider).where(AIProvider.name == provider_name)
                        )
                        db_provider = result.scalar_one_or_none()
                        if db_provider and db_provider.api_key_encrypted:
                            from app.security.encryption import decrypt_secret
                            api_key = decrypt_secret(db_provider.api_key_encrypted)
                except Exception as e:
                    logger.warning("provider_key_decrypt_failed", provider=provider_name, error=str(e))
            if not api_key:
                continue

            # Skip providers that don't support the requested model
            supported_models = config.get("models", [])
            if supported_models and request.model not in supported_models:
                cascade_count += 1
                continue

            cb = self._get_circuit_breaker(provider_name)
            if not cb.can_execute():
                cascade_count += 1
                continue

            try:
                start_time = time.time()
                raw_response = await self._call_provider(provider_name, config, api_key, request)
                latency_ms = (time.time() - start_time) * 1000
                cb.record_success()

                normalized = GeminiNormalizer.normalize_response(raw_response, provider_name, request.model)
                normalized.latency_ms = latency_ms
                normalized.cascade_count = cascade_count

                await self._record_provider_event(
                    provider_name=provider_name, request_type="chat_completion",
                    model_used=request.model, latency_ms=latency_ms, success=True, session=session,
                )
                return normalized

            except httpx.HTTPStatusError as e:
                resp_body = ""
                try:
                    resp_body = e.response.text[:500]
                except Exception:
                    pass
                logger.warning("provider_http_error", provider=provider_name, status=e.response.status_code, body=resp_body)
                failure_type = classify_failure(e.response.status_code, str(e))
                cb.record_failure()
                await self._record_provider_event(
                    provider_name=provider_name, request_type="chat_completion",
                    model_used=request.model, latency_ms=0, success=False,
                    error_message=str(e), error_classification=failure_type.value, session=session,
                )
                if not is_retryable(failure_type):
                    raise ValueError(self._format_provider_error(provider_name, failure_type, e.response.status_code))
                last_error = e
                cascade_count += 1
            except Exception as e:
                cb.record_failure()
                last_error = e
                cascade_count += 1

        raise ValueError(f"All AI providers failed after {cascade_count} cascades. Last error: {last_error}")

    def _format_provider_error(self, provider_name: str, failure_type: FailureType, status_code: int) -> str:
        if failure_type == FailureType.AUTHENTICATION_FAILURE:
            return f"Provider '{provider_name}' authentication failed (HTTP {status_code}). Check API key."
        elif failure_type == FailureType.MODEL_NOT_FOUND:
            return f"Provider '{provider_name}' model not found (HTTP {status_code}). Model may be unavailable or renamed."
        elif failure_type == FailureType.INVALID_REQUEST:
            return f"Provider '{provider_name}' rejected request (HTTP {status_code})."
        elif failure_type == FailureType.RATE_LIMIT:
            return f"Provider '{provider_name}' rate limited (HTTP 429)."
        elif failure_type == FailureType.POLICY:
            return f"Provider '{provider_name}' policy violation."
        elif failure_type == FailureType.TIMEOUT:
            return f"Provider '{provider_name}' request timed out."
        else:
            return f"Provider '{provider_name}' transient failure (HTTP {status_code})."

    async def _select_providers(self, required_capabilities: list[str], session: AsyncSession) -> list[str]:
        """Select providers based on capabilities, health, and policy. DB-resilient."""
        providers: dict = {}
        try:
            result = await session.execute(select(AIProvider))
            providers = {p.name: p for p in result.scalars().all()}
        except Exception as e:
            logger.warning("provider_selection_db_unavailable", error=str(e))

        settings = self._settings
        candidates = []
        for name in ProviderConfig.get_all_providers():
            config = ProviderConfig.get_config(name)
            if not config:
                continue
            api_key = getattr(settings, config["api_key_env"], "")
            if not api_key:
                # Also check if provider has encrypted key in database
                db_prov = providers.get(name)
                if not (db_prov and db_prov.api_key_encrypted):
                    continue
            if required_capabilities:
                provider_caps = set(config.get("capabilities", []))
                if not set(required_capabilities).issubset(provider_caps):
                    continue
            db_provider = providers.get(name)
            if db_provider:
                if db_provider.status == ProviderStatus.DISABLED:
                    continue
                if db_provider.status == ProviderStatus.COOLDOWN:
                    if db_provider.cooldown_until and db_provider.cooldown_until > datetime.now(timezone.utc):
                        continue
            cb = self._get_circuit_breaker(name)
            if not cb.can_execute():
                continue
            score = 0
            if db_provider:
                if db_provider.status == ProviderStatus.HEALTHY:
                    score -= 10
                score += db_provider.avg_latency_ms / 1000
                score += (1 - db_provider.success_rate) * 50
            candidates.append((name, score))

        candidates.sort(key=lambda x: x[1])
        return [name for name, _ in candidates]

    async def _call_provider(self, provider_name: str, config: dict, api_key: str, request: ChatCompletionRequest) -> dict:
        client = await self._get_client()
        headers, payload, url = self._build_request(provider_name, config, api_key, request)
        response = await client.post(url, json=payload, headers=headers, timeout=config.get("timeout", 30))
        response.raise_for_status()
        return response.json()

    def _build_request(self, provider_name: str, config: dict, api_key: str, request: ChatCompletionRequest) -> tuple[dict, dict, str]:
        base_url = config["base_url"]
        if provider_name == "gemini":
            url = f"{base_url}/models/{request.model}:generateContent?key={api_key}"
            payload = GeminiNormalizer.normalize_request_for_gemini(
                messages=request.messages, temperature=request.temperature,
                max_tokens=request.max_tokens, top_p=request.top_p,
            )
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{base_url}/chat/completions"
            payload = {
                "model": request.model,
                "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            }
            if request.temperature is not None:
                payload["temperature"] = request.temperature
            if request.max_tokens is not None:
                payload["max_tokens"] = request.max_tokens
            if request.top_p is not None:
                payload["top_p"] = request.top_p
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        return headers, payload, url

    async def _record_provider_event(
        self, provider_name: str, request_type: str, model_used: str,
        latency_ms: float, success: bool, session: AsyncSession,
        error_message: Optional[str] = None, error_classification: Optional[str] = None,
    ):
        """Record a provider event for observability. Gracefully degrades if DB unavailable."""
        try:
            result = await session.execute(select(AIProvider).where(AIProvider.name == provider_name))
            provider = result.scalar_one_or_none()
            if not provider:
                return
            event = AIProviderEvent(
                provider_id=provider.id, request_type=request_type, model_used=model_used,
                latency_ms=latency_ms, success=success, error_message=error_message,
                error_classification=error_classification,
            )
            session.add(event)
            provider.total_requests += 1
            if not success:
                provider.total_failures += 1
                if error_classification == "rate_limit":
                    provider.recent_429_count += 1
            if provider.total_requests > 0:
                provider.success_rate = 1 - (provider.total_failures / provider.total_requests)
                provider.failure_rate = provider.total_failures / provider.total_requests
            if provider.total_requests == 1:
                provider.avg_latency_ms = latency_ms
            else:
                provider.avg_latency_ms = (
                    (provider.avg_latency_ms * (provider.total_requests - 1) + latency_ms) / provider.total_requests
                )
            provider.updated_at = datetime.now(timezone.utc)
            await session.flush()
        except Exception as e:
            logger.warning("provider_event_recording_failed", provider=provider_name, error=str(e))

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Global AI gateway singleton
ai_gateway = AIGateway()
