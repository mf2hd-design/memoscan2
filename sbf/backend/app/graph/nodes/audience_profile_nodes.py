"""
Audience Profile workflow nodes - Research audience demographics and behavior.
"""

import structlog
from typing import Dict, Any

from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates
from .common import StepStatus
from ...services.scraping.strategies import AudienceScrapingStrategy

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_audience(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research audience demographics, psychographics, and behavior."""
    logger.info("node_research_audience", audience=state.get("audience_name"))

    try:
        strategy = AudienceScrapingStrategy()
        results = await strategy.execute(state)

        # Format scraped data for the prompt
        def format_data(data_list):
            if not data_list:
                return "No data found."
            formatted = ""
            for idx, item in enumerate(data_list, 1):
                formatted += f"\n[Source {idx}] {item.get('url', 'Unknown source')}\n{item.get('content', '')}\n"
            return formatted

        return {
            **state,
            "demographic_data": format_data(results.get("demographic_data", [])),
            "psychographic_data": format_data(results.get("psychographic_data", [])),
            "media_consumption_data": format_data(results.get("media_consumption", [])),
            "brand_preference_data": format_data(results.get("brand_preferences", [])),
            "current_step": "Audience research complete, analyzing...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "research": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        logger.error("audience_research_failed", error=str(e), traceback=traceback.format_exc())
        # Fall back to GPT-5.1 knowledge if scraping fails
        return {
            **state,
            "demographic_data": "Research failed, using GPT-5.1 knowledge.",
            "psychographic_data": "",
            "media_consumption_data": "",
            "brand_preference_data": "",
            "current_step": "Research failed, using GPT-5.1 knowledge...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "research": StepStatus.COMPLETED}
        }


async def node_analyze_audience(state: Dict[str, Any]) -> Dict[str, Any]:
    """GPT-5.1 audience profile analysis."""
    try:
        prompt = PromptTemplates.audience_profile(
            audience_name=state.get("audience_name"),
            geography=state.get("geography"),
            demographic_data=state.get("demographic_data", ""),
            psychographic_data=state.get("psychographic_data", ""),
            media_consumption=state.get("media_consumption_data", ""),
            brand_preferences=state.get("brand_preference_data", "")
        )

        response, meta = llm_client.generate(
            key_name=f"audience_{state.get('audience_name')}",
            prompt=prompt,
            force_json=False
        )

        return {
            **state,
            "final_report": response,
            "current_step": "Audience Profile complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        logger.error("audience_analysis_failed", error=str(e), traceback=traceback.format_exc())
        return {
            **state,
            "final_report": f"# Error\n\nFailed: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
