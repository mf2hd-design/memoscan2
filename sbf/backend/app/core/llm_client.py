"""
LLM Client with GPT-5.1 Responses API and circuit breaker fallback.
Adapted from MemoScan v2 with enhancements for structured output.
"""

from __future__ import annotations

import os
import time
import json
import concurrent.futures
from typing import Optional, Tuple, Dict, Any, Type
from pydantic import BaseModel

try:
    import tiktoken  # type: ignore
except Exception:
    tiktoken = None

from .config import settings


class CircuitBreaker:
    """
    Simple in-memory circuit breaker per key_name.
    - Open after N consecutive failures; remain open for cooldown seconds
    - When open, primary (GPT-5.1) is skipped and we go straight to GPT-4o fallback
    """
    _state: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _now(cls) -> float:
        return time.time()

    @classmethod
    def record_result(cls, key: str, success: bool) -> None:
        st = cls._state.setdefault(key, {"failures": 0, "open_until": 0.0})
        if success:
            st["failures"] = 0
            st["open_until"] = 0.0
        else:
            st["failures"] += 1
            if st["failures"] >= settings.CIRCUIT_BREAKER_THRESHOLD:
                st["open_until"] = cls._now() + settings.CIRCUIT_BREAKER_COOLDOWN

    @classmethod
    def is_open(cls, key: str) -> bool:
        st = cls._state.get(key)
        if not st:
            return False
        if st["open_until"] <= cls._now():
            return False
        return True


def _safe_chat_call(client, timeout_seconds: int = 60, max_retries: int = 1, **kwargs):
    """Safe chat completion call with timeout and retries."""
    last_error = None
    for retry in range(max_retries + 1):
        if retry > 0:
            time.sleep(min(2 ** retry, 8))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(client.chat.completions.create, **kwargs)
            try:
                resp = fut.result(timeout=timeout_seconds)
                return resp
            except concurrent.futures.TimeoutError:
                fut.cancel()
                last_error = TimeoutError(f"Chat call timed out after {timeout_seconds}s")
            except Exception as e:
                raise e
    raise last_error or Exception("Unexpected chat call error")


def _safe_responses_call(client, timeout_seconds: int = 60, **kwargs):
    """Safe Responses API call with timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(client.responses.create, **kwargs)
        try:
            return fut.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            raise TimeoutError(f"Responses call timed out after {timeout_seconds}s")


def _extract_text_from_responses(response) -> Optional[str]:
    """Extract text from GPT-5.1 Responses API response."""
    # Try modern SDK shapes
    if hasattr(response, 'output') and isinstance(response.output, list):
        for item in response.output:
            if hasattr(item, 'content') and item.content:
                for c in item.content:
                    if getattr(c, 'type', '') == 'output_text' and hasattr(c, 'text'):
                        return c.text
    if hasattr(response, 'text') and isinstance(response.text, str):
        return response.text
    # Older shapes
    if hasattr(response, 'content') and isinstance(response.content, list):
        for item in response.content:
            if hasattr(item, 'type') and item.type == 'message':
                if hasattr(item, 'content') and isinstance(item.content, list):
                    for content_item in item.content:
                        if hasattr(content_item, 'text'):
                            return content_item.text
                elif hasattr(item, 'content') and isinstance(item.content, str):
                    return item.content
    if hasattr(response, 'content') and isinstance(response.content, str):
        return response.content
    return None


class LLMClient:
    """
    Unified LLM client with GPT-5.1 (Responses API) and GPT-4o fallback.
    Includes circuit breaker, token estimation, and structured output support.
    """

    def __init__(self, api_key: Optional[str] = None):
        from openai import OpenAI

        self.api_key = api_key or settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")

        self.client = OpenAI(api_key=self.api_key)
        self._responses_capable = None  # Lazy probe

    def _probe_responses(self) -> bool:
        """Check if Responses API is available."""
        if self._responses_capable is not None:
            return self._responses_capable

        try:
            _ = _safe_responses_call(
                self.client,
                timeout_seconds=6,
                model=settings.GPT5_MODEL,
                input="ping",
                reasoning={"effort": "minimal"},
                text={"verbosity": "low"}
            )
            self._responses_capable = True
        except Exception:
            self._responses_capable = False

        return self._responses_capable

    @staticmethod
    def estimate_tokens(text: str, model: str = "gpt-4o") -> int:
        """Estimate token count for text."""
        if not text:
            return 200
        if tiktoken is None:
            return max(200, int(len(text) / 4))
        try:
            try:
                enc = tiktoken.encoding_for_model(model)
            except Exception:
                enc = tiktoken.get_encoding("cl100k_base")
            return max(200, len(enc.encode(text)))
        except Exception:
            return max(200, int(len(text) / 4))

    @staticmethod
    def adaptive_timeout(tokens: int, cap: int = 90) -> int:
        """Calculate adaptive timeout based on token count."""
        return int(min(20 + 0.002 * tokens, cap))

    def generate(
        self,
        key_name: str,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        force_json: bool = True,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Generate text using ONLY GPT-5.1-2025-11-13 via Responses API.
        No fallback to other models - GPT-5.1 only.

        Args:
            key_name: Identifier for circuit breaker tracking
            prompt: The input prompt
            schema: Optional Pydantic model for structured output (ignored for now)
            force_json: Whether to force JSON output format (ignored - GPT-5.1 uses markdown)

        Returns:
            Tuple of (response_text, metadata)
        """
        meta: Dict[str, Any] = {
            "api_used": None,
            "model": None,
            "token_usage": 0,
            "token_estimate": 0
        }

        # Check circuit breaker
        breaker_open = CircuitBreaker.is_open(key_name)
        meta["breaker_open"] = breaker_open

        if breaker_open:
            raise Exception(f"Circuit breaker is open for {key_name}. Wait {settings.CIRCUIT_BREAKER_COOLDOWN}s before retrying.")

        # Call GPT-5.1-2025-11-13 Responses API directly (no probe needed)
        try:
            tokens = LLMClient.estimate_tokens(prompt, settings.GPT5_MODEL)
            resp = _safe_responses_call(
                self.client,
                timeout_seconds=settings.GPT5_TIMEOUT,
                model=settings.GPT5_MODEL,
                input=prompt,
                reasoning={"effort": "medium"},  # SBF needs deeper reasoning
                text={"verbosity": "medium"}
            )
            raw = _extract_text_from_responses(resp)
            if not raw:
                raise Exception("Failed to extract text from GPT-5.1 response")

            meta.update({
                "api_used": "responses_api",
                "model": settings.GPT5_MODEL,
                "token_estimate": tokens
            })
            CircuitBreaker.record_result(key_name, success=True)

            try:
                meta["token_usage"] = resp.usage.total_tokens  # type: ignore
            except Exception:
                pass

            return raw, meta

        except Exception as e:
            CircuitBreaker.record_result(key_name, success=False)
            raise Exception(f"GPT-5.1-2025-11-13 generation failed: {e}")
