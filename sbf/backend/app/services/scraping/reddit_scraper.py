"""
Reddit scraping functionality adapted from Scrapfly scrapers.
Source: https://github.com/scrapfly/scrapfly-scrapers/tree/main/reddit-scraper
"""

from typing import Dict, List, Optional
import structlog
from bs4 import BeautifulSoup
import re

from .base import base_scraping_service

logger = structlog.get_logger()


async def scrape_post(url: str, sort: str = "top") -> Optional[Dict]:
    """
    Scrape a Reddit post and its comments.

    Args:
        url: Full URL to the Reddit post
        sort: Sort order for comments (top, new, old)

    Returns:
        Dict with post data and comments or None if failed
    """
    try:
        logger.info("scraping_reddit_post", url=url, sort=sort)

        # Add sort parameter to URL
        if '?' not in url:
            url = f"{url}?sort={sort}"

        result = await base_scraping_service.scrape_url(
            url,
            country="US",
            render_js=True
        )

        if not result.success or not result.content:
            return None

        soup = BeautifulSoup(result.content, "html.parser")

        post_data = {
            "url": url,
            "title": None,
            "text": None,
            "author": None,
            "upvotes": 0,
            "comments": []
        }

        # Extract post title
        title_elem = soup.select_one('h1')
        if title_elem:
            post_data["title"] = title_elem.get_text().strip()

        # Extract post text
        post_text_elem = soup.select_one('[data-test-id="post-content"]')
        if post_text_elem:
            post_data["text"] = post_text_elem.get_text().strip()

        # Extract author
        author_elem = soup.select_one('[data-testid="post_author_link"]')
        if author_elem:
            post_data["author"] = author_elem.get_text().strip()

        # Extract top comments (simplified parsing)
        comment_elems = soup.select('[data-testid="comment"]')
        for comment_elem in comment_elems[:10]:  # Top 10 comments
            comment_text_elem = comment_elem.select_one('[data-testid="comment-text"]')
            if comment_text_elem:
                post_data["comments"].append({
                    "text": comment_text_elem.get_text().strip(),
                    "author": None  # Could extract if needed
                })

        logger.info(
            "reddit_post_scraped",
            url=url,
            comment_count=len(post_data["comments"])
        )

        return post_data

    except Exception as e:
        logger.error("reddit_post_scrape_failed", url=url, error=str(e))
        return None


async def scrape_subreddit(subreddit_name: str, max_posts: int = 10) -> List[Dict]:
    """
    Scrape posts from a subreddit.

    Args:
        subreddit_name: Subreddit name (without r/)
        max_posts: Maximum number of posts to scrape

    Returns:
        List of post data dicts
    """
    try:
        url = f"https://www.reddit.com/r/{subreddit_name}/"

        logger.info("scraping_subreddit", subreddit=subreddit_name)

        result = await base_scraping_service.scrape_url(
            url,
            country="US",
            render_js=True
        )

        if not result.success or not result.content:
            return []

        soup = BeautifulSoup(result.content, "html.parser")

        posts = []

        # Find post links
        post_links = soup.select('a[data-click-id="body"]')

        for link in post_links[:max_posts]:
            href = link.get('href')
            if href and href.startswith('/r/'):
                full_url = f"https://www.reddit.com{href}"

                # Get post title from link text
                title = link.get_text().strip()

                posts.append({
                    "url": full_url,
                    "title": title,
                    "subreddit": subreddit_name
                })

        logger.info("subreddit_scraped", subreddit=subreddit_name, post_count=len(posts))

        return posts

    except Exception as e:
        logger.error("subreddit_scrape_failed", subreddit=subreddit_name, error=str(e))
        return []


async def search_reddit_mentions(brand_name: str, max_results: int = 10) -> List[Dict]:
    """
    Search for brand mentions on Reddit via Google.

    Args:
        brand_name: Brand name to search for
        max_results: Maximum number of posts to find

    Returns:
        List of Reddit post URLs and metadata
    """
    try:
        # Use Google to find Reddit URLs about the brand
        query = f"site:reddit.com {brand_name}"

        urls = await base_scraping_service.google_search(
            query,
            country="US",
            max_results=max_results
        )

        # Filter for post URLs (not user profiles or subreddit pages)
        post_urls = [
            url for url in urls
            if '/comments/' in url and 'reddit.com' in url
        ]

        # Scrape each post
        posts = []
        for url in post_urls[:5]:  # Limit to top 5 to save API calls
            post_data = await scrape_post(url)
            if post_data:
                posts.append(post_data)

        logger.info("reddit_search_complete", brand_name=brand_name, found=len(posts))

        return posts

    except Exception as e:
        logger.error("reddit_search_failed", brand_name=brand_name, error=str(e))
        return []
