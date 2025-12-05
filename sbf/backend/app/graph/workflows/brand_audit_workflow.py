"""
Brand Audit LangGraph workflow.
Complete pipeline for brand intelligence and strategic analysis.
"""

import structlog
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from ...models.schemas import BrandAuditState
from ..nodes.common import node_initialize, node_cache_check, node_format_report
from ..nodes.brand_audit_nodes import (
    node_ingest_pdfs,
    node_scrape_brand_website,
    node_scrape_social_sentiment,
    node_identify_competitors,
    node_scrape_competitors,
    node_scrape_news_mentions,
    node_gpt5_analyze
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
    return "ingest_pdfs"


async def create_brand_audit_workflow():
    """
    Create and compile the Brand Audit workflow with PostgreSQL checkpointing.

    Workflow steps:
    1. Initialize
    2. Cache check
    3. Ingest PDFs (if uploaded)
    4. Scrape brand website
    5. Scrape social sentiment (Twitter, Reddit, Instagram, Facebook)
    6. Identify competitors
    7. Scrape competitors
    8. Scrape news mentions
    9. GPT-5.1 analysis
    10. Format and cache report

    Returns:
        Compiled workflow
    """
    logger.info("creating_brand_audit_workflow")

    # Create state graph
    workflow = StateGraph(dict)  # Using dict for flexibility

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("cache_check", node_cache_check)
    workflow.add_node("ingest_pdfs", node_ingest_pdfs)
    workflow.add_node("scrape_brand", node_scrape_brand_website)
    workflow.add_node("scrape_social", node_scrape_social_sentiment)
    workflow.add_node("identify_competitors", node_identify_competitors)
    workflow.add_node("scrape_competitors", node_scrape_competitors)
    workflow.add_node("scrape_news", node_scrape_news_mentions)
    workflow.add_node("analyze", node_gpt5_analyze)
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
            "ingest_pdfs": "ingest_pdfs"
        }
    )

    # Linear flow through scraping steps
    workflow.add_edge("ingest_pdfs", "scrape_brand")
    workflow.add_edge("scrape_brand", "scrape_social")
    workflow.add_edge("scrape_social", "identify_competitors")
    workflow.add_edge("identify_competitors", "scrape_competitors")
    workflow.add_edge("scrape_competitors", "scrape_news")
    workflow.add_edge("scrape_news", "analyze")
    workflow.add_edge("analyze", "format")
    workflow.add_edge("format", END)

    # Get PostgreSQL checkpointer
    checkpointer = await get_checkpointer()

    # Compile workflow
    compiled = workflow.compile(checkpointer=checkpointer)

    logger.info("brand_audit_workflow_created")

    return compiled


# Create workflow instance (async initialization handled by FastAPI)
brand_audit_workflow = None
