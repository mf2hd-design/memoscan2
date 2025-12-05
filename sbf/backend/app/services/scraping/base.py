"""
Base web scraping service using Scrapfly SDK.
Provides core scraping functionality for websites with ASP and JS rendering.
"""

import asyncio
from typing import List, Dict, Optional
from scrapfly import ScrapflyClient, ScrapeConfig, ScrapeApiResponse
import structlog

from ...core.config import settings
from ...models.schemas import ScrapeResult

logger = structlog.get_logger()


class BaseScrapingService:
    """Core web scraping service using Scrapfly."""

    def __init__(self):
        self.client = ScrapflyClient(key=settings.SCRAPFLY_KEY)
        self.base_config = {
            "asp": settings.SCRAPFLY_ASP,
            "render_js": settings.SCRAPFLY_RENDER_JS,
            "timeout": settings.SCRAPFLY_TIMEOUT,
        }

    async def scrape_url(
        self,
        url: str,
        country: str = "US",
        wait_for_selector: Optional[str] = None,
        render_js: bool = True
    ) -> ScrapeResult:
        """
        Scrape a single URL.

        Args:
            url: URL to scrape
            country: Country code for geo-targeting
            wait_for_selector: CSS selector to wait for (if JS rendering)
            render_js: Whether to render JavaScript

        Returns:
            ScrapeResult with success status and content
        """
        try:
            config = ScrapeConfig(
                url=url,
                country=country.upper(),
                asp=settings.SCRAPFLY_ASP,
                render_js=render_js,
                # Note: Don't set timeout when using Scrapfly's built-in retry mechanism
            )

            if wait_for_selector and render_js:
                config.rendering_wait = 5000  # Wait 5 seconds for JS
                config.wait_for_selector = wait_for_selector

            logger.info("scraping_url", url=url, country=country, render_js=render_js)

            result = await self.client.async_scrape(config)

            return ScrapeResult(
                success=True,
                url=url,
                content=result.content,
                source_id=0
            )

        except Exception as e:
            logger.error("scrape_failed", url=url, error=str(e))
            return ScrapeResult(
                success=False,
                url=url,
                error=str(e),
                source_id=0
            )

    async def scrape_multiple(
        self,
        urls: List[str],
        country: str = "US",
        max_concurrent: int = 5
    ) -> List[ScrapeResult]:
        """
        Scrape multiple URLs concurrently.

        Args:
            urls: List of URLs to scrape
            country: Country code for geo-targeting
            max_concurrent: Maximum concurrent requests

        Returns:
            List of ScrapeResults
        """
        if not urls:
            return []

        # Blacklist of domains that consistently fail or have strong anti-scraping
        BLACKLISTED_DOMAINS = [
            'g2.com',
            'competitors.app',
            'www.g2.com',
            'www.competitors.app'
        ]

        # Filter out blacklisted URLs
        filtered_urls = []
        for url in urls:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            if not any(blacklisted in domain for blacklisted in BLACKLISTED_DOMAINS):
                filtered_urls.append(url)
            else:
                logger.info("url_blacklisted", url=url, domain=domain)

        if not filtered_urls:
            logger.warning("all_urls_blacklisted", original_count=len(urls))
            return []

        # Create scrape configs
        configs = []
        for idx, url in enumerate(filtered_urls[:max_concurrent]):
            config = ScrapeConfig(
                url=url,
                country=country.upper(),
                asp=settings.SCRAPFLY_ASP,
                render_js=True,
                # Note: Don't set timeout when using Scrapfly's built-in retry mechanism
                tags=[f"batch_{idx}"]
            )
            configs.append(config)

        logger.info("scraping_batch", count=len(configs), country=country)

        try:
            # Concurrent scraping - collect results from async generator
            results = []
            async for result in self.client.concurrent_scrape(configs):
                results.append(result)

            # Convert to ScrapeResults
            scrape_results = []
            for idx, result in enumerate(results):
                if isinstance(result, ScrapeApiResponse) and result.success:
                    scrape_results.append(ScrapeResult(
                        success=True,
                        url=result.context.get("url", filtered_urls[idx]),
                        content=result.content,
                        source_id=idx + 1
                    ))
                else:
                    error_msg = getattr(result, 'error', 'Unknown error')
                    scrape_results.append(ScrapeResult(
                        success=False,
                        url=filtered_urls[idx] if idx < len(filtered_urls) else "unknown",
                        error=str(error_msg),
                        source_id=idx + 1
                    ))

            successful = len([r for r in scrape_results if r.success])
            logger.info("batch_complete", total=len(results), successful=successful)

            return scrape_results

        except Exception as e:
            logger.error("batch_scrape_failed", error=str(e))
            # Return failure results for all URLs
            return [
                ScrapeResult(success=False, url=url, error=str(e), source_id=idx + 1)
                for idx, url in enumerate(urls)
            ]

    async def google_search(
        self,
        query: str,
        country: str = "US",
        max_results: int = 5
    ) -> List[str]:
        """
        Search Google and extract URLs from results.

        Args:
            query: Search query
            country: Country code for geo-targeting
            max_results: Maximum number of URLs to return

        Returns:
            List of URLs from search results
        """
        try:
            # Construct Google Search URL
            google_url = f"https://www.google.com/search?q={query}&gl={country.lower()}&num={max_results}"

            logger.info("google_search", query=query, country=country)

            # Google search WITH JS rendering to bypass bot detection
            # Note: Google returns a JS challenge page without rendering
            config = ScrapeConfig(
                url=google_url,
                asp=True,  # Use ASP for better success with Google
                render_js=True,  # REQUIRED - Google uses JS bot detection
                rendering_wait=3000  # Wait 3 seconds for page to fully load
            )

            result_response = await self.client.async_scrape(config)

            logger.info(
                "scrapfly_response_received",
                query=query,
                status=result_response.success,
                content_length=len(result_response.content) if result_response.content else 0,
                has_error=hasattr(result_response, 'error')
            )

            result = ScrapeResult(
                success=True,
                url=google_url,
                content=result_response.content,
                source_id=0
            )

            if not result.success or not result.content:
                logger.warning("google_search_failed_no_content", query=query)
                return []

            # DEBUG: Save HTML to file for inspection
            import hashlib
            query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
            with open(f"/tmp/sbf_google_search_{query_hash}.html", "w") as f:
                f.write(result.content[:10000])  # First 10KB
            logger.info(f"saved_html_for_inspection", file=f"/tmp/sbf_google_search_{query_hash}.html")

            # Parse URLs from HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result.content, "html.parser")

            urls = []
            # Google search result links - try multiple selectors
            # Modern Google uses various structures
            selectors_to_try = [
                'div.g a',  # Classic structure
                'a[jsname]',  # Modern structure
                'div[data-sokoban-container] a',  # Alternative structure
                'a[href^="http"]'  # Fallback - any link starting with http
            ]

            for selector in selectors_to_try:
                links = soup.select(selector)
                logger.info(f"trying_selector", selector=selector, found_count=len(links))

                for link in links:
                    href = link.get('href')
                    # Filter out Google's own links
                    if href and href.startswith('http') and not any(
                        domain in href for domain in ['google.com', 'gstatic.com', 'googleusercontent.com', 'youtube.com']
                    ):
                        if href not in urls:  # Avoid duplicates
                            urls.append(href)
                            logger.info("found_search_result_url", url=href)
                            if len(urls) >= max_results:
                                break

                if len(urls) >= max_results:
                    break

            logger.info("google_search_complete", query=query, found=len(urls), urls_sample=urls[:3])
            return urls

        except Exception as e:
            logger.error("google_search_error", query=query, error=str(e))
            return []

    async def extract_metadata(self, html_content: str) -> Dict:
        """
        Extract metadata from HTML content.

        Args:
            html_content: HTML string

        Returns:
            Dict with title, description, keywords, etc.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        metadata = {
            "title": None,
            "description": None,
            "keywords": None,
            "og_title": None,
            "og_description": None,
        }

        # Title
        if soup.title:
            metadata["title"] = soup.title.string

        # Meta tags
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            metadata["description"] = meta_desc.get("content")

        meta_keywords = soup.find("meta", attrs={"name": "keywords"})
        if meta_keywords:
            metadata["keywords"] = meta_keywords.get("content")

        # Open Graph tags
        og_title = soup.find("meta", property="og:title")
        if og_title:
            metadata["og_title"] = og_title.get("content")

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            metadata["og_description"] = og_desc.get("content")

        return metadata


# Singleton instance
base_scraping_service = BaseScrapingService()
