"""
Comprehensive test suite for Strategist's Best Friend.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


# ============================================
# Test Fixtures
# ============================================

@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch('app.core.config.settings') as mock:
        mock.OPENAI_API_KEY = "test-api-key"
        mock.SCRAPFLY_KEY = "test-scrapfly-key"
        mock.CACHE_DIR = "/tmp/test_cache"
        mock.CACHE_TTL_HOURS = 24
        mock.GPT5_MODEL = "gpt-5.1-2025-11-13"
        mock.GPT5_TIMEOUT = 180
        mock.CIRCUIT_BREAKER_THRESHOLD = 3
        mock.CIRCUIT_BREAKER_COOLDOWN = 600
        mock.SCRAPFLY_ASP = True
        mock.RATE_LIMIT_PER_HOUR = 3
        yield mock


@pytest.fixture
def sample_brand_audit_state():
    """Sample state for brand audit workflow."""
    return {
        "report_type": "brand_audit",
        "brand_name": "Nike",
        "brand_url": "https://nike.com",
        "competitors": ["Adidas", "Puma"],
        "geography": "US",
        "pdf_context": "",
        "workflow_id": None,
        "current_step": "",
        "progress_percent": 0,
        "steps": {},
        "errors": [],
        "warnings": []
    }


@pytest.fixture
def sample_meeting_brief_state():
    """Sample state for meeting brief workflow."""
    return {
        "report_type": "meeting_brief",
        "person_name": "John Smith",
        "person_role": "CEO",
        "company_name": "Acme Corp",
        "geography": "US",
        "workflow_id": None,
        "current_step": "",
        "progress_percent": 0,
        "steps": {},
        "errors": [],
        "warnings": []
    }


# ============================================
# Cache Service Tests
# ============================================

class TestQueryCache:
    """Tests for QueryCache service."""
    
    def test_cache_set_and_get(self, tmp_path):
        """Test basic cache set and get operations."""
        from app.services.cache import QueryCache
        
        cache = QueryCache(cache_dir=str(tmp_path), ttl_hours=24)
        
        key = "test:key:123"
        value = {"report": "# Test Report", "chart": None}
        
        # Set
        assert cache.set(key, value) is True
        
        # Get
        result = cache.get(key)
        assert result is not None
        assert result["report"] == "# Test Report"
    
    def test_cache_expiry(self, tmp_path):
        """Test cache expiration."""
        from app.services.cache import QueryCache
        import time
        
        # Very short TTL for testing
        cache = QueryCache(cache_dir=str(tmp_path), ttl_hours=0)  # 0 hours = expired immediately
        cache.ttl_seconds = 0.001  # Override to expire very quickly
        
        key = "test:expiry"
        value = {"data": "test"}
        
        cache.set(key, value)
        time.sleep(0.01)  # Wait for expiry
        
        result = cache.get(key)
        assert result is None
    
    def test_cache_key_hashing(self, tmp_path):
        """Test that different keys produce different hashes."""
        from app.services.cache import QueryCache
        
        cache = QueryCache(cache_dir=str(tmp_path))
        
        hash1 = cache._get_key_hash("brand_audit:Nike:US")
        hash2 = cache._get_key_hash("brand_audit:Adidas:US")
        
        assert hash1 != hash2
        assert len(hash1) == 32  # MD5 hex digest
    
    def test_cache_stats(self, tmp_path):
        """Test cache statistics."""
        from app.services.cache import QueryCache
        
        cache = QueryCache(cache_dir=str(tmp_path))
        
        # Add some entries
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        
        stats = cache.get_stats()
        
        assert stats["total_entries"] == 2
        assert stats["active_entries"] == 2
        assert stats["expired_entries"] == 0


# ============================================
# HTML Cleaner Tests
# ============================================

class TestHTMLCleaner:
    """Tests for HTMLCleaner service."""
    
    def test_clean_removes_scripts(self):
        """Test that scripts are removed."""
        from app.services.cleaner import HTMLCleaner
        
        cleaner = HTMLCleaner()
        html = "<html><script>alert('xss')</script><p>Content</p></html>"
        
        result = cleaner.clean(html)
        
        assert "alert" not in result
        assert "Content" in result
    
    def test_clean_removes_styles(self):
        """Test that styles are removed."""
        from app.services.cleaner import HTMLCleaner
        
        cleaner = HTMLCleaner()
        html = "<html><style>.foo{color:red}</style><p>Content</p></html>"
        
        result = cleaner.clean(html)
        
        assert ".foo" not in result
        assert "Content" in result
    
    def test_clean_extracts_text(self):
        """Test text extraction."""
        from app.services.cleaner import HTMLCleaner
        
        cleaner = HTMLCleaner()
        html = """
        <html>
            <body>
                <h1>Title</h1>
                <p>First paragraph.</p>
                <p>Second paragraph.</p>
            </body>
        </html>
        """
        
        result = cleaner.clean(html)
        
        assert "Title" in result
        assert "First paragraph" in result
        assert "Second paragraph" in result
    
    def test_clean_respects_max_length(self):
        """Test max length truncation."""
        from app.services.cleaner import HTMLCleaner
        
        cleaner = HTMLCleaner(max_length=100)
        html = "<p>" + "A" * 200 + "</p>"
        
        result = cleaner.clean(html)
        
        assert len(result) <= 103  # 100 + "..."


# ============================================
# Text Splitter Tests
# ============================================

class TestTextSplitter:
    """Tests for TextSplitter service."""
    
    def test_split_short_text(self):
        """Test that short text isn't split."""
        from app.services.cleaner import TextSplitter
        
        splitter = TextSplitter(chunk_size=1000)
        text = "Short text."
        
        result = splitter.split(text)
        
        assert len(result) == 1
        assert result[0] == "Short text."
    
    def test_split_long_text(self):
        """Test that long text is split."""
        from app.services.cleaner import TextSplitter
        
        splitter = TextSplitter(chunk_size=50, chunk_overlap=10)
        text = "This is a test sentence. " * 20  # 500+ characters
        
        result = splitter.split(text)
        
        assert len(result) > 1
    
    def test_split_preserves_paragraphs(self):
        """Test that paragraph boundaries are respected."""
        from app.services.cleaner import TextSplitter
        
        splitter = TextSplitter(chunk_size=200)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        
        result = splitter.split(text)
        
        # Should keep paragraphs together if possible
        assert any("First paragraph" in chunk for chunk in result)


# ============================================
# Common Nodes Tests
# ============================================

class TestCommonNodes:
    """Tests for common workflow nodes."""
    
    @pytest.mark.asyncio
    async def test_node_initialize(self, sample_brand_audit_state):
        """Test workflow initialization node."""
        from app.graph.nodes.common import node_initialize
        
        result = await node_initialize(sample_brand_audit_state)
        
        assert "workflow_id" in result
        assert len(result["workflow_id"]) == 36  # UUID format
        assert result["progress_percent"] == 5
        assert result["current_step"] == "Initializing workflow..."
        assert "initialize" in result["steps"]
    
    @pytest.mark.asyncio
    async def test_node_cache_check_miss(self, sample_brand_audit_state, tmp_path):
        """Test cache check with miss."""
        from app.graph.nodes.common import node_cache_check
        
        with patch('app.services.cache.query_cache') as mock_cache:
            mock_cache.get.return_value = None
            
            result = await node_cache_check(sample_brand_audit_state)
            
            assert result["cache_hit"] is False
            assert result["progress_percent"] == 10
    
    @pytest.mark.asyncio
    async def test_node_cache_check_hit(self, sample_brand_audit_state):
        """Test cache check with hit."""
        from app.graph.nodes.common import node_cache_check
        
        cached_data = {
            "report": "# Cached Report",
            "chart": {"type": "radar"}
        }
        
        with patch('app.services.cache.query_cache') as mock_cache:
            mock_cache.get.return_value = cached_data
            
            result = await node_cache_check(sample_brand_audit_state)
            
            assert result["cache_hit"] is True
            assert result["final_report"] == "# Cached Report"
            assert result["progress_percent"] == 95


# ============================================
# Brand Audit Nodes Tests
# ============================================

class TestBrandAuditNodes:
    """Tests for brand audit workflow nodes."""
    
    @pytest.mark.asyncio
    async def test_node_ingest_pdf_with_context(self, sample_brand_audit_state):
        """Test PDF ingestion when context exists."""
        from app.graph.nodes.brand_audit_nodes import node_ingest_pdf
        
        state = {**sample_brand_audit_state, "pdf_context": "PDF content here"}
        
        result = await node_ingest_pdf(state)
        
        assert result["progress_percent"] == 15
        assert "ingest_pdf" in result["steps"]
    
    @pytest.mark.asyncio
    async def test_node_identify_competitors_with_provided(self, sample_brand_audit_state):
        """Test competitor identification when already provided."""
        from app.graph.nodes.brand_audit_nodes import node_identify_competitors
        
        state = {**sample_brand_audit_state, "competitors": ["Adidas", "Puma"]}
        
        result = await node_identify_competitors(state)
        
        assert result["identified_competitors"] == ["Adidas", "Puma"]
        assert result["progress_percent"] == 45
    
    @pytest.mark.asyncio
    async def test_node_scrape_competitors_empty(self, sample_brand_audit_state):
        """Test competitor scraping with no competitors."""
        from app.graph.nodes.brand_audit_nodes import node_scrape_competitors
        
        state = {**sample_brand_audit_state, "identified_competitors": []}
        
        result = await node_scrape_competitors(state)
        
        assert result["competitor_data"] == []
        assert result["progress_percent"] == 55


# ============================================
# Schema Validation Tests
# ============================================

class TestSchemas:
    """Tests for Pydantic schemas."""
    
    def test_progress_update_valid(self):
        """Test valid ProgressUpdate creation."""
        from app.models.schemas import ProgressUpdate
        
        progress = ProgressUpdate(
            message="Processing...",
            step="analyze",
            progress_percent=50
        )
        
        assert progress.type == "progress"
        assert progress.message == "Processing..."
        assert progress.progress_percent == 50
    
    def test_result_response_valid(self):
        """Test valid ResultResponse creation."""
        from app.models.schemas import ResultResponse
        
        result = ResultResponse(
            markdown="# Report",
            chart={"type": "radar"},
            metadata={"duration": 10.5}
        )
        
        assert result.type == "result"
        assert result.markdown == "# Report"
    
    def test_error_response_valid(self):
        """Test valid ErrorResponse creation."""
        from app.models.schemas import ErrorResponse
        
        error = ErrorResponse(
            message="Something went wrong",
            details="Stack trace here",
            recoverable=True
        )
        
        assert error.type == "error"
        assert error.message == "Something went wrong"
        assert error.recoverable is True
    
    def test_step_status_enum(self):
        """Test StepStatus enum values."""
        from app.models.schemas import StepStatus
        
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.IN_PROGRESS.value == "in_progress"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"


# ============================================
# Circuit Breaker Tests
# ============================================

