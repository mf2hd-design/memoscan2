"""
Meeting Brief specific workflow nodes.
Simpler workflow focused on person and company intelligence.
"""

import structlog
import json
from typing import Dict, Any

from ...models.schemas import StepStatus
from ...services.scraping.strategies import MeetingBriefScrapingStrategy
from ...core.llm_client import LLMClient
from ..prompts import PromptTemplates

logger = structlog.get_logger()
llm_client = LLMClient()


async def node_research_person_and_company(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Research the person and company.

    Args:
        state: Current state dict

    Returns:
        Updated state with all scraped data
    """
    logger.info(
        "node_research_person_and_company_entry",
        person=state.get("person_name"),
        company=state.get("company_name"),
        state_keys=list(state.keys())
    )

    try:
        strategy = MeetingBriefScrapingStrategy()

        # Execute full research strategy
        results = await strategy.execute(state)

        return {
            **state,  # Preserve all existing state
            "person_profile": results.get("person_profile", {}),
            "company_data": results.get("company_data", {}),
            "company_url": results.get("company_url", ""),
            "recent_news": results.get("recent_news", []),
            "competitors": results.get("competitors", []),
            "current_step": "Research complete, analyzing...",
            "progress_percent": 70,
            "steps": {
                **state.get("steps", {}),
                "scrape_person": StepStatus.COMPLETED,
                "scrape_company": StepStatus.COMPLETED,
                "scrape_news": StepStatus.COMPLETED,
                "scrape_competitors": StepStatus.COMPLETED
            }
        }

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error("meeting_brief_research_failed", error=str(e), traceback=error_traceback)
        return {
            **state,  # Preserve all existing state
            "person_profile": {},
            "company_data": {},
            "recent_news": [],
            "competitors": [],
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Research failed, attempting analysis with available data...",
            "progress_percent": 70,
            "steps": {
                **state.get("steps", {}),
                "scrape_person": StepStatus.FAILED,
                "scrape_company": StepStatus.FAILED,
                "scrape_news": StepStatus.FAILED,
                "scrape_competitors": StepStatus.FAILED
            }
        }


async def node_gpt5_meeting_brief_analyze(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze meeting brief data with GPT-5.1.

    Args:
        state: Current state dict

    Returns:
        Updated state with final report
    """
    logger.info(
        "node_gpt5_meeting_brief_analyze",
        person=state.get("person_name")
    )

    try:
        # Format context strings (handle None case)
        person_profile = json.dumps(state.get("person_profile", {}), indent=2) if state.get("person_profile") else "No person profile data available."

        company_data_dict = state.get("company_data") or {}
        if isinstance(company_data_dict, dict):
            company_data = company_data_dict.get("content", "No company data available.")
        else:
            company_data = "No company data available."

        # Handle news data defensively
        news = state.get("recent_news") or []
        if not isinstance(news, list):
            news = []

        # DEBUG: Log the news data structure
        logger.info("news_data_debug", news_count=len(news), news_sample=news[:2] if news else [])

        news_text = "\n".join([
            f"- {item.get('title', 'Article')}: {item.get('url')}\n  {(item.get('snippet') or '')[:150]}"
            for item in news[:5] if isinstance(item, dict)
        ]) or "No recent news available."

        # DEBUG: Log formatted news text
        logger.info("news_text_debug", news_text_preview=news_text[:300])

        # Handle competitors defensively
        competitors_list = state.get("competitors") or []
        if not isinstance(competitors_list, list):
            competitors_list = []
        competitors_text = ", ".join([c for c in competitors_list if isinstance(c, str)]) or "No competitors identified."

        industry_trends = "Industry trends data not available in meeting brief mode."

        # Build prompt
        prompt = PromptTemplates.meeting_brief(
            person_name=state.get("person_name"),
            person_role=state.get("person_role"),
            company_name=state.get("company_name"),
            person_profile=person_profile,
            company_data=company_data,
            recent_news=news_text,
            competitors=competitors_text,
            industry_trends=industry_trends
        )

        # Call LLM with markdown output (not JSON)
        response, meta = llm_client.generate(
            key_name=f"meeting_brief_{state.get('person_name')}_{state.get('company_name')}",
            prompt=prompt,
            force_json=False  # We want markdown, not JSON
        )

        if not response:
            raise Exception("LLM returned empty response")

        logger.info(
            "meeting_brief_analysis_complete",
            model=meta.get("model"),
            tokens=meta.get("token_usage")
        )

        return {
            **state,  # Preserve all existing state
            "final_report": response,
            "current_step": "Meeting brief complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED}
        }

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error("meeting_brief_analysis_failed", error=str(e), traceback=error_traceback)
        return {
            **state,  # Preserve all existing state
            "final_report": f"# Error\n\nFailed to generate meeting brief: {str(e)}",
            "errors": state.get("errors", []) + [str(e)],
            "current_step": "Analysis failed...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED}
        }
