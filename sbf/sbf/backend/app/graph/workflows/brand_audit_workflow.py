"""
Brand Audit Workflow - LangGraph implementation.
10-step workflow for comprehensive brand analysis.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
brand_audit_workflow = None


class BrandAuditState(TypedDict, total=False):
    """State for Brand Audit workflow using TypedDict for LangGraph compatibility."""
    # Input fields
    report_type: str
    brand_name: str
    brand_url: str
    competitors: List[str]
    geography: str
    pdf_context: str

    # Workflow tracking
    workflow_id: str
    current_step: str
    progress_percent: int
    steps: Dict[str, str]

    # Scraped data
    brand_site_content: str
    social_sentiment: Dict[str, List[Dict]]
    competitor_urls: List[str]
    competitor_data: List[Dict]
    news_mentions: List[Dict]

    # Intermediate results
    identified_competitors: List[str]
    combined_context: str

    # Final output
    final_report: str
    chart_json: Optional[Dict]

    # Error handling (use Annotated for list merging)
    errors: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]

    # Cache
    cache_hit: bool


async def create_brand_audit_workflow():
    """Create and compile the Brand Audit workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.brand_audit_nodes import (
        node_ingest_pdf,
        node_scrape_brand,
        node_social_sentiment,
        node_identify_competitors,
        node_scrape_competitors,
        node_news_mentions,
        node_analyze_brand_audit
    )

    # Build the graph
    workflow = StateGraph(BrandAuditState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("ingest_pdf", node_ingest_pdf)
    workflow.add_node("scrape_brand", node_scrape_brand)
    workflow.add_node("social_sentiment", node_social_sentiment)
    workflow.add_node("identify_competitors", node_identify_competitors)
    workflow.add_node("scrape_competitors", node_scrape_competitors)
    workflow.add_node("news_mentions", node_news_mentions)
    workflow.add_node("analyze", node_analyze_brand_audit)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: BrandAuditState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "ingest_pdf"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "ingest_pdf": "ingest_pdf"
        }
    )

    # Sequential research flow
    workflow.add_edge("ingest_pdf", "scrape_brand")
    workflow.add_edge("scrape_brand", "social_sentiment")
    workflow.add_edge("social_sentiment", "identify_competitors")
    workflow.add_edge("identify_competitors", "scrape_competitors")
    workflow.add_edge("scrape_competitors", "news_mentions")
    workflow.add_edge("news_mentions", "analyze")
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("brand_audit_workflow_compiled")
    return compiled
