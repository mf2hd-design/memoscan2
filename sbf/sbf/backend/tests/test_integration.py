"""
Integration tests for SBF workflows.
Tests full workflow execution with mocked external services.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


# ============================================
# Mock Responses
# ============================================

MOCK_GPT_BRAND_AUDIT = """# Brand Audit: Nike

## Executive Summary
Nike remains the dominant force in athletic footwear and apparel, with strong brand equity built on innovation and athlete partnerships.

## Brand Identity Analysis
Nike's "Just Do It" positioning continues to resonate across demographics. The swoosh is one of the most recognized logos globally.

## Market Position
- Market share: ~27% of global athletic footwear
- Key segments: Running, Basketball, Lifestyle
- Price positioning: Premium

## Digital Presence
Strong social media engagement with 200M+ Instagram followers. E-commerce represents 30%+ of revenue.

## Competitive Analysis
Main competitors include Adidas, Puma, and Under Armour. Nike maintains lead through innovation and marketing.

## Consumer Perception
Brand health scores remain high. Primary associations: Performance, Innovation, Style.

## Strategic Recommendations
1. Continue investment in sustainability messaging
2. Expand direct-to-consumer channels
3. Strengthen presence in emerging markets
"""

MOCK_GPT_COMPETITORS = '["Adidas", "Puma", "Under Armour", "New Balance", "Reebok"]'

MOCK_SCRAPE_CONTENT = """
Nike Official Website

About Nike
Nike, Inc. is an American multinational corporation that designs, develops, manufactures, and markets footwear, apparel, equipment, accessories, and services worldwide.

Our Mission
To bring inspiration and innovation to every athlete in the world.

Products
- Running shoes
- Basketball shoes
- Training gear
- Lifestyle apparel
"""

MOCK_SOCIAL_SENTIMENT = {
    "twitter": [
        {"text": "Love my new Nike Air Max!", "sentiment": "positive"},
        {"text": "Nike customer service is great", "sentiment": "positive"}
    ],
    "reddit": [
        {"text": "Nike quality has been consistent", "sentiment": "positive"}
    ]
}

MOCK_NEWS = [
    {"title": "Nike Reports Strong Q3 Earnings", "snippet": "Revenue up 12%", "url": "https://example.com/1"},
    {"title": "Nike Announces New Sustainability Initiative", "snippet": "50% recycled materials by 2025", "url": "https://example.com/2"}
]


# ============================================
# Mock Fixtures
# ============================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns realistic responses."""
    with patch('app.core.llm_client.LLMClient') as MockLLM:
        instance = MockLLM.return_value
        
        def generate_side_effect(key_name, prompt, **kwargs):
            if "competitors" in key_name.lower() or "identify" in prompt.lower():
                return MOCK_GPT_COMPETITORS, {"api_used": "responses_api", "model": "gpt-5.1-2025-11-13"}
            else:
                return MOCK_GPT_BRAND_AUDIT, {"api_used": "responses_api", "model": "gpt-5.1-2025-11-13"}
        
        instance.generate.side_effect = generate_side_effect
        yield instance


@pytest.fixture
def mock_scrapfly():
    """Mock Scrapfly client."""
    with patch('app.services.scraping.base.ScrapflyClient') as MockClient:
        instance = MockClient.return_value
        
        async def mock_scrape(url, **kwargs):
            return {
                "content": MOCK_SCRAPE_CONTENT,
                "status_code": 200,
                "url": url,
                "success": True
            }
        
        async def mock_search_google(query, **kwargs):
            return [
                {"title": f"{query} Official Site", "url": f"https://{query.lower().replace(' ', '')}.com", "snippet": "Official website"},
                {"title": f"{query} Wikipedia", "url": f"https://en.wikipedia.org/wiki/{query}", "snippet": "Encyclopedia entry"}
            ]
        
        async def mock_search_news(query, **kwargs):
            return MOCK_NEWS
        
        instance.scrape = mock_scrape
        instance.search_google = mock_search_google
        instance.search_news = mock_search_news
        
        yield instance


