"""
Pydantic models for Strategist's Best Friend.
Defines request/response schemas and LangGraph state models.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid


# === Enums ===

class StepStatus(str, Enum):
    """Workflow step status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportType(str, Enum):
    """Available report types."""
    BRAND_AUDIT = "brand_audit"
    MEETING_BRIEF = "meeting_brief"
    INDUSTRY_PROFILE = "industry_profile"


# === Request Models ===

class BrandAuditRequest(BaseModel):
    """Request schema for Brand Audit report."""
    report_type: Literal["brand_audit"]
    brand_name: str = Field(..., min_length=1, description="Brand name to audit")
    brand_url: str = Field(..., description="Brand website URL")
    competitors: Optional[List[str]] = Field(default=[], description="Optional competitor names/URLs")
    geography: str = Field(default="US", description="Target geography code (US, UK, DE, etc.)")


class MeetingBriefRequest(BaseModel):
    """Request schema for Meeting Brief report."""
    report_type: Literal["meeting_brief"]
    person_name: str = Field(..., min_length=1, description="Person's full name")
    person_role: str = Field(..., min_length=1, description="Person's role/title")
    company_name: str = Field(..., min_length=1, description="Company name")
    geography: str = Field(default="US", description="Target geography code")


class IndustryProfileRequest(BaseModel):
    """Request schema for Industry Profile report."""
    report_type: Literal["industry_profile"]
    industry_name: str = Field(..., min_length=1, description="Industry/category name")
    geography: str = Field(default="US", description="Target geography code")


# Union type for all request types
ReportRequest = Union[BrandAuditRequest, MeetingBriefRequest, IndustryProfileRequest]


# === LangGraph State Models ===

class BaseAnalysisState(BaseModel):
    """Base state for all analysis workflows."""
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    report_type: ReportType
    started_at: datetime = Field(default_factory=datetime.utcnow)
    geography: str = "US"

    # Progress tracking
    steps: Dict[str, StepStatus] = Field(default_factory=dict)
    current_step: str = ""
    progress_percent: int = 0

    # Error handling
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Results
    combined_context: str = ""
    final_report: str = ""
    chart_json: Optional[Any] = None

    # Cache
    cache_hit: bool = False

    class Config:
        arbitrary_types_allowed = True


class BrandAuditState(BaseAnalysisState):
    """State for Brand Audit workflow."""
    brand_name: str
    brand_url: str
    competitors: List[str] = Field(default_factory=list)

    # Scraped data
    brand_site_content: str = ""
    social_sentiment: Dict[str, List[Dict]] = Field(default_factory=lambda: {
        "twitter": [],
        "reddit": [],
        "instagram": [],
        "facebook": []
    })
    competitor_urls: List[str] = Field(default_factory=list)
    competitor_data: List[Dict] = Field(default_factory=list)
    news_mentions: List[Dict] = Field(default_factory=list)

    # RAG (PDF uploads)
    pdf_context: str = ""

    # Intermediate results
    identified_competitors: List[str] = Field(default_factory=list)


class MeetingBriefState(BaseAnalysisState):
    """State for Meeting Brief workflow."""
    person_name: str
    person_role: str
    company_name: str

    # Scraped data
    person_profile: Dict = Field(default_factory=dict)
    company_data: Dict = Field(default_factory=dict)
    company_url: str = ""
    recent_news: List[Dict] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list)
    industry_trends: List[Dict] = Field(default_factory=list)


class IndustryProfileState(BaseAnalysisState):
    """State for Industry Profile workflow."""
    industry_name: str

    # Scraped data
    market_reports: List[Dict] = Field(default_factory=list)
    trend_data: List[Dict] = Field(default_factory=list)
    top_brands: List[Dict] = Field(default_factory=list)
    emerging_brands: List[Dict] = Field(default_factory=list)
    news_articles: List[Dict] = Field(default_factory=list)


# === Chart Models ===

