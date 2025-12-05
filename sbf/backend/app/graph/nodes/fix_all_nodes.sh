#!/bin/bash

# Fix Four C's nodes
cat > four_cs_nodes.py << 'FOURCS'
"""
Four C's Analysis workflow nodes.
Uses real Scrapfly scraping - Company, Category, Consumer, Culture analysis.
"""

import structlog
from typing import Dict, Any

from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates
from .common import StepStatus

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_four_cs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research using REAL Scrapfly service."""
    logger.info("node_research_four_cs", brand=state.get("brand_name"))

    try:
        from ...services.scraping.base import base_scraping_service
        from ...services.cleaner import html_cleaner

        brand_url = state.get("brand_url", "")
        geography = state.get("geography", "US")

        # Scrape brand website
        result = await base_scraping_service.scrape_url(brand_url, country=geography)

        brand_content = ""
        if result.success:
            chunks = html_cleaner.clean_and_chunk(result.content, source_id=1, max_chunks=5)
            brand_content = "\n\n".join([chunk.text for chunk in chunks])

        return {
            **state,
            "brand_site_content": brand_content,
            "current_step": "Research complete...",
            "progress_percent": 60,
            "steps": {**state.get("steps", {}), "research": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        logger.error("four_cs_research_failed", error=str(e), traceback=traceback.format_exc())
        return {
            **state,
            "brand_site_content": "",
            "errors": state.get("errors", []) + [str(e)],
            "steps": {**state.get("steps", {}), "research": StepStatus.FAILED}
        }


async def node_analyze_four_cs(state: Dict[str, Any]) -> Dict[str, Any]:
    """GPT-5.1 Four C's analysis."""
    try:
        brand_content = state.get("brand_site_content") or "Limited data available."
        competitor_data = state.get("competitor_data") or []
        
        comp_text = "\n\n".join([
            f"**{c.get('name', 'Competitor')}**: {(c.get('content') or '')[:400]}"
            for c in competitor_data if isinstance(c, dict)
        ]) or "No competitor data."

        prompt = PromptTemplates.four_cs_analysis(
            brand_name=state.get("brand_name"),
            brand_site_content=brand_content,
            competitor_data=comp_text,
            news_mentions="",
            trend_data=""
        )

        response, meta = llm_client.generate(
            key_name=f"four_cs_{state.get('brand_name')}",
            prompt=prompt,
            force_json=False
        )

        return {
            **state,
            "final_report": response,
            "current_step": "Four C's analysis complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        logger.error("four_cs_analysis_failed", error=str(e), traceback=traceback.format_exc())
        return {
            **state,
            "final_report": f"# Error\n\nFailed: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
FOURCS

# Fix Competitive Landscape nodes
cat > competitive_landscape_nodes.py << 'COMPLAND'
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
            chunks = html_cleaner.clean_and_chunk(result.content, source_id=1, max_chunks=3)
            content = "\n\n".join([chunk.text for chunk in chunks])

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
            brand_site_content=state.get("brand_site_content", ""),
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
COMPLAND

# Fix Audience Profile nodes
cat > audience_profile_nodes.py << 'AUDIENCE'
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
            media_consumption_data="",
            brand_preference_data=""
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
AUDIENCE

echo "All 3 node files fixed!"
