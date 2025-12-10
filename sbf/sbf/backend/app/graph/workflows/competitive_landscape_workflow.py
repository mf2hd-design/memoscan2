"""
Competitive Landscape Workflow - LangGraph implementation.
Market positioning and competitive analysis workflow.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
competitive_landscape_workflow = None


class CompetitiveLandscapeState(TypedDict, total=False):
    """State for Competitive Landscape workflow."""
    # Input fields
    report_type: str
    brand_name: str
    brand_url: str
    geography: str

    # Workflow tracking
    workflow_id: str
    current_step: str
    progress_percent: int
    steps: Dict[str, str]

    # Scraped data
    brand_site_content: str
    competitor_urls: List[str]
    competitor_data: List[Dict]
    market_data: Dict

    # Combined context
    combined_context: str

    # Final output
    final_report: str
    chart_json: Optional[Dict]  # Competitive positioning map

    # Error handling
    errors: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]

    # Cache
    cache_hit: bool


async def create_competitive_landscape_workflow():
    """Create and compile the Competitive Landscape workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.competitive_landscape_nodes import (
        node_identify_competitors_landscape,
        node_scrape_competitors_landscape,
        node_market_positioning,
        node_analyze_competitive_landscape
    )

    # Build the graph
    workflow = StateGraph(CompetitiveLandscapeState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("identify_competitors", node_identify_competitors_landscape)
    workflow.add_node("scrape_competitors", node_scrape_competitors_landscape)
    workflow.add_node("market_positioning", node_market_positioning)
    workflow.add_node("analyze", node_analyze_competitive_landscape)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: CompetitiveLandscapeState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "identify_competitors"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "identify_competitors": "identify_competitors"
        }
    )

    # Sequential research flow
    workflow.add_edge("identify_competitors", "scrape_competitors")
    workflow.add_edge("scrape_competitors", "market_positioning")
    workflow.add_edge("market_positioning", "analyze")
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("competitive_landscape_workflow_compiled")
    return compiled