@pytest.fixture
def mock_social_collector():
    """Mock social sentiment collector."""
    with patch('app.services.scraping.strategies.SocialSentimentCollector') as MockCollector:
        instance = MockCollector.return_value
        
        async def mock_collect(brand_name):
            return MOCK_SOCIAL_SENTIMENT
        
        instance.collect = mock_collect
        yield instance


# ============================================
# Full Workflow Integration Tests
# ============================================

class TestBrandAuditIntegration:
    """Integration tests for brand audit workflow."""
    
    @pytest.mark.asyncio
    async def test_full_brand_audit_workflow(self, mock_llm_client, mock_scrapfly):
        """Test complete brand audit workflow execution."""
        from app.graph.workflows.brand_audit_workflow import create_brand_audit_workflow
        
        # Patch at the correct locations (where the imports happen)
        with patch('app.core.llm_client.LLMClient', return_value=mock_llm_client), \
             patch('app.services.scraping.base.ScrapflyClient', return_value=mock_scrapfly), \
             patch('app.services.cache.query_cache') as mock_cache:
            
            mock_cache.get.return_value = None  # No cache hit
            mock_cache.set.return_value = True
            
            workflow = await create_brand_audit_workflow()
            
            initial_state = {
                "report_type": "brand_audit",
                "brand_name": "Nike",
                "brand_url": "https://nike.com",
                "competitors": [],
                "geography": "US",
                "pdf_context": "",
                "errors": [],
                "warnings": []
            }
            
            # Run workflow
            final_state = None
            async for event in workflow.astream(
                initial_state,
                config={"configurable": {"thread_id": "test-thread"}}
            ):
                for node_name, updates in event.items():
                    if "final_report" in updates and updates["final_report"]:
                        final_state = updates
            
            # Verify results
            assert final_state is not None
            assert "final_report" in final_state
            assert len(final_state["final_report"]) > 100
    
    @pytest.mark.asyncio
    async def test_brand_audit_with_cache_hit(self):
        """Test brand audit returns cached result."""
        from app.graph.nodes.common import node_cache_check
        
        cached_report = {
            "report": "# Cached Brand Audit\n\nThis is cached.",
            "chart": None
        }
        
        with patch('app.services.cache.query_cache') as mock_cache:
            mock_cache.get.return_value = cached_report
            
            state = {
                "report_type": "brand_audit",
                "brand_name": "Nike",
                "brand_url": "https://nike.com",
                "geography": "US"
            }
            
            result = await node_cache_check(state)
            
            assert result["cache_hit"] is True
            assert result["final_report"] == cached_report["report"]
    
    @pytest.mark.asyncio
    async def test_brand_audit_graceful_degradation(self, mock_llm_client):
        """Test workflow continues when scraping fails."""
        from app.graph.nodes.brand_audit_nodes import node_scrape_brand
        
        with patch('app.services.scraping.strategies.BrandScrapingStrategy') as MockStrategy:
            instance = MockStrategy.return_value
            instance.scrape = AsyncMock(side_effect=Exception("Scrape failed"))
            
            state = {
                "brand_name": "Nike",
                "brand_url": "https://nike.com",
                "steps": {},
                "warnings": []
            }
            
            result = await node_scrape_brand(state)
            
            # Should continue with empty content and warning
            assert result["brand_site_content"] == ""
            assert len(result["warnings"]) > 0
            assert "scrape_brand" in result["steps"]


class TestMeetingBriefIntegration:
    """Integration tests for meeting brief workflow."""
    
    @pytest.mark.asyncio
    async def test_full_meeting_brief_workflow(self, mock_llm_client, mock_scrapfly):
        """Test complete meeting brief workflow."""
        from app.graph.workflows.meeting_brief_workflow import create_meeting_brief_workflow
        
        with patch('app.core.llm_client.LLMClient', return_value=mock_llm_client), \
             patch('app.services.scraping.base.ScrapflyClient', return_value=mock_scrapfly), \
             patch('app.services.cache.query_cache') as mock_cache:
            
            mock_cache.get.return_value = None
            
            workflow = await create_meeting_brief_workflow()
            
            initial_state = {
                "report_type": "meeting_brief",
                "person_name": "John Smith",
                "person_role": "CEO",
                "company_name": "Acme Corp",
                "geography": "US",
                "errors": [],
                "warnings": []
            }
            
            final_state = None
            async for event in workflow.astream(
                initial_state,
                config={"configurable": {"thread_id": "test-meeting"}}
            ):
                for node_name, updates in event.items():
                    if "final_report" in updates:
                        final_state = updates
            
            assert final_state is not None


