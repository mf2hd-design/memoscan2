"""
Four C's workflow nodes.
Company/Category/Consumer/Culture analysis.
"""

from typing import Dict, Any
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_company_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research the company (first C)."""
    from ...services.scraping.strategies import BrandScrapingStrategy

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")

    try:
        strategy = BrandScrapingStrategy()
        company_data = await strategy.scrape(brand_url, brand_name)

        logger.info(
            "company_researched",
            brand=brand_name,
            content_length=len(company_data.get("content", ""))
        )

        return {
            **state,
            "company_data": company_data,
            "current_step": "Researched Company...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "company": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("company_research_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "company_data": {},
            "warnings": state.get("warnings", []) + [f"Company research failed: {str(e)}"],
            "current_step": "Company research failed, continuing...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "company": StepStatus.FAILED.value}
        }


async def node_category_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research the category/industry (second C)."""
    from ...services.scraping.strategies import IndustryScrapingStrategy
    from ...core.llm_client import LLMClient

    brand_name = state.get("brand_name", "")
    geography = state.get("geography", "US")

    # Infer category from brand
    try:
        llm = LLMClient()
        prompt = f"What product category or industry is {brand_name} in? Reply with just the category name (e.g., 'Automotive', 'Consumer Electronics', 'Fast Food')."
        response, _ = llm.generate(
            key_name=f"infer_category_{brand_name}",
            prompt=prompt
        )
        category = response.strip().strip('"')

        # Get category data
        strategy = IndustryScrapingStrategy()
        category_data = {
            "name": category,
            "reports": await strategy.get_market_reports(category, geography),
            "trends": await strategy.get_trends(category, geography)
        }

        logger.info(
            "category_researched",
            brand=brand_name,
            category=category
        )

        return {
            **state,
            "category_data": category_data,
            "current_step": f"Researched {category} category...",
            "progress_percent": 40,
            "steps": {**state.get("steps", {}), "category": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("category_research_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "category_data": {},
            "warnings": state.get("warnings", []) + [f"Category research failed: {str(e)}"],
            "current_step": "Category research failed, continuing...",
            "progress_percent": 40,
            "steps": {**state.get("steps", {}), "category": StepStatus.FAILED.value}
        }


async def node_consumer_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research the consumer/audience (third C)."""
    from ...core.llm_client import LLMClient

    brand_name = state.get("brand_name", "")
    geography = state.get("geography", "US")

    try:
        llm = LLMClient()
        prompt = f"""Analyze the target consumer for {brand_name} in the {geography} market.

Provide a JSON object with these fields:
{{
    "primary_audience": "description of primary target",
    "demographics": "age, income, location details",
    "psychographics": "values, lifestyle, attitudes",
    "purchase_drivers": ["driver1", "driver2", "driver3"],
    "pain_points": ["pain1", "pain2", "pain3"]
}}"""

        response, _ = llm.generate(
            key_name=f"consumer_research_{brand_name}",
            prompt=prompt,
            force_json=True
        )

        import json
        consumer_data = json.loads(response.strip())

        logger.info(
            "consumer_researched",
            brand=brand_name
        )

        return {
            **state,
            "consumer_data": consumer_data,
            "current_step": "Researched Consumer insights...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "consumer": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("consumer_research_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "consumer_data": {},
            "warnings": state.get("warnings", []) + [f"Consumer research failed: {str(e)}"],
            "current_step": "Consumer research failed, continuing...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "consumer": StepStatus.FAILED.value}
        }


async def node_culture_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research cultural context (fourth C)."""
    from ...core.llm_client import LLMClient
    from ...services.scraping.base import ScrapflyClient

    brand_name = state.get("brand_name", "")
    geography = state.get("geography", "US")

    try:
        # Get cultural news and trends
        client = ScrapflyClient()
        cultural_news = await client.search_news(f"{brand_name} culture trends", limit=5)

        # Use GPT to analyze cultural context
        llm = LLMClient()
        prompt = f"""Analyze the cultural context relevant to {brand_name} in the {geography} market.

Consider:
- Macro cultural trends affecting the brand
- Social movements and values shifts
- Pop culture connections
- Regional/local cultural factors

Provide a JSON object:
{{
    "macro_trends": ["trend1", "trend2", "trend3"],
    "social_values": ["value1", "value2"],
    "pop_culture": "relevant pop culture connections",
    "regional_factors": "local cultural considerations"
}}"""

        response, _ = llm.generate(
            key_name=f"culture_research_{brand_name}",
            prompt=prompt,
            force_json=True
        )

        import json
        culture_analysis = json.loads(response.strip())
        culture_data = {
            "analysis": culture_analysis,
            "news": cultural_news
        }

        logger.info(
            "culture_researched",
            brand=brand_name
        )

        return {
            **state,
            "culture_data": culture_data,
            "current_step": "Researched Cultural context...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "culture": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("culture_research_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "culture_data": {},
            "warnings": state.get("warnings", []) + [f"Culture research failed: {str(e)}"],
            "current_step": "Culture research failed, continuing...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "culture": StepStatus.FAILED.value}
        }


async def node_analyze_four_cs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive Four C's analysis."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import FOUR_CS_PROMPT

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")
    geography = state.get("geography", "US")

    # Compile context from all 4 C's
    context_parts = []

    # Company
    company_data = state.get("company_data", {})
    if company_data and isinstance(company_data, dict):
        content = company_data.get("content", "")[:3000] if company_data.get("content") else str(company_data)[:3000]
        context_parts.append(f"## Company\n{content}")

    # Category
    category_data = state.get("category_data", {})
    if category_data and isinstance(category_data, dict):
        cat_name = category_data.get("name", "Unknown")
        trends = category_data.get("trends", [])[:3]
        trends_text = "\n".join([f"- {t.get('name', t) if isinstance(t, dict) else t}" for t in trends])
        context_parts.append(f"## Category: {cat_name}\n{trends_text}")

    # Consumer
    consumer_data = state.get("consumer_data", {})
    if consumer_data and isinstance(consumer_data, dict):
        import json
        context_parts.append(f"## Consumer\n{json.dumps(consumer_data, indent=2)}")

    # Culture
    culture_data = state.get("culture_data", {})
    if culture_data and isinstance(culture_data, dict):
        analysis = culture_data.get("analysis", {})
        import json
        context_parts.append(f"## Culture\n{json.dumps(analysis, indent=2)}")

    combined_context = "\n\n".join(context_parts)

    prompt = FOUR_CS_PROMPT.format(
        brand_name=brand_name,
        brand_url=brand_url,
        geography=geography,
        context=combined_context
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"four_cs_{brand_name}",
            prompt=prompt
        )

        logger.info(
            "four_cs_generated",
            brand=brand_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "combined_context": combined_context,
            "final_report": report,
            "current_step": "Four C's analysis complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "four_cs_generation_failed",
            brand=brand_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "combined_context": combined_context,
            "final_report": f"# Four C's Analysis: {brand_name}\n\nAnalysis generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Analysis failed: {str(e)}"],
            "current_step": "Analysis failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }
