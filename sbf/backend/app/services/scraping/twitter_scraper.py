"""
Twitter/X scraping functionality adapted from Scrapfly scrapers.
Source: https://github.com/scrapfly/scrapfly-scrapers/tree/main/twitter-scraper
"""

from typing import Dict, Optional
import structlog
from scrapfly import ScrapeConfig
from bs4 import BeautifulSoup

from .base import base_scraping_service
from ...core.config import settings

logger = structlog.get_logger()


async def scrape_tweet(url: str) -> Optional[Dict]:
    """
    Scrape a single tweet from X.com.

    Args:
        url: Full URL to the tweet

    Returns:
        Dict with tweet data or None if failed
    """
    try:
        logger.info("scraping_tweet", url=url)

        result = await base_scraping_service.scrape_url(
            url,
            country="US",
            wait_for_selector='[data-testid="tweet"]',
            render_js=True
        )

        if not result.success or not result.content:
            return None

        # Parse tweet data from HTML
        soup = BeautifulSoup(result.content, "html.parser")

        tweet_data = {
            "url": url,
            "text": None,
            "author": None,
            "likes": 0,
            "retweets": 0,
            "replies": 0,
        }

        # Extract tweet text
        tweet_text_elem = soup.select_one('[data-testid="tweetText"]')
        if tweet_text_elem:
            tweet_data["text"] = tweet_text_elem.get_text()

        # Extract author
        author_elem = soup.select_one('[data-testid="User-Name"]')
        if author_elem:
            tweet_data["author"] = author_elem.get_text().split('\n')[0]

        # Extract engagement metrics (simplified - actual implementation needs JS parsing)
        # In production, you'd parse the XHR background requests for accurate numbers

        logger.info("tweet_scraped", url=url, has_text=bool(tweet_data["text"]))

        return tweet_data

    except Exception as e:
        logger.error("tweet_scrape_failed", url=url, error=str(e))
        return None


async def scrape_profile(username: str) -> Optional[Dict]:
    """
    Scrape a Twitter/X user profile.

    Args:
        username: Twitter handle (without @)

    Returns:
        Dict with profile data or None if failed
    """
    try:
        url = f"https://twitter.com/{username}"

        logger.info("scraping_twitter_profile", username=username)

        result = await base_scraping_service.scrape_url(
            url,
            country="US",
            wait_for_selector='[data-testid="UserDescription"]',
            render_js=True
        )

        if not result.success or not result.content:
            return None

        soup = BeautifulSoup(result.content, "html.parser")

        profile_data = {
            "username": username,
            "url": url,
            "bio": None,
            "followers": 0,
            "following": 0,
            "recent_tweets": []
        }

        # Extract bio
        bio_elem = soup.select_one('[data-testid="UserDescription"]')
        if bio_elem:
            profile_data["bio"] = bio_elem.get_text()

        # Extract recent tweets (simplified)
        tweet_elems = soup.select('[data-testid="tweet"]')
        for tweet_elem in tweet_elems[:5]:  # Get up to 5 recent tweets
            tweet_text_elem = tweet_elem.select_one('[data-testid="tweetText"]')
            if tweet_text_elem:
                profile_data["recent_tweets"].append(tweet_text_elem.get_text())

        logger.info(
            "twitter_profile_scraped",
            username=username,
            tweet_count=len(profile_data["recent_tweets"])
        )

        return profile_data

    except Exception as e:
        logger.error("twitter_profile_scrape_failed", username=username, error=str(e))
        return None


async def search_twitter_mentions(brand_name: str, max_results: int = 10) -> list:
    """
    Search for brand mentions on Twitter via Google.

    Args:
        brand_name: Brand name to search for
        max_results: Maximum number of tweets to find

    Returns:
        List of tweet URLs
    """
    try:
        # Use Google to find Twitter URLs about the brand
        query = f"site:twitter.com OR site:x.com {brand_name}"

        urls = await base_scraping_service.google_search(
            query,
            country="US",
            max_results=max_results
        )

        # Filter for tweet URLs (not profiles)
        tweet_urls = [
            url for url in urls
            if '/status/' in url and ('twitter.com' in url or 'x.com' in url)
        ]

        logger.info("twitter_search_complete", brand_name=brand_name, found=len(tweet_urls))

        return tweet_urls

    except Exception as e:
        logger.error("twitter_search_failed", brand_name=brand_name, error=str(e))
        return []
