"""
Common LangGraph nodes shared across all workflows.
"""

import structlog
from typing import Dict, Any

from ...models.schemas import StepStatus
from ...services.cache import query_cache

logger = structlog.get_logger()


async def node_initialize(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize workflow state.

    Args:
        state: Current state dict

    Returns:
        Updated state with initialization
    """
    logger.info(
        "node_initialize_entry",
        workflow_id=state.get("workflow_id"),
        person_name=state.get("person_name"),
        company_name=state.get("company_name"),
        state_keys=list(state.keys())
    )

    # Initialize steps based on report type
    report_type = state.get("report_type")

    if report_type == "brand_audit":
        steps = {
            "initialize": StepStatus.IN_PROGRESS,
            "cache_check": StepStatus.PENDING,
            "ingest_pdfs": StepStatus.PENDING,
            "scrape_brand": StepStatus.PENDING,
            "scrape_social": StepStatus.PENDING,
            "identify_competitors": StepStatus.PENDING,
            "scrape_competitors": StepStatus.PENDING,
            "scrape_news": StepStatus.PENDING,
            "analyze": StepStatus.PENDING,
            "format": StepStatus.PENDING
        }
    elif report_type == "meeting_brief":
        steps = {
            "initialize": StepStatus.IN_PROGRESS,
            "cache_check": StepStatus.PENDING,
            "scrape_person": StepStatus.PENDING,
            "scrape_company": StepStatus.PENDING,
            "scrape_news": StepStatus.PENDING,
            "scrape_competitors": StepStatus.PENDING,
            "analyze": StepStatus.PENDING,
            "format": StepStatus.PENDING
        }
    else:  # industry_profile
        steps = {
            "initialize": StepStatus.IN_PROGRESS,
            "cache_check": StepStatus.PENDING,
            "research_market": StepStatus.PENDING,
            "research_brands": StepStatus.PENDING,
            "scrape_news": StepStatus.PENDING,
            "analyze": StepStatus.PENDING,
            "format": StepStatus.PENDING
        }

    # IMPORTANT: Return the merged state to preserve initial values
    # LangGraph StateGraph(dict) replaces state on return, not merges
    return {
        **state,  # Preserve all existing state (industry_name, geography, etc.)
        "steps": steps,
        "current_step": "Initializing workflow...",
        "progress_percent": 5
    }


async def node_cache_check(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if cached results exist for this query.

    Args:
        state: Current state dict

    Returns:
        Updated state with cache hit status
    """
    logger.info("node_cache_check", workflow_id=state.get("workflow_id"))

    report_type = state.get("report_type")

    # Build cache key based on report type
    if report_type == "brand_audit":
        cache_key_parts = (
            report_type,
            state.get("brand_name"),
            state.get("geography")
        )
    elif report_type == "meeting_brief":
        cache_key_parts = (
            report_type,
            state.get("person_name"),
            state.get("company_name"),
            state.get("geography")
        )
    else:  # industry_profile
        cache_key_parts = (
            report_type,
            state.get("industry_name"),
            state.get("geography")
        )

    # Check cache
    cached_data = query_cache.get(*cache_key_parts)

    if cached_data:
        logger.info("cache_hit", workflow_id=state.get("workflow_id"))

        return {
            "cache_hit": True,
            "final_report": cached_data.get("report", ""),
            "chart_json": cached_data.get("chart"),
            "current_step": "Using cached results...",
            "progress_percent": 95,
            "steps": {**state.get("steps", {}), "cache_check": StepStatus.COMPLETED}
        }

    logger.info("cache_miss", workflow_id=state.get("workflow_id"))

    # IMPORTANT: Preserve all existing state
    return {
        **state,  # Preserve all existing state (industry_name, geography, etc.)
        "cache_hit": False,
        "current_step": "Starting fresh research...",
        "progress_percent": 10,
        "steps": {**state.get("steps", {}), "cache_check": StepStatus.COMPLETED}
    }


async def node_format_report(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final formatting and caching of report.

    Args:
        state: Current state dict

    Returns:
        Updated state with formatted report
    """
    logger.info("node_format_report", workflow_id=state.get("workflow_id"))

    report_type = state.get("report_type")

    # Cache the results
    cache_data = {
        "report": state.get("final_report", ""),
        "chart": state.get("chart_json")
    }

    if report_type == "brand_audit":
        cache_key_parts = (
            report_type,
            state.get("brand_name"),
            state.get("geography")
        )
    elif report_type == "meeting_brief":
        cache_key_parts = (
            report_type,
            state.get("person_name"),
            state.get("company_name"),
            state.get("geography")
        )
    else:  # industry_profile
        cache_key_parts = (
            report_type,
            state.get("industry_name"),
            state.get("geography")
        )

    query_cache.set(cache_data, *cache_key_parts)

    return {
        "current_step": "Report complete!",
        "progress_percent": 100,
        "steps": {**state.get("steps", {}), "format": StepStatus.COMPLETED}
    }