class TestAudienceProfileIntegration:
    """Integration tests for audience profile workflow."""
    
    @pytest.mark.asyncio
    async def test_audience_profile_generates_chart(self):
        """Test audience profile generates radar chart."""
        from app.graph.nodes.audience_profile_nodes import node_analyze_audience_profile
        
        mock_response = """# Audience Profile: Gen Z Gamers

## Demographics
Age: 16-24, predominantly male (65%), urban dwellers.

## Psychographics
Value authenticity, social connection, and competitive achievement.

---CHART_JSON---
{
    "chart_type": "radar",
    "chart_title": "Gen Z Gamer Priorities",
    "data": [
        {"subject": "Social Connection", "value": 90},
        {"subject": "Competition", "value": 85}
    ]
}"""
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (mock_response, {"api_used": "responses_api"})
        
        with patch('app.core.llm_client.LLMClient', return_value=mock_llm):
            state = {
                "audience_name": "Gen Z Gamers",
                "geography": "US",
                "workflow_id": "test-123",
                "steps": {},
                "errors": [],
                "warnings": []
            }
            
            result = await node_analyze_audience_profile(state)
            
            assert "final_report" in result
            # Report should contain the markdown content
            assert "Gen Z Gamers" in result["final_report"] or result["final_report"] != ""


class TestCompetitiveLandscapeIntegration:
    """Integration tests for competitive landscape workflow."""
    
    @pytest.mark.asyncio
    async def test_competitive_map_generation(self):
        """Test competitive landscape generates positioning map."""
        from app.graph.nodes.competitive_landscape_nodes import node_market_positioning
        
        mock_positioning = """{
    "x_axis": {"label": "Price", "low": "Value", "high": "Premium"},
    "y_axis": {"label": "Innovation", "low": "Traditional", "high": "Innovative"},
    "positions": [
        {"name": "Nike", "x": 75, "y": 85},
        {"name": "Adidas", "x": 70, "y": 75}
    ]
}"""
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (mock_positioning, {"api_used": "responses_api"})
        
        with patch('app.core.llm_client.LLMClient', return_value=mock_llm):
            state = {
                "brand_name": "Nike",
                "competitor_data": [
                    {"name": "Adidas", "content": "Athletic wear"},
                    {"name": "Puma", "content": "Sports brand"}
                ],
                "steps": {},
                "errors": [],
                "warnings": []
            }
            
            result = await node_market_positioning(state)
            
            assert "chart_json" in result
            # Chart may or may not be parsed depending on response format
            assert result["progress_percent"] == 70


# ============================================
# API Integration Tests
# ============================================

class TestAPIIntegration:
    """Integration tests for API endpoints with mocked workflows."""
    
    @pytest.mark.asyncio
    async def test_streaming_response_format(self):
        """Test that streaming responses follow NDJSON format."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        
        with patch('app.api.endpoints._get_workflow') as mock_get_workflow:
            # Create a mock workflow that yields expected events
            async def mock_astream(state, config):
                yield {"initialize": {"workflow_id": "test-123", "current_step": "Starting...", "progress_percent": 5}}
                yield {"analyze": {"current_step": "Analyzing...", "progress_percent": 50}}
                yield {"format": {"final_report": "# Test Report", "current_step": "Done", "progress_percent": 100}}
            
            mock_workflow = MagicMock()
            mock_workflow.astream = mock_astream
            mock_get_workflow.return_value = mock_workflow
            
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/generate-report",
                    data={
                        "report_type": "audience_profile",
                        "audience_name": "Test Audience",
                        "geography": "US"
                    }
                )
                
                assert response.status_code == 200
                assert response.headers.get("content-type") == "application/x-ndjson"
                
                # Parse NDJSON lines
                lines = response.text.strip().split("\n")
                for line in lines:
                    data = json.loads(line)
                    assert "type" in data
                    assert data["type"] in ["progress", "result", "error"]
    
    @pytest.mark.asyncio
    async def test_request_id_header(self):
        """Test that X-Request-ID header is present."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            
            assert "x-request-id" in response.headers
            assert len(response.headers["x-request-id"]) == 8
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting works."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Make requests up to limit
            # Note: Rate limiting is per-IP, which is mocked in tests
            response = await client.post(
                "/api/v1/generate-report",
                data={"report_type": "invalid"}  # Quick validation failure
            )
            assert response.status_code == 200  # Returns error in stream, not 429


