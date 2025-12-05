"""
Competitive Landscape LangGraph workflow.
Deep competitive intelligence and market positioning map.
"""

import structlog
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from ..nodes.common import node_initialize, node_cache_check, node_format_report
from ..nodes.brand_audit_nodes import node_identify_competitors, node_scrape_competitors
from ..nodes.competitive_landscape_nodes import node_research_competitive_landscape, node_analyze_competitive_landscape
from .base import get_checkpointer

logger = structlog.get_logger()

# Module-level variable for lazy initialization
competitive_landscape_workflow = None


def should_skip_to_format(state: Dict[str, Any]) -> str:
    """Conditional edge: If cache hit, skip directly to format."""
    if state.get("cache_hit"):
        logger.info("cache_hit_routing_to_format")
        return "format"
    return "identify_competitors"


async def create_competitive_landscape_workflow():
    """
    Create and compile the Competitive Landscape workflow.

    Workflow steps:
    1. Initialize
    2. Cache check
    3. Identify competitors (reused from Brand Audit)
    4. Scrape competitors (reused from Brand Audit)
    5. Research market analysis
    6. GPT-5.1 analysis
    7. Format and cache report

    Returns:
        Compiled workflow
    """
    logger.info("creating_competitive_landscape_workflow")

    # Create state graph
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("identify_competitors", node_identify_competitors)
    workflow.add_node("scrape_competitors", node_scrape_competitors)
    workflow.add_node("research_market", node_research_competitive_landscape)
    workflow.add_node("analyze", node_analyze_competitive_landscape)
    workflow.add_node("format", node_format_report)

    # Define flow
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "cache_check")
    workflow.add_conditional_edges(
        "cache_check",
        should_skip_to_format,
        {
            "format": "format",
            "identify_competitors": "identify_competitors"
        }
    )
    workflow.add_edge("identify_competitors", "scrape_competitors")
    workflow.add_edge("scrape_competitors", "research_market")
    workflow.add_edge("research_market", "analyze")
    workflow.add_edge("analyze", "format")
    workflow.add_edge("format", END)

    # Get checkpointer
    checkpointer = await get_checkpointer()

    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)

    logger.info("competitive_landscape_workflow_compiled")
    return app
