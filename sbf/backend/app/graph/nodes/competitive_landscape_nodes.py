"""
Competitive Landscape workflow nodes with REAL scraping.
"""

import structlog
from typing import Dict, Any

from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates
from .common import StepStatus

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_competitive_landscape(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research using REAL Scrapfly."""
    try:
        from ...services.scraping.base import base_scraping_service
        from ...services.cleaner import html_cleaner

        brand_url = state.get("brand_url", "")
        result = await base_scraping_service.scrape_url(brand_url, country=state.get("geography", "US"))

        content = ""
        if result.success:
            # clean_and_chunk returns a single formatted string, not a list
            content = html_cleaner.clean_and_chunk(result.content, source_id=1, max_chunks=3)

        return {
            **state,
            "market_analysis_data": [{"content": content}],
            "current_step": "Research complete...",
            "progress_percent": 60,
            "steps": {**state.get("steps", {}), "research": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        logger.error("competitive_research_failed", error=str(e), traceback=traceback.format_exc())
        return {
            **state,
            "market_analysis_data": [],
            "errors": state.get("errors", []) + [str(e)],
            "steps": {**state.get("steps", {}), "research": StepStatus.FAILED}
        }


async def node_analyze_competitive_landscape(state: Dict[str, Any]) -> Dict[str, Any]:
    """GPT-5.1 competitive analysis."""
    try:
        competitor_data = state.get("competitor_data") or []
        comp_text = "\n\n".join([
            f"**{c.get('name')}**: {(c.get('content') or '')[:400]}"
            for c in competitor_data if isinstance(c, dict)
        ]) or "Limited data."

        prompt = PromptTemplates.competitive_landscape(
            brand_name=state.get("brand_name"),
            industry_name=state.get("industry_name", "General Market"),
            competitor_data=comp_text,
            market_analysis="See competitor data above."
        )

        response, meta = llm_client.generate(
            key_name=f"comp_landscape_{state.get('brand_name')}",
            prompt=prompt,
            force_json=False
        )

        return {
            **state,
            "final_report": response,
            "current_step": "Competitive Landscape complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        logger.error("competitive_analysis_failed", error=str(e), traceback=traceback.format_exc())
        return {
            **state,
            "final_report": f"# Error\n\nFailed: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
