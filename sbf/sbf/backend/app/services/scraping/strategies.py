"""
Scraping strategies for different report types.
"""

from typing import Dict, Any, List, Optional
import structlog

from .base import ScrapflyClient
from ..cleaner import html_cleaner

logger = structlog.get_logger()


class BrandScrapingStrategy:
    """Strategy for scraping brand websites."""

    def __init__(self):
        self.client = ScrapflyClient()

    async def scrape(self, url: str, brand_name: str) -> Dict[str, Any]:
        """
        Scrape a brand's website.

        Args:
            url: Brand website URL
            brand_name: Brand name for context

        Returns:
            Dict with cleaned content and metadata
        """
        try:
            # Scrape main page
            result = await self.client.scrape(
                url,
                render_js=True,
                timeout=30000
            )

            if not result.get("success"):
                raise Exception(f"Scrape failed for {url}")

            # Clean HTML
            content = html_cleaner.clean(result.get("content", ""))

            # Try to scrape about page too
            about_content = ""
            about_urls = [
                f"{url.rstrip('/')}/about",
                f"{url.rstrip('/')}/about-us",
                f"{url.rstrip('/')}/company",
            ]

            for about_url in about_urls:
                try:
                    about_result = await self.client.scrape(about_url, render_js=False)
                    if about_result.get("success"):
                        about_content = html_cleaner.clean(about_result.get("content", ""))
                        break
                except Exception:
                    continue

            combined_content = content
            if about_content:
                combined_content += f"\n\n## About Page\n{about_content}"

            return {
                "content": combined_content[:15000],  # Limit size
                "url": url,
                "brand_name": brand_name
            }

        except Exception as e:
            logger.error("brand_scrape_failed", url=url, error=str(e))
            raise

    async def scrape_by_name(self, brand_name: str) -> Dict[str, Any]:
        """
        Find and scrape a brand by name.

        Args:
            brand_name: Brand name to search for

        Returns:
            Dict with content and discovered URL
        """
        try:
            # Search for brand website
            search_results = await self.client.search_google(
                f"{brand_name} official website",
                num_results=3
            )

            if not search_results:
                return {"content": "", "url": "", "brand_name": brand_name}

            # Use first result
            brand_url = search_results[0].get("url", "")

            if not brand_url:
                return {"content": "", "url": "", "brand_name": brand_name}

            return await self.scrape(brand_url, brand_name)

        except Exception as e:
            logger.error("brand_search_failed", brand=brand_name, error=str(e))
            return {"content": "", "url": "", "brand_name": brand_name, "error": str(e)}


class IndustryScrapingStrategy:
    """Strategy for scraping industry/market data."""

    def __init__(self):
        self.client = ScrapflyClient()

    async def get_market_reports(
        self,
        industry: str,
        geography: str = "US"
    ) -> List[Dict[str, Any]]:
        """Get market research report summaries."""
        try:
            search_query = f"{industry} market research report {geography} 2024"
            results = await self.client.search_google(search_query, num_results=10)

            reports = []
            for result in results:
                reports.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", ""),
                    "source": "search"
                })

            return reports

        except Exception as e:
            logger.error("market_reports_failed", industry=industry, error=str(e))
            return []

    async def get_top_brands(
        self,
        industry: str,
        geography: str = "US"
    ) -> List[Dict[str, Any]]:
        """Get top brands in industry."""
        try:
            search_query = f"top {industry} brands {geography} 2024"
            results = await self.client.search_google(search_query, num_results=10)

            brands = []
            for result in results:
                brands.append({
                    "name": result.get("title", "").split(" - ")[0],
                    "url": result.get("url", ""),
                    "description": result.get("snippet", "")
                })

            return brands

        except Exception as e:
            logger.error("top_brands_failed", industry=industry, error=str(e))
            return []

    async def get_emerging_brands(
        self,
        industry: str,
        geography: str = "US"
    ) -> List[Dict[str, Any]]:
        """Get emerging/disruptor brands in industry."""
        try:
            search_query = f"emerging {industry} brands startups {geography} 2024"
            results = await self.client.search_google(search_query, num_results=8)

            brands = []
            for result in results:
                brands.append({
                    "name": result.get("title", "").split(" - ")[0],
                    "url": result.get("url", ""),
                    "description": result.get("snippet", "")
                })

            return brands

        except Exception as e:
            logger.error("emerging_brands_failed", industry=industry, error=str(e))
            return []

    async def get_trends(
        self,
        industry: str,
        geography: str = "US"
    ) -> List[Dict[str, Any]]:
        """Get industry trends."""
        try:
            search_query = f"{industry} trends 2024 2025 {geography}"
            results = await self.client.search_google(search_query, num_results=10)

            trends = []
            for result in results:
                trends.append({
                    "name": result.get("title", ""),
                    "url": result.get("url", ""),
                    "description": result.get("snippet", "")
                })

            return trends

        except Exception as e:
            logger.error("trends_failed", industry=industry, error=str(e))
            return []


