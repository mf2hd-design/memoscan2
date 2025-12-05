"""
Brand House workflow nodes.
Reuses Brand Audit research infrastructure with strategic brand positioning analysis.
"""

import structlog
from typing import Dict, Any

from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates
from .common import StepStatus

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_brand_positioning(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Research current brand positioning through website analysis.
    Uses real Scrapfly scraping (not fake imports).

    Args:
        state: Current workflow state

    Returns:
        Updated state with brand positioning data
    """
    logger.info(
        "node_research_brand_positioning",
        brand=state.get("brand_name")
    )

    try:
        from ...services.scraping.base import base_scraping_service
        from ...services.cleaner import html_cleaner

        brand_url = state.get("brand_url", "")
        geography = state.get("geography", "US")

        # Scrape brand website using real Scrapfly service
        result = await base_scraping_service.scrape_url(
            brand_url,
            country=geography
        )

        brand_content = ""
        if result.success:
            # Clean and chunk the HTML content
            chunks = html_cleaner.clean_and_chunk(
                result.content,
                source_id=1,
                max_chunks=5
            )
            brand_content = "\n\n".join([chunk.text for chunk in chunks])
        else:
            logger.warning("brand_scrape_failed", url=brand_url, error=result.error)

        logger.info("brand_positioning_research_complete", content_length=len(brand_content))

        return {
            **state,  # Preserve all existing state
            "brand_site_content": brand_content,
            "current_step": "Brand positioning researched...",
            "progress_percent": 30,
            "steps": {**state.get("steps", {}), "research": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error("brand_positioning_research_failed", error=str(e), traceback=error_traceback)
        return {
            **state,  # Preserve all existing state
            "brand_site_content": "",
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Research failed, continuing with limited data...",
            "progress_percent": 30,
            "steps": {**state.get("steps", {}), "research": StepStatus.FAILED}
        }


async def node_analyze_brand_house(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    GPT-5.1 analysis to generate Brand House strategy.

    Args:
        state: Current workflow state

    Returns:
        Updated state with Brand House report
    """
    logger.info(
        "node_analyze_brand_house",
        brand=state.get("brand_name")
    )

    try:
        # Format context strings with defensive None handling
        brand_site_content = state.get("brand_site_content") or "No brand website content available."

        # Get competitor data from state (populated by Brand Audit nodes)
        competitor_data_list = state.get("competitor_data") or []
        if not isinstance(competitor_data_list, list):
            competitor_data_list = []
        competitor_text = "\n\n".join([
            f"**{comp.get('name', 'Competitor')}**\n{(comp.get('content') or '')[:500]}"
            for comp in competitor_data_list if isinstance(comp, dict)
        ]) or "No competitor data available."

        # Get news mentions from state
        news_data = state.get("news_data") or []
        if not isinstance(news_data, list):
            news_data = []
        news_text = "\n\n".join([
            f"- {(item.get('content') or item.get('title') or '')[:300]}"
            for item in news_data if isinstance(item, dict)
        ]) or "No recent news available."

        # Build prompt
        prompt = PromptTemplates.brand_house(
            brand_name=state.get("brand_name"),
            brand_site_content=brand_site_content,
            current_positioning=f"Brand website analysis shows: {brand_site_content[:500]}...",
            competitor_data=competitor_text,
            news_mentions=news_text
        )

        # Call GPT-5.1-2025-11-13
        response, meta = llm_client.generate(
            key_name=f"brand_house_{state.get('brand_name')}_{state.get('geography')}",
            prompt=prompt,
            force_json=False  # Markdown output
        )

        logger.info(
            "brand_house_analysis_complete",
            brand=state.get("brand_name"),
            model=meta.get("model"),
            chars=len(response or "")
        )

        return {
            **state,  # Preserve all existing state
            "final_report": response,
            "current_step": "Brand House complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error("brand_house_analysis_failed", error=str(e), traceback=error_traceback)
        return {
            **state,
            "final_report": f"# Error\n\nFailed to generate Brand House report: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Analysis failed...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
