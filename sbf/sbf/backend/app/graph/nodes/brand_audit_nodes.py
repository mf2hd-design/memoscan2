"""
Brand Audit workflow nodes.
Handles PDF ingestion, brand scraping, social sentiment, competitors, and analysis.
"""

from typing import Dict, Any, List
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_ingest_pdf(state: Dict[str, Any]) -> Dict[str, Any]:
    """Process uploaded PDF documents for RAG context."""
    pdf_context = state.get("pdf_context", "")

    # PDF context is already processed in endpoint if files were uploaded
    if pdf_context:
        logger.info("pdf_context_available", context_length=len(pdf_context))
    else:
        logger.info("no_pdf_context")

    return {
        **state,
        "current_step": "Processing brand documents...",
        "progress_percent": 15,
        "steps": {**state.get("steps", {}), "ingest_pdf": StepStatus.COMPLETED.value}
    }


async def node_scrape_brand(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scrape the brand's website for content analysis."""
    from ...services.scraping.strategies import BrandScrapingStrategy

    brand_url = state.get("brand_url", "")
    brand_name = state.get("brand_name", "")

    try:
        strategy = BrandScrapingStrategy()
        brand_content = await strategy.scrape(brand_url, brand_name)

        logger.info(
            "brand_scraped",
            url=brand_url,
            content_length=len(brand_content.get("content", ""))
        )

        return {
            **state,
            "brand_site_content": brand_content.get("content", ""),
            "current_step": "Analyzing brand website...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("brand_scrape_failed", url=brand_url, error=str(e))
        return {
            **state,
            "brand_site_content": "",
            "warnings": state.get("warnings", []) + [f"Could not scrape brand website: {str(e)}"],
            "current_step": "Brand website scrape failed, continuing...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.FAILED.value}
        }


async def node_social_sentiment(state: Dict[str, Any]) -> Dict[str, Any]:
    """Collect social media sentiment data."""
    from ...services.scraping.strategies import SocialSentimentCollector

    brand_name = state.get("brand_name", "")

    try:
        collector = SocialSentimentCollector()
        sentiment_data = await collector.collect(brand_name)

        logger.info(
            "social_sentiment_collected",
            brand=brand_name,
            platforms=list(sentiment_data.keys()) if sentiment_data else []
        )

        return {
            **state,
            "social_sentiment": sentiment_data or {},
            "current_step": "Gathering social media insights...",
            "progress_percent": 35,
            "steps": {**state.get("steps", {}), "social_sentiment": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("social_sentiment_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "social_sentiment": {},
            "warnings": state.get("warnings", []) + [f"Could not collect social sentiment: {str(e)}"],
            "current_step": "Social sentiment collection failed, continuing...",
            "progress_percent": 35,
            "steps": {**state.get("steps", {}), "social_sentiment": StepStatus.FAILED.value}
        }


async def node_identify_competitors(state: Dict[str, Any]) -> Dict[str, Any]:
    """Identify competitors using GPT-5.1."""
    from ...core.llm_client import LLMClient

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")
    geography = state.get("geography", "US")
    provided_competitors = state.get("competitors", [])

    # If competitors already provided, use those
    if provided_competitors:
        logger.info("using_provided_competitors", competitors=provided_competitors)
        return {
            **state,
            "identified_competitors": provided_competitors,
            "current_step": "Using provided competitors...",
            "progress_percent": 45,
            "steps": {**state.get("steps", {}), "identify_competitors": StepStatus.COMPLETED.value}
        }

    try:
        llm = LLMClient()
        prompt = f"""Identify the top 5 direct competitors for {brand_name} ({brand_url}) in the {geography} market.

Return ONLY a JSON array of competitor names, no explanation:
["Competitor 1", "Competitor 2", "Competitor 3", "Competitor 4", "Competitor 5"]"""

        response, meta = llm.generate(
            key_name=f"identify_competitors_{brand_name}",
            prompt=prompt,
            force_json=True
        )

        # Parse response with validation
        import json
        try:
            competitors = json.loads(response.strip())
            # Validate it's a list of strings
            if not isinstance(competitors, list):
                competitors = []
            competitors = [str(c).strip() for c in competitors if c][:5]
        except json.JSONDecodeError:
            logger.warning("competitor_json_parse_failed", response=response[:100])
            competitors = []

        logger.info(
            "competitors_identified",
            brand=brand_name,
            competitors=competitors
        )

        return {
            **state,
            "identified_competitors": competitors,
            "current_step": "Identified key competitors...",
            "progress_percent": 45,
            "steps": {**state.get("steps", {}), "identify_competitors": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("competitor_identification_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "identified_competitors": [],
            "warnings": state.get("warnings", []) + [f"Could not identify competitors: {str(e)}"],
            "current_step": "Competitor identification failed, continuing...",
            "progress_percent": 45,
            "steps": {**state.get("steps", {}), "identify_competitors": StepStatus.FAILED.value}
        }


async def node_scrape_competitors(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scrape competitor websites for comparison data (parallel execution)."""
    from ...services.scraping.strategies import BrandScrapingStrategy
    import asyncio

    competitors = state.get("identified_competitors", [])
    competitor_data: List[Dict] = []

    if not competitors:
        logger.info("no_competitors_to_scrape")
        return {
            **state,
            "competitor_data": [],
            "current_step": "No competitors to analyze...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "scrape_competitors": StepStatus.COMPLETED.value}
        }

    strategy = BrandScrapingStrategy()

    async def scrape_competitor(competitor: str) -> Dict:
        """Scrape a single competitor."""
        try:
            data = await strategy.scrape_by_name(competitor)
            logger.info("competitor_scraped", name=competitor)
            return {
                "name": competitor,
                "content": data.get("content", ""),
                "url": data.get("url", "")
            }
        except Exception as e:
            logger.warning("competitor_scrape_failed", name=competitor, error=str(e))
            return {
                "name": competitor,
                "content": "",
                "url": "",
                "error": str(e)
            }

    # Scrape competitors in parallel (limit to 5)
    tasks = [scrape_competitor(comp) for comp in competitors[:5]]
    competitor_data = await asyncio.gather(*tasks)

    return {
        **state,
        "competitor_data": list(competitor_data),
        "current_step": f"Analyzed {len(competitor_data)} competitors...",
        "progress_percent": 55,
        "steps": {**state.get("steps", {}), "scrape_competitors": StepStatus.COMPLETED.value}
    }


async def node_news_mentions(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gather recent news mentions for the brand."""
    from ...services.scraping.base import ScrapflyClient

    brand_name = state.get("brand_name", "")

    try:
        client = ScrapflyClient()
        news_data = await client.search_news(brand_name, limit=10)

        logger.info(
            "news_collected",
            brand=brand_name,
            count=len(news_data)
        )

        return {
            **state,
            "news_mentions": news_data,
            "current_step": "Gathered recent news coverage...",
            "progress_percent": 65,
            "steps": {**state.get("steps", {}), "news_mentions": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("news_collection_failed", brand=brand_name, error=str(e))
        return {
            **state,
            "news_mentions": [],
            "warnings": state.get("warnings", []) + [f"Could not collect news: {str(e)}"],
            "current_step": "News collection failed, continuing...",
            "progress_percent": 65,
            "steps": {**state.get("steps", {}), "news_mentions": StepStatus.FAILED.value}
        }


async def node_analyze_brand_audit(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive brand audit analysis using GPT-5.1."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import BRAND_AUDIT_PROMPT

    brand_name = state.get("brand_name", "")
    brand_url = state.get("brand_url", "")
    geography = state.get("geography", "US")

    # Compile context
    context_parts = []

    # Brand website content
    brand_content = state.get("brand_site_content", "")
    if brand_content:
        context_parts.append(f"## Brand Website Content\n{brand_content[:8000]}")

    # PDF context
    pdf_context = state.get("pdf_context", "")
    if pdf_context:
        context_parts.append(f"## Uploaded Documents\n{pdf_context[:5000]}")

    # Social sentiment
    social = state.get("social_sentiment")
    if social and isinstance(social, dict):
        social_summary = []
        for platform, posts in social.items():
            if isinstance(posts, list) and posts:
                social_summary.append(f"- {platform}: {len(posts)} mentions")
        if social_summary:
            context_parts.append("## Social Media Presence\n" + "\n".join(social_summary))

    # Competitors
    competitor_data = state.get("competitor_data")
    if competitor_data and isinstance(competitor_data, list):
        comp_summary = []
        for comp in competitor_data:
            if isinstance(comp, dict):
                name = comp.get("name", "Unknown")
                content = comp.get("content", "")[:1000] if comp.get("content") else "No data"
                comp_summary.append(f"### {name}\n{content}")
        if comp_summary:
            context_parts.append("## Competitor Analysis\n" + "\n\n".join(comp_summary[:5]))

    # News
    news = state.get("news_mentions")
    if news and isinstance(news, list):
        news_summary = []
        for article in news[:5]:
            if isinstance(article, dict):
                title = article.get("title", "")
                snippet = article.get("snippet", "")[:200]
                news_summary.append(f"- {title}: {snippet}")
        if news_summary:
            context_parts.append("## Recent News\n" + "\n".join(news_summary))

    combined_context = "\n\n".join(context_parts)

    # Build prompt
    prompt = BRAND_AUDIT_PROMPT.format(
        brand_name=brand_name,
        brand_url=brand_url,
        geography=geography,
        context=combined_context
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"brand_audit_{brand_name}",
            prompt=prompt
        )

        logger.info(
            "brand_audit_generated",
            brand=brand_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "combined_context": combined_context,
            "final_report": report,
            "current_step": "Analysis complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "brand_audit_generation_failed",
            brand=brand_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "combined_context": combined_context,
            "final_report": f"# Brand Audit for {brand_name}\n\nAnalysis generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Analysis failed: {str(e)}"],
            "current_step": "Analysis failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }
