"""
Industry Profile LangGraph workflow.
Market research and analysis workflow.
"""

import structlog
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from ...models.schemas import IndustryProfileState
from ..nodes.common import node_initialize, node_cache_check, node_format_report
from ..nodes.industry_nodes import (
    node_research_industry,
    node_gpt5_industry_analyze
)
from .base import get_checkpointer

logger = structlog.get_logger()


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


async def create_industry_profile_workflow():
    """
    Create and compile the Industry Profile workflow with PostgreSQL checkpointing.

    Workflow steps:
    1. Initialize
    2. Cache check
    3. Research industry (market, brands, trends, news)
    4. GPT-5.1 analysis
    5. Format and cache report

    Returns:
        Compiled workflow
    """
    logger.info("creating_industry_profile_workflow")

    # Create state graph
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("research", node_research_industry)
    workflow.add_node("analyze", node_gpt5_industry_analyze)
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

    logger.info("industry_profile_workflow_created")

    return compiled


# Create workflow instance (async initialization handled by FastAPI)
industry_profile_workflow = None
