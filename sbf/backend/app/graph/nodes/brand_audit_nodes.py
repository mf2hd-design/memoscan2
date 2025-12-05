"""
Brand Audit specific workflow nodes.
"""

import structlog
import json
from typing import Dict, Any

from ...models.schemas import StepStatus, BrandAuditState
from ...services.scraping.strategies import BrandScrapingStrategy, SocialSentimentCollector
from ...services.rag_service import RAGService
from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_ingest_pdfs(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingest uploaded PDF documents (if any).

    Args:
        state: Current state dict

    Returns:
        Updated state with PDF context
    """
    logger.info("node_ingest_pdfs", workflow_id=state.get("workflow_id"))

    # PDFs are handled in the API endpoint before workflow starts
    # This node just updates progress

    return {
        **state,  # Preserve all existing state
        "current_step": "PDF documents processed...",
        "progress_percent": 15,
        "steps": {**state.get("steps", {}), "ingest_pdfs": StepStatus.COMPLETED}
    }


async def node_scrape_brand_website(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape the brand's website.

    Args:
        state: Current state dict

    Returns:
        Updated state with brand site content
    """
    logger.info("node_scrape_brand_website", brand=state.get("brand_name"))

    try:
        from ...services.scraping.base import base_scraping_service
        from ...services.cleaner import html_cleaner

        result = await base_scraping_service.scrape_url(
            state.get("brand_url"),
            country=state.get("geography", "US")
        )

        if result.success:
            brand_content = html_cleaner.clean_and_chunk(
                result.content,
                source_id=1,
                max_chunks=5
            )

            return {
                **state,  # Preserve all existing state
                "brand_site_content": brand_content,
                "current_step": "Brand website scraped successfully...",
                "progress_percent": 25,
                "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.COMPLETED}
            }
        else:
            return {
                **state,  # Preserve all existing state
                "brand_site_content": "",
                "warnings": state.get("warnings", []) + [f"Failed to scrape brand website: {result.error}"],
                "current_step": "Brand website scrape failed, continuing...",
                "progress_percent": 25,
                "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.FAILED}
            }

    except Exception as e:
        logger.error("brand_scrape_failed", error=str(e))
        return {
            **state,  # Preserve all existing state
            "brand_site_content": "",
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Error scraping brand website...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "scrape_brand": StepStatus.FAILED}
        }


