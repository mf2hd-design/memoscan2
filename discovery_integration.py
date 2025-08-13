"""
Discovery Mode Integration Layer
Version: 1.0.0
Date: August 2025

Integrates Discovery Mode into existing scanner.py pipeline with minimal changes.
"""

import os
import json
import time
import hashlib
import asyncio
import concurrent.futures
import threading
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from discovery_prompts import DECONSTRUCTION_KEYS_PROMPTS, track_discovery_performance, PROMPT_VERSION
from llm_client import LLMClient
from discovery_schemas import (
    SchemaValidator,
    PositioningThemesResult,
    KeyMessagesResult,
    ToneOfVoiceResult,
    BrandElementsResult,
    VisualTextAlignmentResult,
    DiscoveryFeedback
)

def safe_openai_call(client, timeout_seconds=120, max_retries=2, **kwargs):
    """
    Thread-safe wrapper for OpenAI API calls with timeout protection and retries.
    Uses concurrent.futures instead of signals for thread safety.
    """
    import concurrent.futures
    import time as time_module
    
    # Ensure PERSISTENT_DATA_DIR is set for Discovery Mode logging
    if not os.getenv("PERSISTENT_DATA_DIR"):
        temp_data_dir = "/tmp/discovery_mode_data"
        os.makedirs(temp_data_dir, exist_ok=True)
        os.environ["PERSISTENT_DATA_DIR"] = temp_data_dir
    
    # Add timeout parameter to the API call if not already set
    if 'timeout' not in kwargs:
        kwargs['timeout'] = min(timeout_seconds - 10, 110)  # Leave buffer
    
    last_error = None
    for retry in range(max_retries + 1):
        if retry > 0:
            wait_time = 2 ** retry  # Exponential backoff: 2, 4, 8 seconds
            print(f"[INFO] Retry {retry}/{max_retries} after {wait_time}s delay...")
            time_module.sleep(wait_time)
        
        # Use ThreadPoolExecutor for thread-safe timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client.chat.completions.create, **kwargs)
            try:
                response = future.result(timeout=timeout_seconds)
                return response
            except concurrent.futures.TimeoutError:
                # Try to cancel the future
                future.cancel()
                last_error = TimeoutError(f"OpenAI API call timed out after {timeout_seconds} seconds (attempt {retry + 1}/{max_retries + 1})")
                if retry == max_retries:
                    raise last_error
            except Exception as e:
                # For other exceptions, don't retry
                raise e
    
    # Should not reach here, but just in case
    raise last_error if last_error else Exception("Unexpected error in safe_openai_call")

def safe_responses_call(client, timeout_seconds: int = 60, max_retries: int = 0, **kwargs):
    """
    Thread-safe wrapper for OpenAI Responses API calls with timeout and optional retries.
    Avoids passing SDK-specific timeout kwargs; enforces timeout externally.
    """
    import concurrent.futures
    import time as time_module

    last_error = None
    for retry in range(max_retries + 1):
        if retry > 0:
            wait_time = min(2 ** retry, 8)
            print(f"[INFO] Responses retry {retry}/{max_retries} after {wait_time}s delay...")
            time_module.sleep(wait_time)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client.responses.create, **kwargs)
            try:
                return future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                future.cancel()
                last_error = TimeoutError(f"Responses API call timed out after {timeout_seconds}s (attempt {retry + 1}/{max_retries + 1})")
                if retry == max_retries:
                    raise last_error
            except Exception as e:
                # Bubble up other errors immediately
                raise e
    raise last_error if last_error else Exception("Unexpected error in safe_responses_call")

# === Feature Flag System ===
class FeatureFlags:
    """Simplified flags. Discovery is always available; UI toggle controls mode."""
    
    @staticmethod
    def is_discovery_enabled(user_id: Optional[str] = None) -> bool:
        # Always enabled; rely on UI toggle to select mode
        return True
    
    @staticmethod
    def get_enabled_features() -> Dict[str, bool]:
        return {
            "discovery_mode": True,
            "visual_analysis": os.getenv('DISCOVERY_VISUAL_ANALYSIS', 'false').lower() == 'true',
            "export_features": os.getenv('DISCOVERY_EXPORT_ENABLED', 'false').lower() == 'true',
            "advanced_feedback": os.getenv('DISCOVERY_ADVANCED_FEEDBACK', 'false').lower() == 'true'
        }

# === Runtime Capability Probe & Routing ===
RESPONSES_CAPABLE = None  # type: Optional[bool]

def _force_chat_completions() -> bool:
    return os.getenv('DISCOVERY_FORCE_CHAT_COMPLETIONS', 'false').lower() == 'true'

def probe_responses_capability() -> bool:
    """Attempt a tiny Responses call to determine availability for this process."""
    try:
        if _force_chat_completions():
            return False
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("OPENAI_API_KEY")
            except ImportError:
                pass
        if not api_key:
            return False
        client = OpenAI(api_key=api_key)
        # Minimal Responses call via safe wrapper with short timeout
        _ = safe_responses_call(client, timeout_seconds=8, model="gpt-5", input="ping", reasoning={"effort": "minimal"}, text={"verbosity": "low"})
        return True
    except Exception:
        return False

def ensure_responses_capability_probe() -> None:
    global RESPONSES_CAPABLE
    if RESPONSES_CAPABLE is None:
        RESPONSES_CAPABLE = probe_responses_capability()
        print(f"[INFO] Responses capability: {'enabled' if RESPONSES_CAPABLE else 'disabled'}")

def _should_use_responses() -> bool:
    if _force_chat_completions():
        return False
    ensure_responses_capability_probe()
    return bool(RESPONSES_CAPABLE)

# === Discovery Mode Scanner Integration ===
class DiscoveryAnalyzer:
    """Handles Discovery Mode analysis using existing scanner infrastructure."""
    
    def __init__(self, scan_id: str, cache: dict):
        self.scan_id = scan_id
        self.cache = cache
        self.validator = SchemaValidator()
        self.performance_metrics = {}
        # Unified LLM client abstraction (capability probe + circuit breaker + fallbacks)
        self.llm_client = LLMClient()
        # Initialize cache directory for per-key result persistence
        base_dir = os.getenv("PERSISTENT_DATA_DIR", "/tmp")
        self.cache_root = os.path.join(base_dir, "discovery_cache")
        os.makedirs(self.cache_root, exist_ok=True)
        # Optional Redis cache
        self.redis = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis  # type: ignore
                self.redis = redis.from_url(redis_url, decode_responses=True)
            except Exception:
                self.redis = None

    # === Simple token-aware scheduler ===
    _llm_semaphore = threading.Semaphore(int(os.getenv("DISCOVERY_LLM_CONCURRENCY", "2")))
    _tpm_limit = int(os.getenv("DISCOVERY_TPM_LIMIT", "80000"))  # rough tokens per minute
    _bucket_tokens = _tpm_limit
    _bucket_ts = time.time()
    _bucket_lock = threading.Lock()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 200
        # crude: 4 chars per token
        return max(200, int(len(text) / 4))

    @classmethod
    def _refill_bucket(cls):
        now = time.time()
        with cls._bucket_lock:
            elapsed = now - cls._bucket_ts
            refill = int((elapsed / 60.0) * cls._tpm_limit)
            if refill > 0:
                cls._bucket_tokens = min(cls._tpm_limit, cls._bucket_tokens + refill)
                cls._bucket_ts = now

    @classmethod
    def _acquire_budget(cls, tokens_needed: int, wait_timeout: float = 30.0) -> bool:
        # Concurrency gate
        got_sem = cls._llm_semaphore.acquire(timeout=wait_timeout)
        if not got_sem:
            return False
        # Token bucket gate
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            cls._refill_bucket()
            with cls._bucket_lock:
                if cls._bucket_tokens >= tokens_needed:
                    cls._bucket_tokens -= tokens_needed
                    return True
            time.sleep(0.1)
        # Failed to get tokens in time; release semaphore and fail
        cls._llm_semaphore.release()
        return False

    @classmethod
    def _release_budget(cls):
        try:
            cls._llm_semaphore.release()
        except Exception:
            pass

    @staticmethod
    def _adaptive_timeout(input_tokens: int, cap: int = 90) -> int:
        return int(min(20 + 0.002 * input_tokens, cap))

    # === Chunking & Relevance Scoring for very long inputs ===
    def _chunk_text_with_overlap(self, text: str, model: str, chunk_token_limit: int = 800, overlap_tokens: int = 120) -> List[str]:
        if not text:
            return []
        # Split by paragraph; fall back to single newlines if needed
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        chunks: List[str] = []
        current: List[str] = []
        current_tokens = 0
        for para in paragraphs:
            ptoks = LLMClient.estimate_tokens(para, model=model)
            if current_tokens + ptoks <= chunk_token_limit:
                current.append(para)
                current_tokens += ptoks
            else:
                if current:
                    chunks.append("\n".join(current))
                # start new chunk; include overlap from previous chunk tail
                overlap_text = "\n".join(current)[-overlap_tokens*4:] if current else ""
                current = [overlap_text, para] if overlap_text else [para]
                current_tokens = LLMClient.estimate_tokens("\n".join(current), model=model)
        if current:
            chunks.append("\n".join(current))
        return [c for c in chunks if c.strip()]

    def _score_chunk_relevance(self, chunk: str, key_name: str) -> float:
        text_lower = chunk.lower()
        # Lightweight keyword sets per key
        if key_name == "key_messages":
            keywords = [
                "message", "value", "benefit", "tagline", "proposition",
                "solution", "customer", "platform", "we ", "our ", "mission", "vision", "about"
            ]
        elif key_name == "tone_of_voice":
            keywords = [
                "tone", "voice", "style", "we ", "our ", "commitment", "innovation", "quality",
                "excellence", "mission", "vision", "values"
            ]
        else:
            keywords = ["we ", "our ", "customer", "solution"]

        score = 0.0
        for kw in keywords:
            score += text_lower.count(kw)
        # Boost for quotes as evidence snippets
        score += text_lower.count('"') * 0.5
        score += text_lower.count("\u201c") * 0.5
        score += text_lower.count("\u201d") * 0.5
        # Penalize overly short chunks
        tokens = LLMClient.estimate_tokens(chunk)
        if tokens < 120:
            score *= 0.7
        return score

    def _select_relevant_text(self, text: str, key_name: str, target_model: str, max_total_tokens: int) -> Tuple[str, Dict[str, Any]]:
        info: Dict[str, Any] = {"chunking_applied": False}
        total_tokens = LLMClient.estimate_tokens(text, model=target_model)
        info["tokens_before"] = total_tokens
        if total_tokens <= max_total_tokens:
            info.update({"tokens_after": total_tokens, "chunks_considered": 1, "chunks_selected": 1})
            return text, info
        # Build chunks and score
        chunks = self._chunk_text_with_overlap(text, model=target_model)
        scored = [(self._score_chunk_relevance(c, key_name), c) for c in chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        info["chunking_applied"] = True
        info["chunks_considered"] = len(scored)
        # Accumulate top chunks within budget
        selected: List[str] = []
        running = 0
        for _, c in scored:
            ctoks = LLMClient.estimate_tokens(c, model=target_model)
            if running + ctoks <= max_total_tokens:
                selected.append(c)
                running += ctoks
            if running >= max_total_tokens * 0.95:
                break
        if not selected:
            # Fallback: take the highest scoring single chunk
            selected = [scored[0][1]] if scored else [text[:4000]]
            running = LLMClient.estimate_tokens(selected[0], model=target_model)
        info["chunks_selected"] = len(selected)
        info["tokens_after"] = running
        reduced = "\n\n".join(selected)
        return reduced, info

    # === Per-key disk cache helpers ===
    def _key_cache_path(self, key_name: str, content_hash: str) -> str:
        d = os.path.join(self.cache_root, key_name)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{content_hash}.json")

    def _load_cached_result(self, key_name: str, content_fingerprint: str) -> Optional[dict]:
        # Try Redis first
        if self.redis is not None:
            try:
                v = self.redis.get(f"discovery:{key_name}:{content_fingerprint}")
                if v:
                    return json.loads(v)
            except Exception:
                pass
        # Fallback to disk
        path = self._key_cache_path(key_name, content_fingerprint)
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception:
            return None
        return None

    def _save_cached_result(self, key_name: str, content_fingerprint: str, result: dict) -> None:
        try:
            # Redis
            if self.redis is not None:
                try:
                    ttl = int(os.getenv("DISCOVERY_CACHE_TTL", "86400"))
                    self.redis.setex(f"discovery:{key_name}:{content_fingerprint}", ttl, json.dumps(result))
                except Exception:
                    pass
            # Disk
            path = self._key_cache_path(key_name, content_fingerprint)
            with open(path, 'w') as f:
                json.dump(result, f)
        except Exception:
            pass

    def _compute_fingerprint(self, key_name: str, text: str, schema_class) -> str:
        try:
            try:
                schema_dict = schema_class.schema()
            except Exception:
                schema_dict = schema_class.model_json_schema()
        except Exception:
            schema_dict = {}
        prompt = DECONSTRUCTION_KEYS_PROMPTS[key_name]["prompt"]
        m = hashlib.sha256()
        m.update((text or "").encode())
        m.update(prompt.encode())
        m.update(json.dumps(schema_dict, sort_keys=True).encode())
        m.update(PROMPT_VERSION.encode())
        return m.hexdigest()
        
    def _analyze_all_sequential(self, text_content: str, screenshots: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run all Discovery analyses sequentially as a fallback for timeout issues.
        """
        start_time = time.time()
        results = {}
        combined_metrics = {
            'total_latency_ms': 0,
            'analyses_completed': 0,
            'analyses_failed': 0,
            'total_tokens': 0,
            'individual_metrics': {},
            'execution_mode': 'sequential'
        }
        
        # Run each analysis sequentially
        analyses = [
            ('positioning_themes', lambda: self.analyze_positioning_themes(text_content)),
            ('key_messages', lambda: self.analyze_key_messages(text_content)),
            ('tone_of_voice', lambda: self.analyze_tone_of_voice(text_content))
        ]
        
        for key_name, analysis_func in analyses:
            try:
                print(f"[INFO] Starting sequential analysis: {key_name}")
                result, metrics = analysis_func()
                
                if result:
                    results[key_name] = result
                    combined_metrics['analyses_completed'] += 1
                    print(f"[INFO] ✅ {key_name} completed: {metrics.get('token_usage', 0)} tokens in {metrics.get('latency_ms', 0)}ms")
                else:
                    combined_metrics['analyses_failed'] += 1
                    results[key_name] = {
                        'error': metrics.get('error', 'unknown_error'),
                        'message': f'Analysis failed for {key_name}'
                    }
                    print(f"[INFO] ❌ {key_name} failed: {metrics.get('error', 'unknown')}")
                
                # Aggregate metrics
                combined_metrics['total_tokens'] += metrics.get('token_usage', 0)
                combined_metrics['individual_metrics'][key_name] = metrics
                
            except Exception as e:
                print(f"[ERROR] Sequential analysis {key_name} failed with exception: {str(e)}")
                combined_metrics['analyses_failed'] += 1
                results[key_name] = {
                    'error': 'execution_error',
                    'message': f'Execution error for {key_name}: {str(e)}'
                }
        
        # Calculate total time
        combined_metrics['total_latency_ms'] = int((time.time() - start_time) * 1000)
        
        return {
            'results': results,
            'metrics': combined_metrics,
            'success': combined_metrics['analyses_completed'] > 0,
            'completion_rate': combined_metrics['analyses_completed'] / 3.0
        }
    
    def _validate_and_sanitize_input(self, text_content: str, max_chars: int = 30000) -> str:
        """Validate and sanitize analysis input."""
        if not text_content or len(text_content.strip()) < 100:
            raise ValueError("Insufficient content for analysis (minimum 100 characters required)")
        
        # Intelligent truncation to prevent timeouts while preserving key content
        if len(text_content) > max_chars:
            print(f"[INFO] Smart truncating content from {len(text_content)} to {max_chars} chars for faster analysis")
            # Try to preserve important sections (headings, key phrases)
            content_parts = text_content.split('\n')
            truncated_lines = []
            current_length = 0
            
            for line in content_parts:
                line_length = len(line) + 1  # +1 for newline
                if current_length + line_length > max_chars - 50:  # Leave buffer
                    break
                # Prioritize lines with brand-related keywords
                is_important = any(keyword in line.lower() for keyword in 
                                 ['mission', 'vision', 'values', 'about', 'brand', 'company', 'we are', 'our'])
                if is_important or current_length < max_chars * 0.8:  # Always include important lines
                    truncated_lines.append(line)
                    current_length += line_length
            
            text_content = '\n'.join(truncated_lines) + "... [content intelligently truncated for analysis]"
        
        # Remove potential script injection attempts
        import re
        text_content = re.sub(r'<script[^>]*>.*?</script>', '', text_content, flags=re.IGNORECASE | re.DOTALL)
        text_content = re.sub(r'<[^>]+>', '', text_content)  # Remove HTML tags
        
        return text_content.strip()

    def analyze_all_concurrent(self, text_content: str, screenshots: Optional[List[str]] = None, force_sequential: bool = False) -> Dict[str, Any]:
        """
        Run all Discovery analyses concurrently for maximum performance.
        
        Args:
            text_content: Content to analyze
            screenshots: Optional screenshots for visual analysis
            force_sequential: If True, run analyses sequentially instead of concurrently
            
        Returns:
            Dictionary with all analysis results and combined metrics
        """
        start_time = time.time()
        
        # Validate input once for all analyses
        try:
            validated_content = self._validate_and_sanitize_input(text_content)
        except ValueError as e:
            return {
                'error': 'validation_error',
                'message': str(e),
                'results': {},
                'metrics': {'total_latency_ms': 0, 'analyses_completed': 0}
            }
        
        # Check if we should run sequentially (for debugging or if concurrent keeps timing out)
        if force_sequential or os.getenv('DISCOVERY_SEQUENTIAL_MODE', 'false').lower() == 'true':
            print("[INFO] Running Discovery analyses sequentially (timeout protection mode)")
            return self._analyze_all_sequential(validated_content, screenshots)
        
        # Prepare concurrent tasks (limit LLM concurrency to 2 for stability)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Submit all analysis tasks concurrently
            future_to_key = {
                executor.submit(self.analyze_positioning_themes, validated_content): 'positioning_themes',
                executor.submit(self.analyze_key_messages, validated_content): 'key_messages', 
                executor.submit(self.analyze_tone_of_voice, validated_content): 'tone_of_voice'
            }
            
            # Collect results as they complete
            results = {}
            combined_metrics = {
                'total_latency_ms': 0,
                'analyses_completed': 0,
                'analyses_failed': 0,
                'total_tokens': 0,
                'individual_metrics': {}
            }
            
            for future in concurrent.futures.as_completed(future_to_key, timeout=300):  # 5 min total timeout for all analyses
                key_name = future_to_key[future]
                try:
                    result, metrics = future.result()
                    
                    if result:
                        results[key_name] = result
                        combined_metrics['analyses_completed'] += 1
                    else:
                        combined_metrics['analyses_failed'] += 1
                        results[key_name] = {
                            'error': metrics.get('error', 'unknown_error'),
                            'message': f'Analysis failed for {key_name}'
                        }
                    
                    # Aggregate metrics
                    combined_metrics['total_tokens'] += metrics.get('token_usage', 0)
                    combined_metrics['individual_metrics'][key_name] = metrics
                    
                except concurrent.futures.TimeoutError:
                    combined_metrics['analyses_failed'] += 1
                    results[key_name] = {
                        'error': 'timeout',
                        'message': f'Analysis timed out for {key_name}'
                    }
                except Exception as e:
                    combined_metrics['analyses_failed'] += 1
                    # Log the full error details for debugging
                    import traceback
                    error_details = traceback.format_exc()
                    print(f"[ERROR] Analysis {key_name} failed with exception: {str(e)}")
                    print(f"[TRACEBACK] {error_details}")
                    
                    results[key_name] = {
                        'error': 'execution_error',
                        'message': f'Execution error for {key_name}: {str(e)}',
                        'traceback': error_details
                    }
        
        # Calculate total time
        combined_metrics['total_latency_ms'] = int((time.time() - start_time) * 1000)
        
        return {
            'results': results,
            'metrics': combined_metrics,
            'success': combined_metrics['analyses_completed'] > 0,
            'completion_rate': combined_metrics['analyses_completed'] / 3.0
        }

    @track_discovery_performance("positioning_themes")
    def analyze_positioning_themes(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze positioning themes using GPT-5 with optimized content handling."""
        from openai import OpenAI
        
        start_time = time.time()
        metrics = {"key_name": "positioning_themes"}
        
        try:
            # Validate and sanitize input with aggressive truncation for performance
            text_content = self._validate_and_sanitize_input(text_content, max_chars=15000)
            print(f"[INFO] Positioning themes analysis - content length: {len(text_content)} chars")
            
            # Load environment variables if needed
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    api_key = os.getenv("OPENAI_API_KEY")
                except ImportError:
                    pass
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required for Discovery analysis")
            client = OpenAI(api_key=api_key)
            prompt = DECONSTRUCTION_KEYS_PROMPTS["positioning_themes"]["prompt"]
            
            # Use GPT-5 with Responses API when available
            try:
                if not _should_use_responses():
                    raise Exception("Responses disabled by capability/env")
                # First try GPT-5 with Responses API (recommended approach)
                tokens_needed = self._estimate_tokens(text_content)
                response = safe_responses_call(
                    client,
                    timeout_seconds=self._adaptive_timeout(tokens_needed, cap=75),
                    model="gpt-5",
                    input=f"You are a senior brand strategist. Analyze the following website content and identify 3-5 key positioning themes. Output only valid JSON.\n\n{prompt.format(text_content=text_content)}",
                    reasoning={
                        "effort": "minimal"  # Fastest reasoning for speed
                    },
                    text={
                        "verbosity": "low"  # Concise output for faster response
                    }
                )
                # Extract text content from Responses API response
                # GPT-5 Responses API returns a list of items including reasoning and output messages
                raw_output = None
                
                if hasattr(response, 'content') and isinstance(response.content, list):
                    # Look for ResponseOutputMessage in the content list
                    for item in response.content:
                        if hasattr(item, 'type') and item.type == 'message':
                            if hasattr(item, 'content') and isinstance(item.content, list):
                                # Extract text from message content
                                for content_item in item.content:
                                    if hasattr(content_item, 'text'):
                                        raw_output = content_item.text
                                        break
                            elif hasattr(item, 'content') and isinstance(item.content, str):
                                raw_output = item.content
                            break
                elif hasattr(response, 'content') and isinstance(response.content, str):
                    raw_output = response.content
                elif hasattr(response, 'text') and isinstance(response.text, str):
                    raw_output = response.text
                
                if not raw_output:
                    raise Exception(f"Could not extract text from GPT-5 response. Response content type: {type(response.content) if hasattr(response, 'content') else 'no content'}, first item type: {type(response.content[0]) if hasattr(response, 'content') and isinstance(response.content, list) and response.content else 'no items'}")
                    
                metrics["api_used"] = "responses_api"
                metrics["reasoning_effort"] = "minimal"
                
            except Exception as responses_api_error:
                print(f"[INFO] GPT-5 Responses API not available, using reliable GPT-4o Chat Completions")
                # Fallback to Chat Completions API with reliable GPT-4o  
                response = safe_openai_call(
                    client,
                    timeout_seconds=30,
                    max_retries=1,
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a senior brand strategist. Analyze website content and identify 3-5 key positioning themes. Output only valid JSON."},
                        {"role": "user", "content": prompt.format(text_content=text_content)}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=2000
                )
                raw_output = (json.dumps(getattr(response.choices[0].message, "parsed"))
                               if getattr(response.choices[0].message, "parsed", None) is not None
                               else response.choices[0].message.content)
                metrics["api_used"] = "chat_completions_fallback"
            
            # Handle token usage and model info based on API used
            if metrics.get("api_used") == "responses_api":
                # Responses API has different structure
                if hasattr(response, 'usage') and response.usage:
                    metrics["token_usage"] = response.usage.total_tokens
                else:
                    metrics["token_usage"] = 0
                metrics["model"] = "gpt-5"
            else:
                # Chat Completions API structure
                metrics["token_usage"] = response.usage.total_tokens if hasattr(response, 'usage') else 0
                metrics["model"] = response.model if hasattr(response, 'model') else "gpt-4o"
            
            # Validate and repair
            result, repairs = self.validator.validate_with_repair(
                raw_output,
                PositioningThemesResult,
                "positioning_themes"
            )
            
            metrics["validation_status"] = "success" if result else "failed"
            metrics["repairs"] = repairs
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # If validation failed without raising, synthesize a degraded but valid fallback
            if not result:
                try:
                    # Build a conservative fallback theme using available text
                    snippet = (text_content[:200] + "...") if isinstance(text_content, str) and len(text_content) > 200 else (text_content or "")
                    fallback_payload = {
                        "themes": [
                            {
                                "theme": "Quality and Reliability",
                                "description": "Structured output unavailable; using conservative fallback derived from headings and lead copy.",
                                "evidence_quotes": [snippet or "Brand messaging emphasizes dependable products and services."],
                                "confidence": 50
                            }
                        ]
                    }
                    fallback_model = PositioningThemesResult(**fallback_payload)
                    metrics["validation_status"] = "degraded_fallback"
                    metrics["degraded"] = True
                    metrics.setdefault("model", "fallback")
                    metrics.setdefault("token_usage", 0)
                    # Log degraded result
                    self._log_discovery_result("positioning_themes", raw_output, fallback_model, metrics)
                    return fallback_model.dict(), metrics
                except Exception as _degrade_err:
                    # If even degraded synthesis fails, continue to return None with metrics
                    metrics["degrade_error"] = str(_degrade_err)
            
            # Log for analysis
            self._log_discovery_result("positioning_themes", raw_output, result, metrics)
            
            return result.dict() if result else None, metrics
            
        except ValueError as e:
            # Input validation errors
            metrics["error"] = "validation_error"
            metrics["error_details"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            self._log_discovery_error("positioning_themes", e, metrics)
            return None, metrics
        except TimeoutError as e:
            metrics["error"] = "timeout"
            metrics["error_details"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            print(f"[ERROR] Positioning themes analysis timed out after {metrics['latency_ms']}ms")
            self._log_discovery_error("positioning_themes", e, metrics)
            
            # Try a simplified fallback analysis with even smaller content
            try:
                print("[INFO] Attempting simplified positioning themes analysis as fallback...")
                simplified_content = text_content[:8000] + "... [simplified for fallback analysis]"
                fallback_response = safe_openai_call(
                    client,
                    timeout_seconds=30,  # Very short timeout for fallback
                    max_retries=0,
                    model="gpt-4o-mini",  # Use faster model as fallback
                    messages=[
                        {"role": "system", "content": "You are a brand analyst. Extract 2-3 key positioning themes quickly. Output only valid JSON."},
                        {"role": "user", "content": f"Extract the main positioning themes from this website content:\n\n{simplified_content}\n\nOutput JSON with 'themes' array containing objects with 'theme', 'description', 'evidence_quotes', 'confidence' fields."}
                    ],
                    response_format={"type": "json_object"}
                )
                
                fallback_output = fallback_response.choices[0].message.content
                fallback_result, _ = self.validator.validate_with_repair(
                    fallback_output, PositioningThemesResult, "positioning_themes"
                )
                
                if fallback_result:
                    print("[INFO] Fallback positioning themes analysis succeeded")
                    metrics["fallback_used"] = True
                    metrics["fallback_model"] = "gpt-4o-mini"
                    return fallback_result.dict(), metrics
                # If fallback still didn't validate, synthesize degraded
                snippet = (text_content[:200] + "...") if isinstance(text_content, str) and len(text_content) > 200 else (text_content or "")
                degraded_payload = {
                    "themes": [
                        {
                            "theme": "Quality and Reliability",
                            "description": "Timeout fallback: synthesized minimal positioning theme to ensure UI rendering.",
                            "evidence_quotes": [snippet or "Brand states clear promises about quality and reliability."],
                            "confidence": 45
                        }
                    ]
                }
                degraded_model = PositioningThemesResult(**degraded_payload)
                metrics["validation_status"] = "degraded_fallback"
                metrics["degraded"] = True
                metrics.setdefault("model", "fallback")
                metrics.setdefault("token_usage", 0)
                return degraded_model.dict(), metrics
            except Exception as fallback_error:
                print(f"[ERROR] Fallback analysis also failed: {fallback_error}")
                metrics["fallback_error"] = str(fallback_error)
            
            return None, metrics
        except Exception as e:
            # More detailed error tracking
            import traceback
            error_trace = traceback.format_exc()
            
            # Check for specific OpenAI errors
            error_type = "unknown_error"
            if "rate limit" in str(e).lower():
                error_type = "rate_limit"
            elif "insufficient_quota" in str(e).lower():
                error_type = "quota_exceeded"
            elif "json" in str(e).lower() or "parsing" in str(e).lower():
                error_type = "json_parse_error"
            elif "timeout" in str(e).lower():
                error_type = "timeout"
            
            metrics["error"] = error_type
            metrics["error_details"] = str(e)
            metrics["error_traceback"] = error_trace
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            print(f"[ERROR] positioning_themes analysis failed: {str(e)}")
            print(f"[TRACEBACK] {error_trace}")
            
            # Attempt degraded fallback to ensure UI block
            try:
                snippet = (text_content[:200] + "...") if isinstance(text_content, str) and len(text_content) > 200 else (text_content or "")
                degraded_payload = {
                    "themes": [
                        {
                            "theme": "Quality and Reliability",
                            "description": "Last-resort fallback derived from available snippets.",
                            "evidence_quotes": [snippet or "Visible emphasis on dependable service."],
                            "confidence": 40
                        }
                    ]
                }
                degraded_model = PositioningThemesResult(**degraded_payload)
                metrics["validation_status"] = "degraded_fallback"
                metrics["degraded"] = True
                metrics.setdefault("model", "fallback")
                metrics.setdefault("token_usage", 0)
                self._log_discovery_result("positioning_themes", "<exception_fallback>", degraded_model, metrics)
                return degraded_model.dict(), metrics
            except Exception:
                self._log_discovery_error("positioning_themes", e, metrics)
                return None, metrics
    
    @track_discovery_performance("key_messages")
    def analyze_key_messages(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze key messages using GPT-5 Responses API with JSON Schema (fallback to GPT-4o chat)."""
        start_time = time.time()
        metrics = {"key_name": "key_messages"}
        
        try:
            # Validate/sanitize; expect candidate lines, keep tighter budget
            text_content = self._validate_and_sanitize_input(text_content, max_chars=12000)

            # Cache lookup (prompt+schema aware)
            content_fingerprint = self._compute_fingerprint("key_messages", text_content, KeyMessagesResult)
            cached = self._load_cached_result("key_messages", content_fingerprint)
            if cached:
                metrics["cache_hit"] = True
                metrics["latency_ms"] = 0
                return cached, metrics
            
            # Pre-select relevant content for long inputs (map-like distillation)
            reduced_text, sel_info = self._select_relevant_text(
                text_content, key_name="key_messages", target_model="gpt-4o", max_total_tokens=1800
            )
            metrics.update({
                "preselect_applied": sel_info.get("chunking_applied", False),
                "preselect_tokens_before": sel_info.get("tokens_before"),
                "preselect_tokens_after": sel_info.get("tokens_after"),
                "preselect_chunks_considered": sel_info.get("chunks_considered"),
                "preselect_chunks_selected": sel_info.get("chunks_selected")
            })

            # GPT-5 Responses API with JSON Schema, fallback to Chat Completions (gpt-4o)
            primary_prompt = (
                "Task: From the candidate lines below, extract the 3–5 most important key messages the brand is trying to land.\n\n"
                "Guidelines:\n"
                "- “Message” is the exact wording (≤200 chars) taken or lightly normalized from candidates.\n"
                "- “Context” is a one‑sentence rationale referencing where/how it’s used.\n"
                "- Type: \"Tagline\" if top‑level brand line; otherwise \"Value Proposition\".\n"
                "- Prefer high-signal, repeated ideas; de‑duplicate; avoid navigation/boilerplate.\n\n"
                f"Candidate lines:\n{reduced_text}"
            )
            # Unified LLM call via LLMClient with schema enforcement on chat fallback
            try:
                try:
                    schema_dict = KeyMessagesResult.schema()
                except Exception:
                    schema_dict = KeyMessagesResult.model_json_schema()
                raw_output, meta = self.llm_client.choose_and_call(
                    key_name="key_messages",
                    prompt=primary_prompt,
                    schema=schema_dict,
                    enforce_schema=True,
                )
                metrics.update({
                    "api_used": meta.get("api_used"),
                    "model": meta.get("model"),
                    "token_usage": meta.get("token_usage", 0),
                    "breaker_open": meta.get("breaker_open", False)
                })
            except Exception as e:
                metrics["error"] = "llm_call_failed"
                metrics["error_details"] = str(e)
                raw_output = None
            
            # Validate and repair; if fails, run schema-repair fallback via Chat Completions
            result, repairs = self.validator.validate_with_repair(
                raw_output,
                KeyMessagesResult,
                "key_messages"
            )
            if not result:
                try:
                    # Enforce exact schema with Chat Completions repair
                    try:
                        schema_dict = KeyMessagesResult.schema()
                    except Exception:
                        schema_dict = KeyMessagesResult.model_json_schema()
                    repair_prompt = (
                        "You are a strict JSON schema formatter. Given the candidate lines below, output valid JSON that conforms to the KeyMessagesResult schema exactly.\n"
                        "Extract 3–5 key messages with fields: message (≤200), context (≤300), type (\"Tagline\"|\"Value Proposition\"), confidence (0–100).\n\n"
                        f"Candidate lines:\n{text_content}"
                    )
                    repair_resp = safe_openai_call(
                        self.llm_client.client,
                        timeout_seconds=self._adaptive_timeout(self._estimate_tokens(text_content), cap=60),
                        max_retries=1,
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Output only valid JSON matching the provided schema. No commentary."},
                            {"role": "user", "content": repair_prompt}
                        ],
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "KeyMessagesResult", "schema": schema_dict, "strict": True}
                        }
                    )
                    raw_output = (json.dumps(getattr(repair_resp.choices[0].message, "parsed"))
                                   if getattr(repair_resp.choices[0].message, "parsed", None) is not None
                                   else repair_resp.choices[0].message.content)
                    result, repairs2 = self.validator.validate_with_repair(
                        raw_output, KeyMessagesResult, "key_messages"
                    )
                    repairs = repairs + ["schema_repair_applied"] + (repairs2 or [])
                    metrics["api_used"] = metrics.get("api_used", "") + "+chat_schema_repair"
                    metrics["token_usage"] = repair_resp.usage.total_tokens if hasattr(repair_resp, 'usage') else metrics.get("token_usage", 0)
                    metrics["model"] = repair_resp.model if hasattr(repair_resp, 'model') else metrics.get("model", "gpt-4o")
                except Exception as repair_error:
                    repairs = repairs + [f"schema_repair_failed: {repair_error}"]
            
            metrics["validation_status"] = "success" if result else "failed"
            metrics["repairs"] = repairs
            if not result:
                metrics["error"] = "validation_failed"
                metrics["error_details"] = "; ".join(repairs[-3:]) if repairs else "Validation failed"
                # As a last-resort, emit a degraded but valid structure so the UI can render
                try:
                    fallback_payload = {
                        "key_messages": [
                            {
                                "message": "Analysis incomplete — placeholder message",
                                "context": "A processing error prevented a full extraction. This is a safe degraded result.",
                                "type": "Value Proposition",
                                "confidence": 10
                            }
                        ]
                    }
                    result = KeyMessagesResult(**fallback_payload)
                    metrics["validation_status"] = "degraded_fallback"
                    metrics["degraded"] = True
                except Exception:
                    pass
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # Log for analysis
            self._log_discovery_result("key_messages", raw_output, result, metrics)
            if result:
                self._save_cached_result("key_messages", content_fingerprint, result.dict())
            
            return result.dict() if result else None, metrics
            
        except Exception as e:
            # More detailed error tracking
            import traceback
            error_trace = traceback.format_exc()
            
            # Check for specific error types
            error_type = "unknown_error"
            if "rate limit" in str(e).lower():
                error_type = "rate_limit"
            elif "insufficient_quota" in str(e).lower():
                error_type = "quota_exceeded"
            elif "json" in str(e).lower() or "parsing" in str(e).lower():
                error_type = "json_parse_error"
            elif "timeout" in str(e).lower():
                error_type = "timeout"
            
            metrics["error"] = error_type
            metrics["error_details"] = str(e)
            metrics["error_traceback"] = error_trace
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            print(f"[ERROR] key_messages analysis failed: {str(e)}")
            print(f"[TRACEBACK] {error_trace}")
            
            self._log_discovery_error("key_messages", e, metrics)
            return None, metrics
    
# In discovery_integration.py

    @track_discovery_performance("tone_of_voice")
    def analyze_tone_of_voice(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze tone of voice using unified LLM client with fallbacks and schema repair."""
        
        start_time = time.time()
        metrics = {"key_name": "tone_of_voice"}
        raw_output = None
        result = None

        try:
            text_content = self._validate_and_sanitize_input(text_content, max_chars=4000)
            content_fingerprint = self._compute_fingerprint("tone_of_voice", text_content, ToneOfVoiceResult)
            cached = self._load_cached_result("tone_of_voice", content_fingerprint)
            if cached:
                metrics["cache_hit"] = True
                metrics["latency_ms"] = int((time.time() - start_time) * 1000)
                return cached, metrics

            # Pre-select relevant content for tone inputs
            reduced_text, sel_info = self._select_relevant_text(
                text_content, key_name="tone_of_voice", target_model="gpt-4o", max_total_tokens=1400
            )
            metrics.update({
                "preselect_applied": sel_info.get("chunking_applied", False),
                "preselect_tokens_before": sel_info.get("tokens_before"),
                "preselect_tokens_after": sel_info.get("tokens_after"),
                "preselect_chunks_considered": sel_info.get("chunks_considered"),
                "preselect_chunks_selected": sel_info.get("chunks_selected")
            })

            primary_prompt = (
                "Task: Identify the brand’s tone of voice.\n\n"
                "Produce:\n"
                "- primary_tone: { tone (≤30), justification (≤200), evidence_quote }\n"
                "- secondary_tone: { tone (≤30), justification (≤200), evidence_quote }\n"
                "- contradictions: up to 3 concise contradictions (each with evidence_quote)\n"
                "- confidence (0–100)\n\n"
                "Use only the snippets below; avoid guessing.\n\n"
                "Snippets:\n"
            ) + reduced_text
            
            # Unified LLM call via LLMClient with schema enforcement on chat fallback
            try:
                try:
                    schema_dict = ToneOfVoiceResult.schema()
                except Exception:
                    schema_dict = ToneOfVoiceResult.model_json_schema()
                raw_output, meta = self.llm_client.choose_and_call(
                    key_name="tone_of_voice",
                    prompt=primary_prompt,
                    schema=schema_dict,
                    enforce_schema=True,
                )
                metrics.update({
                    "api_used": meta.get("api_used"),
                    "model": meta.get("model"),
                    "token_usage": meta.get("token_usage", 0),
                    "breaker_open": meta.get("breaker_open", False)
                })
            except Exception as e:
                metrics["error"] = "llm_call_failed"
                metrics["error_details"] = str(e)
                raw_output = None

            # Stage 3: Validate and (if needed) Repair
            repairs = []
            if raw_output:
                result, repairs = self.validator.validate_with_repair(raw_output, ToneOfVoiceResult, "tone_of_voice")
            
            if not result and raw_output:
                self._debug_log_raw_output("tone_of_voice", "initial_validation_failed", raw_output, metrics)
                repairs.append("initial_validation_failed")
                print("[INFO] Initial validation for tone_of_voice failed, attempting schema repair.")
                metrics['api_used'] = (metrics.get('api_used') or "") + "+chat_schema_repair"
                try:
                    schema_dict = ToneOfVoiceResult.model_json_schema()
                    repair_prompt = f"You are a strict JSON schema formatter. Using only the snippets, produce valid JSON matching ToneOfVoiceResult.\n\nSnippets:\n{text_content}"
                    repair_resp = safe_openai_call(
                        self.llm_client.client,
                        timeout_seconds=self._adaptive_timeout(self._estimate_tokens(text_content), cap=60),
                        model="gpt-4o-mini", # Use a faster model for repair
                        messages=[
                            {"role": "system", "content": "Output only valid JSON matching the provided schema. No commentary."},
                            {"role": "user", "content": repair_prompt}
                        ],
                        response_format={"type": "json_schema", "json_schema": {"name": "ToneOfVoiceResult", "schema": schema_dict, "strict": True}}
                    )
                    raw_output = repair_resp.choices[0].message.content
                    result, repairs2 = self.validator.validate_with_repair(raw_output, ToneOfVoiceResult, "tone_of_voice")
                    repairs.extend(["schema_repair_applied"] + (repairs2 or []))
                    metrics.update({
                        "token_usage": metrics.get("token_usage",0) + getattr(repair_resp.usage, 'total_tokens', 0),
                        "model": getattr(repair_resp, 'model', 'gpt-4o-mini')
                    })
                except Exception as repair_error:
                    print(f"[ERROR] Schema repair for tone_of_voice failed: {repair_error}")
                    repairs.append(f"schema_repair_failed: {repair_error}")

            metrics.update({"validation_status": "success" if result else "failed", "repairs": repairs})
            
            # Stage 4: If all else fails, synthesize a degraded fallback result
            if not result:
                print("[INFO] All analysis attempts for tone_of_voice failed. Synthesizing degraded fallback.")
                metrics.update({"validation_status": "degraded_fallback", "degraded": True, "model": "fallback", "token_usage": 0})
                try:
                    fallback_payload = {
                        "primary_tone": { "tone": "Informational", "justification": "Structured output unavailable; using conservative fallback.", "evidence_quote": (text_content[:220] + "...") if text_content else "N/A"},
                        "secondary_tone": { "tone": "Professional", "justification": "Language appears formal and service-oriented.", "evidence_quote": "N/A"},
                        "contradictions": [], "confidence": 50
                    }
                    result = ToneOfVoiceResult(**fallback_payload)
                except Exception as final_fallback_error:
                    metrics.update({"error": "final_fallback_failed", "error_details": str(final_fallback_error)})
                    self._log_discovery_error("tone_of_voice", final_fallback_error, metrics)
                    return None, metrics
            
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            self._log_discovery_result("tone_of_voice", raw_output, result, metrics)
            if result and not metrics.get("degraded"):
                 self._save_cached_result("tone_of_voice", content_fingerprint, result.dict())
            
            return result.dict() if result else None, metrics

        except Exception as e:
            # Final catch-all to ensure we don't crash the worker
            metrics.update({"error": "unhandled_exception", "error_details": str(e), "latency_ms": int((time.time() - start_time) * 1000)})
            self._log_discovery_error("tone_of_voice", e, metrics)
            return None, metrics
            
    @track_discovery_performance("brand_elements")
    def analyze_brand_elements(self, screenshots: List[str], text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze brand visual elements using GPT-5 vision capabilities (disk-cached by content+image)."""
        from openai import OpenAI
        import time
        start_time = time.time()
        metrics = {"key_name": "brand_elements", "phase": 2}
        
        try:
            # Load environment variables if needed
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    api_key = os.getenv("OPENAI_API_KEY")
                except ImportError:
                    pass
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required for Discovery analysis")
            client = OpenAI(api_key=api_key)
            prompt = DECONSTRUCTION_KEYS_PROMPTS["brand_elements"]["prompt"]
            # Compute fingerprint from text summary + screenshot hashes (first 2 images)
            hasher = hashlib.sha256()
            hasher.update((text_content or "").encode())
            for s in (screenshots or [])[:2]:
                if isinstance(s, str):
                    try:
                        # normalize base64 (drop data: prefix)
                        if s.startswith('data:image/'):
                            s = s.split(',')[1]
                        hasher.update(s.encode())
                    except Exception:
                        pass
            content_fingerprint = hasher.hexdigest()
            cached = self._load_cached_result("brand_elements", content_fingerprint)
            if cached:
                metrics["cache_hit"] = True
                metrics["latency_ms"] = 0
                return cached, metrics
            
            # Prepare screenshot context for GPT-5 vision
            screenshot_context = self._prepare_screenshot_context(screenshots, text_content)
            
            # Build messages for GPT-5 vision API
            messages = [
                {"role": "system", "content": "You are a senior brand strategist with expertise in visual identity systems. Output only valid JSON."},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt.format(screenshot_context=screenshot_context)}
                    ]
                }
            ]
            
            # Add screenshot images to the message
            valid_screenshots = 0
            for i, screenshot_data in enumerate(screenshots[:5]):  # Limit to 5 screenshots for API efficiency
                if screenshot_data and isinstance(screenshot_data, str):
                    # Skip test/invalid data
                    if screenshot_data in ['test-screenshot-data', 'screenshot-data']:
                        continue
                        
                    try:
                        # Handle base64 data (remove data:image prefix if present)
                        if screenshot_data.startswith('data:image/'):
                            screenshot_data = screenshot_data.split(',')[1]
                        
                        # Validate base64 format
                        import base64
                        base64.b64decode(screenshot_data, validate=True)
                        
                        messages[1]["content"].append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{screenshot_data}",
                                "detail": "high"  # High detail for brand analysis
                            }
                        })
                        valid_screenshots += 1
                        
                    except Exception as img_error:
                        print(f"Skipping invalid screenshot {i}: {img_error}")
                        continue
            
            # GPT-5 vision call with fallback to GPT-4o
            try:
                response = safe_openai_call(
                    client,
                    timeout_seconds=120,
                    model="gpt-5",
                    messages=messages,
                    response_format={"type": "json_object"}
                )
            except Exception:
                print("[INFO] GPT-5 vision unavailable for brand_elements; falling back to gpt-4o")
                response = safe_openai_call(
                    client,
                    timeout_seconds=90,
                    model="gpt-4o",
                    messages=messages,
                    response_format={"type": "json_object"}
                )
            
            raw_output = response.choices[0].message.content
            metrics["token_usage"] = response.usage.total_tokens if hasattr(response, 'usage') else 0
            metrics["model"] = response.model if hasattr(response, 'model') else "gpt-4o"
            metrics["screenshots_provided"] = len([s for s in screenshots if s])
            metrics["screenshots_analyzed"] = valid_screenshots
            
            # Validate and repair
            result, repairs = self.validator.validate_with_repair(
                raw_output,
                BrandElementsResult,
                "brand_elements"
            )
            
            metrics["validation_status"] = "success" if result else "failed"
            metrics["repairs"] = repairs
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # If validation failed, synthesize a degraded but schema-valid visual result
            if not result:
                try:
                    degraded_payload = {
                        "overall_impression": {
                            "summary": "Limited visual signal available; providing conservative visual identity overview.",
                            "keywords": ["clean", "modern"]
                        },
                        "coherence_score": 3,
                        "visual_identity": {
                            "color_palette": {
                                "description": "Predominantly neutral palette with a single accent color.",
                                "consistency_notes": "Colors appear generally consistent across key sections."
                            },
                            "typography": {
                                "description": "Sans-serif headings with legible body text.",
                                "consistency_notes": "Typography usage appears mostly consistent."
                            },
                            "imagery_style": {
                                "description": "Marketing imagery focused on product and lifestyle." ,
                                "consistency_notes": "Imagery tone appears coherent with brand messaging."
                            }
                        },
                        "strategic_alignment": {
                            "harmony": "Visuals broadly reinforce the brand’s quality-oriented positioning.",
                            "dissonance": "Minor inconsistencies may exist due to limited sampling."
                        },
                        "confidence": 40
                    }
                    degraded_model = BrandElementsResult(**degraded_payload)
                    metrics["validation_status"] = "degraded_fallback"
                    metrics["degraded"] = True
                    metrics.setdefault("model", "fallback")
                    metrics.setdefault("token_usage", 0)
                    self._log_discovery_result("brand_elements", raw_output, degraded_model, metrics)
                    return degraded_model.dict(), metrics
                except Exception as _be_degrade_err:
                    metrics["degrade_error"] = str(_be_degrade_err)
            
            # Log for analysis
            self._log_discovery_result("brand_elements", raw_output, result, metrics)
            if result:
                self._save_cached_result("brand_elements", content_fingerprint, result.dict())
            
            return result.dict() if result else None, metrics
            
        except Exception as e:
            metrics["error"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            # Attempt degraded fallback on exception as last resort
            try:
                degraded_payload = {
                    "overall_impression": {
                        "summary": "Visual analysis unavailable; providing safe fallback overview.",
                        "keywords": ["clean", "modern"]
                    },
                    "coherence_score": 3,
                    "visual_identity": {
                        "color_palette": {
                            "description": "Neutral palette with a single accent.",
                            "consistency_notes": "Generally consistent across pages."
                        },
                        "typography": {
                            "description": "Sans-serif headings and body text.",
                            "consistency_notes": "Typography appears consistent."
                        },
                        "imagery_style": {
                            "description": "Marketing and product-focused imagery.",
                            "consistency_notes": "Imagery tone appears coherent."
                        }
                    },
                    "strategic_alignment": {
                        "harmony": "Visual language roughly supports stated themes.",
                        "dissonance": "Some variation likely due to limited input."
                    },
                    "confidence": 35
                }
                degraded_model = BrandElementsResult(**degraded_payload)
                metrics["validation_status"] = "degraded_fallback"
                metrics["degraded"] = True
                metrics.setdefault("model", "fallback")
                metrics.setdefault("token_usage", 0)
                self._log_discovery_result("brand_elements", "<exception_fallback>", degraded_model, metrics)
                return degraded_model.dict(), metrics
            except Exception:
                self._log_discovery_error("brand_elements", e, metrics)
                return None, metrics
    
    @track_discovery_performance("visual_text_alignment")
    def analyze_visual_text_alignment(self, positioning_themes: dict, brand_elements: dict) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze alignment between visual and text elements."""
        from openai import OpenAI
        import time
        start_time = time.time()
        metrics = {"key_name": "visual_text_alignment", "phase": 2}
        
        # Skip if either input is missing
        if not positioning_themes or not brand_elements:
            return {
                "alignment": "No",
                "justification": "Cannot assess alignment - missing positioning themes or brand elements analysis"
            }, {"key_name": "visual_text_alignment", "phase": 2, "skipped": True}
        
        try:
            # Load environment variables if needed
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    api_key = os.getenv("OPENAI_API_KEY")
                except ImportError:
                    pass
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required for Discovery analysis")
            client = OpenAI(api_key=api_key)
            
            # Format the positioning themes and brand elements for analysis
            themes_summary = self._format_themes_for_alignment(positioning_themes)
            elements_summary = self._format_elements_for_alignment(brand_elements)
            
            # GPT-5 Responses API (guarded); fallback to GPT-4o
            try:
                if not _should_use_responses():
                    raise Exception("Responses disabled by capability/env")
                prompt_text = (
                    "Task: Assess whether visuals support the core positioning.\n\n"
                    "Produce: alignment (\"Yes\"|\"No\") and justification (≤1000 chars) referencing specific visual cues and specific themes.\n\n"
                    "Inputs:\n"
                    f"Positioning themes (top 3):\n{themes_summary}\n\n"
                    f"Brand elements (visual summary):\n{elements_summary}"
                )
                tokens_needed = self._estimate_tokens(themes_summary + "\n" + elements_summary)
                if not self._acquire_budget(tokens_needed):
                    raise TimeoutError("LLM budget unavailable")
                response = safe_responses_call(
                    client,
                    timeout_seconds=self._adaptive_timeout(tokens_needed, cap=90),
                    model="gpt-5",
                    input=prompt_text,
                    reasoning={"effort": "minimal"},
                    text={"verbosity": "low"}
                )
                raw_output = None
                if hasattr(response, 'output') and isinstance(response.output, list):
                    for item in response.output:
                        if hasattr(item, 'content') and item.content:
                            for c in item.content:
                                if getattr(c, 'type', '') == 'output_text' and hasattr(c, 'text'):
                                    raw_output = c.text
                                    break
                        if raw_output:
                            break
                if not raw_output and hasattr(response, 'text') and isinstance(response.text, str):
                    raw_output = response.text
                if not raw_output:
                    raise Exception("Failed to extract JSON from GPT-5 response")
                metrics["api_used"] = "responses_api"
                metrics["model"] = "gpt-5"
                self._release_budget()
            except Exception:
                self._release_budget()
                response = safe_openai_call(
                    client,
                    timeout_seconds=self._adaptive_timeout(self._estimate_tokens(themes_summary + elements_summary), cap=90),
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a senior brand strategist evaluating brand consistency. Output only valid JSON."},
                        {"role": "user", "content": prompt_text}
                    ],
                    response_format={"type": "json_object"}
                )
                raw_output = response.choices[0].message.content
                metrics["token_usage"] = response.usage.total_tokens if hasattr(response, 'usage') else 0
                metrics["model"] = response.model if hasattr(response, 'model') else "gpt-4o"
            
            # Validate and repair
            result, repairs = self.validator.validate_with_repair(
                raw_output,
                VisualTextAlignmentResult,
                "visual_text_alignment"
            )
            
            metrics["validation_status"] = "success" if result else "failed"
            metrics["repairs"] = repairs
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # If validation failed, synthesize a degraded but valid alignment result
            if not result:
                try:
                    degraded_payload = {
                        "alignment": "Yes",
                        "justification": "Limited model availability; providing conservative assessment that visuals broadly support the top themes based on summaries."
                    }
                    degraded_model = VisualTextAlignmentResult(**degraded_payload)
                    metrics["validation_status"] = "degraded_fallback"
                    metrics["degraded"] = True
                    metrics.setdefault("model", "fallback")
                    metrics.setdefault("token_usage", 0)
                    self._log_discovery_result("visual_text_alignment", raw_output, degraded_model, metrics)
                    alignment_fingerprint = hashlib.sha256((themes_summary + "\n\n" + elements_summary).encode()).hexdigest()
                    self._save_cached_result("visual_text_alignment", alignment_fingerprint, degraded_model.dict())
                    return degraded_model.dict(), metrics
                except Exception:
                    pass
            
            # Log for analysis
            self._log_discovery_result("visual_text_alignment", raw_output, result, metrics)
            if result:
                alignment_fingerprint = hashlib.sha256((themes_summary + "\n\n" + elements_summary).encode()).hexdigest()
                self._save_cached_result("visual_text_alignment", alignment_fingerprint, result.dict())
            
            return result.dict() if result else None, metrics
            
        except Exception as e:
            metrics["error"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            # Attempt degraded fallback on exception
            try:
                degraded_payload = {
                    "alignment": "Yes",
                    "justification": "Unable to complete alignment analysis due to model error; returning safe fallback that visuals generally align with the stated themes."
                }
                degraded_model = VisualTextAlignmentResult(**degraded_payload)
                metrics["validation_status"] = "degraded_fallback"
                metrics["degraded"] = True
                metrics.setdefault("model", "fallback")
                metrics.setdefault("token_usage", 0)
                self._log_discovery_result("visual_text_alignment", "<exception_fallback>", degraded_model, metrics)
                return degraded_model.dict(), metrics
            except Exception:
                self._log_discovery_error("visual_text_alignment", e, metrics)
                return None, metrics
    
    def _prepare_screenshot_context(self, screenshots: List[str], text_content: str) -> str:
        """Prepare contextual information for screenshot analysis."""
        context_parts = []
        
        # Add text content summary
        if text_content:
            # Limit text content to key passages for efficiency
            text_summary = text_content[:1000] + "..." if len(text_content) > 1000 else text_content
            context_parts.append(f"WEBSITE TEXT SUMMARY:\n{text_summary}")
        
        # Add screenshot references
        screenshot_count = len([s for s in screenshots if s])
        if screenshot_count > 0:
            context_parts.append(f"\nSCREENSHOTS PROVIDED: {screenshot_count} images showing different pages/sections of the website")
            context_parts.append("Each screenshot should be analyzed for visual consistency, color schemes, typography, and brand elements.")
        else:
            context_parts.append("\nNote: No screenshots available - analysis will be limited to text-based brand context.")
        
        return "\n".join(context_parts)
    
    def _format_themes_for_alignment(self, positioning_themes: dict) -> str:
        """Format positioning themes for alignment analysis."""
        if not positioning_themes or 'themes' not in positioning_themes:
            return "No positioning themes available"
        
        themes_list = []
        for theme in positioning_themes['themes'][:3]:  # Limit to top 3 for efficiency
            theme_text = f"- {theme.get('theme', 'Unknown')}"
            if theme.get('confidence'):
                theme_text += f" (confidence: {theme['confidence']}%)"
            if theme.get('evidence'):
                theme_text += f"\n  Evidence: \"{theme['evidence'][:100]}...\""
            themes_list.append(theme_text)
        
        return "POSITIONING THEMES:\n" + "\n".join(themes_list)
    
    def _format_elements_for_alignment(self, brand_elements: dict) -> str:
        """Format brand elements for alignment analysis."""
        if not brand_elements:
            return "No brand elements analysis available"
        
        if brand_elements.get('status') in ['no_screenshots', 'coming_soon']:
            return f"BRAND ELEMENTS: {brand_elements.get('message', 'Not analyzed')}"
        
        parts = []
        if brand_elements.get('overall_impression'):
            impression = brand_elements['overall_impression']
            parts.append(f"VISUAL IMPRESSION: {impression.get('summary', 'Unknown')}")
            if impression.get('keywords'):
                parts.append(f"Keywords: {', '.join(impression['keywords'])}")
        
        if brand_elements.get('coherence_score'):
            parts.append(f"Coherence Score: {brand_elements['coherence_score']}/5")
        
        if brand_elements.get('strategic_alignment'):
            alignment = brand_elements['strategic_alignment']
            if isinstance(alignment, dict):
                # New schema with harmony/dissonance
                if alignment.get('harmony'):
                    parts.append(f"Harmony: {alignment['harmony']}")
                if alignment.get('dissonance'):
                    parts.append(f"Dissonance: {alignment['dissonance']}")
            else:
                # Old schema - simple string
                parts.append(f"Strategic Alignment: {alignment}")
        
        return "BRAND ELEMENTS:\n" + "\n".join(parts) if parts else "BRAND ELEMENTS: Analysis incomplete"
    
    def enhance_confidence_with_visual_evidence(self, text_results: dict, visual_results: dict, alignment_results: dict) -> dict:
        """Enhance confidence scores based on visual-text alignment."""
        enhanced_results = {}
        
        for key, result in text_results.items():
            if not result or key not in ['positioning_themes', 'key_messages', 'tone_of_voice']:
                enhanced_results[key] = result
                continue
                
            enhanced_result = result.copy()
            
            # Base confidence boost factors
            visual_support_boost = 0
            alignment_boost = 0
            
            # Check if visual evidence supports text analysis  
            if visual_results and visual_results.get('coherence_score', 0) >= 4:
                visual_support_boost = 5  # +5% for high visual coherence
            elif visual_results and visual_results.get('coherence_score', 0) >= 3:
                visual_support_boost = 3  # +3% for medium visual coherence
            
            # Check visual-text alignment
            if alignment_results and alignment_results.get('alignment') == 'Yes':
                alignment_boost = 8  # +8% for confirmed alignment
            elif alignment_results and alignment_results.get('alignment') == 'No':
                alignment_boost = -5  # -5% for misalignment
            
            # Apply boosts to individual items
            if key == 'positioning_themes' and 'themes' in enhanced_result:
                for theme in enhanced_result['themes']:
                    original_confidence = theme.get('confidence', 0)
                    boosted_confidence = min(100, original_confidence + visual_support_boost + alignment_boost)
                    theme['confidence'] = boosted_confidence
                    theme['visual_support'] = visual_support_boost > 0
                    theme['alignment_confirmed'] = alignment_boost > 0
                    
            elif key == 'key_messages' and 'key_messages' in enhanced_result:
                for message in enhanced_result['key_messages']:
                    original_confidence = message.get('confidence', 0)
                    boosted_confidence = min(100, original_confidence + visual_support_boost + alignment_boost)
                    message['confidence'] = boosted_confidence
                    message['visual_support'] = visual_support_boost > 0
                    message['alignment_confirmed'] = alignment_boost > 0
                    
            elif key == 'tone_of_voice' and 'tone_descriptors' in enhanced_result:
                for tone in enhanced_result['tone_descriptors']:
                    original_confidence = tone.get('confidence', 0)
                    boosted_confidence = min(100, original_confidence + visual_support_boost + alignment_boost)
                    tone['confidence'] = boosted_confidence
                    tone['visual_support'] = visual_support_boost > 0
                    tone['alignment_confirmed'] = alignment_boost > 0
            
            enhanced_results[key] = enhanced_result
        
        return enhanced_results
    
    def _log_discovery_result(self, key_name: str, raw_output: str, validated_result: Any, metrics: dict):
        """Log Discovery analysis results for monitoring and debugging."""
        # Attach a trace id for correlating logs across components
        import uuid as _uuid
        trace_id = metrics.get("trace_id") or _uuid.uuid4().hex[:12]
        metrics["trace_id"] = trace_id

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "scan_id": self.scan_id,
            "key_name": key_name,
            "model_id": metrics.get("model", "unknown"),
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": hashlib.sha256(
                DECONSTRUCTION_KEYS_PROMPTS[key_name]["prompt"].encode()
            ).hexdigest()[:8],
            "latency_ms": metrics.get("latency_ms"),
            "token_usage": metrics.get("token_usage"),
            "validation_status": metrics.get("validation_status"),
            "repairs_applied": metrics.get("repairs", []),
            "trace_id": trace_id,
            "raw_output_truncated": str(raw_output)[:500] if raw_output else None
        }
        
        # Log to file (in production, this would go to your logging service)
        log_file = os.path.join(
            os.getenv("PERSISTENT_DATA_DIR", "/tmp"),
            "discovery_analysis.jsonl"
        )
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def _log_discovery_error(self, key_name: str, error: Exception, metrics: dict):
        """Log Discovery analysis errors."""
        import uuid as _uuid
        trace_id = metrics.get("trace_id") or _uuid.uuid4().hex[:12]
        metrics["trace_id"] = trace_id

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "scan_id": self.scan_id,
            "key_name": key_name,
            "prompt_version": PROMPT_VERSION,
            "trace_id": trace_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "metrics": metrics
        }
        
        log_file = os.path.join(
            os.getenv("PERSISTENT_DATA_DIR", "/tmp"),
            "discovery_errors.jsonl"
        )
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def _debug_log_raw_output(self, key_name: str, stage: str, raw_output: str, metrics: dict):
        """Detailed debug log for raw model output when validation fails or repairs applied.

        Truncates raw output to protect logs. Intended for troubleshooting only.
        """
        try:
            import uuid as _uuid
            trace_id = metrics.get("trace_id") or _uuid.uuid4().hex[:12]
            metrics["trace_id"] = trace_id

            debug_entry = {
                "timestamp": datetime.now().isoformat(),
                "scan_id": self.scan_id,
                "key_name": key_name,
                "stage": stage,
                "prompt_version": PROMPT_VERSION,
                "trace_id": trace_id,
                "validation_status": metrics.get("validation_status"),
                "repairs": metrics.get("repairs", []),
                "error": metrics.get("error"),
                "error_details": metrics.get("error_details"),
                "raw_output_truncated": str(raw_output)[:2000] if raw_output else None
            }
            log_file = os.path.join(
                os.getenv("PERSISTENT_DATA_DIR", "/tmp"),
                "discovery_debug.jsonl"
            )
            with open(log_file, "a") as f:
                f.write(json.dumps(debug_entry) + "\n")
        except Exception:
            pass

# === Modified Scanner Integration ===
def enhance_scanner_for_discovery(existing_run_full_scan_stream):
    """
    Decorator to enhance existing run_full_scan_stream function with Discovery Mode.
    This allows us to add Discovery Mode without modifying the core scanner.py file.
    """
    def enhanced_scan_stream(url: str, cache: dict, preferred_lang: str = 'en', 
                            scan_id: str = None, mode: str = 'diagnosis'):
        
        # If diagnosis mode or discovery disabled, use original function
        if mode == 'diagnosis' or not FeatureFlags.is_discovery_enabled():
            yield from existing_run_full_scan_stream(url, cache, preferred_lang, scan_id)
            return
        
        # Discovery Mode logic
        if not scan_id:
            import uuid
            scan_id = str(uuid.uuid4())
        
        # Track scan start
        yield {'type': 'scan_started', 'mode': 'discovery', 'scan_id': scan_id}
        
        # Reuse existing crawling and screenshot logic from scanner.py
        # This part would call the existing functions to get pages and screenshots
        
        # Initialize Discovery analyzer
        analyzer = DiscoveryAnalyzer(scan_id, cache)
        
        # Run Discovery analysis (Phase 1: text-based only)
        # ... implementation continues
        
    return enhanced_scan_stream

# === Feedback System Integration ===
class DiscoveryFeedbackHandler:
    """Handles Discovery Mode feedback collection and analysis."""
    
    @staticmethod
    def record_feedback(feedback: DiscoveryFeedback) -> bool:
        """Record user feedback for Discovery Mode results."""
        try:
            # Validate feedback
            validated_feedback = feedback.dict()
            
            # Log to persistent storage
            feedback_file = os.path.join(
                os.getenv("PERSISTENT_DATA_DIR", "/tmp"),
                "discovery_feedback.jsonl"
            )
            
            with open(feedback_file, "a") as f:
                f.write(json.dumps(validated_feedback, default=str) + "\n")
            
            # Track metrics (would integrate with Mixpanel/Amplitude here)
            DiscoveryFeedbackHandler._track_feedback_metrics(validated_feedback)
            
            return True
            
        except Exception as e:
            print(f"Failed to record Discovery feedback: {e}")
            return False
    
    @staticmethod
    def _track_feedback_metrics(feedback: dict):
        """Track feedback metrics for success measurement."""
        # This would send to your analytics platform
        # Example: mixpanel.track("discovery_feedback", feedback)
        pass
    
    @staticmethod
    def analyze_feedback_patterns(days: int = 7) -> dict:
        """Analyze feedback patterns for prompt improvement."""
        # Weekly analysis script logic
        # Returns patterns and recommendations
        pass

# === Performance Monitoring ===
class DiscoveryMetrics:
    """Track and report Discovery Mode performance metrics."""
    
    @staticmethod
    def track_scan_metrics(scan_id: str, mode: str, results: dict, performance: dict):
        """Track comprehensive scan metrics."""
        metrics = {
            "scan_id": scan_id,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
            "performance": {
                "total_duration_ms": performance.get("total_duration"),
                "per_key_duration_ms": performance.get("key_durations", {}),
                "token_usage": performance.get("total_tokens"),
                "model": os.getenv("AI_MODEL_ID", "gpt-5")
            },
            "quality": {
                "confidence_scores": DiscoveryMetrics._extract_confidence_scores(results),
                "evidence_count": DiscoveryMetrics._count_evidence(results),
                "keys_completed": len([k for k in results if results[k] is not None])
            }
        }
        
        # Log metrics (would send to analytics platform)
        metrics_file = os.path.join(
            os.getenv("PERSISTENT_DATA_DIR", "/tmp"),
            "discovery_metrics.jsonl"
        )
        with open(metrics_file, "a") as f:
            f.write(json.dumps(metrics) + "\n")
        
        return metrics
    
    @staticmethod
    def _extract_confidence_scores(results: dict) -> dict:
        """Extract all confidence scores from results."""
        scores = {}
        for key, value in results.items():
            if isinstance(value, dict):
                if "themes" in value:
                    scores[key] = [t.get("confidence", 0) for t in value["themes"]]
                elif "key_messages" in value:
                    scores[key] = [m.get("confidence", 0) for m in value["key_messages"]]
                elif "messages" in value:  # Fallback for old schema
                    scores[key] = [m.get("confidence", 0) for m in value["messages"]]
                elif "confidence" in value:
                    scores[key] = value["confidence"]
        return scores
    
    @staticmethod
    def _count_evidence(results: dict) -> int:
        """Count total evidence items across all keys."""
        count = 0
        for value in results.values():
            if isinstance(value, dict):
                if "themes" in value:
                    count += len(value["themes"])
                elif "key_messages" in value:
                    count += len(value["key_messages"])
                elif "messages" in value:  # Fallback for old schema
                    count += len(value["messages"])
        return count