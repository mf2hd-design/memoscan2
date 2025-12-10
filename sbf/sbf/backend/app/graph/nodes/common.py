"""
Common workflow nodes shared across all report types.
"""

from typing import Dict, Any
from uuid import uuid4
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_initialize(state: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize workflow with ID and timestamps."""
    workflow_id = str(uuid4())

    logger.info(
        "workflow_initialized",
        workflow_id=workflow_id,
        report_type=state.get("report_type")
    )

    return {
        **state,
        "workflow_id": workflow_id,
        "current_step": "Initializing workflow...",
        "progress_percent": 5,
        "steps": {"initialize": StepStatus.COMPLETED.value},
        "errors": [],
        "warnings": []
    }


async def node_cache_check(state: Dict[str, Any]) -> Dict[str, Any]:
    """Check if we have a cached result for this query."""
    from ...services.cache import query_cache

    # Build cache key from relevant state fields
    report_type = state.get("report_type", "")

    if report_type == "brand_audit":
        cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
    elif report_type == "meeting_brief":
        cache_key = f"{report_type}:{state.get('person_name')}:{state.get('company_name')}:{state.get('geography')}"
    elif report_type == "industry_profile":
        cache_key = f"{report_type}:{state.get('industry_name')}:{state.get('geography')}"
    elif report_type == "brand_house":
        cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
    elif report_type == "four_cs":
        cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
    elif report_type == "competitive_landscape":
        cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
    elif report_type == "audience_profile":
        cache_key = f"{report_type}:{state.get('audience_name')}:{state.get('geography')}"
    else:
        cache_key = f"unknown:{uuid4()}"

    cached = query_cache.get(cache_key)

    if cached:
        logger.info("cache_hit", cache_key=cache_key)
        return {
            **state,
            "cache_hit": True,
            "final_report": cached.get("report", ""),
            "chart_json": cached.get("chart"),
            "current_step": "Retrieved from cache",
            "progress_percent": 95,
            "steps": {**state.get("steps", {}), "cache_check": StepStatus.COMPLETED.value}
        }

    logger.info("cache_miss", cache_key=cache_key)
    return {
        **state,
        "cache_hit": False,
        "current_step": "Starting research...",
        "progress_percent": 10,
        "steps": {**state.get("steps", {}), "cache_check": StepStatus.COMPLETED.value}
    }


async def node_format_report(state: Dict[str, Any]) -> Dict[str, Any]:
    """Final formatting and cache storage."""
    from ...services.cache import query_cache

    final_report = state.get("final_report", "")
    chart_json = state.get("chart_json")
    report_type = state.get("report_type", "")

    # Only cache if we have a report and it wasn't a cache hit
    if final_report and not state.get("cache_hit"):
        # Build cache key (same as cache_check)
        if report_type == "brand_audit":
            cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
        elif report_type == "meeting_brief":
            cache_key = f"{report_type}:{state.get('person_name')}:{state.get('company_name')}:{state.get('geography')}"
        elif report_type == "industry_profile":
            cache_key = f"{report_type}:{state.get('industry_name')}:{state.get('geography')}"
        elif report_type == "brand_house":
            cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
        elif report_type == "four_cs":
            cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
        elif report_type == "competitive_landscape":
            cache_key = f"{report_type}:{state.get('brand_name')}:{state.get('brand_url')}:{state.get('geography')}"
        elif report_type == "audience_profile":
            cache_key = f"{report_type}:{state.get('audience_name')}:{state.get('geography')}"
        else:
            cache_key = None

        if cache_key:
            query_cache.set(cache_key, {
                "report": final_report,
                "chart": chart_json
            })
            logger.info("report_cached", cache_key=cache_key)

    logger.info(
        "report_formatted",
        workflow_id=state.get("workflow_id"),
        report_length=len(final_report)
    )

    return {
        **state,
        "current_step": "Report complete",
        "progress_percent": 100,
        "steps": {**state.get("steps", {}), "format_report": StepStatus.COMPLETED.value}
    }