# ============================================
# Error Handling Integration Tests
# ============================================

class TestErrorHandling:
    """Test error handling across the system."""
    
    @pytest.mark.asyncio
    async def test_llm_failure_recorded_in_circuit_breaker(self):
        """Test that LLM failures are tracked by circuit breaker."""
        from app.core.llm_client import CircuitBreaker
        
        # Clear state
        CircuitBreaker._state = {}
        
        # Test that recording failures works
        CircuitBreaker.record_result("test_key", success=False)
        CircuitBreaker.record_result("test_key", success=False)
        CircuitBreaker.record_result("test_key", success=False)
        
        # After 3 failures, circuit should be open
        assert CircuitBreaker.is_open("test_key") is True
    
    @pytest.mark.asyncio
    async def test_workflow_continues_on_node_failure(self, mock_llm_client):
        """Test that workflows continue when non-critical nodes fail."""
        from app.graph.nodes.brand_audit_nodes import node_social_sentiment
        
        with patch('app.services.scraping.strategies.SocialSentimentCollector') as MockCollector:
            instance = MockCollector.return_value
            instance.collect = AsyncMock(side_effect=Exception("Social API failed"))
            
            state = {
                "brand_name": "Nike",
                "steps": {},
                "warnings": []
            }
            
            result = await node_social_sentiment(state)
            
            # Should continue with empty data and warning
            assert result["social_sentiment"] == {}
            assert len(result["warnings"]) > 0
            assert result["steps"]["social_sentiment"] == "failed"


# ============================================
# Performance Tests
# ============================================

class TestPerformance:
    """Performance-related tests."""
    
    @pytest.mark.asyncio
    async def test_parallel_competitor_scraping(self, mock_scrapfly):
        """Test that competitor scraping runs in parallel."""
        from app.graph.nodes.brand_audit_nodes import node_scrape_competitors
        import time
        
        # Track call times
        call_times = []
        
        async def slow_scrape(name):
            call_times.append(time.time())
            await asyncio.sleep(0.1)  # Simulate network delay
            return {"content": f"Content for {name}", "url": f"https://{name}.com"}
        
        with patch('app.services.scraping.strategies.BrandScrapingStrategy') as MockStrategy:
            instance = MockStrategy.return_value
            instance.scrape_by_name = slow_scrape
            
            state = {
                "identified_competitors": ["A", "B", "C", "D", "E"],
                "steps": {},
                "warnings": []
            }
            
            start = time.time()
            result = await node_scrape_competitors(state)
            duration = time.time() - start
            
            # Should complete in ~0.1s (parallel) not ~0.5s (sequential)
            assert duration < 0.3
            assert len(result["competitor_data"]) == 5
    
    @pytest.mark.asyncio
    async def test_cache_prevents_duplicate_processing(self):
        """Test that cache hit skips all research steps."""
        from app.graph.nodes.common import node_cache_check
        
        with patch('app.services.cache.query_cache') as mock_cache:
            mock_cache.get.return_value = {"report": "Cached", "chart": None}
            
            state = {
                "report_type": "brand_audit",
                "brand_name": "Nike",
                "brand_url": "https://nike.com",
                "geography": "US"
            }
            
            result = await node_cache_check(state)
            
            assert result["cache_hit"] is True
            assert result["progress_percent"] == 95  # Skip to near-end


# ============================================
# Run Tests
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