class MeetingBriefScrapingStrategy:
    """Strategy for scraping person and company data."""

    def __init__(self):
        self.client = ScrapflyClient()

    async def research_person(
        self,
        person_name: str,
        person_role: str,
        company_name: str
    ) -> Dict[str, Any]:
        """Research a person for meeting prep."""
        try:
            # Search for LinkedIn and general info
            search_query = f"{person_name} {person_role} {company_name}"
            results = await self.client.search_google(search_query, num_results=10)

            profile_data = {
                "name": person_name,
                "role": person_role,
                "company": company_name,
                "sources": []
            }

            for result in results:
                profile_data["sources"].append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", "")
                })

            # Try to get LinkedIn data (limited without login)
            linkedin_query = f"{person_name} {company_name} site:linkedin.com"
            linkedin_results = await self.client.search_google(linkedin_query, num_results=3)

            if linkedin_results:
                profile_data["linkedin_url"] = linkedin_results[0].get("url", "")
                profile_data["linkedin_snippet"] = linkedin_results[0].get("snippet", "")

            return profile_data

        except Exception as e:
            logger.error("person_research_failed", person=person_name, error=str(e))
            return {"name": person_name, "role": person_role, "company": company_name}

    async def research_company(
        self,
        company_name: str,
        geography: str = "US"
    ) -> Dict[str, Any]:
        """Research a company for meeting prep."""
        try:
            # Search for company
            search_query = f"{company_name} company overview {geography}"
            results = await self.client.search_google(search_query, num_results=10)

            company_data = {
                "name": company_name,
                "geography": geography,
                "sources": []
            }

            for result in results:
                company_data["sources"].append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", "")
                })

                # Try to identify company URL
                if not company_data.get("url"):
                    url = result.get("url", "")
                    if company_name.lower().replace(" ", "") in url.lower():
                        company_data["url"] = url

            # Get recent news
            news = await self.client.search_news(company_name, limit=5)
            company_data["recent_news"] = news

            return company_data

        except Exception as e:
            logger.error("company_research_failed", company=company_name, error=str(e))
            return {"name": company_name, "geography": geography}


class SocialSentimentCollector:
    """Collect social media sentiment data."""

    def __init__(self):
        self.client = ScrapflyClient()

    async def collect(self, brand_name: str) -> Dict[str, List[Dict]]:
        """
        Collect social sentiment for a brand.

        Note: Full social media scraping requires platform-specific APIs.
        This is a simplified version using search.
        """
        sentiment_data = {
            "twitter": [],
            "reddit": [],
            "instagram": [],
            "facebook": []
        }

        try:
            # Search for Twitter mentions
            twitter_query = f"{brand_name} site:twitter.com OR site:x.com"
            twitter_results = await self.client.search_google(twitter_query, num_results=5)
            sentiment_data["twitter"] = [
                {"url": r.get("url"), "snippet": r.get("snippet")}
                for r in twitter_results
            ]

            # Search for Reddit discussions
            reddit_query = f"{brand_name} site:reddit.com"
            reddit_results = await self.client.search_google(reddit_query, num_results=5)
            sentiment_data["reddit"] = [
                {"url": r.get("url"), "snippet": r.get("snippet")}
                for r in reddit_results
            ]

            # Search for Instagram
            instagram_query = f"{brand_name} site:instagram.com"
            instagram_results = await self.client.search_google(instagram_query, num_results=3)
            sentiment_data["instagram"] = [
                {"url": r.get("url"), "snippet": r.get("snippet")}
                for r in instagram_results
            ]

            # Search for Facebook
            facebook_query = f"{brand_name} site:facebook.com"
            facebook_results = await self.client.search_google(facebook_query, num_results=3)
            sentiment_data["facebook"] = [
                {"url": r.get("url"), "snippet": r.get("snippet")}
                for r in facebook_results
            ]

            return sentiment_data

        except Exception as e:
            logger.error("social_sentiment_failed", brand=brand_name, error=str(e))
            return sentiment_data
