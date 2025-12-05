"""
Scraping strategies for different report types.
Orchestrates web scraping, social media, and competitor analysis.
"""

import asyncio
from typing import List, Dict, Optional
import structlog

from .base import base_scraping_service
from .twitter_scraper import search_twitter_mentions, scrape_tweet
from .reddit_scraper import search_reddit_mentions
from .instagram_scraper import find_instagram_handle, scrape_user as scrape_instagram_user, search_instagram_mentions
from .facebook_scraper import find_facebook_page, search_facebook_page, scrape_facebook_page_metadata
from ...models.schemas import BrandAuditState, MeetingBriefState, IndustryProfileState
from ..cleaner import html_cleaner

logger = structlog.get_logger()


class SocialSentimentCollector:
    """Unified social media scraping for brand mentions."""

    async def collect_brand_sentiment(
        self,
        brand_name: str,
        brand_url: str,
        brand_site_html: Optional[str] = None
    ) -> Dict:
        """
        Scrape Twitter, Reddit, Instagram, Facebook for brand mentions.

        Args:
            brand_name: Brand name
            brand_url: Brand website URL
            brand_site_html: Optional pre-scraped brand website HTML

        Returns:
            Dict with social sentiment data from all platforms
        """
        logger.info("collecting_social_sentiment", brand=brand_name)

        # Run all social platform scrapes in parallel
        tasks = [
            self._scrape_twitter(brand_name),
            self._scrape_reddit(brand_name),
            self._scrape_instagram(brand_name, brand_site_html),
            self._scrape_facebook(brand_name, brand_site_html)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        sentiment_data = {
            "twitter": results[0] if not isinstance(results[0], Exception) else [],
            "reddit": results[1] if not isinstance(results[1], Exception) else [],
            "instagram": results[2] if not isinstance(results[2], Exception) else {},
            "facebook": results[3] if not isinstance(results[3], Exception) else []
        }

        logger.info(
            "social_sentiment_collected",
            brand=brand_name,
            twitter_count=len(sentiment_data["twitter"]),
            reddit_count=len(sentiment_data["reddit"])
        )

        return sentiment_data

    async def _scrape_twitter(self, brand_name: str) -> List[Dict]:
        """Search and scrape Twitter mentions."""
        try:
            tweet_urls = await search_twitter_mentions(brand_name, max_results=10)

            tweets = []
            for url in tweet_urls[:5]:  # Limit to top 5
                tweet_data = await scrape_tweet(url)
                if tweet_data:
                    tweets.append(tweet_data)

            return tweets

        except Exception as e:
            logger.error("twitter_collection_failed", brand=brand_name, error=str(e))
            return []

    async def _scrape_reddit(self, brand_name: str) -> List[Dict]:
        """Search and scrape Reddit mentions."""
        try:
            posts = await search_reddit_mentions(brand_name, max_results=10)
            return posts

        except Exception as e:
            logger.error("reddit_collection_failed", brand=brand_name, error=str(e))
            return []

    async def _scrape_instagram(self, brand_name: str, brand_site_html: Optional[str]) -> Dict:
        """Find and scrape Instagram profile."""
        try:
            username = None

            # Try to extract from brand website first
            if brand_site_html:
                username = await find_instagram_handle(brand_site_html)

            # Fallback to search
            if not username:
                username = await search_instagram_mentions(brand_name)

            if username:
                user_data = await scrape_instagram_user(username)
                return user_data or {}

            return {}

        except Exception as e:
            logger.error("instagram_collection_failed", brand=brand_name, error=str(e))
            return {}

    async def _scrape_facebook(self, brand_name: str, brand_site_html: Optional[str]) -> List[Dict]:
        """Find and scrape Facebook page."""
        try:
            page_url = None

            # Try to extract from brand website first
            if brand_site_html:
                page_url = await find_facebook_page(brand_site_html)

            # Fallback to search
            if not page_url:
                page_url = await search_facebook_page(brand_name)

            if page_url:
                page_data = await scrape_facebook_page_metadata(page_url)
                return [page_data] if page_data else []

            return []

        except Exception as e:
            logger.error("facebook_collection_failed", brand=brand_name, error=str(e))
            return []


class BrandScrapingStrategy:
    """Complete brand intelligence gathering for Brand Audit reports."""

    async def execute(self, state: BrandAuditState) -> Dict:
        """
        Brand Audit scraping pipeline:
        1. Deep scrape brand website
        2. Extract social media handles
        3. Scrape all social platforms
        4. Identify competitors (auto or manual)
        5. Scrape top 3 competitors
        6. News search for brand mentions

        Args:
            state: BrandAuditState with brand details

        Returns:
            Dict with all scraped data
        """
        # Extract state values using dict access
        brand_name = state.get("brand_name")
        brand_url = state.get("brand_url")
        geography = state.get("geography")
        competitors_input = state.get("competitors")

        logger.info("executing_brand_strategy", brand=brand_name)

        results = {}

        # 1. Brand website
        brand_result = await base_scraping_service.scrape_url(
            brand_url,
            country=geography
        )

        if brand_result.success:
            results["brand_site_content"] = html_cleaner.clean_and_chunk(
                brand_result.content,
                source_id=1,
                max_chunks=5
            )
            brand_html = brand_result.content
        else:
            results["brand_site_content"] = ""
            brand_html = ""

        # 2. Social sentiment (parallel)
        social_collector = SocialSentimentCollector()
        social_data = await social_collector.collect_brand_sentiment(
            brand_name,
            brand_url,
            brand_html
        )
        results["social_sentiment"] = social_data

        # 3. Identify competitors
        competitors = competitors_input if competitors_input else []

        if not competitors and brand_html:
            # Auto-detect competitors from brand site
            competitors = await self._detect_competitors(brand_name, brand_html)

        results["identified_competitors"] = competitors[:3]  # Top 3

        # 4. Scrape competitors
        competitor_data = []
        if results["identified_competitors"]:
            competitor_urls = []
            for comp in results["identified_competitors"]:
                # Try to find competitor URLs via Google
                search_results = await base_scraping_service.google_search(
                    f"{comp} official website",
                    country=geography,
                    max_results=1
                )
                if search_results:
                    competitor_urls.append(search_results[0])

            # Scrape competitors in parallel
            if competitor_urls:
                comp_results = await base_scraping_service.scrape_multiple(
                    competitor_urls,
                    country=geography
                )

                for idx, result in enumerate(comp_results):
                    if result.success:
                        competitor_data.append({
                            "name": results["identified_competitors"][idx],
                            "url": result.url,
                            "content": html_cleaner.clean_and_chunk(
                                result.content,
                                source_id=10 + idx,
                                max_chunks=2
                            )
                        })

        results["competitor_data"] = competitor_data

        # 5. News mentions
        news_urls = await base_scraping_service.google_search(
            f"{brand_name} news",
            country=geography,
            max_results=5
        )

        results["news_mentions"] = [{"url": url} for url in news_urls]

        logger.info(
            "brand_strategy_complete",
            brand=brand_name,
            competitors_found=len(results["identified_competitors"]),
            social_platforms=4
        )

        return results

    async def _detect_competitors(self, brand_name: str, brand_html: str) -> List[str]:
        """
        Auto-detect competitors from brand website or via Google search.

        Args:
            brand_name: Brand name
            brand_html: Brand website HTML

        Returns:
            List of competitor names
        """
        try:
            # Try Google search for competitors
            query = f"{brand_name} competitors alternatives"
            urls = await base_scraping_service.google_search(query, max_results=3)

            # Scrape competitor pages
            results = await base_scraping_service.scrape_multiple(urls)

            competitors = []
            for result in results:
                if result.success:
                    # Extract company names (simplified - could use NLP)
                    keywords = html_cleaner.extract_keywords(
                        html_cleaner.clean_html(result.content),
                        max_keywords=5
                    )
                    competitors.extend(keywords)

            # Deduplicate and filter out the brand itself
            unique_competitors = list(set(competitors))
            filtered = [c for c in unique_competitors if c.lower() != brand_name.lower()]

            return filtered[:5]  # Top 5

        except Exception as e:
            logger.error("competitor_detection_failed", brand=brand_name, error=str(e))
            return []


class MeetingBriefScrapingStrategy:
    """Person and company intelligence gathering for Meeting Brief reports."""

    async def execute(self, state: Dict) -> Dict:
        """
        Meeting Brief scraping pipeline:
        1. Search for person's LinkedIn/profile
        2. Scrape company website
        3. Search for recent company news
        4. Identify top competitors
        5. Gather industry trends

        Args:
            state: Dict with person and company details

        Returns:
            Dict with all scraped data
        """
        # Extract values from state dict
        person_name = state.get("person_name")
        person_role = state.get("person_role")
        company_name = state.get("company_name")
        geography = state.get("geography", "US")

        logger.info(
            "executing_meeting_brief_strategy",
            person=person_name,
            company=company_name
        )

        results = {}

        # 1. Person profile search
        person_query = f"{person_name} {person_role} {company_name}"
        person_urls = await base_scraping_service.google_search(
            person_query,
            country=geography,
            max_results=3
        )

        results["person_profile"] = {"search_urls": person_urls}

        # 2. Company website
        company_query = f"{company_name} official website"
        company_urls = await base_scraping_service.google_search(
            company_query,
            country=geography,
            max_results=1
        )

        if company_urls:
            company_result = await base_scraping_service.scrape_url(
                company_urls[0],
                country=geography
            )

            if company_result.success:
                results["company_url"] = company_urls[0]
                results["company_data"] = {
                    "url": company_urls[0],
                    "content": html_cleaner.clean_and_chunk(
                        company_result.content,
                        source_id=1,
                        max_chunks=3
                    )
                }

        # 3. Recent news - scrape the actual articles to get titles
        news_query = f"{company_name} news 2024 2025"
        news_urls = await base_scraping_service.google_search(
            news_query,
            country=geography,
            max_results=5
        )

        # Scrape news articles to get titles
        news_items = []
        if news_urls:
            news_results = await base_scraping_service.scrape_multiple(
                news_urls[:5],
                country=geography
            )

            for idx, result in enumerate(news_results):
                if result.success:
                    # Extract title from HTML - try <title> tag or first <h1>
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(result.content, 'html.parser')
                        title_tag = soup.find('title')
                        h1_tag = soup.find('h1')
                        title = (title_tag.get_text().strip() if title_tag else None) or \
                                (h1_tag.get_text().strip() if h1_tag else None) or \
                                f"News article {idx + 1}"
                        # Limit title length
                        title = title[:100] if len(title) > 100 else title
                    except:
                        title = f"News article {idx + 1}"

                    cleaned = html_cleaner.clean_html(result.content)
                    news_items.append({
                        "url": result.url,
                        "title": title,
                        "snippet": cleaned[:200]  # First 200 chars as snippet
                    })
                else:
                    news_items.append({
                        "url": news_urls[idx],
                        "title": f"Article {idx + 1}",
                        "snippet": ""
                    })

        results["recent_news"] = news_items

        # 4. Competitors
        competitor_query = f"{company_name} competitors"
        competitor_urls = await base_scraping_service.google_search(
            competitor_query,
            country=geography,
            max_results=3
        )

        # Extract competitor names (simplified)
        competitors = []
        for url in competitor_urls[:2]:
            result = await base_scraping_service.scrape_url(url, country=geography)
            if result.success:
                keywords = html_cleaner.extract_keywords(
                    html_cleaner.clean_html(result.content),
                    max_keywords=5
                )
                competitors.extend(keywords)

        results["competitors"] = list(set(competitors))[:5]

        logger.info(
            "meeting_brief_strategy_complete",
            person=person_name,
            news_count=len(results["recent_news"])
        )

        return results


class IndustryScrapingStrategy:
    """Market research for Industry Profile reports."""

    async def execute(self, state: IndustryProfileState) -> Dict:
        """
        Industry Profile scraping pipeline:
        1. Search for market reports and analyses
        2. Gather industry trends
        3. Identify top brands
        4. Find emerging players
        5. Recent industry news

        Args:
            state: IndustryProfileState with industry details

        Returns:
            Dict with all scraped data
        """
        # Extract state values using dict access
        industry_name = state.get("industry_name")
        geography = state.get("geography")

        logger.info("executing_industry_strategy", industry=industry_name, geography=geography)

        results = {}

        logger.info("starting_parallel_google_searches", industry=industry_name)
        # Run searches in parallel
        tasks = [
            # Market analysis
            base_scraping_service.google_search(
                f"{industry_name} market analysis trends {geography}",
                country=geography,
                max_results=5
            ),
            # Top brands
            base_scraping_service.google_search(
                f"top companies {industry_name} {geography}",
                country=geography,
                max_results=5
            ),
            # Emerging brands
            base_scraping_service.google_search(
                f"emerging startups {industry_name}",
                country=geography,
                max_results=5
            ),
            # Recent news
            base_scraping_service.google_search(
                f"{industry_name} industry news",
                country=geography,
                max_results=5
            )
        ]

        search_results = await asyncio.gather(*tasks)

        logger.info(
            "google_searches_complete",
            search_results_counts=[len(urls) for urls in search_results]
        )

        # Scrape top results from each search
        all_urls = []
        for urls in search_results:
            all_urls.extend(urls[:2])  # Top 2 from each search

        logger.info("collected_urls_for_scraping", url_count=len(all_urls), urls=all_urls[:5])

        # DEBUG: Write to file for debugging
        import json
        with open("/tmp/sbf_scraping_debug.json", "w") as f:
            json.dump({
                "industry": industry_name,
                "geography": geography,
                "search_results_counts": [len(urls) for urls in search_results],
                "all_urls": all_urls
            }, f, indent=2)

        # Scrape in parallel
        scrape_results = await base_scraping_service.scrape_multiple(
            all_urls,
            country=geography
        )

        logger.info(
            "scrape_multiple_complete",
            total_results=len(scrape_results),
            successful=[r.success for r in scrape_results],
            success_count=sum(1 for r in scrape_results if r.success)
        )

        # Organize results
        results["market_reports"] = []
        results["top_brands"] = []
        results["emerging_brands"] = []
        results["news_articles"] = []

        for idx, result in enumerate(scrape_results):
            if result.success:
                cleaned_content = html_cleaner.clean_and_chunk(
                    result.content,
                    source_id=idx + 1,
                    max_chunks=2
                )

                logger.info(
                    "scraped_content_cleaned",
                    idx=idx,
                    url=result.url[:100],
                    content_length=len(cleaned_content),
                    content_preview=cleaned_content[:200] if cleaned_content else "EMPTY"
                )

                data_entry = {
                    "url": result.url,
                    "content": cleaned_content
                }

                # Categorize based on which search it came from
                if idx < 4:
                    results["market_reports"].append(data_entry)
                elif idx < 8:
                    results["top_brands"].append(data_entry)
                elif idx < 12:
                    results["emerging_brands"].append(data_entry)
                else:
                    results["news_articles"].append(data_entry)

        logger.info(
            "industry_strategy_complete",
            industry=industry_name,
            sources_scraped=len(scrape_results)
        )

        return results
