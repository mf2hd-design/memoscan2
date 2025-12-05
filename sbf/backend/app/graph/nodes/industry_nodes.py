"""
Industry Profile specific workflow nodes.
Market research focused workflow.
"""

import structlog
import json
from typing import Dict, Any

from ...models.schemas import StepStatus
from ...services.scraping.strategies import IndustryScrapingStrategy
from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_industry(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Research industry data, trends, brands, and news.

    Args:
        state: Current state dict

    Returns:
        Updated state with all scraped data
    """
    logger.info(
        "node_research_industry_ENTRY",
        industry=state.get("industry_name"),
        geography=state.get("geography"),
        all_keys=list(state.keys()),
        full_state=state
    )

    try:
        logger.info("creating_industry_scraping_strategy")
        strategy = IndustryScrapingStrategy()

        logger.info("executing_industry_scraping_strategy", state_keys=list(state.keys()))
        # Execute full research strategy
        results = await strategy.execute(state)

        logger.info(
            "industry_research_results",
            market_reports_count=len(results.get("market_reports", [])),
            top_brands_count=len(results.get("top_brands", [])),
            emerging_brands_count=len(results.get("emerging_brands", [])),
            news_count=len(results.get("news_articles", []))
        )

        # IMPORTANT: Preserve all existing state (industry_name, geography, etc.)
        return {
            **state,  # Preserve all existing state
            "market_reports": results.get("market_reports", []),
            "top_brands": results.get("top_brands", []),
            "emerging_brands": results.get("emerging_brands", []),
            "news_articles": results.get("news_articles", []),
            "current_step": "Research complete, analyzing...",
            "progress_percent": 70,
            "steps": {
                **state.get("steps", {}),
                "research_market": StepStatus.COMPLETED,
                "research_brands": StepStatus.COMPLETED,
                "scrape_news": StepStatus.COMPLETED
            }
        }

    except Exception as e:
        logger.error("industry_research_failed", error=str(e))
        return {
            **state,  # Preserve all existing state
            "market_reports": [],
            "top_brands": [],
            "emerging_brands": [],
            "news_articles": [],
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Research failed, attempting analysis with available data...",
            "progress_percent": 70,
            "steps": {
                **state.get("steps", {}),
                "research_market": StepStatus.FAILED,
                "research_brands": StepStatus.FAILED,
                "scrape_news": StepStatus.FAILED
            }
        }


async def node_gpt5_industry_analyze(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze industry data with GPT-5.1.

    Args:
        state: Current state dict

    Returns:
        Updated state with final report
    """
    logger.info("node_gpt5_industry_analyze", industry=state.get("industry_name"))

    try:
        # Format context strings (handle None case)
        market_reports_data = state.get("market_reports") or []
        if not isinstance(market_reports_data, list):
            market_reports_data = []
        market_reports_text = "\n\n".join([
            f"**Source [{idx+1}]**\nURL: {item.get('url')}\n{item.get('content', '')}"
            for idx, item in enumerate(market_reports_data) if isinstance(item, dict)
        ]) or "No market reports available."

        top_brands_data = state.get("top_brands") or []
        if not isinstance(top_brands_data, list):
            top_brands_data = []
        top_brands_text = "\n\n".join([
            f"**Brand [{idx+1}]**\nURL: {item.get('url')}\n{item.get('content', '')}"
            for idx, item in enumerate(top_brands_data) if isinstance(item, dict)
        ]) or "No top brands data available."

        emerging_brands_data = state.get("emerging_brands") or []
        if not isinstance(emerging_brands_data, list):
            emerging_brands_data = []
        emerging_brands_text = "\n\n".join([
            f"**Emerging [{idx+1}]**\nURL: {item.get('url')}\n{item.get('content', '')}"
            for idx, item in enumerate(emerging_brands_data) if isinstance(item, dict)
        ]) or "No emerging brands data available."

        # DEBUG: Log what's being sent to GPT
        logger.info(
            "preparing_gpt_context",
            market_reports_count=len(market_reports_data),
            top_brands_count=len(top_brands_data),
            emerging_brands_count=len(emerging_brands_data),
            market_text_length=len(market_reports_text),
            brands_text_length=len(top_brands_text),
            emerging_text_length=len(emerging_brands_text),
            market_preview=market_reports_text[:300],
            brands_preview=top_brands_text[:300]
        )

        # DEBUG: Write full context to file
        import json
        with open("/tmp/sbf_gpt_context.json", "w") as f:
            json.dump({
                "market_reports": market_reports_text[:2000],
                "top_brands": top_brands_text[:2000],
                "emerging_brands": emerging_brands_text[:2000],
            }, f, indent=2)

        news_data = state.get("news_articles") or []
        if not isinstance(news_data, list):
            news_data = []
        news_text = "\n".join([
            f"- {item.get('url')}"
            for item in news_data[:5] if isinstance(item, dict)
        ]) or "No recent news available."

        # Build prompt
        prompt = PromptTemplates.industry_profile(
            industry_name=state.get("industry_name"),
            geography=state.get("geography"),
            market_reports=market_reports_text,
            trend_data=market_reports_text,  # Same as market reports
            top_brands=top_brands_text,
            emerging_brands=emerging_brands_text,
            news_articles=news_text
        )

        # Call LLM with markdown output (not JSON)
        response, meta = llm_client.generate(
            key_name=f"industry_profile_{state.get('industry_name')}_{state.get('geography')}",
            prompt=prompt,
            force_json=False  # We want markdown, not JSON
        )

        if not response:
            raise Exception("LLM returned empty response")

        logger.info(
            "industry_analysis_complete",
            model=meta.get("model"),
            tokens=meta.get("token_usage")
        )

        return {
            **state,  # Preserve all existing state
            "final_report": response,
            "current_step": "Industry profile complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error("industry_analysis_failed", error=str(e), traceback=error_traceback)
        return {
            **state,  # Preserve all existing state
            "final_report": f"# Error\n\nFailed to generate industry profile: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Analysis failed...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
