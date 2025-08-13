"""
LLM Client Abstraction for Discovery Mode

Unifies:
- Capability probe (Responses API) with fast circuit breaker per key
- Fallback chain: gpt-5 (Responses) -> gpt-4o (Chat) -> gpt-4o-mini (Chat)
- Token estimation via tiktoken (fallback to len/4)
- Safe timeouts via thread executor wrappers

Returns (raw_output, meta) where meta includes: api_used, model, token_usage, breaker_open
"""

from __future__ import annotations

import os
import time
import json
import concurrent.futures
from typing import Optional, Tuple, Dict, Any

try:
    import tiktoken  # type: ignore
except Exception:
    tiktoken = None  # Optional; we fallback if unavailable


class CircuitBreaker:
    """
    Simple in-memory circuit breaker per key_name.
    - Open after N consecutive failures; remain open for cooldown seconds
    - When open, primary (gpt-5) is skipped and we go straight to chat fallback
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
            threshold = int(os.getenv("DISCOVERY_CB_THRESHOLD", "3"))
            if st["failures"] >= threshold:
                cooldown = int(os.getenv("DISCOVERY_CB_COOLDOWN_SECONDS", "600"))
                st["open_until"] = cls._now() + cooldown

    @classmethod
    def is_open(cls, key: str) -> bool:
        st = cls._state.get(key)
        if not st:
            return False
        if st["open_until"] <= cls._now():
            return False
        return True


def _safe_chat_call(client, timeout_seconds: int = 60, max_retries: int = 1, **kwargs):
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(client.responses.create, **kwargs)
        try:
            return fut.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            raise TimeoutError(f"Responses call timed out after {timeout_seconds}s")


def _extract_text_from_responses(response) -> Optional[str]:
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
    def __init__(self, api_key: Optional[str] = None):
        from openai import OpenAI  # Local import to avoid hard dep at import time
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                self.api_key = os.getenv("OPENAI_API_KEY")
            except Exception:
                pass
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=self.api_key)
        self._responses_capable = None  # Lazy probe

    def _probe_responses(self) -> bool:
        if self._responses_capable is not None:
            return self._responses_capable
        if os.getenv('DISCOVERY_FORCE_CHAT_COMPLETIONS', 'false').lower() == 'true':
            self._responses_capable = False
            return False
        try:
            _ = _safe_responses_call(self.client, timeout_seconds=6, model="gpt-5", input="ping", reasoning={"effort": "minimal"}, text={"verbosity": "low"})
            self._responses_capable = True
        except Exception:
            self._responses_capable = False
        return self._responses_capable

    @staticmethod
    def estimate_tokens(text: str, model: str = "gpt-4o") -> int:
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
        return int(min(20 + 0.002 * tokens, cap))

    def choose_and_call(
        self,
        key_name: str,
        prompt: str,
        schema: Optional[dict] = None,
        enforce_schema: bool = False,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        meta: Dict[str, Any] = {"api_used": None, "model": None, "token_usage": 0, "token_estimate": 0}

        # Decide whether to try Responses first
        breaker_open = CircuitBreaker.is_open(key_name)
        meta["breaker_open"] = breaker_open
        use_responses = (not breaker_open) and self._probe_responses()

        # 1) Try GPT-5 Responses if allowed
        if use_responses:
            try:
                tokens = LLMClient.estimate_tokens(prompt, "gpt-5")
                resp = _safe_responses_call(
                    self.client,
                    timeout_seconds=LLMClient.adaptive_timeout(tokens, cap=75),
                    model="gpt-5",
                    input=prompt,
                    reasoning={"effort": "minimal"},
                    text={"verbosity": "low"}
                )
                raw = _extract_text_from_responses(resp)
                if not raw:
                    raise Exception("Failed to extract JSON from GPT-5 response")
                meta.update({"api_used": "responses_api", "model": "gpt-5", "token_estimate": tokens})
                CircuitBreaker.record_result(key_name, success=True)
                # usage is not standardized; leave token_usage as 0 if missing
                try:
                    meta["token_usage"] = resp.usage.total_tokens  # type: ignore
                except Exception:
                    pass
                return raw, meta
            except Exception:
                CircuitBreaker.record_result(key_name, success=False)

        # 2) Fallback to GPT-4o Chat with optional schema enforcement
        try:
            kwargs = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a senior brand strategist. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
            }
            if enforce_schema and schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "Schema", "schema": schema, "strict": True},
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}

            tokens = LLMClient.estimate_tokens(prompt, "gpt-4o")
            chat_resp = _safe_chat_call(self.client, timeout_seconds=LLMClient.adaptive_timeout(tokens, cap=75), max_retries=1, **kwargs)
            raw = getattr(chat_resp.choices[0].message, "content", None)
            meta.update({
                "api_used": "chat_completions",
                "model": getattr(chat_resp, 'model', 'gpt-4o'),
                "token_usage": getattr(getattr(chat_resp, 'usage', None), 'total_tokens', 0),
                "token_estimate": tokens
            })
            CircuitBreaker.record_result(key_name, success=True)
            return raw, meta
        except Exception:
            CircuitBreaker.record_result(key_name, success=False)

        # 3) Final fallback to GPT-4o-mini (fast)
        try:
            kwargs = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a senior brand strategist. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"}
            }
            tokens = LLMClient.estimate_tokens(prompt, "gpt-4o-mini")
            mini_resp = _safe_chat_call(self.client, timeout_seconds=LLMClient.adaptive_timeout(tokens, cap=60), max_retries=0, **kwargs)
            raw = getattr(mini_resp.choices[0].message, "content", None)
            meta.update({
                "api_used": "chat_completions_fallback",
                "model": getattr(mini_resp, 'model', 'gpt-4o-mini'),
                "token_usage": getattr(getattr(mini_resp, 'usage', None), 'total_tokens', 0),
                "token_estimate": tokens
            })
            CircuitBreaker.record_result(key_name, success=True)
            return raw, meta
        except Exception:
            CircuitBreaker.record_result(key_name, success=False)
            raise


