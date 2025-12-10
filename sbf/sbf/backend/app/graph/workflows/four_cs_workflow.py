"""
Four C's Workflow - LangGraph implementation.
Company/Category/Consumer/Culture analysis workflow.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
four_cs_workflow = None


class FourCsState(TypedDict, total=False):
    """State for Four C's workflow."""
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

    # Scraped data for each C
    company_data: Dict
    category_data: Dict
    consumer_data: Dict
    culture_data: Dict

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


async def create_four_cs_workflow():
    """Create and compile the Four C's workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.four_cs_nodes import (
        node_company_research,
        node_category_research,
        node_consumer_research,
        node_culture_research,
        node_analyze_four_cs
    )

    # Build the graph
    workflow = StateGraph(FourCsState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("company", node_company_research)
    workflow.add_node("category", node_category_research)
    workflow.add_node("consumer", node_consumer_research)
    workflow.add_node("culture", node_culture_research)
    workflow.add_node("analyze", node_analyze_four_cs)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: FourCsState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "company"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "company": "company"
        }
    )

    # Sequential research flow (all 4 C's)
    workflow.add_edge("company", "category")
    workflow.add_edge("category", "consumer")
    workflow.add_edge("consumer", "culture")
    workflow.add_edge("culture", "analyze")
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("four_cs_workflow_compiled")
    return compiled
