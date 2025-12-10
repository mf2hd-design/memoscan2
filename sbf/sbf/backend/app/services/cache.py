"""
File-based query cache with 24-hour TTL.
Uses MD5 hashing for cache keys.
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any
import structlog

from ..core.config import settings

logger = structlog.get_logger()


class QueryCache:
    """Simple file-based cache with TTL."""

    def __init__(self, cache_dir: Optional[str] = None, ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir or settings.CACHE_DIR)
        self.ttl_seconds = ttl_hours * 3600
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_key_hash(self, key: str) -> str:
        """Generate MD5 hash for cache key."""
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """Get file path for cache key."""
        key_hash = self._get_key_hash(key)
        return self.cache_dir / f"{key_hash}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached value if exists and not expired."""
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)

            # Check expiration
            created_at = data.get("created_at", 0)
            if time.time() - created_at > self.ttl_seconds:
                # Expired - delete and return None
                cache_path.unlink(missing_ok=True)
                logger.debug("cache_expired", key=key[:50])
                return None

            logger.debug("cache_hit", key=key[:50])
            return data.get("value")

        except Exception as e:
            logger.warning("cache_read_error", key=key[:50], error=str(e))
            return None

    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """Set cache value with timestamp."""
        cache_path = self._get_cache_path(key)

        try:
            data = {
                "key": key,
                "value": value,
                "created_at": time.time()
            }

            with open(cache_path, 'w') as f:
                json.dump(data, f)

            logger.debug("cache_set", key=key[:50])
            return True

        except Exception as e:
            logger.warning("cache_write_error", key=key[:50], error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Delete cache entry."""
        cache_path = self._get_cache_path(key)

        try:
            cache_path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def clear_expired(self) -> int:
        """Clear all expired cache entries."""
        cleared = 0
        current_time = time.time()

        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        data = json.load(f)

                    created_at = data.get("created_at", 0)
                    if current_time - created_at > self.ttl_seconds:
                        cache_file.unlink()
                        cleared += 1

                except Exception:
                    # Invalid cache file - delete it
                    cache_file.unlink(missing_ok=True)
                    cleared += 1

        except Exception as e:
            logger.error("cache_clear_error", error=str(e))

        logger.info("cache_cleared_expired", count=cleared)
        return cleared

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_files = 0
        total_size = 0
        expired_count = 0
        current_time = time.time()

        try:
            for cache_file in self.cache_dir.glob("*.json"):
                total_files += 1
                total_size += cache_file.stat().st_size

                try:
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                    created_at = data.get("created_at", 0)
                    if current_time - created_at > self.ttl_seconds:
                        expired_count += 1
                except Exception:
                    expired_count += 1

        except Exception as e:
            logger.error("cache_stats_error", error=str(e))

        return {
            "total_entries": total_files,
            "expired_entries": expired_count,
            "active_entries": total_files - expired_count,
            "total_size_bytes": total_size,
            "cache_dir": str(self.cache_dir),
            "ttl_hours": self.ttl_seconds / 3600
        }


# Global cache instance
query_cache = QueryCache()
