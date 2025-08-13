"""
Discovery Mode Schema Definitions
Version: 1.0.0
Date: August 2025

Pydantic models for strict schema validation with auto-repair capabilities.
"""

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, validator
from typing import List, Optional, Dict, Any, Literal

import json
from datetime import datetime

# Pydantic v2 compatible model configuration
# Forbids extra fields to ensure strict schema adherence required by OpenAI's API
strict_config = ConfigDict(extra='forbid')

# === Positioning Themes Schema ===
class PositioningTheme(BaseModel):
    model_config = strict_config
    theme: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1, max_length=200)
    evidence_quotes: List[str] = Field(..., min_items=1, max_items=3)
    confidence: int = Field(..., ge=0, le=100)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        """Auto-repair: Convert string numbers to int."""
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

class PositioningThemesResult(BaseModel):
    model_config = strict_config
    themes: List[PositioningTheme] = Field(..., min_items=1, max_items=5)

# === Key Messages Schema ===
class KeyMessage(BaseModel):
    model_config = strict_config
    message: str = Field(..., min_length=1, max_length=200)  # Increased from 100 to 200
    context: str = Field(..., min_length=1, max_length=300)
    type: Literal["Tagline", "Value Proposition"]
    confidence: int = Field(..., ge=0, le=100)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

class KeyMessagesResult(BaseModel):
    model_config = strict_config
    key_messages: List[KeyMessage] = Field(..., min_items=1, max_items=5)
    
    @validator('key_messages', pre=True)
    def limit_key_messages(cls, v):
        """Auto-repair: Limit to top 5 key messages if more are provided."""
        if isinstance(v, list) and len(v) > 5:
            return v[:5]  # Keep only the first 5
        return v

# === Tone of Voice Schema ===
class ToneElement(BaseModel):
    model_config = strict_config
    tone: str = Field(..., min_length=1, max_length=30)
    justification: str = Field(..., min_length=1, max_length=200)
    evidence_quote: str = Field(..., min_length=1)

class ToneContradiction(BaseModel):
    model_config = strict_config
    contradiction: str = Field(..., min_length=1, max_length=200)
    evidence_quote: str = Field(..., min_length=1)

class ToneOfVoiceResult(BaseModel):
    model_config = strict_config
    primary_tone: ToneElement
    secondary_tone: ToneElement
    contradictions: List[ToneContradiction] = Field(..., max_length=3)
    confidence: int = Field(..., ge=0, le=100)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

# === Brand Elements Schema ===
class OverallImpression(BaseModel):
    model_config = strict_config
    summary: str = Field(..., min_length=1, max_length=300)  # Increased from 200 to 300
    keywords: List[str] = Field(..., min_items=1, max_items=5)
    
    @validator('keywords', pre=True)
    def limit_keywords(cls, v):
        """Auto-repair: Limit to top 5 keywords if more are provided."""
        if isinstance(v, list) and len(v) > 5:
            return v[:5]  # Keep only the first 5
        return v

class VisualIdentityElement(BaseModel):
    model_config = strict_config
    description: str = Field(..., min_length=1, max_length=400)  # Increased from 300
    consistency_notes: str = Field(..., min_length=1, max_length=250)  # Increased from 200
    
    @validator('description', pre=True)
    def truncate_description(cls, v):
        """Auto-repair: Truncate description if too long."""
        if isinstance(v, str) and len(v) > 400:
            return v[:397] + "..."
        return v
    
    @validator('consistency_notes', pre=True)
    def truncate_consistency_notes(cls, v):
        """Auto-repair: Truncate consistency notes if too long."""
        if isinstance(v, str) and len(v) > 250:
            return v[:247] + "..."
        return v

class VisualIdentity(BaseModel):
    model_config = strict_config
    color_palette: VisualIdentityElement
    typography: VisualIdentityElement
    imagery_style: VisualIdentityElement

