"""
Audience Profile workflow nodes - NO WEB SCRAPING (audience analysis from GPT-5.1 knowledge).
"""

import structlog
from typing import Dict, Any

from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates
from .common import StepStatus

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_audience(state: Dict[str, Any]) -> Dict[str, Any]:
    """No scraping needed - audience analysis uses GPT-5.1 knowledge."""
    logger.info("node_research_audience", audience=state.get("audience_name"))

    return {
        **state,
        "demographic_data": [],
        "psychographic_data": [],
        "media_consumption_data": [],
        "brand_preference_data": [],
        "current_step": "Research skipped (using GPT-5.1 knowledge)...",
        "progress_percent": 70,
        "steps": {**state.get("steps", {}), "research": StepStatus.COMPLETED}
    }


async def node_analyze_audience(state: Dict[str, Any]) -> Dict[str, Any]:
    """GPT-5.1 audience profile analysis."""
    try:
        prompt = PromptTemplates.audience_profile(
            audience_name=state.get("audience_name"),
            geography=state.get("geography"),
            demographic_data="GPT-5.1 will use built-in knowledge.",
            psychographic_data="",
            media_consumption="",
            brand_preferences=""
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
