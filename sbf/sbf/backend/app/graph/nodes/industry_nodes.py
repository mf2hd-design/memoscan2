"""
Industry Profile workflow nodes.
Handles market reports, brands, trends, news, and analysis.
"""

from typing import Dict, Any
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_market_reports(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gather market research reports for the industry."""
    from ...services.scraping.strategies import IndustryScrapingStrategy

    industry_name = state.get("industry_name", "")
    geography = state.get("geography", "US")

    try:
        strategy = IndustryScrapingStrategy()
        reports = await strategy.get_market_reports(industry_name, geography)

        logger.info(
            "market_reports_gathered",
            industry=industry_name,
            count=len(reports)
        )

        return {
            **state,
            "market_reports": reports,
            "current_step": f"Found {len(reports)} market reports...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "market_reports": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("market_reports_failed", industry=industry_name, error=str(e))
        return {
            **state,
            "market_reports": [],
            "warnings": state.get("warnings", []) + [f"Could not gather market reports: {str(e)}"],
            "current_step": "Market reports failed, continuing...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "market_reports": StepStatus.FAILED.value}
        }


async def node_top_brands(state: Dict[str, Any]) -> Dict[str, Any]:
    """Identify top brands in the industry."""
    from ...services.scraping.strategies import IndustryScrapingStrategy

    industry_name = state.get("industry_name", "")
    geography = state.get("geography", "US")

    try:
        strategy = IndustryScrapingStrategy()
        top_brands = await strategy.get_top_brands(industry_name, geography)
        emerging_brands = await strategy.get_emerging_brands(industry_name, geography)

        logger.info(
            "brands_identified",
            industry=industry_name,
            top_count=len(top_brands),
            emerging_count=len(emerging_brands)
        )

        return {
            **state,
            "top_brands": top_brands,
            "emerging_brands": emerging_brands,
            "current_step": f"Identified {len(top_brands)} leading brands...",
            "progress_percent": 40,
            "steps": {**state.get("steps", {}), "top_brands": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("brand_identification_failed", industry=industry_name, error=str(e))
        return {
            **state,
            "top_brands": [],
            "emerging_brands": [],
            "warnings": state.get("warnings", []) + [f"Could not identify brands: {str(e)}"],
            "current_step": "Brand identification failed, continuing...",
            "progress_percent": 40,
            "steps": {**state.get("steps", {}), "top_brands": StepStatus.FAILED.value}
        }


async def node_trends(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gather industry trends and insights."""
    from ...services.scraping.strategies import IndustryScrapingStrategy

    industry_name = state.get("industry_name", "")
    geography = state.get("geography", "US")

    try:
        strategy = IndustryScrapingStrategy()
        trends = await strategy.get_trends(industry_name, geography)

        logger.info(
            "trends_gathered",
            industry=industry_name,
            count=len(trends)
        )

        return {
            **state,
            "trend_data": trends,
            "current_step": f"Identified {len(trends)} key trends...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "trends": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("trends_failed", industry=industry_name, error=str(e))
        return {
            **state,
            "trend_data": [],
            "warnings": state.get("warnings", []) + [f"Could not gather trends: {str(e)}"],
            "current_step": "Trends gathering failed, continuing...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "trends": StepStatus.FAILED.value}
        }


async def node_news(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gather recent industry news."""
    from ...services.scraping.base import ScrapflyClient

    industry_name = state.get("industry_name", "")

    try:
        client = ScrapflyClient()
        news = await client.search_news(f"{industry_name} industry", limit=10)

        logger.info(
            "news_gathered",
            industry=industry_name,
            count=len(news)
        )

        return {
            **state,
            "news_articles": news,
            "current_step": f"Found {len(news)} recent articles...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "news": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("news_failed", industry=industry_name, error=str(e))
        return {
            **state,
            "news_articles": [],
            "warnings": state.get("warnings", []) + [f"Could not gather news: {str(e)}"],
            "current_step": "News gathering failed, continuing...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "news": StepStatus.FAILED.value}
        }


async def node_analyze_industry(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive industry analysis using GPT-5.1."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import INDUSTRY_PROFILE_PROMPT

    industry_name = state.get("industry_name", "")
    geography = state.get("geography", "US")

    # Compile context
    context_parts = []

    # Market reports
    reports = state.get("market_reports", [])
    if reports and isinstance(reports, list):
        report_text = []
        for report in reports[:5]:
            if isinstance(report, dict):
                title = report.get("title", "")
                snippet = report.get("snippet", "")[:300]
                report_text.append(f"- {title}: {snippet}")
        if report_text:
            context_parts.append("## Market Reports\n" + "\n".join(report_text))

    # Top brands
    top_brands = state.get("top_brands", [])
    if top_brands and isinstance(top_brands, list):
        brands_text = []
        for brand in top_brands[:10]:
            if isinstance(brand, dict):
                name = brand.get("name", "")
                desc = brand.get("description", "")[:200]
                brands_text.append(f"- {name}: {desc}")
            elif isinstance(brand, str):
                brands_text.append(f"- {brand}")
        if brands_text:
            context_parts.append("## Leading Brands\n" + "\n".join(brands_text))

    # Emerging brands
    emerging = state.get("emerging_brands", [])
    if emerging and isinstance(emerging, list):
        emerging_text = []
        for brand in emerging[:5]:
            if isinstance(brand, dict):
                name = brand.get("name", "")
                desc = brand.get("description", "")[:200]
                emerging_text.append(f"- {name}: {desc}")
            elif isinstance(brand, str):
                emerging_text.append(f"- {brand}")
        if emerging_text:
            context_parts.append("## Emerging Brands\n" + "\n".join(emerging_text))

    # Trends
    trends = state.get("trend_data", [])
    if trends and isinstance(trends, list):
        trends_text = []
        for trend in trends[:5]:
            if isinstance(trend, dict):
                name = trend.get("name", trend.get("title", ""))
                desc = trend.get("description", trend.get("snippet", ""))[:200]
                trends_text.append(f"- {name}: {desc}")
        if trends_text:
            context_parts.append("## Key Trends\n" + "\n".join(trends_text))

    # News
    news = state.get("news_articles", [])
    if news and isinstance(news, list):
        news_text = []
        for article in news[:5]:
            if isinstance(article, dict):
                title = article.get("title", "")
                snippet = article.get("snippet", "")[:200]
                news_text.append(f"- {title}: {snippet}")
        if news_text:
            context_parts.append("## Recent News\n" + "\n".join(news_text))

    combined_context = "\n\n".join(context_parts)

    # Build prompt
    prompt = INDUSTRY_PROFILE_PROMPT.format(
        industry_name=industry_name,
        geography=geography,
        context=combined_context
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"industry_profile_{industry_name}",
            prompt=prompt
        )

        logger.info(
            "industry_profile_generated",
            industry=industry_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "combined_context": combined_context,
            "final_report": report,
            "current_step": "Industry profile complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "industry_profile_generation_failed",
            industry=industry_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "combined_context": combined_context,
            "final_report": f"# Industry Profile: {industry_name}\n\nProfile generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Profile generation failed: {str(e)}"],
            "current_step": "Profile generation failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }
