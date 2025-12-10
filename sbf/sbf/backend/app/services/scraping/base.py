"""
Base Scrapfly client for web scraping.
"""

import asyncio
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus
import structlog

from ...core.config import settings

logger = structlog.get_logger()


class ScrapflyClient:
    """
    Scrapfly API client for web scraping with anti-bot protection.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SCRAPFLY_KEY
        if not self.api_key:
            raise ValueError("SCRAPFLY_KEY is required")

        self._client = None

    def _get_client(self):
        """Get or create Scrapfly client."""
        if self._client is not None:
            return self._client

        try:
            from scrapfly import ScrapflyClient as SF, ScrapeConfig

            self._client = SF(key=self.api_key)
            return self._client

        except ImportError:
            logger.error("scrapfly_not_installed")
            raise ImportError("scrapfly-sdk not installed. Run: pip install scrapfly-sdk")

    async def scrape(
        self,
        url: str,
        render_js: bool = True,
        wait_for_selector: Optional[str] = None,
        timeout: int = 30000
    ) -> Dict[str, Any]:
        """
        Scrape a URL using Scrapfly.

        Args:
            url: URL to scrape
            render_js: Whether to render JavaScript
            wait_for_selector: CSS selector to wait for
            timeout: Timeout in milliseconds

        Returns:
            Dict with 'content', 'status_code', 'url'
        """
        try:
            from scrapfly import ScrapeConfig

            client = self._get_client()

            config = ScrapeConfig(
                url=url,
                asp=settings.SCRAPFLY_ASP,
                render_js=render_js,
                timeout=timeout,
                wait_for_selector=wait_for_selector
            )

            # Run in thread since scrapfly is sync
            result = await asyncio.to_thread(
                client.scrape, config
            )

            return {
                "content": result.content,
                "status_code": result.status_code,
                "url": result.url,
                "success": result.success
            }

        except Exception as e:
            logger.error("scrape_failed", url=url, error=str(e))
            raise

    async def scrape_multiple(
        self,
        urls: List[str],
        render_js: bool = True,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Scrape multiple URLs concurrently.

        Args:
            urls: List of URLs to scrape
            render_js: Whether to render JavaScript
            max_concurrent: Maximum concurrent requests

        Returns:
            List of scrape results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def scrape_with_semaphore(url: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self.scrape(url, render_js=render_js)
                except Exception as e:
                    return {
                        "content": "",
                        "url": url,
                        "error": str(e),
                        "success": False
                    }

        tasks = [scrape_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks)

        return list(results)

    async def search_google(
        self,
        query: str,
        num_results: int = 10,
        country: str = "US"
    ) -> List[Dict[str, Any]]:
        """
        Search Google using Scrapfly.

        Args:
            query: Search query
            num_results: Number of results
            country: Country code for localization

        Returns:
            List of search results with title, url, snippet
        """
        try:
            from scrapfly import ScrapeConfig

            client = self._get_client()

            # Use Google search URL with proper encoding
            encoded_query = quote_plus(query)
            search_url = f"https://www.google.com/search?q={encoded_query}&num={num_results}&gl={country.lower()}"

            config = ScrapeConfig(
                url=search_url,
                asp=True,
                render_js=True,
                timeout=30000,
                country=country
            )

            result = await asyncio.to_thread(
                client.scrape, config
            )

            # Parse search results from HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result.content, 'html.parser')

            results = []
            for g in soup.find_all('div', class_='g'):
                title_elem = g.find('h3')
                link_elem = g.find('a', href=True)
                snippet_elem = g.find('div', class_=['VwiC3b', 'yXK7lf'])

                if title_elem and link_elem:
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "url": link_elem['href'],
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else ""
                    })

            return results[:num_results]

        except Exception as e:
            logger.error("google_search_failed", query=query, error=str(e))
            return []

    async def search_news(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for news articles.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of news articles with title, url, snippet
        """
        try:
            # Use Google News search with proper encoding
            encoded_query = quote_plus(query)
            news_url = f"https://news.google.com/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

            result = await self.scrape(news_url, render_js=True)

            if not result.get("success"):
                return []

            # Parse news results
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result["content"], 'html.parser')

            articles = []
            for article in soup.find_all('article')[:limit]:
                title_elem = article.find('a', class_='JtKRv')
                if not title_elem:
                    title_elem = article.find('h3') or article.find('h4')

                source_elem = article.find('div', class_='vr1PYe')
                time_elem = article.find('time')

                if title_elem:
                    articles.append({
                        "title": title_elem.get_text(strip=True),
                        "url": title_elem.get('href', ''),
                        "source": source_elem.get_text(strip=True) if source_elem else "",
                        "time": time_elem.get('datetime', '') if time_elem else "",
                        "snippet": ""
                    })

            return articles

        except Exception as e:
            logger.error("news_search_failed", query=query, error=str(e))
            return []