async def node_scrape_social_sentiment(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape social media platforms for brand sentiment.

    Args:
        state: Current state dict

    Returns:
        Updated state with social sentiment data
    """
    logger.info("node_scrape_social_sentiment", brand=state.get("brand_name"))

    try:
        collector = SocialSentimentCollector()

        social_data = await collector.collect_brand_sentiment(
            state.get("brand_name"),
            state.get("brand_url"),
            brand_site_html=state.get("brand_site_content", "")
        )

        return {
            **state,  # Preserve all existing state
            "social_sentiment": social_data,
            "current_step": "Social media sentiment collected...",
            "progress_percent": 45,
            "steps": {**state.get("steps", {}), "scrape_social": StepStatus.COMPLETED}
        }

    except Exception as e:
        logger.error("social_sentiment_failed", error=str(e))
        return {
            **state,  # Preserve all existing state
            "social_sentiment": {"twitter": [], "reddit": [], "instagram": {}, "facebook": []},
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Social sentiment collection failed, continuing...",
            "progress_percent": 45,
            "steps": {**state.get("steps", {}), "scrape_social": StepStatus.FAILED}
        }


async def node_identify_competitors(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identify competitors (use provided list or auto-detect).

    Args:
        state: Current state dict

    Returns:
        Updated state with identified competitors
    """
    logger.info("node_identify_competitors", brand=state.get("brand_name"))

    competitors = state.get("competitors", [])

    if not competitors:
        # Auto-detect
        logger.info("auto_detecting_competitors")

        try:
            strategy = BrandScrapingStrategy()
            competitors = await strategy._detect_competitors(
                state.get("brand_name"),
                state.get("brand_site_content", "")
            )
        except Exception as e:
            logger.error("competitor_detection_failed", error=str(e))
            competitors = []

    identified = competitors[:3]  # Top 3

    return {
        **state,  # Preserve all existing state
        "identified_competitors": identified,
        "current_step": f"Identified {len(identified)} competitors...",
        "progress_percent": 55,
        "steps": {**state.get("steps", {}), "identify_competitors": StepStatus.COMPLETED}
    }


async def node_scrape_competitors(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape competitor websites.

    Args:
        state: Current state dict

    Returns:
        Updated state with competitor data
    """
    logger.info("node_scrape_competitors", brand=state.get("brand_name"))

    try:
        from ...services.scraping.base import base_scraping_service
        from ...services.cleaner import html_cleaner

        competitors = state.get("identified_competitors", [])

        if not competitors:
            return {
                **state,  # Preserve all existing state
                "competitor_data": [],
                "current_step": "No competitors to scrape...",
                "progress_percent": 65,
                "steps": {**state.get("steps", {}), "scrape_competitors": StepStatus.COMPLETED}
            }

        # Find competitor URLs
        competitor_urls = []
        for comp in competitors:
            urls = await base_scraping_service.google_search(
                f"{comp} official website",
                country=state.get("geography", "US"),
                max_results=1
            )
            if urls:
                competitor_urls.append(urls[0])

        # Scrape competitors
        if competitor_urls:
            results = await base_scraping_service.scrape_multiple(
                competitor_urls,
                country=state.get("geography", "US")
            )

            competitor_data = []
            for idx, result in enumerate(results):
                if result.success:
                    competitor_data.append({
                        "name": competitors[idx],
                        "url": result.url,
                        "content": html_cleaner.clean_and_chunk(
                            result.content,
                            source_id=10 + idx,
                            max_chunks=2
                        )
                    })

            return {
                **state,  # Preserve all existing state
                "competitor_data": competitor_data,
                "current_step": f"Scraped {len(competitor_data)} competitors...",
                "progress_percent": 65,
                "steps": {**state.get("steps", {}), "scrape_competitors": StepStatus.COMPLETED}
            }

    except Exception as e:
        logger.error("competitor_scraping_failed", error=str(e))

    return {
        **state,  # Preserve all existing state
        "competitor_data": [],
        "warnings": state.get("warnings", []) + ["Competitor scraping failed"],
        "current_step": "Competitor scraping failed, continuing...",
        "progress_percent": 65,
        "steps": {**state.get("steps", {}), "scrape_competitors": StepStatus.FAILED}
    }


async def node_scrape_news_mentions(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape recent news mentions of the brand.

    Args:
        state: Current state dict

    Returns:
        Updated state with news mentions
    """
    logger.info("node_scrape_news_mentions", brand=state.get("brand_name"))

    try:
        from ...services.scraping.base import base_scraping_service

        news_urls = await base_scraping_service.google_search(
            f"{state.get('brand_name')} news",
            country=state.get("geography", "US"),
            max_results=5
        )

        news_mentions = [{"url": url, "title": None} for url in news_urls]

        return {
            **state,  # Preserve all existing state
            "news_mentions": news_mentions,
            "current_step": "News mentions collected...",
            "progress_percent": 75,
            "steps": {**state.get("steps", {}), "scrape_news": StepStatus.COMPLETED}
        }

    except Exception as e:
        logger.error("news_scraping_failed", error=str(e))
        return {
            **state,  # Preserve all existing state
            "news_mentions": [],
            "warnings": state.get("warnings", []) + ["News scraping failed"],
            "current_step": "News scraping failed, continuing...",
            "progress_percent": 75,
            "steps": {**state.get("steps", {}), "scrape_news": StepStatus.FAILED}
        }


async def node_gpt5_analyze(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze all collected data with GPT-5.1.

    Args:
        state: Current state dict

    Returns:
        Updated state with final report
    """
    logger.info("node_gpt5_analyze", brand=state.get("brand_name"))

    try:
        # Prepare context strings
        brand_content = state.get("brand_site_content", "No brand website content available.")

        # Format social sentiment (handle None case)
        social_sentiment = state.get("social_sentiment") or {}

        twitter_data = social_sentiment.get("twitter", []) if isinstance(social_sentiment, dict) else []
        twitter_sentiment = "\n".join([
            f"- {tweet.get('text', '')} (by @{tweet.get('author', 'unknown')})"
            for tweet in twitter_data[:10]
        ]) or "No Twitter data available."

        reddit_data = social_sentiment.get("reddit", []) if isinstance(social_sentiment, dict) else []
        reddit_sentiment = "\n".join([
            f"- {post.get('title', '')}: {(post.get('text') or '')[:200]}"
            for post in reddit_data[:10]
        ]) or "No Reddit data available."

        instagram_data = social_sentiment.get("instagram", {}) if isinstance(social_sentiment, dict) else {}
        instagram_sentiment = f"Bio: {instagram_data.get('bio', 'N/A')}\nFollowers: {instagram_data.get('followers', 0)}" if instagram_data else "No Instagram data available."

        facebook_data = social_sentiment.get("facebook", []) if isinstance(social_sentiment, dict) else []
        facebook_sentiment = "\n".join([
            f"- {page.get('title', '')}: {page.get('description', '')}"
            for page in facebook_data[:5]
        ]) or "No Facebook data available."

        # Format competitor data (handle None case)
        competitors = state.get("competitor_data") or []
        if not isinstance(competitors, list):
            competitors = []
        competitor_text = "\n\n".join([
            f"**Competitor: {comp.get('name')}**\nURL: {comp.get('url')}\nContent:\n{comp.get('content', '')}"
            for comp in competitors if isinstance(comp, dict)
        ]) or "No competitor data available."

        # Format news (handle None case)
        news = state.get("news_mentions") or []
        if not isinstance(news, list):
            news = []
        news_text = "\n".join([
            f"- {item.get('url')}"
            for item in news[:5] if isinstance(item, dict)
        ]) or "No recent news available."

        # PDF context
        pdf_context = state.get("pdf_context", "")

        # Build prompt
        prompt = PromptTemplates.brand_audit(
            brand_name=state.get("brand_name"),
            brand_site_content=brand_content,
            twitter_sentiment=twitter_sentiment,
            reddit_sentiment=reddit_sentiment,
            instagram_sentiment=instagram_sentiment,
            facebook_sentiment=facebook_sentiment,
            competitor_data=competitor_text,
            news_mentions=news_text,
            pdf_context=pdf_context
        )

        # Call LLM with markdown output (not JSON)
        response, meta = llm_client.generate(
            key_name=f"brand_audit_{state.get('brand_name')}",
            prompt=prompt,
            force_json=False  # We want markdown, not JSON
        )

        if not response:
            raise Exception("LLM returned empty response")

        logger.info(
            "llm_analysis_complete",
            brand=state.get("brand_name"),
            model=meta.get("model"),
            tokens=meta.get("token_usage")
        )

        return {
            **state,  # Preserve all existing state
            "final_report": response,
            "current_step": "Analysis complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error("llm_analysis_failed", error=str(e), traceback=error_traceback)
        return {
            **state,  # Preserve all existing state
            "final_report": f"# Error\n\nFailed to generate report: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Analysis failed...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
