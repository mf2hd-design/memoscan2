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
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from discovery_prompts import DECONSTRUCTION_KEYS_PROMPTS, track_discovery_performance
from discovery_schemas import (
    SchemaValidator,
    PositioningThemesResult,
    KeyMessagesResult,
    ToneOfVoiceResult,
    BrandElementsResult,
    VisualTextAlignmentResult,
    DiscoveryFeedback
)

# === Feature Flag System ===
class FeatureFlags:
    """Centralized feature flag management for Discovery Mode."""
    
    @staticmethod
    def is_discovery_enabled(user_id: Optional[str] = None) -> bool:
        """Check if Discovery Mode is enabled for the given user."""
        
        # Global feature flag
        if os.getenv('DISCOVERY_MODE_ENABLED', 'false').lower() != 'true':
            return False
        
        # Check rollout percentage
        rollout_percentage = int(os.getenv('DISCOVERY_ROLLOUT_PERCENTAGE', '0'))
        if rollout_percentage < 100:
            # Use consistent hashing for gradual rollout
            if user_id:
                user_hash = int(hashlib.md5(user_id.encode()).hexdigest()[:8], 16)
                if (user_hash % 100) >= rollout_percentage:
                    return False
        
        # Check user whitelist
        whitelist = os.getenv('DISCOVERY_MODE_WHITELIST', '').split(',')
        if whitelist and whitelist[0]:  # If whitelist exists and is not empty
            if not user_id or user_id not in whitelist:
                return False
        
        return True
    
    @staticmethod
    def get_enabled_features() -> Dict[str, bool]:
        """Get all feature flag states."""
        return {
            "discovery_mode": FeatureFlags.is_discovery_enabled(),
            "visual_analysis": os.getenv('DISCOVERY_VISUAL_ANALYSIS', 'false').lower() == 'true',
            "export_features": os.getenv('DISCOVERY_EXPORT_ENABLED', 'false').lower() == 'true',
            "advanced_feedback": os.getenv('DISCOVERY_ADVANCED_FEEDBACK', 'false').lower() == 'true'
        }

# === Discovery Mode Scanner Integration ===
class DiscoveryAnalyzer:
    """Handles Discovery Mode analysis using existing scanner infrastructure."""
    
    def __init__(self, scan_id: str, cache: dict):
        self.scan_id = scan_id
        self.cache = cache
        self.validator = SchemaValidator()
        self.performance_metrics = {}
        
    @track_discovery_performance("positioning_themes")
    def analyze_positioning_themes(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze positioning themes using GPT-5."""
        from openai import OpenAI
        
        start_time = time.time()
        metrics = {"key_name": "positioning_themes"}
        
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            prompt = DECONSTRUCTION_KEYS_PROMPTS["positioning_themes"]["prompt"]
            
            # GPT-5 call with enhanced parameters
            response = client.chat.completions.create(
                model=os.getenv("AI_MODEL_ID", "gpt-5"),
                messages=[
                    {"role": "system", "content": "You are a senior brand strategist. Output only valid JSON."},
                    {"role": "user", "content": prompt.format(text_content=text_content)}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=1000,
                response_format={"type": "json_object"}  # GPT-5 structured output
            )
            
            raw_output = response.choices[0].message.content
            metrics["token_usage"] = response.usage.total_tokens
            metrics["model"] = response.model
            
            # Validate and repair
            result, repairs = self.validator.validate_with_repair(
                raw_output,
                PositioningThemesResult,
                "positioning_themes"
            )
            
            metrics["validation_status"] = "success" if result else "failed"
            metrics["repairs"] = repairs
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # Log for analysis
            self._log_discovery_result("positioning_themes", raw_output, result, metrics)
            
            return result.dict() if result else None, metrics
            
        except Exception as e:
            metrics["error"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            self._log_discovery_error("positioning_themes", e, metrics)
            return None, metrics
    
    @track_discovery_performance("key_messages")
    def analyze_key_messages(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze key messages using GPT-5."""
        # Similar structure to positioning_themes
        # Implementation follows same pattern
        pass
    
    @track_discovery_performance("tone_of_voice")
    def analyze_tone_of_voice(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze tone of voice using GPT-5."""
        # Similar structure to positioning_themes
        # Implementation follows same pattern
        pass
    
    @track_discovery_performance("brand_elements")
    def analyze_brand_elements(self, screenshots: List[str], text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze brand visual elements using GPT-5 vision capabilities."""
        # This will be implemented in Phase 2
        # For Phase 1, return placeholder
        return {
            "status": "coming_soon",
            "message": "Visual analysis will be available in Phase 2"
        }, {"key_name": "brand_elements", "phase": 1}
    
    @track_discovery_performance("visual_text_alignment")
    def analyze_visual_text_alignment(self, positioning_themes: dict, brand_elements: dict) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Analyze alignment between visual and text elements."""
        # This will be implemented in Phase 2
        # Requires results from positioning_themes and brand_elements
        pass
    
    def _log_discovery_result(self, key_name: str, raw_output: str, validated_result: Any, metrics: dict):
        """Log Discovery analysis results for monitoring and debugging."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "scan_id": self.scan_id,
            "key_name": key_name,
            "model_id": metrics.get("model", "unknown"),
            "prompt_hash": hashlib.sha256(
                DECONSTRUCTION_KEYS_PROMPTS[key_name]["prompt"].encode()
            ).hexdigest()[:8],
            "latency_ms": metrics.get("latency_ms"),
            "token_usage": metrics.get("token_usage"),
            "validation_status": metrics.get("validation_status"),
            "repairs_applied": metrics.get("repairs", []),
            "raw_output_truncated": raw_output[:500] if raw_output else None
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
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "scan_id": self.scan_id,
            "key_name": key_name,
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
                elif "messages" in value:
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
                elif "messages" in value:
                    count += len(value["messages"])
        return count