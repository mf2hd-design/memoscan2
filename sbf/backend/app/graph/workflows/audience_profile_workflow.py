"""
Audience Profile LangGraph workflow.
Deep-dive target audience demographics, psychographics, and behavior analysis.
"""

import structlog
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from ..nodes.common import node_initialize, node_cache_check, node_format_report
from ..nodes.audience_profile_nodes import node_research_audience, node_analyze_audience
from .base import get_checkpointer

logger = structlog.get_logger()

# Module-level variable for lazy initialization
audience_profile_workflow = None


def should_skip_to_format(state: Dict[str, Any]) -> str:
    """Conditional edge: If cache hit, skip directly to format."""
    if state.get("cache_hit"):
        logger.info("cache_hit_routing_to_format")
        return "format"
    return "research"


async def create_audience_profile_workflow():
    """
    Create and compile the Audience Profile workflow.

    Workflow steps:
    1. Initialize
    2. Cache check
    3. Research audience (demographics, psychographics, media, brands)
    4. GPT-5.1 analysis
    5. Format and cache report

    Returns:
        Compiled workflow
    """
    logger.info("creating_audience_profile_workflow")

    # Create state graph
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("research", node_research_audience)
    workflow.add_node("analyze", node_analyze_audience)
    workflow.add_node("format", node_format_report)

    # Define flow
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")
    workflow.add_conditional_edges(
        "cache_check",
        should_skip_to_format,
        {
            "format": "format",
            "research": "research"
        }
    )
    workflow.add_edge("research", "analyze")
    workflow.add_edge("analyze", "format")
    workflow.add_edge("format", END)

    # Get checkpointer
    checkpointer = await get_checkpointer()

    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)

    logger.info("audience_profile_workflow_compiled")
    return app
