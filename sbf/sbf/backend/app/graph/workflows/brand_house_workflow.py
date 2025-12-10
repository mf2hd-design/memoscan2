"""
Brand House Workflow - LangGraph implementation.
Strategic brand positioning analysis workflow.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
brand_house_workflow = None


class BrandHouseState(TypedDict, total=False):
    """State for Brand House workflow."""
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

    # Scraped data (reuses Brand Audit nodes)
    brand_site_content: str
    competitor_data: List[Dict]
    news_mentions: List[Dict]

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


async def create_brand_house_workflow():
    """Create and compile the Brand House workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.brand_house_nodes import (
        node_scrape_brand_house,
        node_competitor_analysis,
        node_analyze_brand_house
    )

    # Build the graph
    workflow = StateGraph(BrandHouseState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("scrape_brand", node_scrape_brand_house)
    workflow.add_node("competitor_analysis", node_competitor_analysis)
    workflow.add_node("analyze", node_analyze_brand_house)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: BrandHouseState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "scrape_brand"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "scrape_brand": "scrape_brand"
        }
    )

    # Sequential research flow
    workflow.add_edge("scrape_brand", "competitor_analysis")
    workflow.add_edge("competitor_analysis", "analyze")
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("brand_house_workflow_compiled")
    return compiled
