"""
Pytest configuration and shared fixtures.
"""

import pytest
import sys
import os

# Add the backend app to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set required environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("SCRAPFLY_KEY", "test-scrapfly-key")
    # Increase rate limit for tests
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "1000")
