"""
Competitive Landscape workflow nodes.
Market positioning and competitive analysis.
"""

from typing import Dict, Any, List
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_identify_competitors_landscape(state: Dict[str, Any]) -> Dict[str, Any]:
    """Identify competitors for landscape analysis."""
    from ...core.llm_client import LLMClient

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")
    geography = state.get("geography", "US")

    try:
        llm = LLMClient()
        prompt = f"""Identify the top 8 competitors for {brand_name} ({brand_url}) in the {geography} market for a competitive landscape analysis.

Include both direct and indirect competitors.

Return ONLY a JSON array of competitor names:
["Competitor 1", "Competitor 2", "Competitor 3", "Competitor 4", "Competitor 5", "Competitor 6", "Competitor 7", "Competitor 8"]"""

        response, _ = llm.generate(
            key_name=f"identify_competitors_landscape_{brand_name}",
            prompt=prompt,
            force_json=True
        )

        import json
        competitors = json.loads(response.strip())

        logger.info(
            "competitors_identified_landscape",
            brand=brand_name,
            count=len(competitors)
        )

        return {
            **state,
            "competitor_urls": competitors,
            "current_step": f"Identified {len(competitors)} competitors...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "identify_competitors": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("competitor_identification_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "competitor_urls": [],
            "warnings": state.get("warnings", []) + [f"Could not identify competitors: {str(e)}"],
            "current_step": "Competitor identification failed, continuing...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "identify_competitors": StepStatus.FAILED.value}
        }


async def node_scrape_competitors_landscape(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scrape competitor data for positioning analysis."""
    from ...services.scraping.strategies import BrandScrapingStrategy

    competitors = state.get("competitor_urls", [])
    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")

    competitor_data: List[Dict] = []

    # First scrape the main brand
    strategy = BrandScrapingStrategy()
    try:
        brand_data = await strategy.scrape(brand_url, brand_name)
        competitor_data.append({
            "name": brand_name,
            "content": brand_data.get("content", "")[:2000],
            "is_target": True
        })
    except Exception as e:
        logger.warning("target_brand_scrape_failed", brand=brand_name, error=str(e))
        competitor_data.append({
            "name": brand_name,
            "content": "",
            "is_target": True,
            "error": str(e)
        })

    # Scrape competitors
    for competitor in competitors[:8]:
        try:
            data = await strategy.scrape_by_name(competitor)
            competitor_data.append({
                "name": competitor,
                "content": data.get("content", "")[:2000],
                "url": data.get("url", ""),
                "is_target": False
            })
            logger.info("competitor_scraped_landscape", name=competitor)
        except Exception as e:
            logger.warning("competitor_scrape_failed", name=competitor, error=str(e))
            competitor_data.append({
                "name": competitor,
                "content": "",
                "is_target": False,
                "error": str(e)
            })

    return {
        **state,
        "competitor_data": competitor_data,
        "current_step": f"Analyzed {len(competitor_data)} brands...",
        "progress_percent": 50,
        "steps": {**state.get("steps", {}), "scrape_competitors": StepStatus.COMPLETED.value}
    }


async def node_market_positioning(state: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze market positioning for all brands."""
    from ...core.llm_client import LLMClient

    brand_name = state.get("brand_name", "")
    competitor_data = state.get("competitor_data", [])
    geography = state.get("geography", "US")

    try:
        # Build brand summaries
        brand_summaries = []
        for brand in competitor_data:
            if isinstance(brand, dict):
                name = brand.get("name", "Unknown")
                content = brand.get("content", "")[:500]
                brand_summaries.append(f"- {name}: {content}")

        llm = LLMClient()
        prompt = f"""Analyze the competitive positioning of these brands in the {geography} market:

{chr(10).join(brand_summaries)}

Create a positioning map with two axes. Return a JSON object:
{{
    "x_axis": {{"label": "axis name", "low": "low end label", "high": "high end label"}},
    "y_axis": {{"label": "axis name", "low": "low end label", "high": "high end label"}},
    "positions": [
        {{"name": "Brand Name", "x": 75, "y": 60, "rationale": "why positioned here"}}
    ]
}}

X and Y values should be 0-100."""

        response, _ = llm.generate(
            key_name=f"market_positioning_{brand_name}",
            prompt=prompt,
            force_json=True
        )

        import json
        market_data = json.loads(response.strip())

        # Build chart JSON
        chart_json = {
            "chart_type": "competitive_map",
            "chart_title": f"Competitive Positioning: {brand_name}",
            "x_axis": market_data.get("x_axis", {}),
            "y_axis": market_data.get("y_axis", {}),
            "brands": market_data.get("positions", [])
        }

        logger.info(
            "market_positioning_complete",
            brand=brand_name,
            positions=len(market_data.get("positions", []))
        )

        return {
            **state,
            "market_data": market_data,
            "chart_json": chart_json,
            "current_step": "Created positioning map...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "market_positioning": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("market_positioning_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "market_data": {},
            "warnings": state.get("warnings", []) + [f"Market positioning failed: {str(e)}"],
            "current_step": "Positioning analysis failed, continuing...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "market_positioning": StepStatus.FAILED.value}
        }


async def node_analyze_competitive_landscape(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive competitive landscape report."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import COMPETITIVE_LANDSCAPE_PROMPT

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")
    geography = state.get("geography", "US")

    # Compile context
    context_parts = []

    # Competitor data
    competitor_data = state.get("competitor_data", [])
    if competitor_data and isinstance(competitor_data, list):
        comp_text = []
        for comp in competitor_data:
            if isinstance(comp, dict):
                name = comp.get("name", "Unknown")
                content = comp.get("content", "")[:1000]
                is_target = comp.get("is_target", False)
                marker = " (TARGET)" if is_target else ""
                comp_text.append(f"### {name}{marker}\n{content}")
        if comp_text:
            context_parts.append("## Brand Analysis\n" + "\n\n".join(comp_text))

    # Market positioning
    market_data = state.get("market_data", {})
    if market_data and isinstance(market_data, dict):
        import json
        context_parts.append(f"## Positioning Analysis\n{json.dumps(market_data, indent=2)}")

    combined_context = "\n\n".join(context_parts)

    prompt = COMPETITIVE_LANDSCAPE_PROMPT.format(
        brand_name=brand_name,
        brand_url=brand_url,
        geography=geography,
        context=combined_context
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"competitive_landscape_{brand_name}",
            prompt=prompt
        )

        logger.info(
            "competitive_landscape_generated",
            brand=brand_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "combined_context": combined_context,
            "final_report": report,
            "current_step": "Competitive landscape complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "competitive_landscape_generation_failed",
            brand=brand_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "combined_context": combined_context,
            "final_report": f"# Competitive Landscape: {brand_name}\n\nAnalysis generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Analysis failed: {str(e)}"],
            "current_step": "Analysis failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }
