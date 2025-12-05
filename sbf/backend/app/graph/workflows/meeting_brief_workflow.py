"""
Meeting Brief LangGraph workflow.
Simpler workflow focused on person and company intelligence.
"""

import structlog
import operator
from langgraph.graph import StateGraph, END
from typing import Dict, Any, TypedDict, Annotated

from ...models.schemas import MeetingBriefState
from ..nodes.common import node_initialize, node_cache_check, node_format_report
from ..nodes.meeting_brief_nodes import (
    node_research_person_and_company,
    node_gpt5_meeting_brief_analyze
)
from .base import get_checkpointer

logger = structlog.get_logger()


# Define state schema with proper merging behavior
class MeetingBriefWorkflowState(TypedDict, total=False):
    """State schema for meeting brief workflow with merge semantics."""
    # Inputs (never change, so no special reducer needed)
    report_type: str
    person_name: str
    person_role: str
    company_name: str
    geography: str
    workflow_id: str

    # Progress tracking (update via replacement)
    steps: Dict[str, str]
    current_step: str
    progress_percent: int

    # Accumulating fields (merge via operator.add)
    errors: Annotated[list, operator.add]
    warnings: Annotated[list, operator.add]

    # Scraped data (update via replacement)
    person_profile: Dict[str, Any]
    company_data: Dict[str, Any]
    company_url: str
    recent_news: list
    competitors: list

    # Results (update via replacement)
    final_report: str
    chart_json: Any
    cache_hit: bool


def should_skip_to_format(state: Dict[str, Any]) -> str:
    """
    Conditional edge: If cache hit, skip directly to format.

    Args:
        state: Current state

    Returns:
        Next node name
    """
    if state.get("cache_hit"):
        logger.info("cache_hit_routing_to_format")
        return "format"
    return "research"


async def create_meeting_brief_workflow():
    """
    Create and compile the Meeting Brief workflow with PostgreSQL checkpointing.

    Workflow steps:
    1. Initialize
    2. Cache check
    3. Research person and company (combined node)
    4. GPT-5.1 analysis
    5. Format and cache report

    Returns:
        Compiled workflow
    """
    logger.info("creating_meeting_brief_workflow")

    # Create state graph with TypedDict schema for proper state merging
    workflow = StateGraph(MeetingBriefWorkflowState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("research", node_research_person_and_company)
    workflow.add_node("analyze", node_gpt5_meeting_brief_analyze)
    workflow.add_node("format", node_format_report)

    # Define flow
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")

    # Conditional: if cache hit, skip to format
    workflow.add_conditional_edges(
        "cache_check",
        should_skip_to_format,
        {
            "format": "format",
            "research": "research"
        }
    )

    # Linear flow through research and analysis
    workflow.add_edge("research", "analyze")
    workflow.add_edge("analyze", "format")
    workflow.add_edge("format", END)

    # Get PostgreSQL checkpointer
    checkpointer = await get_checkpointer()

    # Compile workflow
    compiled = workflow.compile(checkpointer=checkpointer)

    logger.info("meeting_brief_workflow_created")

    return compiled


# Create workflow instance (async initialization handled by FastAPI)
meeting_brief_workflow = None