class StrategicAlignment(BaseModel):
    model_config = strict_config
    harmony: str = Field(..., min_length=1, max_length=500)  # Increased from 400
    dissonance: str = Field(..., min_length=1, max_length=500)  # Increased from 400
    
    @validator('harmony', pre=True)
    def truncate_harmony(cls, v):
        """Auto-repair: Truncate harmony if too long."""
        if isinstance(v, str) and len(v) > 500:
            return v[:497] + "..."
        return v
    
    @validator('dissonance', pre=True)
    def truncate_dissonance(cls, v):
        """Auto-repair: Truncate dissonance if too long."""
        if isinstance(v, str) and len(v) > 500:
            return v[:497] + "..."
        return v

class BrandElementsResult(BaseModel):
    model_config = strict_config
    overall_impression: OverallImpression
    coherence_score: int = Field(..., ge=1, le=5)
    visual_identity: VisualIdentity
    strategic_alignment: StrategicAlignment
    confidence: int = Field(..., ge=0, le=100)
    
    @validator('coherence_score', pre=True)
    def clamp_coherence_score(cls, v):
        """Auto-repair: Clamp coherence score to valid range 1-5."""
        if isinstance(v, int):
            return max(1, min(5, v))
        return v
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

# === Visual-Text Alignment Schema ===
class VisualTextAlignmentResult(BaseModel):
    model_config = strict_config
    alignment: Literal["Yes", "No"]
    justification: str = Field(..., min_length=1, max_length=1000)  # Increased from 200 to 1000
    
    @validator('justification', pre=True)
    def truncate_justification(cls, v):
        """Auto-repair: Truncate justification if too long."""
        if isinstance(v, str) and len(v) > 1000:
            return v[:997] + "..."
        return v

# === Discovery Scan Result ===
class DiscoveryScanResult(BaseModel):
    model_config = strict_config
    scan_id: str
    mode: Literal["discovery"]
    url: str
    timestamp: datetime
    results: dict  # Will contain the individual key results
    metadata: dict  # Performance and model information
    
class DiscoveryFeedback(BaseModel):
    """Schema for Discovery Mode feedback."""
    model_config = strict_config
    scan_id: str
    key_name: str
    helpful: bool
    category: Optional[Literal["incorrect_evidence", "missing_context", "wrong_confidence", "other"]]
    comment: Optional[str] = Field(None, max_length=1000)
    timestamp: datetime = Field(default_factory=datetime.now)

