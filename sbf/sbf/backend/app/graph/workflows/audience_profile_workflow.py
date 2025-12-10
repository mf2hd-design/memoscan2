"""
Audience Profile Workflow - LangGraph implementation.
Demographics and psychographics analysis workflow.
Uses GPT-5.1 knowledge only (no web scraping).
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
audience_profile_workflow = None


class AudienceProfileState(TypedDict, total=False):
    """State for Audience Profile workflow."""
    # Input fields
    report_type: str
    audience_name: str
    geography: str

    # Workflow tracking
    workflow_id: str
    current_step: str
    progress_percent: int
    steps: Dict[str, str]

    # Analysis results (GPT-5.1 knowledge only)
    demographics: Dict
    psychographics: Dict
    media_habits: Dict
    purchase_behavior: Dict

    # Combined context
    combined_context: str

    # Final output
    final_report: str
    chart_json: Optional[Dict]  # Radar chart for priorities

    # Error handling
    errors: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]

    # Cache
    cache_hit: bool


async def create_audience_profile_workflow():
    """Create and compile the Audience Profile workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.audience_profile_nodes import node_analyze_audience_profile

    # Build the graph
    workflow = StateGraph(AudienceProfileState)

    # Add nodes - simplified workflow (GPT-5.1 only)
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("analyze", node_analyze_audience_profile)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: AudienceProfileState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "analyze"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "analyze": "analyze"
        }
    )

    # Direct to format after analysis (no scraping steps)
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("audience_profile_workflow_compiled")
    return compiled
