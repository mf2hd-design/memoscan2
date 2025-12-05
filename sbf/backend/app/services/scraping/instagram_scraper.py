"""
Instagram scraping functionality adapted from Scrapfly scrapers.
Source: https://github.com/scrapfly/scrapfly-scrapers/tree/main/instagram-scraper
"""

from typing import Dict, List, Optional
import structlog
from bs4 import BeautifulSoup
import re

from .base import base_scraping_service

logger = structlog.get_logger()


async def scrape_user(username: str) -> Optional[Dict]:
    """
    Scrape an Instagram user profile.

    Args:
        username: Instagram username (without @)

    Returns:
        Dict with user profile data or None if failed
    """
    try:
        url = f"https://www.instagram.com/{username}/"

        logger.info("scraping_instagram_user", username=username)

        result = await base_scraping_service.scrape_url(
            url,
            country="US",
            render_js=True
        )

        if not result.success or not result.content:
            return None

        soup = BeautifulSoup(result.content, "html.parser")

        user_data = {
            "username": username,
            "url": url,
            "bio": None,
            "followers": 0,
            "following": 0,
            "posts": 0,
            "recent_posts": []
        }

        # Extract metadata from JSON-LD or meta tags
        # Instagram embeds user data in <script type="application/ld+json">
        json_ld_scripts = soup.find_all('script', type='application/ld+json')

        for script in json_ld_scripts:
            try:
                import json
                data = json.loads(script.string)

                if isinstance(data, dict):
                    if 'biography' in data:
                        user_data['bio'] = data['biography']

                    # Extract follower counts if available
                    if 'edge_followed_by' in data:
                        user_data['followers'] = data['edge_followed_by'].get('count', 0)

            except Exception:
                pass

        # Extract bio from meta tags if not found in JSON-LD
        if not user_data['bio']:
            meta_desc = soup.find('meta', property='og:description')
            if meta_desc:
                user_data['bio'] = meta_desc.get('content', '')

        logger.info("instagram_user_scraped", username=username, has_bio=bool(user_data['bio']))

        return user_data

    except Exception as e:
        logger.error("instagram_user_scrape_failed", username=username, error=str(e))
        return None


async def scrape_post(shortcode: str) -> Optional[Dict]:
    """
    Scrape an Instagram post.

    Args:
        shortcode: Instagram post shortcode (from URL)

    Returns:
        Dict with post data or None if failed
    """
    try:
        url = f"https://www.instagram.com/p/{shortcode}/"

        logger.info("scraping_instagram_post", shortcode=shortcode)

        result = await base_scraping_service.scrape_url(
            url,
            country="US",
            render_js=True
        )

        if not result.success or not result.content:
            return None

        soup = BeautifulSoup(result.content, "html.parser")

        post_data = {
            "shortcode": shortcode,
            "url": url,
            "caption": None,
            "likes": 0,
            "comments": 0
        }

        # Extract caption from meta tags
        meta_desc = soup.find('meta', property='og:description')
        if meta_desc:
            caption = meta_desc.get('content', '')
            # Instagram captions often include like/comment counts
            # Extract just the text part
            if ':' in caption:
                post_data['caption'] = caption.split(':')[0].strip()

        logger.info("instagram_post_scraped", shortcode=shortcode, has_caption=bool(post_data['caption']))

        return post_data

    except Exception as e:
        logger.error("instagram_post_scrape_failed", shortcode=shortcode, error=str(e))
        return None


async def find_instagram_handle(brand_website_html: str) -> Optional[str]:
    """
    Extract Instagram handle from brand website HTML.

    Args:
        brand_website_html: HTML content from brand website

    Returns:
        Instagram username if found, None otherwise
    """
    try:
        soup = BeautifulSoup(brand_website_html, "html.parser")

        # Look for Instagram links
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()

            if 'instagram.com' in href:
                # Extract username from URL
                # Handles: https://instagram.com/username, https://www.instagram.com/username/
                match = re.search(r'instagram\.com/([^/?]+)', href)
                if match:
                    username = match.group(1)
                    # Filter out generic paths
                    if username not in ['explore', 'accounts', 'p', 'tv', 'reel']:
                        logger.info("instagram_handle_found", username=username)
                        return username

        return None

    except Exception as e:
        logger.error("instagram_handle_extraction_failed", error=str(e))
        return None


async def search_instagram_mentions(brand_name: str) -> Optional[str]:
    """
    Search for brand's Instagram handle via Google.

    Args:
        brand_name: Brand name to search for

    Returns:
        Instagram username if found
    """
    try:
        query = f"site:instagram.com {brand_name}"

        urls = await base_scraping_service.google_search(
            query,
            country="US",
            max_results=5
        )

        # Extract username from first valid Instagram URL
        for url in urls:
            if 'instagram.com' in url and '/p/' not in url:  # Not a post URL
                match = re.search(r'instagram\.com/([^/?]+)', url)
                if match:
                    username = match.group(1)
                    if username not in ['explore', 'accounts', 'p', 'tv', 'reel']:
                        logger.info("instagram_handle_found_via_search", brand_name=brand_name, username=username)
                        return username

        return None

    except Exception as e:
        logger.error("instagram_search_failed", brand_name=brand_name, error=str(e))
        return None
