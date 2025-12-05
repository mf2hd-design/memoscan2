"""
Query cache service for reducing API costs.
Caches scraped content and search results with TTL.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import structlog

from ..core.config import settings

logger = structlog.get_logger()


class QueryCache:
    """
    File-based cache for scraping results and LLM outputs.
    Uses 24-hour TTL to balance freshness vs. cost savings.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or settings.CACHE_DIR)
        self.ttl_hours = settings.CACHE_TTL_HOURS
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("cache_initialized", cache_dir=str(self.cache_dir))

    def _hash_key(self, *args: str) -> str:
        """Generate cache key from arguments."""
        key_string = "_".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def _is_expired(self, cache_data: Dict) -> bool:
        """Check if cache entry is expired."""
        if "timestamp" not in cache_data:
            return True

        cached_time = datetime.fromisoformat(cache_data["timestamp"])
        expiry_time = cached_time + timedelta(hours=self.ttl_hours)

        return datetime.utcnow() > expiry_time

    def get(self, *key_parts: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached data.

        Args:
            *key_parts: Parts of the cache key (brand_name, geo, etc.)

        Returns:
            Cached data if valid, None otherwise
        """
        cache_key = self._hash_key(*key_parts)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            logger.debug("cache_miss", key=cache_key)
            return None

        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)

            if self._is_expired(cache_data):
                logger.info("cache_expired", key=cache_key)
                cache_path.unlink()  # Delete expired cache
                return None

            logger.info("cache_hit", key=cache_key)
            return cache_data.get("data")

        except Exception as e:
            logger.error("cache_read_error", key=cache_key, error=str(e))
            return None

    def set(self, data: Dict[str, Any], *key_parts: str) -> bool:
        """
        Store data in cache.

        Args:
            data: Data to cache
            *key_parts: Parts of the cache key

        Returns:
            True if successful, False otherwise
        """
        cache_key = self._hash_key(*key_parts)
        cache_path = self._get_cache_path(cache_key)

        try:
            cache_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            }

            with open(cache_path, 'w') as f:
                json.dump(cache_entry, f, indent=2)

            logger.info("cache_set", key=cache_key)
            return True

        except Exception as e:
            logger.error("cache_write_error", key=cache_key, error=str(e))
            return False

    def delete(self, *key_parts: str) -> bool:
        """
        Delete cached entry.

        Args:
            *key_parts: Parts of the cache key

        Returns:
            True if deleted, False otherwise
        """
        cache_key = self._hash_key(*key_parts)
        cache_path = self._get_cache_path(cache_key)

        try:
            if cache_path.exists():
                cache_path.unlink()
                logger.info("cache_deleted", key=cache_key)
                return True
            return False
        except Exception as e:
            logger.error("cache_delete_error", key=cache_key, error=str(e))
            return False

    def clear_expired(self) -> int:
        """
        Clear all expired cache entries.

        Returns:
            Number of entries cleared
        """
        cleared = 0
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)

                    if self._is_expired(cache_data):
                        cache_file.unlink()
                        cleared += 1

                except Exception:
                    pass  # Skip problematic files

            logger.info("cache_cleanup", cleared=cleared)
            return cleared

        except Exception as e:
            logger.error("cache_cleanup_error", error=str(e))
            return cleared

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache size, entry count, etc.
        """
        try:
            cache_files = list(self.cache_dir.glob("*.json"))
            total_size = sum(f.stat().st_size for f in cache_files)

            # Count expired entries
            expired = 0
            for cache_file in cache_files:
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    if self._is_expired(cache_data):
                        expired += 1
                except Exception:
                    pass

            return {
                "total_entries": len(cache_files),
                "expired_entries": expired,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cache_dir": str(self.cache_dir)
            }

        except Exception as e:
            logger.error("cache_stats_error", error=str(e))
            return {}


# Singleton instance
query_cache = QueryCache()
