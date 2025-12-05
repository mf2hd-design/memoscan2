"""
Base workflow utilities including memory checkpointing.
"""

from typing import Optional
import structlog
from langgraph.checkpoint.memory import MemorySaver

from ...core.config import settings

logger = structlog.get_logger()

# Global checkpointer instance
_checkpointer: Optional[MemorySaver] = None


async def get_checkpointer() -> MemorySaver:
    """
    Get or create in-memory checkpointer for LangGraph.

    Note: For local development. In production, use PostgreSQL checkpointer.

    Returns:
        MemorySaver instance
    """
    global _checkpointer

    if _checkpointer is None:
        try:
            # Create in-memory checkpointer (ephemeral, resets on restart)
            _checkpointer = MemorySaver()

            logger.info("checkpointer_initialized", type="memory", note="ephemeral - will reset on restart")

        except Exception as e:
            logger.error("checkpointer_initialization_failed", error=str(e))
            raise

    return _checkpointer


async def close_checkpointer():
    """Close checkpointer connection."""
    global _checkpointer

    if _checkpointer is not None:
        try:
            # MemorySaver cleanup
            _checkpointer = None
            logger.info("checkpointer_closed")
        except Exception as e:
            logger.error("checkpointer_close_failed", error=str(e))