class RadarChartData(BaseModel):
    """Radar chart data (for Audience Profile)."""
    chart_type: Literal["radar"] = "radar"
    chart_title: str
    data: List[Dict[str, Any]] = Field(
        ...,
        description="List of data points with 'subject' and value keys"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "chart_type": "radar",
                "chart_title": "Audience Priorities",
                "data": [
                    {"subject": "Convenience", "A": 85, "fullMark": 100},
                    {"subject": "Trust", "A": 90, "fullMark": 100},
                    {"subject": "Innovation", "A": 70, "fullMark": 100}
                ]
            }
        }


class CompetitiveMapData(BaseModel):
    """Competitive positioning map (2x2 matrix)."""
    chart_type: Literal["competitive_map"] = "competitive_map"
    chart_title: str
    quadrants: List[Dict[str, Any]] = Field(
        ...,
        description="List of brands with x, y coordinates and labels"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "chart_type": "competitive_map",
                "chart_title": "Competitive Landscape",
                "quadrants": [
                    {"x": 0.8, "y": 0.7, "label": "Brand A", "category": "Leader"},
                    {"x": 0.4, "y": 0.3, "label": "Brand B", "category": "Challenger"}
                ]
            }
        }


class TableData(BaseModel):
    """Table chart data."""
    chart_type: Literal["table"] = "table"
    chart_title: str
    headers: List[str]
    rows: List[List[str]]

    class Config:
        json_schema_extra = {
            "example": {
                "chart_type": "table",
                "chart_title": "Competitor Comparison",
                "headers": ["Company", "Description", "Category", "Strengths"],
                "rows": [
                    ["Company A", "Market leader", "Enterprise", "Scale, Innovation"],
                    ["Company B", "Fast follower", "Mid-market", "Price, Agility"]
                ]
            }
        }


# === Response Models (for API streaming) ===

class ProgressUpdate(BaseModel):
    """Progress update event."""
    type: Literal["progress"] = "progress"
    message: str
    step: Optional[str] = None
    progress_percent: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ResultResponse(BaseModel):
    """Final result event."""
    type: Literal["result"] = "result"
    markdown: str
    chart: Optional[Union[RadarChartData, CompetitiveMapData, TableData]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error event."""
    type: Literal["error"] = "error"
    message: str
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# === Scraping Result Models ===

class ScrapeResult(BaseModel):
    """Result of a web scraping operation."""
    success: bool
    url: str
    content: Optional[str] = None
    error: Optional[str] = None
    source_id: int = 0
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class SocialSentimentResult(BaseModel):
    """Social media sentiment analysis result."""
    platform: Literal["twitter", "reddit", "instagram", "facebook"]
    posts: List[Dict[str, Any]]
    summary: str = ""
    sentiment_score: Optional[float] = None


# === Structured LLM Output Models ===

class BrandAuditOutput(BaseModel):
    """Structured output from Brand Audit LLM analysis."""
    executive_summary: str = Field(..., description="Strategic tensions and key insights")
    owned_space: str = Field(..., description="What the brand does well")
    recent_developments: str = Field(..., description="Recent news and developments")
    social_sentiment: str = Field(..., description="Social media sentiment analysis")
    competitor_analysis: str = Field(..., description="Competitive landscape")
    recommendations: str = Field(..., description="Strategic recommendations")
    chart_data: Optional[CompetitiveMapData] = None


class MeetingBriefOutput(BaseModel):
    """Structured output from Meeting Brief LLM analysis."""
    person_background: str = Field(..., description="Background on the person")
    company_overview: str = Field(..., description="Company information")
    recent_news: str = Field(..., description="Recent news and updates")
    competitors: str = Field(..., description="Competitive landscape")
    industry_trends: str = Field(..., description="Relevant industry trends")
    talking_points: List[str] = Field(..., description="Suggested conversation topics")


class IndustryProfileOutput(BaseModel):
    """Structured output from Industry Profile LLM analysis."""
    macro_trends: str = Field(..., description="Major industry trends")
    challenges: str = Field(..., description="Industry challenges and threats")
    opportunities: str = Field(..., description="Growth opportunities")
    drivers: str = Field(..., description="Market drivers")
    consumer_mindset: str = Field(..., description="Consumer preferences")
    leading_brands: str = Field(..., description="Top industry players")
    emerging_brands: str = Field(..., description="Disruptors and startups")
