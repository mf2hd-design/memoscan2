"""
Core configuration for Strategist's Best Friend.
Uses Pydantic Settings for environment variable management.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # === API Keys ===
    OPENAI_API_KEY: str
    SCRAPFLY_KEY: str

    # === Database ===
    DATABASE_URL: str = "postgresql+asyncpg://localhost/sbf_dev"  # Default for local dev

    # === App Configuration ===
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # === Rate Limiting ===
    RATE_LIMIT_PER_HOUR: int = 3

    # === Cache Configuration ===
    CACHE_TTL_HOURS: int = 24
    CACHE_DIR: str = "/tmp/sbf_cache"

    # === GPT-5.1 Configuration ===
    GPT5_MODEL: str = "gpt-5.1-2025-11-13"
    GPT5_TIMEOUT: int = 90
    CIRCUIT_BREAKER_THRESHOLD: int = 3
    CIRCUIT_BREAKER_COOLDOWN: int = 600  # 10 minutes

    # === Scrapfly Configuration ===
    SCRAPFLY_ASP: bool = True  # Anti-Scraping Protection
    SCRAPFLY_RENDER_JS: bool = True
    SCRAPFLY_TIMEOUT: int = 30000  # 30 seconds per request

    # === Geography Options ===
    AVAILABLE_GEOS: List[str] = [
        "US", "UK", "DE", "FR", "ES", "IT", "CA", "AU", "JP", "IN"
    ]

    # === ChromaDB Configuration ===
    CHROMA_PERSIST: bool = False  # In-memory only for MVP

    # === Processing Limits ===
    MAX_CONCURRENT_SCRAPES: int = 10
    MAX_PDF_SIZE_MB: int = 10
    MAX_CONTEXT_TOKENS: int = 50000

    # === Timeouts ===
    WORKFLOW_TIMEOUT: int = 900  # 15 minutes max per report
    SCRAPE_TIMEOUT: int = 45  # 45 seconds per individual scrape

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# Global settings instance
settings = Settings()
