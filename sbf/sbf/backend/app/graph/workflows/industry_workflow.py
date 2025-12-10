"""
Industry Profile Workflow - LangGraph implementation.
Market research workflow for industry/category analysis.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
industry_profile_workflow = None


class IndustryProfileState(TypedDict, total=False):
    """State for Industry Profile workflow."""
    # Input fields
    report_type: str
    industry_name: str
    geography: str

    # Workflow tracking
    workflow_id: str
    current_step: str
    progress_percent: int
    steps: Dict[str, str]

    # Scraped data
    market_reports: List[Dict]
    trend_data: List[Dict]
    top_brands: List[Dict]
    emerging_brands: List[Dict]
    news_articles: List[Dict]

    # Combined context
    combined_context: str

    # Final output
    final_report: str
    chart_json: Optional[Dict]

    # Error handling
    errors: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]

    # Cache
    cache_hit: bool


async def create_industry_profile_workflow():
    """Create and compile the Industry Profile workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.industry_nodes import (
        node_market_reports,
        node_top_brands,
        node_trends,
        node_news,
        node_analyze_industry
    )

    # Build the graph
    workflow = StateGraph(IndustryProfileState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("market_reports", node_market_reports)
    workflow.add_node("top_brands", node_top_brands)
    workflow.add_node("trends", node_trends)
    workflow.add_node("news", node_news)
    workflow.add_node("analyze", node_analyze_industry)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: IndustryProfileState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "market_reports"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "market_reports": "market_reports"
        }
    )

    # Sequential research flow
    workflow.add_edge("market_reports", "top_brands")
    workflow.add_edge("top_brands", "trends")
    workflow.add_edge("trends", "news")
    workflow.add_edge("news", "analyze")
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("industry_profile_workflow_compiled")
    return compiled