# === Validation and Auto-Repair Functions ===
class SchemaValidator:
    """Handles schema validation with auto-repair capabilities."""
    
    @staticmethod
    def _normalize_tone_of_voice_payload(data: Any) -> Any:
        """Normalize common variants to match ToneOfVoiceResult schema, and ensure non-empty evidence_quote fields."""
        try:
            if not isinstance(data, dict):
                return data
            # Map root keys variants
            if 'primary' in data and 'primary_tone' not in data:
                data['primary_tone'] = data.pop('primary')
            if 'secondary' in data and 'secondary_tone' not in data:
                data['secondary_tone'] = data.pop('secondary')

            # Helper to ensure non-empty quote
            def ensure_quote(val: Any) -> str:
                if isinstance(val, str) and val.strip():
                    return val.strip()
                # fall back placeholder; upstream may replace with snippet
                return "No specific quote; inferred from overall copy."

            # Normalize ToneElement fields for primary and secondary
            for key in ['primary_tone', 'secondary_tone']:
                if key in data and isinstance(data[key], dict):
                    elem = data[key]
                    # Field aliasing
                    if 'evidence' in elem and 'evidence_quote' not in elem:
                        elem['evidence_quote'] = elem.pop('evidence')
                    if 'quote' in elem and 'evidence_quote' not in elem:
                        elem['evidence_quote'] = elem.pop('quote')
                    if 'justification_text' in elem and 'justification' not in elem:
                        elem['justification'] = elem.pop('justification_text')
                    # Ensure required fields exist
                    if 'tone' not in elem or not isinstance(elem.get('tone'), str) or not elem.get('tone').strip():
                        elem['tone'] = 'Informational'
                    if 'justification' not in elem or not isinstance(elem.get('justification'), str) or not elem.get('justification').strip():
                        elem['justification'] = 'Inferred from the dominant writing style across the provided snippets.'
                    # Ensure non-empty evidence_quote
                    eq = elem.get('evidence_quote', '')
                    elem['evidence_quote'] = ensure_quote(eq)
                    data[key] = elem

            # Normalize contradictions list
            contr = data.get('contradictions')
            if contr is not None:
                norm_contr: List[Dict[str, Any]] = []
                if isinstance(contr, list):
                    for item in contr[:3]:
                        if isinstance(item, str):
                            norm_contr.append({'contradiction': item, 'evidence_quote': "No specific quote; inferred from overall copy."})
                        elif isinstance(item, dict):
                            ctext = item.get('contradiction') or item.get('text') or item.get('reason') or item.get('note') or ''
                            eq = item.get('evidence_quote') or item.get('evidence') or item.get('quote') or ''
                            norm_contr.append({'contradiction': ctext, 'evidence_quote': ensure_quote(eq)})
                data['contradictions'] = norm_contr
            return data
        except Exception:
            return data

    def validate_with_repair(self, raw_json: str, schema_class, key_name: str) -> tuple[Optional[BaseModel], list[str]]:
        """Attempt to validate JSON against schema with auto-repair. Returns (validated_model|None, repairs)."""
        repairs: list[str] = []

        def _extract_json(text: str):
            """Extract first JSON object or array from a possibly fenced/verbose string."""
            try:
                return json.loads(text), []
            except Exception:
                pass
            s = text.strip()
            # Strip ```json fences
            if s.startswith("```"):
                fence_end = s.find("\n")
                if fence_end != -1:
                    s2 = s[fence_end+1:]
                    close = s2.rfind("```")
                    if close != -1:
                        s2 = s2[:close]
                    try:
                        return json.loads(s2), ["stripped_code_fence"]
                    except Exception:
                        s = s2
            # Find first balanced JSON object/array
            brace_idx = s.find("{")
            bracket_idx = s.find("[")
            idx = min([i for i in [brace_idx, bracket_idx] if i != -1], default=-1)
            if idx != -1:
                stack = []
                start_char = s[idx]
                end_char = "}" if start_char == "{" else "]"
                i = idx
                in_str = False
                esc = False
                while i < len(s):
                    ch = s[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                    else:
                        if ch == '"':
                            in_str = True
                        elif ch == start_char:
                            stack.append(end_char)
                        elif ch == end_char:
                            if stack:
                                stack.pop()
                                if not stack:
                                    candidate = s[idx:i+1]
                                    try:
                                        return json.loads(candidate), ["extracted_subjson"]
                                    except Exception:
                                        break
                    i += 1
            return None, ["json_parse_failed"]

        data = None
        # Try direct, then fence/substring extraction
        if isinstance(raw_json, (dict, list)):
            data = raw_json
        elif isinstance(raw_json, str):
            data, notes = _extract_json(raw_json)
            repairs += notes
        else:
            repairs.append("raw_json_not_str_or_dict")

        if data is None:
                return None, repairs
        
        # Domain-specific normalization
        if schema_class.__name__ == 'ToneOfVoiceResult':
            data = SchemaValidator._normalize_tone_of_voice_payload(data)

        # First validation attempt
        try:
            model = schema_class(**data)
            return model, repairs
        except Exception as e:
            repairs.append(f"Initial validation error: {e}")
        
        # Selective list cleanup
        if hasattr(schema_class, '__fields__'):
            for field_name, field_info in schema_class.__fields__.items():
                if field_name in data and isinstance(data[field_name], list):
                    items = data[field_name]
                    if isinstance(items, list):
                        data[field_name] = items[:10]

        # Final attempt
        try:
            model = schema_class(**data)
            return model, repairs
        except Exception as e:
            repairs.append(f"Final validation failed: {e}")
            return None, repairs