class TestCircuitBreaker:
    """Tests for CircuitBreaker functionality."""
    
    def test_circuit_breaker_starts_closed(self):
        """Test that circuit breaker starts closed."""
        from app.core.llm_client import CircuitBreaker
        
        # Clear any existing state
        CircuitBreaker._state = {}
        
        assert CircuitBreaker.is_open("test_key") is False
    
    def test_circuit_breaker_opens_after_failures(self, mock_settings):
        """Test that circuit breaker opens after threshold failures."""
        from app.core.llm_client import CircuitBreaker
        
        CircuitBreaker._state = {}
        
        # Record failures up to threshold
        for i in range(mock_settings.CIRCUIT_BREAKER_THRESHOLD):
            CircuitBreaker.record_result("fail_key", success=False)
        
        assert CircuitBreaker.is_open("fail_key") is True
    
    def test_circuit_breaker_resets_on_success(self):
        """Test that circuit breaker resets on success."""
        from app.core.llm_client import CircuitBreaker
        
        CircuitBreaker._state = {}
        
        # Record some failures
        CircuitBreaker.record_result("reset_key", success=False)
        CircuitBreaker.record_result("reset_key", success=False)
        
        # Record success
        CircuitBreaker.record_result("reset_key", success=True)
        
        assert CircuitBreaker._state["reset_key"]["failures"] == 0


# ============================================
# Workflow Creation Tests
# ============================================

class TestWorkflowCreation:
    """Tests for workflow creation functions."""
    
    @pytest.mark.asyncio
    async def test_brand_audit_workflow_creation(self):
        """Test brand audit workflow can be created."""
        from app.graph.workflows.brand_audit_workflow import create_brand_audit_workflow
        
        workflow = await create_brand_audit_workflow()
        
        assert workflow is not None
        assert len(workflow.nodes) == 11  # Including __start__
    
    @pytest.mark.asyncio
    async def test_meeting_brief_workflow_creation(self):
        """Test meeting brief workflow can be created."""
        from app.graph.workflows.meeting_brief_workflow import create_meeting_brief_workflow
        
        workflow = await create_meeting_brief_workflow()
        
        assert workflow is not None
        assert len(workflow.nodes) == 9
    
    @pytest.mark.asyncio
    async def test_audience_profile_workflow_creation(self):
        """Test audience profile workflow can be created."""
        from app.graph.workflows.audience_profile_workflow import create_audience_profile_workflow
        
        workflow = await create_audience_profile_workflow()
        
        assert workflow is not None
        assert len(workflow.nodes) == 5  # Simplest workflow


# ============================================
# API Endpoint Tests
# ============================================

class TestAPIEndpoints:
    """Tests for FastAPI endpoints."""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_invalid_report_type(self):
        """Test endpoint with invalid report type."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/generate-report",
                data={"report_type": "invalid_type"},
                headers={"X-Forwarded-For": "10.0.0.1"}  # Unique IP
            )
            
            if response.status_code == 429:
                pytest.skip("Rate limited")
                return
            
            assert response.status_code == 200
            lines = response.text.strip().split("\n")
            data = json.loads(lines[0])
            assert data["type"] == "error"
            assert "Invalid report type" in data["message"]
    
    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        """Test endpoint with missing required fields."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/generate-report",
                data={
                    "report_type": "brand_audit",
                    "brand_name": "Nike"
                    # Missing brand_url
                },
                headers={"X-Forwarded-For": "192.168.1.100"}  # Unique IP to avoid rate limit
            )
            
            # Check if rate limited
            if response.status_code == 429:
                pytest.skip("Rate limited - skipping validation test")
                return
            
            lines = response.text.strip().split("\n")
            data = json.loads(lines[0])
            assert data["type"] == "error"
            assert "Missing required fields" in data["message"]


# ============================================
# Integration Tests
# ============================================

class TestIntegration:
    """Integration tests requiring multiple components."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_initialization(self, sample_brand_audit_state):
        """Test full workflow can initialize and run first steps."""
        from app.graph.nodes.common import node_initialize, node_cache_check
        
        # Run initialization
        state = await node_initialize(sample_brand_audit_state)
        assert "workflow_id" in state
        
        # Mock cache miss and run cache check
        with patch('app.services.cache.query_cache') as mock_cache:
            mock_cache.get.return_value = None
            state = await node_cache_check(state)
        
        assert state["cache_hit"] is False
        assert state["progress_percent"] == 10


# ============================================
# Run Tests
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
