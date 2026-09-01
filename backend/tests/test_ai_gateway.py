"""
Tests for AI Gateway - Gemini normalization, failure classification,
circuit breaker, provider selection, and OpenAI compatibility.
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gateway.ai_gateway import (
    AIGateway,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CircuitBreaker,
    CircuitState,
    FailureType,
    GeminiNormalizer,
    ProviderConfig,
    classify_failure,
    is_retryable,
)


# ============================================================================
# Gemini Normalizer Tests
# ============================================================================

class TestGeminiNormalizerRequest:
    """Test Gemini request transformation."""

    def test_simple_user_message(self):
        messages = [ChatMessage(role="user", content="Hello")]
        result = GeminiNormalizer.normalize_request_for_gemini(messages)

        assert "contents" in result
        assert len(result["contents"]) == 1
        assert result["contents"][0]["role"] == "user"
        assert result["contents"][0]["parts"][0]["text"] == "Hello"
        assert "systemInstruction" not in result

    def test_system_message_becomes_instruction(self):
        messages = [
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="Hello"),
        ]
        result = GeminiNormalizer.normalize_request_for_gemini(messages)

        assert "systemInstruction" in result
        assert result["systemInstruction"]["parts"][0]["text"] == "You are a helpful assistant."
        # System message should NOT appear in contents
        assert len(result["contents"]) == 1
        assert result["contents"][0]["role"] == "user"

    def test_multiple_system_messages_concatenated(self):
        messages = [
            ChatMessage(role="system", content="Be helpful."),
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="Hi"),
        ]
        result = GeminiNormalizer.normalize_request_for_gemini(messages)

        assert result["systemInstruction"]["parts"][0]["text"] == "Be helpful.\nBe concise."

    def test_assistant_message_becomes_model(self):
        messages = [
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content="Hello!"),
            ChatMessage(role="user", content="How are you?"),
        ]
        result = GeminiNormalizer.normalize_request_for_gemini(messages)

        assert len(result["contents"]) == 3
        assert result["contents"][1]["role"] == "model"
        assert result["contents"][1]["parts"][0]["text"] == "Hello!"

    def test_generation_config(self):
        messages = [ChatMessage(role="user", content="Hi")]
        result = GeminiNormalizer.normalize_request_for_gemini(
            messages, temperature=0.5, max_tokens=100, top_p=0.9
        )

        assert result["generationConfig"]["temperature"] == 0.5
        assert result["generationConfig"]["maxOutputTokens"] == 100
        assert result["generationConfig"]["topP"] == 0.9

    def test_no_generation_config_when_none(self):
        messages = [ChatMessage(role="user", content="Hi")]
        result = GeminiNormalizer.normalize_request_for_gemini(messages)

        assert "generationConfig" not in result


class TestGeminiNormalizerResponse:
    """Test Gemini response transformation to OpenAI format."""

    def test_normal_response(self):
        gemini_response = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Hello world"}],
                    "role": "model",
                },
                "finishReason": "STOP",
                "index": 0,
            }],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
            "modelVersion": "gemini-2.5-flash",
            "responseId": "abc123",
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "gemini-2.5-flash")

        assert isinstance(result, ChatCompletionResponse)
        assert result.id == "abc123"
        assert result.object == "chat.completion"
        assert result.model == "gemini-2.5-flash"
        assert result.provider == "gemini"
        assert len(result.choices) == 1
        assert result.choices[0]["message"]["content"] == "Hello world"
        assert result.choices[0]["message"]["role"] == "assistant"
        assert result.choices[0]["finish_reason"] == "stop"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5
        assert result.usage["total_tokens"] == 15
        assert isinstance(result.created, int)

    def test_empty_candidates(self):
        gemini_response = {
            "candidates": [],
            "usageMetadata": {"totalTokenCount": 5},
            "responseId": "xyz",
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.choices[0]["message"]["content"] == ""
        assert result.choices[0]["finish_reason"] == "stop"

    def test_missing_candidates(self):
        gemini_response = {
            "usageMetadata": {"totalTokenCount": 3},
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert len(result.choices) == 1
        assert result.choices[0]["message"]["content"] == ""

    def test_safety_blocked_response(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [], "role": "model"},
                "finishReason": "SAFETY",
            }],
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.choices[0]["finish_reason"] == "content_filter"
        content = result.choices[0]["message"]["content"].lower()
        assert "blocked" in content or result.choices[0]["message"]["content"] == ""

    def test_recitation_blocked(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [], "role": "model"},
                "finishReason": "RECITATION",
            }],
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.choices[0]["finish_reason"] == "content_filter"

    def test_missing_usage_metadata(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [{"text": "Hi"}], "role": "model"},
                "finishReason": "STOP",
            }],
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.usage is None

    def test_missing_response_id(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [{"text": "Hi"}], "role": "model"},
                "finishReason": "STOP",
            }],
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.id.startswith("chatcmpl-")

    def test_multiple_parts_concatenated(self):
        gemini_response = {
            "candidates": [{
                "content": {
                    "parts": [
                        {"text": "Part 1"},
                        {"text": "Part 2"},
                    ],
                    "role": "model",
                },
                "finishReason": "STOP",
            }],
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert "Part 1" in result.choices[0]["message"]["content"]
        assert "Part 2" in result.choices[0]["message"]["content"]

    def test_max_tokens_finish_reason(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [{"text": "Truncated..."}], "role": "model"},
                "finishReason": "MAX_TOKENS",
            }],
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.choices[0]["finish_reason"] == "length"

    def test_usage_normalization(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [{"text": "Hi"}], "role": "model"},
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
                "totalTokenCount": 150,
                "thoughtsTokenCount": 20,  # Gemini-specific, should be ignored
            },
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "test")

        assert result.usage["prompt_tokens"] == 100
        assert result.usage["completion_tokens"] == 50
        assert result.usage["total_tokens"] == 150


# ============================================================================
# Failure Classification Tests
# ============================================================================

class TestFailureClassification:
    """Test fine-grained failure classification."""

    def test_429_is_rate_limit(self):
        assert classify_failure(429, "Rate limit exceeded") == FailureType.RATE_LIMIT

    def test_401_is_auth_failure(self):
        assert classify_failure(401, "Invalid API key") == FailureType.AUTHENTICATION_FAILURE

    def test_403_policy(self):
        assert classify_failure(403, "Provider disabled") == FailureType.POLICY

    def test_403_auth_with_api_key_message(self):
        assert classify_failure(403, "Invalid API key") == FailureType.AUTHENTICATION_FAILURE

    def test_404_model_not_found(self):
        assert classify_failure(404, "Model not found") == FailureType.MODEL_NOT_FOUND

    def test_404_wrong_endpoint(self):
        # "Not found" contains 'not found', so it maps to MODEL_NOT_FOUND
        assert classify_failure(404, "Not found") == FailureType.MODEL_NOT_FOUND

    def test_404_other_404(self):
        # A 404 without model/not-found keywords maps to INVALID_REQUEST
        assert classify_failure(404, "Something else") == FailureType.INVALID_REQUEST

    def test_400_is_invalid_request(self):
        assert classify_failure(400, "Bad request") == FailureType.INVALID_REQUEST

    def test_500_is_transient(self):
        assert classify_failure(500, "Internal server error") == FailureType.TRANSIENT_PROVIDER_FAILURE

    def test_503_is_transient(self):
        assert classify_failure(503, "Service unavailable") == FailureType.TRANSIENT_PROVIDER_FAILURE

    def test_408_is_timeout(self):
        assert classify_failure(408, "Request timeout") == FailureType.TIMEOUT

    def test_quota_is_policy(self):
        assert classify_failure(403, "Quota exceeded") == FailureType.POLICY

    def test_retryable_types(self):
        assert is_retryable(FailureType.RATE_LIMIT) is True
        assert is_retryable(FailureType.TIMEOUT) is True
        assert is_retryable(FailureType.TRANSIENT_PROVIDER_FAILURE) is True

    def test_non_retryable_types(self):
        assert is_retryable(FailureType.AUTHENTICATION_FAILURE) is False
        assert is_retryable(FailureType.MODEL_NOT_FOUND) is False
        assert is_retryable(FailureType.INVALID_REQUEST) is False
        assert is_retryable(FailureType.POLICY) is False


# ============================================================================
# Circuit Breaker Tests
# ============================================================================

class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        # With recovery_timeout=0, accessing .state immediately transitions to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0, half_open_max_calls=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes
        for _ in range(3):
            cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1000, half_open_max_calls=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Force transition to half-open
        cb._last_failure_time = time.time() - 2000
        assert cb.state == CircuitState.HALF_OPEN

        # Any failure re-opens the circuit
        cb.record_failure()
        # recovery_timeout=1000 means it stays OPEN (won't auto-transition back)
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_success_decay(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2

        cb.record_success()
        assert cb._failure_count == 1

    def test_can_execute_limits_half_open_calls(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0, half_open_max_calls=2)
        cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        # First two calls allowed
        assert cb.can_execute() is True
        assert cb.can_execute() is True

        # Third call blocked
        assert cb.can_execute() is False


# ============================================================================
# Provider Config Tests
# ============================================================================

class TestProviderConfig:
    """Test provider configuration."""

    def test_gemini_config_exists(self):
        config = ProviderConfig.get_config("gemini")
        assert config is not None
        assert "base_url" in config
        assert "models" in config
        assert "gemini-3.5-flash" in config["models"]

    def test_openai_config_exists(self):
        config = ProviderConfig.get_config("openai")
        assert config is not None
        assert "gpt-4o" in config["models"]

    def test_groq_config_exists(self):
        config = ProviderConfig.get_config("groq")
        assert config is not None
        assert "llama-3.3-70b-versatile" in config["models"]

    def test_unknown_provider_returns_none(self):
        assert ProviderConfig.get_config("nonexistent") is None

    def test_default_model(self):
        model = ProviderConfig.get_default_model("gemini")
        assert model == "gemini-3.5-flash"

    def test_all_providers(self):
        providers = ProviderConfig.get_all_providers()
        assert "gemini" in providers
        assert "openai" in providers
        assert "groq" in providers


# ============================================================================
# Request Building Tests
# ============================================================================

class TestRequestBuilding:
    """Test provider-specific request building."""

    def test_gemini_request_uses_generate_content(self):
        gateway = AIGateway()
        config = ProviderConfig.get_config("gemini")
        request = ChatCompletionRequest(
            model="gemini-2.5-flash",
            messages=[ChatMessage(role="user", content="Hi")],
        )

        headers, payload, url = gateway._build_request(
            "gemini", config, "test-key", request
        )

        assert "generateContent" in url
        assert "test-key" in url
        assert "contents" in payload
        assert "systemInstruction" not in payload

    def test_gemini_request_with_system_message(self):
        gateway = AIGateway()
        config = ProviderConfig.get_config("gemini")
        request = ChatCompletionRequest(
            model="gemini-2.5-flash",
            messages=[
                ChatMessage(role="system", content="Be helpful."),
                ChatMessage(role="user", content="Hi"),
            ],
        )

        _, payload, _ = gateway._build_request("gemini", config, "test-key", request)

        assert "systemInstruction" in payload
        assert payload["systemInstruction"]["parts"][0]["text"] == "Be helpful."

    def test_openai_request_uses_chat_completions(self):
        gateway = AIGateway()
        config = ProviderConfig.get_config("openai")
        request = ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Hi")],
        )

        headers, payload, url = gateway._build_request(
            "openai", config, "test-key", request
        )

        assert "/chat/completions" in url
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["model"] == "gpt-4o"


# ============================================================================
# OpenAI Compatibility Tests
# ============================================================================

class TestOpenAICompatibility:
    """Test that responses are structurally compatible with OpenAI API."""

    def test_response_has_required_fields(self):
        gemini_response = {
            "candidates": [{
                "content": {"parts": [{"text": "Hello"}], "role": "model"},
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
            "modelVersion": "gemini-2.5-flash",
            "responseId": "test-123",
        }

        result = GeminiNormalizer.normalize_response(gemini_response, "gemini", "gemini-2.5-flash")

        # Required OpenAI fields
        assert hasattr(result, "id")
        assert hasattr(result, "object")
        assert hasattr(result, "created")
        assert hasattr(result, "model")
        assert hasattr(result, "choices")
        assert hasattr(result, "usage")

        # Correct values
        assert result.object == "chat.completion"
        assert isinstance(result.created, int)
        assert result.created > 0

        # Choices structure
        choice = result.choices[0]
        assert "index" in choice
        assert "message" in choice
        assert "finish_reason" in choice
        assert choice["message"]["role"] == "assistant"
        assert isinstance(choice["message"]["content"], str)

        # Usage structure
        assert "prompt_tokens" in result.usage
        assert "completion_tokens" in result.usage
        assert "total_tokens" in result.usage


# ============================================================================
# Provider Statistics Tests
# ============================================================================

class TestProviderStatistics:
    """Test provider statistics tracking."""

    def test_failure_type_for_429(self):
        ft = classify_failure(429, "Rate limit")
        assert ft == FailureType.RATE_LIMIT
        assert is_retryable(ft) is True

    def test_failure_type_for_500(self):
        ft = classify_failure(500, "Server error")
        assert ft == FailureType.TRANSIENT_PROVIDER_FAILURE
        assert is_retryable(ft) is True

    def test_failure_type_for_auth(self):
        ft = classify_failure(401, "Invalid key")
        assert ft == FailureType.AUTHENTICATION_FAILURE
        assert is_retryable(ft) is False
