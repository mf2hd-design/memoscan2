"""
Facebook scraping functionality.
Note: Facebook has strict scraping protections. This focuses on public pages via Google search.
"""

from typing import List, Dict, Optional
import structlog
from bs4 import BeautifulSoup
import re

from .base import base_scraping_service

logger = structlog.get_logger()


async def find_facebook_page(brand_website_html: str) -> Optional[str]:
    """
    Extract Facebook page URL from brand website HTML.

    Args:
        brand_website_html: HTML content from brand website

    Returns:
        Facebook page URL if found
    """
    try:
        soup = BeautifulSoup(brand_website_html, "html.parser")

        # Look for Facebook links
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()

            if 'facebook.com' in href:
                # Filter out generic Facebook links
                if '/sharer' not in href and '/share' not in href:
                    logger.info("facebook_page_found", url=link['href'])
                    return link['href']

        return None

    except Exception as e:
        logger.error("facebook_extraction_failed", error=str(e))
        return None


async def search_facebook_page(brand_name: str) -> Optional[str]:
    """
    Search for brand's Facebook page via Google.

    Args:
        brand_name: Brand name to search for

    Returns:
        Facebook page URL if found
    """
    try:
        query = f"site:facebook.com {brand_name} page"

        urls = await base_scraping_service.google_search(
            query,
            country="US",
            max_results=5
        )

        # Return first valid Facebook page URL
        for url in urls:
            if 'facebook.com' in url and '/posts/' not in url and '/sharer' not in url:
                logger.info("facebook_page_found_via_search", brand_name=brand_name, url=url)
                return url

        return None

    except Exception as e:
        logger.error("facebook_search_failed", brand_name=brand_name, error=str(e))
        return None


async def scrape_facebook_page_metadata(page_url: str) -> Optional[Dict]:
    """
    Scrape basic metadata from a Facebook page.
    Limited due to Facebook's protections - mainly extracts Open Graph data.

    Args:
        page_url: Facebook page URL

    Returns:
        Dict with page metadata or None if failed
    """
    try:
        logger.info("scraping_facebook_page", url=page_url)

        result = await base_scraping_service.scrape_url(
            page_url,
            country="US",
            render_js=True
        )

        if not result.success or not result.content:
            return None

        soup = BeautifulSoup(result.content, "html.parser")

        page_data = {
            "url": page_url,
            "title": None,
            "description": None,
            "type": "facebook_page"
        }

        # Extract Open Graph metadata
        og_title = soup.find('meta', property='og:title')
        if og_title:
            page_data['title'] = og_title.get('content')

        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            page_data['description'] = og_desc.get('content')

        logger.info("facebook_page_scraped", url=page_url, has_title=bool(page_data['title']))

        return page_data

    except Exception as e:
        logger.error("facebook_page_scrape_failed", url=page_url, error=str(e))
        return None


async def search_facebook_mentions(brand_name: str, max_results: int = 5) -> List[str]:
    """
    Search for brand mentions on Facebook via Google.

    Args:
        brand_name: Brand name to search for
        max_results: Maximum number of URLs to return

    Returns:
        List of Facebook URLs mentioning the brand
    """
    try:
        query = f"site:facebook.com {brand_name}"

        urls = await base_scraping_service.google_search(
            query,
            country="US",
            max_results=max_results
        )

        # Filter for valid Facebook content URLs
        facebook_urls = [
            url for url in urls
            if 'facebook.com' in url and '/sharer' not in url
        ]

        logger.info("facebook_search_complete", brand_name=brand_name, found=len(facebook_urls))

        return facebook_urls

    except Exception as e:
        logger.error("facebook_search_failed", brand_name=brand_name, error=str(e))
        return []
