"""
Discovery Mode Schema Definitions
Version: 1.0.0
Date: August 2025

Pydantic models for strict schema validation with auto-repair capabilities.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
import json
from datetime import datetime

# === Positioning Themes Schema ===
class PositioningTheme(BaseModel):
    theme: str = Field(..., min_length=1, max_length=50)
    confidence: int = Field(..., ge=0, le=100)
    evidence: str = Field(..., min_length=1)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        """Auto-repair: Convert string numbers to int."""
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

class PositioningThemesResult(BaseModel):
    themes: List[PositioningTheme] = Field(..., min_items=1, max_items=5)

# === Key Messages Schema ===
class KeyMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=100)
    confidence: int = Field(..., ge=0, le=100)
    evidence: str = Field(..., min_length=1)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

class KeyMessagesResult(BaseModel):
    messages: List[KeyMessage] = Field(..., min_items=1, max_items=5)

# === Tone of Voice Schema ===
class ToneDescriptor(BaseModel):
    adjective: str = Field(..., min_length=1, max_length=30)
    justification: str = Field(..., min_length=1, max_length=200)
    confidence: int = Field(..., ge=0, le=100)
    evidence: str = Field(..., min_length=1)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

class ToneOfVoiceResult(BaseModel):
    tone_descriptors: List[ToneDescriptor] = Field(..., min_items=1, max_items=4)

# === Brand Elements Schema ===
class OverallImpression(BaseModel):
    summary: str = Field(..., min_length=1, max_length=200)
    keywords: List[str] = Field(..., min_items=1, max_items=5)

class ConsistencyAnalysis(BaseModel):
    consistency: Literal["High", "Medium", "Low"]
    notes: str = Field(..., min_length=1, max_length=200)

class DetailedAnalysis(BaseModel):
    color_palette: ConsistencyAnalysis
    typography: ConsistencyAnalysis
    imagery: ConsistencyAnalysis
    brand_architecture: ConsistencyAnalysis

class BrandElementsResult(BaseModel):
    overall_impression: OverallImpression
    coherence_score: int = Field(..., ge=1, le=5)
    detailed_analysis: DetailedAnalysis
    strategic_alignment: str = Field(..., min_length=1, max_length=300)
    confidence: int = Field(..., ge=0, le=100)
    evidence: str = Field(..., min_length=1)
    
    @validator('confidence', pre=True)
    def coerce_confidence(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

# === Visual-Text Alignment Schema ===
class VisualTextAlignmentResult(BaseModel):
    alignment: Literal["Yes", "No"]
    justification: str = Field(..., min_length=1, max_length=200)

# === Discovery Scan Result ===
class DiscoveryScanResult(BaseModel):
    scan_id: str
    mode: Literal["discovery"]
    url: str
    timestamp: datetime
    results: dict  # Will contain the individual key results
    metadata: dict  # Performance and model information
    
class DiscoveryFeedback(BaseModel):
    """Schema for Discovery Mode feedback."""
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
    def validate_with_repair(raw_json: str, schema_class, key_name: str) -> tuple[Optional[BaseModel], list[str]]:
        """
        Attempt to validate JSON against schema with auto-repair.
        
        Returns:
            Tuple of (validated_model or None, list of repair actions taken)
        """
        repairs = []
        
        try:
            # First attempt: Parse as-is
            data = json.loads(raw_json)
            model = schema_class(**data)
            return model, ["No repairs needed"]
        
        except json.JSONDecodeError as e:
            repairs.append(f"JSON decode error: {e}")
            # Attempt to fix common JSON issues
            try:
                # Fix single quotes, trailing commas, etc.
                import re
                fixed_json = raw_json.replace("'", '"')
                fixed_json = re.sub(r',\s*}', '}', fixed_json)
                fixed_json = re.sub(r',\s*]', ']', fixed_json)
                data = json.loads(fixed_json)
                repairs.append("Fixed JSON syntax issues")
            except:
                repairs.append("JSON repair failed - discarding result")
                return None, repairs
        
        except Exception as e:
            data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            repairs.append(f"Initial validation error: {e}")
        
        # Selective invalidation for list items
        if hasattr(schema_class, '__fields__'):
            for field_name, field in schema_class.__fields__.items():
                if field_name in data and isinstance(data[field_name], list):
                    valid_items = []
                    for i, item in enumerate(data[field_name]):
                        try:
                            # Validate individual item
                            if hasattr(field.type_, '__args__'):
                                item_class = field.type_.__args__[0]
                                validated_item = item_class(**item)
                                valid_items.append(item.dict())
                        except Exception as item_error:
                            repairs.append(f"Discarded invalid {field_name}[{i}]: {item_error}")
                    
                    if valid_items:
                        data[field_name] = valid_items
                    else:
                        repairs.append(f"All items in {field_name} were invalid")
                        return None, repairs
        
        # Final validation attempt with repaired data
        try:
            model = schema_class(**data)
            return model, repairs
        except Exception as e:
            repairs.append(f"Final validation failed: {e}")
            return None, repairs

# === Export Functions ===
def export_to_json(scan_result: DiscoveryScanResult) -> str:
    """Export scan result to clean JSON format."""
    return json.dumps(scan_result.dict(), indent=2, default=str)

def export_to_pdf(scan_result: DiscoveryScanResult, screenshots: list) -> bytes:
    """
    Export scan result to PDF format.
    Note: This is a placeholder - actual PDF generation would use reportlab or similar.
    """
    # This would be implemented with a PDF library in production
    pass