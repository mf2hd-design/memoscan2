"""
Four C's Analysis LangGraph workflow.
Deep-dive analysis through Company, Category, Consumer, and Culture lenses.
"""

import structlog
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from ..nodes.common import node_initialize, node_cache_check, node_format_report
from ..nodes.brand_audit_nodes import node_identify_competitors, node_scrape_competitors, node_scrape_social_sentiment
from ..nodes.four_cs_nodes import node_research_four_cs, node_analyze_four_cs
from .base import get_checkpointer

logger = structlog.get_logger()

# Module-level variable for lazy initialization
four_cs_workflow = None


def should_skip_to_format(state: Dict[str, Any]) -> str:
    """Conditional edge: If cache hit, skip directly to format."""
    if state.get("cache_hit"):
        logger.info("cache_hit_routing_to_format")
        return "format"
    return "research"


async def create_four_cs_workflow():
    """
    Create and compile the Four C's Analysis workflow.

    Workflow steps:
    1. Initialize
    2. Cache check
    3. Research (brand, news, industry trends)
    4. Identify competitors (reused from Brand Audit)
    5. Scrape competitors (reused from Brand Audit)
    6. Scrape social sentiment (reused from Brand Audit)
    7. GPT-5.1 analysis
    8. Format and cache report

    Returns:
        Compiled workflow
    """
    logger.info("creating_four_cs_workflow")

    # Create state graph
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("research", node_research_four_cs)
    workflow.add_node("identify_competitors", node_identify_competitors)
    workflow.add_node("scrape_competitors", node_scrape_competitors)
    workflow.add_node("scrape_social", node_scrape_social_sentiment)
    workflow.add_node("analyze", node_analyze_four_cs)
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
    workflow.add_edge("research", "identify_competitors")
    workflow.add_edge("identify_competitors", "scrape_competitors")
    workflow.add_edge("scrape_competitors", "scrape_social")
    workflow.add_edge("scrape_social", "analyze")
    workflow.add_edge("analyze", "format")
    workflow.add_edge("format", END)

    # Get checkpointer
    checkpointer = await get_checkpointer()

    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)

    logger.info("four_cs_workflow_compiled")
    return app
