"""
Meeting Brief Workflow - LangGraph implementation.
Research workflow for person/company intelligence before meetings.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
import structlog

logger = structlog.get_logger()

# Module-level workflow (lazy initialized)
meeting_brief_workflow = None


class MeetingBriefState(TypedDict, total=False):
    """State for Meeting Brief workflow."""
    # Input fields
    report_type: str
    person_name: str
    person_role: str
    company_name: str
    geography: str

    # Workflow tracking
    workflow_id: str
    current_step: str
    progress_percent: int
    steps: Dict[str, str]

    # Scraped data
    person_profile: Dict
    company_data: Dict
    company_url: str
    recent_news: List[Dict]
    competitors: List[str]
    industry_trends: List[Dict]

    # Combined context
    combined_context: str

    # Final output
    final_report: str
    chart_json: Optional[Dict]

    # Error handling (use Annotated for proper list merging)
    errors: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]

    # Cache
    cache_hit: bool


async def create_meeting_brief_workflow():
    """Create and compile the Meeting Brief workflow graph."""
    from ..nodes.common import node_initialize, node_cache_check, node_format_report
    from ..nodes.meeting_brief_nodes import (
        node_research_person,
        node_research_company,
        node_recent_news,
        node_industry_context,
        node_analyze_meeting_brief
    )

    # Build the graph
    workflow = StateGraph(MeetingBriefState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("research_person", node_research_person)
    workflow.add_node("research_company", node_research_company)
    workflow.add_node("recent_news", node_recent_news)
    workflow.add_node("industry_context", node_industry_context)
    workflow.add_node("analyze", node_analyze_meeting_brief)
    workflow.add_node("format_report", node_format_report)

    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional edge from cache_check
    def route_from_cache(state: MeetingBriefState) -> str:
        if state.get("cache_hit"):
            return "format_report"
        return "research_person"

    workflow.add_conditional_edges(
        "cache_check",
        route_from_cache,
        {
            "format_report": "format_report",
            "research_person": "research_person"
        }
    )

    # Sequential research flow
    workflow.add_edge("research_person", "research_company")
    workflow.add_edge("research_company", "recent_news")
    workflow.add_edge("recent_news", "industry_context")
    workflow.add_edge("industry_context", "analyze")
    workflow.add_edge("analyze", "format_report")
    workflow.add_edge("format_report", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    logger.info("meeting_brief_workflow_compiled")
    return compiled
