"""
Base workflow utilities and shared components.
"""

from langgraph.checkpoint.memory import MemorySaver
from typing import Optional
import structlog

logger = structlog.get_logger()

# Global memory saver instance (shared across workflows)
_memory_saver: Optional[MemorySaver] = None


def get_memory_saver() -> MemorySaver:
    """Get or create the shared MemorySaver instance."""
    global _memory_saver
    if _memory_saver is None:
        _memory_saver = MemorySaver()
        logger.info("memory_saver_initialized")
    return _memory_saver


def reset_memory_saver():
    """Reset the memory saver (useful for testing)."""
    global _memory_saver
    _memory_saver = None
    logger.info("memory_saver_reset")
