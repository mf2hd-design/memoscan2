"""
Discovery Mode Integration Layer - OPTIMIZED VERSION
Aggressive optimizations for large content and timeout prevention
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
)

def smart_truncate_content(text: str, max_chars: int = 10000) -> str:
    """
    Intelligently truncate content to keep the most relevant parts.
    Prioritizes unique content over repetitive sections.
    """
    if len(text) <= max_chars:
        return text
    
    # Split into paragraphs
    paragraphs = text.split('\n\n')
    
    # Remove very short paragraphs (likely navigation/footer content)
    meaningful_paragraphs = [p for p in paragraphs if len(p) > 100]
    
    # Take first 30% and last 20% of content (usually most important)
    if meaningful_paragraphs:
        first_portion = meaningful_paragraphs[:len(meaningful_paragraphs)//3]
        last_portion = meaningful_paragraphs[-len(meaningful_paragraphs)//5:]
        middle_sample = meaningful_paragraphs[len(meaningful_paragraphs)//3:len(meaningful_paragraphs)//2][:3]
        
        selected = first_portion + middle_sample + last_portion
        result = '\n\n'.join(selected)
        
        if len(result) > max_chars:
            result = result[:max_chars]
        
        print(f"[INFO] Smart truncated content from {len(text)} to {len(result)} chars")
        return result + "\n[Content intelligently sampled for analysis]"
    
    # Fallback to simple truncation
    print(f"[INFO] Simple truncated content from {len(text)} to {max_chars} chars")
    return text[:max_chars] + "\n[Content truncated for analysis]"

class OptimizedDiscoveryAnalyzer:
    """Optimized Discovery analyzer for large content and timeout prevention."""
    
    def __init__(self, scan_id: str, cache: dict):
        self.scan_id = scan_id
        self.cache = cache
        self.validator = SchemaValidator()
    
    def analyze_all_optimized(self, text_content: str) -> Dict[str, Any]:
        """
        Run Discovery analyses with aggressive optimizations.
        """
        start_time = time.time()
        
        # Aggressively truncate content for fast processing
        optimized_content = smart_truncate_content(text_content, max_chars=10000)
        
        results = {}
        metrics = {
            'total_latency_ms': 0,
            'analyses_completed': 0,
            'analyses_failed': 0,
            'total_tokens': 0,
            'execution_mode': 'optimized_sequential'
        }
        
        # Run each analysis with optimized content
        analyses = [
            ('positioning_themes', self.analyze_positioning_themes_fast),
            ('key_messages', self.analyze_key_messages_fast),
            ('tone_of_voice', self.analyze_tone_of_voice_fast)
        ]
        
        for key_name, analysis_func in analyses:
            try:
                print(f"[INFO] Starting optimized {key_name} analysis...")
                result, analysis_metrics = analysis_func(optimized_content)
                
                if result:
                    results[key_name] = result
                    metrics['analyses_completed'] += 1
                    metrics['total_tokens'] += analysis_metrics.get('token_usage', 0)
                    print(f"[INFO] ✅ {key_name} completed: {analysis_metrics.get('token_usage', 0)} tokens")
                else:
                    metrics['analyses_failed'] += 1
                    results[key_name] = {'error': 'analysis_failed'}
                    print(f"[INFO] ❌ {key_name} failed")
                    
            except Exception as e:
                print(f"[ERROR] {key_name} exception: {str(e)}")
                metrics['analyses_failed'] += 1
                results[key_name] = {'error': str(e)}
        
        metrics['total_latency_ms'] = int((time.time() - start_time) * 1000)
        
        return {
            'results': results,
            'metrics': metrics,
            'success': metrics['analyses_completed'] > 0,
            'completion_rate': metrics['analyses_completed'] / 3.0
        }
    
    def analyze_positioning_themes_fast(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Fast positioning themes analysis with simplified prompt."""
        from openai import OpenAI
        
        start_time = time.time()
        metrics = {"key_name": "positioning_themes"}
        
        try:
            # Load API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("OPENAI_API_KEY")
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY required")
            
            client = OpenAI(api_key=api_key)
            
            # Simplified, focused prompt
            fast_prompt = """Analyze this brand content and identify 3 main positioning themes.

For each theme provide:
- theme: The positioning concept (max 50 chars)
- description: One sentence explanation (max 200 chars)
- evidence_quotes: Two supporting quotes from the text
- confidence: Score 0-100

Output as JSON:
{{"themes": [{{"theme": "...", "description": "...", "evidence_quotes": ["...", "..."], "confidence": 85}}]}}

CONTENT:
{text_content}"""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a brand strategist. Output only valid JSON."},
                    {"role": "user", "content": fast_prompt.format(text_content=text_content)}
                ],
                temperature=0.3,
                max_tokens=1500,
                timeout=60,  # Hard 60 second timeout
                response_format={"type": "json_object"}
            )
            
            raw_output = response.choices[0].message.content
            metrics["token_usage"] = response.usage.total_tokens
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # Parse and validate
            result = json.loads(raw_output)
            return result, metrics
            
        except Exception as e:
            metrics["error"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            return None, metrics
    
    def analyze_key_messages_fast(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Fast key messages analysis with simplified prompt."""
        from openai import OpenAI
        
        start_time = time.time()
        metrics = {"key_name": "key_messages"}
        
        try:
            # Load API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("OPENAI_API_KEY")
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY required")
            
            client = OpenAI(api_key=api_key)
            
            # Very simple prompt
            fast_prompt = """Find 3 key brand messages in this content.

For each message:
- message: The key message (max 200 chars)
- context: Supporting context (max 200 chars)
- type: "Tagline" or "Value Proposition"
- confidence: 0-100

Output as JSON:
{{"key_messages": [{{"message": "...", "context": "...", "type": "Tagline", "confidence": 90}}]}}

CONTENT:
{text_content}"""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a copywriter. Output only valid JSON."},
                    {"role": "user", "content": fast_prompt.format(text_content=text_content)}
                ],
                temperature=0.3,
                max_tokens=1000,
                timeout=60,  # Hard 60 second timeout
                response_format={"type": "json_object"}
            )
            
            raw_output = response.choices[0].message.content
            metrics["token_usage"] = response.usage.total_tokens
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # Parse and validate
            result = json.loads(raw_output)
            return result, metrics
            
        except Exception as e:
            metrics["error"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            return None, metrics
    
    def analyze_tone_of_voice_fast(self, text_content: str) -> Tuple[Optional[dict], Dict[str, Any]]:
        """Fast tone of voice analysis with simplified prompt."""
        from openai import OpenAI
        
        start_time = time.time()
        metrics = {"key_name": "tone_of_voice"}
        
        try:
            # Load API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("OPENAI_API_KEY")
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY required")
            
            client = OpenAI(api_key=api_key)
            
            # Simple tone analysis
            fast_prompt = """Analyze the brand's tone of voice.

Provide:
- primary_tone: {{"tone": "...", "justification": "...", "evidence_quote": "..."}}
- secondary_tone: {{"tone": "...", "justification": "...", "evidence_quote": "..."}}
- contradictions: []
- confidence: 0-100

Output as JSON with this exact structure.

CONTENT:
{text_content}"""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a brand analyst. Output only valid JSON."},
                    {"role": "user", "content": fast_prompt.format(text_content=text_content)}
                ],
                temperature=0.3,
                max_tokens=1000,
                timeout=60,  # Hard 60 second timeout
                response_format={"type": "json_object"}
            )
            
            raw_output = response.choices[0].message.content
            metrics["token_usage"] = response.usage.total_tokens
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            
            # Parse and validate
            result = json.loads(raw_output)
            return result, metrics
            
        except Exception as e:
            metrics["error"] = str(e)
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            return None, metrics