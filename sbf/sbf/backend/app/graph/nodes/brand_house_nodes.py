"""
Brand House workflow nodes.
Strategic brand positioning analysis.
"""

from typing import Dict, Any
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_scrape_brand_house(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scrape brand website for positioning analysis."""
    from ...services.scraping.strategies import BrandScrapingStrategy

    brand_url = state.get("brand_url", "")
    brand_name = state.get("brand_name", "")

    try:
        strategy = BrandScrapingStrategy()
        brand_content = await strategy.scrape(brand_url, brand_name)

        logger.info(
            "brand_scraped_for_house",
            url=brand_url,
            content_length=len(brand_content.get("content", ""))
        )

        return {
            **state,
            "brand_site_content": brand_content.get("content", ""),
            "current_step": "Analyzed brand website...",
            "progress_percent": 30,
            "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("brand_scrape_failed", url=brand_url, error=str(e))
        return {
            **state,
            "brand_site_content": "",
            "warnings": state.get("warnings", []) + [f"Could not scrape brand website: {str(e)}"],
            "current_step": "Brand website scrape failed, continuing...",
            "progress_percent": 30,
            "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.FAILED.value}
        }


async def node_competitor_analysis(state: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze competitor positioning for comparison."""
    from ...core.llm_client import LLMClient
    from ...services.scraping.strategies import BrandScrapingStrategy

    brand_name = state.get("brand_name", "")
    geography = state.get("geography", "US")

    try:
        # Use GPT to identify key competitors
        llm = LLMClient()
        prompt = f"""Identify the top 3 direct competitors for {brand_name} in the {geography} market that would be relevant for brand positioning analysis.

Return ONLY a JSON array of competitor names:
["Competitor 1", "Competitor 2", "Competitor 3"]"""

        response, _ = llm.generate(
            key_name=f"identify_competitors_house_{brand_name}",
            prompt=prompt,
            force_json=True
        )

        import json
        competitors = json.loads(response.strip())

        # Scrape competitor sites
        strategy = BrandScrapingStrategy()
        competitor_data = []

        for competitor in competitors[:3]:
            try:
                data = await strategy.scrape_by_name(competitor)
                competitor_data.append({
                    "name": competitor,
                    "content": data.get("content", "")[:3000]
                })
            except Exception as e:
                logger.warning("competitor_scrape_failed", name=competitor, error=str(e))

        logger.info(
            "competitor_analysis_complete",
            brand=brand_name,
            competitors_analyzed=len(competitor_data)
        )

        return {
            **state,
            "competitor_data": competitor_data,
            "current_step": f"Analyzed {len(competitor_data)} competitors...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "competitor_analysis": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("competitor_analysis_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "competitor_data": [],
            "warnings": state.get("warnings", []) + [f"Could not analyze competitors: {str(e)}"],
            "current_step": "Competitor analysis failed, continuing...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "competitor_analysis": StepStatus.FAILED.value}
        }


async def node_analyze_brand_house(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Brand House strategic positioning analysis."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import BRAND_HOUSE_PROMPT

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")
    geography = state.get("geography", "US")

    # Compile context
    context_parts = []

    # Brand content
    brand_content = state.get("brand_site_content", "")
    if brand_content:
        context_parts.append(f"## Brand Website Content\n{brand_content[:6000]}")

    # Competitor data
    competitor_data = state.get("competitor_data", [])
    if competitor_data and isinstance(competitor_data, list):
        comp_text = []
        for comp in competitor_data[:3]:
            if isinstance(comp, dict):
                name = comp.get("name", "")
                content = comp.get("content", "")[:1500]
                comp_text.append(f"### {name}\n{content}")
        if comp_text:
            context_parts.append("## Competitor Positioning\n" + "\n\n".join(comp_text))

    combined_context = "\n\n".join(context_parts)

    prompt = BRAND_HOUSE_PROMPT.format(
        brand_name=brand_name,
        brand_url=brand_url,
        geography=geography,
        context=combined_context
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"brand_house_{brand_name}",
            prompt=prompt
        )

        logger.info(
            "brand_house_generated",
            brand=brand_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "combined_context": combined_context,
            "final_report": report,
            "current_step": "Brand House analysis complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "brand_house_generation_failed",
            brand=brand_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "combined_context": combined_context,
            "final_report": f"# Brand House: {brand_name}\n\nAnalysis generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Analysis failed: {str(e)}"],
            "current_step": "Analysis failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }
