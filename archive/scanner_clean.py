# MemoScan v2 Scanner with Discovery Mode Integration
# Clean implementation with proper function decomposition

import os
import json
import time
import uuid
import asyncio
import concurrent.futures
from typing import Optional, Tuple, Generator, List, Dict, Any
from threading import ThreadLock
from concurrent.futures import ThreadPoolExecutor

# === Core Scanner Functionality ===

def log(level: str, message: str):
    """Simple logging function."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {level.upper()}: {message}")

def validate_url(url: str) -> Tuple[bool, str, str]:
    """Validate and normalize URL."""
    try:
        if not url.strip():
            return False, "Empty URL provided", ""
        
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Basic validation
        if not url or len(url) > 2048:
            return False, "Invalid URL format", ""
        
        return True, "", url
    except Exception as e:
        return False, f"URL validation error: {e}", ""

# === Discovery Mode Integration ===

DISCOVERY_AVAILABLE = False
DiscoveryAnalyzer = None
DiscoveryMetrics = None

def init_discovery_mode():
    """Initialize Discovery Mode components."""
    global DISCOVERY_AVAILABLE, DiscoveryAnalyzer, DiscoveryMetrics
    
    try:
        # Test that Discovery components can be imported
        from discovery_integration import DiscoveryAnalyzer as DA, DiscoveryMetrics as DM
        from discovery_integration import FeatureFlags
        
        # Verify Discovery Mode is enabled
        if not FeatureFlags.is_discovery_enabled():
            log("warn", "Discovery Mode is disabled by feature flags")
            return False
            
        # Test OpenAI API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            log("warn", "Discovery Mode requires OPENAI_API_KEY environment variable")
            return False
        
        # Set global references
        DiscoveryAnalyzer = DA
        DiscoveryMetrics = DM
        DISCOVERY_AVAILABLE = True
        
        log("info", "Discovery Mode initialized successfully")
        return True
        
    except ImportError as e:
        log("warn", f"Discovery Mode not available - missing dependencies: {e}")
        return False
    except Exception as e:
        log("error", f"Failed to initialize Discovery Mode: {e}")
        return False

def _get_discovery_error_explanation(error_msg: str) -> str:
    """Provide user-friendly explanation for Discovery analysis failures."""
    
    if "OPENAI_API_KEY" in error_msg:
        return ("Discovery analysis failed because the OpenAI API key is missing or invalid. "
                "Please check your API key configuration and try again.")
    
    elif "timeout" in error_msg.lower():
        return ("Discovery analysis failed due to a timeout. The AI analysis is taking longer than expected. "
                "This may be due to high API load. Please try again in a few moments.")
    
    elif "rate limit" in error_msg.lower():
        return ("Discovery analysis failed because you've reached the API rate limit. "
                "Please wait a moment and try again, or check your OpenAI account limits.")
    
    elif "insufficient content" in error_msg.lower():
        return ("Discovery analysis failed because there wasn't enough content found on the website "
                "to perform meaningful brand analysis. Please try a different URL with more content.")
    
    elif "json" in error_msg.lower() or "parsing" in error_msg.lower():
        return ("Discovery analysis failed due to an AI response formatting issue. "
                "This is usually temporary - please try scanning again.")
    
    else:
        return (f"Discovery analysis encountered an unexpected error: {error_msg}. "
                "Please try again, and if the problem persists, contact support.")

# === Phase Functions for Decomposed Scanning ===

def run_discovery_phase(initial_url: str) -> Generator[Dict[str, Any], None, Tuple[Optional[str], Optional[str], Optional[List]]]:
    """Phase 1: Discover all brand pages from HTML and sitemaps."""
    yield {'type': 'status', 'message': 'Step 1/5: Discovering all brand pages...', 'phase': 'discovery', 'progress': 10}
    yield {'type': 'activity', 'message': f'🌐 Starting scan at {initial_url}', 'timestamp': time.time()}
    
    # Mock implementation for now - in real version this would use the actual scanner functions
    try:
        # Simulate page discovery
        yield {'type': 'activity', 'message': f'🔍 Analyzing HTML structure...', 'timestamp': time.time()}
        
        # Mock discovered links
        all_discovered_links = [{'url': initial_url, 'score': 1.0}]
        homepage_html = "<html><head><title>Test</title></head><body>Sample content</body></html>"
        
        yield {'type': 'activity', 'message': f'✅ Found {len(all_discovered_links)} links in HTML', 'timestamp': time.time()}
        
        return initial_url, homepage_html, all_discovered_links
        
    except Exception as e:
        error_msg = f'Error during page discovery: {e}'
        yield {'type': 'error', 'message': error_msg}
        return None, None, None

def run_content_extraction_phase(initial_url: str, homepage_html: str, all_discovered_links: list, preferred_lang: str) -> Generator[Dict[str, Any], None, Tuple[Optional[str], Optional[str]]]:
    """Phase 2: Extract content from discovered pages."""
    yield {'type': 'status', 'message': 'Step 2/5: Analyzing and scoring all pages...', 'phase': 'content_extraction', 'progress': 35}
    yield {'type': 'activity', 'message': f'📄 Extracting content from {len(all_discovered_links)} pages...', 'timestamp': time.time()}
    
    try:
        # Mock content extraction
        full_corpus = "Sample brand content extracted from the website. This includes positioning, messaging, and key brand themes."
        homepage_screenshot_b64 = ""  # Mock screenshot
        
        yield {'type': 'activity', 'message': '✅ Content extraction completed', 'timestamp': time.time()}
        
        return full_corpus, homepage_screenshot_b64
        
    except Exception as e:
        error_msg = f'Error during content extraction: {e}'
        yield {'type': 'error', 'message': error_msg}
        return None, None

def run_analysis_phase(mode: str, scan_id: str, full_corpus: str, homepage_screenshot_b64: str, brand_summary: str, circuit_breaker) -> Generator[Dict[str, Any], None, Optional[List]]:
    """Phase 3: Perform Discovery or Diagnosis analysis based on mode."""
    
    if mode == 'discovery' and DISCOVERY_AVAILABLE:
        yield {'type': 'status', 'message': 'Step 4/5: Performing Discovery analysis...', 'phase': 'discovery_analysis', 'progress': 75}
        
        try:
            # Run Discovery Mode analysis
            from discovery_integration import DiscoveryAnalyzer
            
            discovery_analyzer = DiscoveryAnalyzer(scan_id, {})
            discovery_keys = ['positioning_themes', 'key_messages', 'tone_of_voice']
            
            all_results = []
            
            for key_name in discovery_keys:
                try:
                    yield {'type': 'activity', 'message': f'🔍 Analyzing {key_name.replace("_", " ")}...', 'timestamp': time.time()}
                    
                    if key_name == 'positioning_themes':
                        result, metrics = discovery_analyzer.analyze_positioning_themes(full_corpus)
                    elif key_name == 'key_messages':
                        result, metrics = discovery_analyzer.analyze_key_messages(full_corpus)
                    elif key_name == 'tone_of_voice':
                        result, metrics = discovery_analyzer.analyze_tone_of_voice(full_corpus)
                    else:
                        continue
                    
                    if result:
                        all_results.append({
                            'type': 'discovery_result',
                            'key': key_name,
                            'analysis': result
                        })
                        yield {
                            'type': 'discovery_result',
                            'key': key_name,
                            'analysis': result,
                            'metrics': {
                                'latency_ms': metrics.get('latency_ms', 0),
                                'token_usage': metrics.get('token_usage', 0),
                                'model': metrics.get('model', 'gpt-5')
                            }
                        }
                        yield {'type': 'activity', 'message': f'✅ {key_name.replace("_", " ").title()} analysis complete', 'timestamp': time.time()}
                    else:
                        error_msg = f"Discovery analysis failed for {key_name}: {metrics.get('error', 'Unknown error')}"
                        user_error = _get_discovery_error_explanation(error_msg)
                        yield {'type': 'error', 'message': user_error}
                        log("error", error_msg)
                        
                except Exception as e:
                    error_msg = f"Discovery analysis failed for {key_name}: {str(e)}"
                    user_error = _get_discovery_error_explanation(error_msg)
                    yield {'type': 'error', 'message': user_error}
                    log("error", error_msg)
            
            return all_results
            
        except Exception as e:
            error_msg = f"Discovery analysis failed: {str(e)}"
            user_error = _get_discovery_error_explanation(error_msg)
            yield {'type': 'error', 'message': user_error}
            log("error", error_msg)
            return []
    
    else:
        # Fallback to regular diagnosis mode
        yield {'type': 'status', 'message': 'Step 4/5: Performing memorability analysis...', 'phase': 'analysis', 'progress': 75}
        yield {'type': 'activity', 'message': '🧠 Running memorability analysis...', 'timestamp': time.time()}
        
        # Mock memorability analysis results
        mock_results = [
            {'key': 'emotion', 'score': 4, 'analysis': 'Strong emotional connection', 'evidence': 'Sample evidence'}
        ]
        
        for result in mock_results:
            yield {
                'type': 'key_result',
                'key': result['key'],
                'analysis': result['analysis'],
                'score': result['score'],
                'evidence': result['evidence']
            }
        
        return mock_results

def run_summary_phase(all_results: list) -> Generator[Dict[str, Any], None, str]:
    """Phase 4: Generate executive summary."""
    yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...', 'phase': 'summary', 'progress': 90}
    yield {'type': 'activity', 'message': '📋 Creating executive summary...', 'timestamp': time.time()}
    
    try:
        if any(r.get('type') == 'discovery_result' for r in all_results):
            executive_summary = "🔍 **Discovery Mode Analysis Complete**\n\nThis analysis focused on brand positioning, key messages, and tone of voice using advanced AI analysis.\n\nKey insights have been extracted and are available in the detailed results above."
        else:
            executive_summary = "📊 **Memorability Analysis Complete**\n\nThis analysis evaluated the brand's memorability across six key factors.\n\nDetailed results and recommendations are provided above."
        
        yield {'type': 'activity', 'message': '✅ Executive summary generated', 'timestamp': time.time()}
        return executive_summary
        
    except Exception as e:
        error_msg = f'Error generating summary: {e}'
        yield {'type': 'error', 'message': error_msg}
        return "Summary generation failed due to an error."

# === Main Decomposed Scanner Function ===

def run_full_scan_stream(url: str, cache: dict, preferred_lang: str = 'en', scan_id: str = None, mode: str = 'diagnosis') -> Generator[Dict[str, Any], None, None]:
    """
    Main scanning function with proper phase decomposition.
    
    Args:
        url: URL to scan
        cache: Shared cache for storing results
        preferred_lang: Language preference
        scan_id: Unique scan identifier
        mode: 'diagnosis' for memorability analysis, 'discovery' for Discovery Mode
    """
    
    # Initialize scan
    if not scan_id:
        scan_id = str(uuid.uuid4())
    
    log("info", f"Starting {mode} mode scan for {url}")
    
    # Validate URL
    is_valid, error_msg, initial_url = validate_url(url)
    if not is_valid:
        error_explanation = _get_discovery_error_explanation(error_msg) if mode == 'discovery' else error_msg
        log("error", f"URL validation failed: {error_msg}")
        yield {'type': 'error', 'message': error_explanation}
        return

    try:
        # Phase 1: Discovery
        discovery_generator = run_discovery_phase(initial_url)
        initial_url, homepage_html, all_discovered_links = None, None, None
        
        for message in discovery_generator:
            yield message
            if message.get('type') == 'error':
                return
        
        # Get the return value from the generator
        try:
            initial_url, homepage_html, all_discovered_links = discovery_generator.send(None)
        except StopIteration as e:
            if hasattr(e, 'value') and e.value:
                initial_url, homepage_html, all_discovered_links = e.value
            else:
                yield {'type': 'error', 'message': 'Page discovery failed'}
                return
        
        if not initial_url or not all_discovered_links:
            yield {'type': 'error', 'message': 'Page discovery failed - no content found'}
            return

        # Phase 2: Content Extraction
        extraction_generator = run_content_extraction_phase(initial_url, homepage_html, all_discovered_links, preferred_lang)
        full_corpus, homepage_screenshot_b64 = None, None
        
        for message in extraction_generator:
            yield message
            if message.get('type') == 'error':
                return
        
        # Get the return value from the generator
        try:
            full_corpus, homepage_screenshot_b64 = extraction_generator.send(None)
        except StopIteration as e:
            if hasattr(e, 'value') and e.value:
                full_corpus, homepage_screenshot_b64 = e.value
            else:
                yield {'type': 'error', 'message': 'Content extraction failed'}
                return
        
        if not full_corpus:
            yield {'type': 'error', 'message': 'Content extraction failed - insufficient content'}
            return

        # Phase 3: Brand Overview (simplified)
        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...', 'phase': 'analysis', 'progress': 65}
        brand_summary = "Brand overview synthesis complete"  # Mock for now
        
        # Phase 4: Analysis
        circuit_breaker = None  # Mock circuit breaker
        analysis_generator = run_analysis_phase(mode, scan_id, full_corpus, homepage_screenshot_b64, brand_summary, circuit_breaker)
        all_results = []
        
        for message in analysis_generator:
            yield message
            if message.get('type') in ['discovery_result', 'key_result']:
                all_results.append(message)
            elif message.get('type') == 'error':
                if mode == 'discovery':
                    # For Discovery Mode, reset scanner on analysis failure
                    yield {'type': 'status', 'message': 'Resetting scanner due to Discovery analysis failure...', 'phase': 'reset'}
                    return
        
        # Get the return value from the generator
        try:
            analysis_results = analysis_generator.send(None)
            if analysis_results:
                all_results.extend(analysis_results)
        except StopIteration as e:
            if hasattr(e, 'value') and e.value:
                all_results.extend(e.value)

        # Phase 5: Summary
        summary_generator = run_summary_phase(all_results)
        executive_summary = None
        
        for message in summary_generator:
            yield message
        
        # Get the return value from the generator
        try:
            executive_summary = summary_generator.send(None)
        except StopIteration as e:
            if hasattr(e, 'value') and e.value:
                executive_summary = e.value
            else:
                executive_summary = "Summary generation completed"

        # Final results
        yield {'type': 'summary', 'text': executive_summary}
        yield {'type': 'complete', 'message': '🎉 Scan completed successfully!', 'timestamp': time.time()}
        
        log("info", f"Scan completed successfully: {scan_id}")
        
    except Exception as e:
        error_msg = f'Critical error during scan: {e}'
        if mode == 'discovery':
            user_error = _get_discovery_error_explanation(error_msg)
        else:
            user_error = error_msg
            
        log("error", error_msg)
        yield {'type': 'error', 'message': user_error}

# === Mock Helper Functions ===

def discover_links_from_html(html: str, base_url: str) -> list:
    """Mock link discovery function."""
    return [{'url': base_url, 'score': 1.0}]

def discover_links_from_sitemap(url: str) -> list:
    """Mock sitemap discovery function.""" 
    return []

def find_high_value_subdomain(links: list, base_url: str, lang: str) -> Optional[str]:
    """Mock high value subdomain detection."""
    return None

def score_links_with_llm(links: list, html: str, base_url: str, cache: dict) -> list:
    """Mock link scoring function."""
    return links

def call_openai_for_synthesis(corpus: str) -> str:
    """Mock OpenAI synthesis function."""
    return "Brand synthesis complete"

def call_openai_for_memorability_key(key: str, corpus: str, brand_summary: str, circuit_breaker, screenshot: str = "") -> Optional[dict]:
    """Mock memorability analysis function."""
    return {
        'key': key,
        'score': 4,
        'analysis': f'Analysis for {key}',
        'evidence': f'Evidence for {key}'
    }

def call_openai_for_executive_summary(results: list, brand_summary: str, quantitative_summary: dict, url: str, corpus: str) -> str:
    """Mock executive summary function."""
    return "Executive summary generated"

# === Circuit Breaker Mock ===
class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: int):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

def fetch_page_content_robustly_sync(url: str, take_screenshot: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """Mock page content fetching function."""
    return "Sample content", "<html><body>Sample HTML</body></html>"

def capture_screenshots_playwright(url: str, cache: dict) -> Optional[str]:
    """Mock screenshot capture function."""
    return ""

def close_shared_http_client():
    """Mock cleanup function."""
    pass

def close_shared_playwright_browser():
    """Mock cleanup function."""
    pass

def track_scan_metric(scan_id: str, status: str, data: dict):
    """Mock metrics tracking function."""
    pass

def _calculate_urls_to_fetch(total_links: int) -> int:
    """Calculate optimal number of URLs to fetch."""
    return min(10, max(3, total_links // 2))