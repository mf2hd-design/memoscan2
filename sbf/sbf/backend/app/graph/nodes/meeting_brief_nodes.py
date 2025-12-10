"""
Meeting Brief workflow nodes.
Handles person research, company research, news, and analysis.
"""

from typing import Dict, Any
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_research_person(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research the person using LinkedIn and web sources."""
    from ...services.scraping.strategies import MeetingBriefScrapingStrategy

    person_name = state.get("person_name", "")
    person_role = state.get("person_role", "")
    company_name = state.get("company_name", "")

    try:
        strategy = MeetingBriefScrapingStrategy()
        person_data = await strategy.research_person(person_name, person_role, company_name)

        logger.info(
            "person_researched",
            person=person_name,
            data_keys=list(person_data.keys()) if person_data else []
        )

        return {
            **state,
            "person_profile": person_data or {},
            "current_step": f"Researched {person_name}...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "research_person": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("person_research_failed", person=person_name, error=str(e))
        return {
            **state,
            "person_profile": {},
            "warnings": state.get("warnings", []) + [f"Could not research person: {str(e)}"],
            "current_step": "Person research failed, continuing...",
            "progress_percent": 25,
            "steps": {**state.get("steps", {}), "research_person": StepStatus.FAILED.value}
        }


async def node_research_company(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research the company website and background."""
    from ...services.scraping.strategies import MeetingBriefScrapingStrategy

    company_name = state.get("company_name", "")
    geography = state.get("geography", "US")

    try:
        strategy = MeetingBriefScrapingStrategy()
        company_data = await strategy.research_company(company_name, geography)

        logger.info(
            "company_researched",
            company=company_name,
            data_keys=list(company_data.keys()) if company_data else []
        )

        return {
            **state,
            "company_data": company_data or {},
            "company_url": company_data.get("url", "") if company_data else "",
            "current_step": f"Researched {company_name}...",
            "progress_percent": 40,
            "steps": {**state.get("steps", {}), "research_company": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("company_research_failed", company=company_name, error=str(e))
        return {
            **state,
            "company_data": {},
            "company_url": "",
            "warnings": state.get("warnings", []) + [f"Could not research company: {str(e)}"],
            "current_step": "Company research failed, continuing...",
            "progress_percent": 40,
            "steps": {**state.get("steps", {}), "research_company": StepStatus.FAILED.value}
        }


async def node_recent_news(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gather recent news about the person and company."""
    from ...services.scraping.base import ScrapflyClient

    person_name = state.get("person_name", "")
    company_name = state.get("company_name", "")

    try:
        client = ScrapflyClient()

        # Search for both person and company news
        person_news = await client.search_news(person_name, limit=5)
        company_news = await client.search_news(company_name, limit=5)

        # Combine and deduplicate
        all_news = person_news + company_news
        seen_titles = set()
        unique_news = []
        for article in all_news:
            title = article.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(article)

        logger.info(
            "news_collected",
            person=person_name,
            company=company_name,
            count=len(unique_news)
        )

        return {
            **state,
            "recent_news": unique_news[:10],
            "current_step": "Gathered recent news...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "recent_news": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("news_collection_failed", error=str(e))
        return {
            **state,
            "recent_news": [],
            "warnings": state.get("warnings", []) + [f"Could not collect news: {str(e)}"],
            "current_step": "News collection failed, continuing...",
            "progress_percent": 55,
            "steps": {**state.get("steps", {}), "recent_news": StepStatus.FAILED.value}
        }


async def node_industry_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """Gather industry context for the company."""
    from ...services.scraping.strategies import IndustryScrapingStrategy

    company_data = state.get("company_data", {})
    geography = state.get("geography", "US")

    # Try to infer industry from company data
    industry = company_data.get("industry", "") if isinstance(company_data, dict) else ""

    if not industry:
        # Use GPT to infer industry
        from ...core.llm_client import LLMClient

        company_name = state.get("company_name", "")
        try:
            llm = LLMClient()
            prompt = f"What industry is {company_name} in? Reply with just the industry name (e.g., 'Technology', 'Healthcare', 'Financial Services')."
            response, _ = llm.generate(
                key_name=f"infer_industry_{company_name}",
                prompt=prompt
            )
            industry = response.strip().strip('"')
        except Exception:
            industry = "General Business"

    try:
        strategy = IndustryScrapingStrategy()
        trends = await strategy.get_trends(industry, geography)

        logger.info(
            "industry_context_gathered",
            industry=industry,
            trends_count=len(trends)
        )

        return {
            **state,
            "industry_trends": trends,
            "current_step": f"Researched {industry} trends...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "industry_context": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error("industry_context_failed", industry=industry, error=str(e))
        return {
            **state,
            "industry_trends": [],
            "warnings": state.get("warnings", []) + [f"Could not gather industry context: {str(e)}"],
            "current_step": "Industry research failed, continuing...",
            "progress_percent": 70,
            "steps": {**state.get("steps", {}), "industry_context": StepStatus.FAILED.value}
        }


async def node_analyze_meeting_brief(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive meeting brief using GPT-5.1."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import MEETING_BRIEF_PROMPT

    person_name = state.get("person_name", "")
    person_role = state.get("person_role", "")
    company_name = state.get("company_name", "")
    geography = state.get("geography", "US")

    # Compile context
    context_parts = []

    # Person profile
    person_profile = state.get("person_profile", {})
    if person_profile and isinstance(person_profile, dict):
        profile_text = []
        for key, value in person_profile.items():
            if value:
                profile_text.append(f"- {key}: {value}")
        if profile_text:
            context_parts.append("## Person Profile\n" + "\n".join(profile_text))

    # Company data
    company_data = state.get("company_data", {})
    if company_data and isinstance(company_data, dict):
        company_text = []
        for key, value in company_data.items():
            if value and key != "url":
                company_text.append(f"- {key}: {value}")
        if company_text:
            context_parts.append("## Company Information\n" + "\n".join(company_text))

    # Recent news
    news = state.get("recent_news", [])
    if news and isinstance(news, list):
        news_text = []
        for article in news[:5]:
            if isinstance(article, dict):
                title = article.get("title", "")
                snippet = article.get("snippet", "")[:200]
                news_text.append(f"- {title}: {snippet}")
        if news_text:
            context_parts.append("## Recent News\n" + "\n".join(news_text))

    # Industry trends
    trends = state.get("industry_trends", [])
    if trends and isinstance(trends, list):
        trends_text = []
        for trend in trends[:5]:
            if isinstance(trend, dict):
                name = trend.get("name", trend.get("title", ""))
                desc = trend.get("description", trend.get("snippet", ""))[:200]
                trends_text.append(f"- {name}: {desc}")
        if trends_text:
            context_parts.append("## Industry Trends\n" + "\n".join(trends_text))

    combined_context = "\n\n".join(context_parts)

    # Build prompt
    prompt = MEETING_BRIEF_PROMPT.format(
        person_name=person_name,
        person_role=person_role,
        company_name=company_name,
        geography=geography,
        context=combined_context
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"meeting_brief_{person_name}_{company_name}",
            prompt=prompt
        )

        logger.info(
            "meeting_brief_generated",
            person=person_name,
            company=company_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "combined_context": combined_context,
            "final_report": report,
            "current_step": "Meeting brief complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "meeting_brief_generation_failed",
            person=person_name,
            company=company_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "combined_context": combined_context,
            "final_report": f"# Meeting Brief: {person_name} at {company_name}\n\nBrief generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Brief generation failed: {str(e)}"],
            "current_step": "Brief generation failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }
