# MemoScan v2 Scanner with Discovery Mode Integration
# Clean implementation with proper function decomposition

import os
import json
import time
import uuid
import asyncio
import concurrent.futures
from typing import Optional, Tuple, Generator, List, Dict, Any, Set
from threading import Lock
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
        # SSRF hardening: block localhost and private IP ranges (by hostname and resolved IP)
        from urllib.parse import urlparse
        import socket
        import ipaddress
        hostname = urlparse(url).hostname or ""
        host_lower = hostname.lower()
        blocked_prefixes = ('localhost', '127.', '0.0.0.0', '::1')
        if host_lower.startswith(blocked_prefixes):
            return False, "Blocked host (localhost/private)", ""
        try:
            resolved = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(resolved)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                return False, "Blocked host (private address)", ""
        except Exception:
            pass
        
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

def run_discovery_phase(initial_url: str):
    """Phase 1: Discover all brand pages from HTML and sitemaps."""
    yield {'type': 'status', 'message': 'Step 1/5: Discovering all brand pages...', 'phase': 'discovery', 'progress': 10}
    yield {'type': 'activity', 'message': f'🌐 Starting scan at {initial_url}', 'timestamp': time.time()}
    
    # Use real scanner functions for page discovery
    try:
        # Import real scanner functions
        from scanner import (
            discover_links_from_html, discover_links_from_sitemap, 
            find_high_value_subdomain, fetch_page_content_robustly
        )
        
        # Fetch homepage content
        yield {'type': 'activity', 'message': f'🔍 Fetching homepage content...', 'timestamp': time.time()}
        screenshot, homepage_html = fetch_page_content_robustly(initial_url, take_screenshot=False)
        
        if not homepage_html:
            raise Exception(f"Failed to fetch homepage content from {initial_url}")
        
        # Discover links from HTML
        yield {'type': 'activity', 'message': f'🔍 Analyzing HTML structure for links...', 'timestamp': time.time()}
        html_links = discover_links_from_html(homepage_html, initial_url)
        
        # Discover links from sitemap
        yield {'type': 'activity', 'message': f'🗺️ Checking for XML sitemaps...', 'timestamp': time.time()}
        sitemap_links = discover_links_from_sitemap(initial_url, 'en')
        sitemap_links = sitemap_links or []
        
        # Combine all discovered links
        all_links = html_links + sitemap_links
        yield {'type': 'activity', 'message': f'📊 Found {len(html_links)} HTML links + {len(sitemap_links)} sitemap links', 'timestamp': time.time()}
        
        # Check for high-value subdomain
        better_domain = find_high_value_subdomain(all_links, initial_url, 'en')
        if better_domain:
            yield {'type': 'activity', 'message': f'🎯 Found high-value subdomain: {better_domain}', 'timestamp': time.time()}
            initial_url = better_domain
            # Re-fetch content from better domain
            screenshot, homepage_html = fetch_page_content_robustly(initial_url, take_screenshot=False)
            html_links = discover_links_from_html(homepage_html, initial_url)
            all_links = html_links + sitemap_links
        
        # Convert to the format expected by the rest of the pipeline
        all_discovered_links = [{'url': url, 'score': 1.0, 'title': title} for url, title in all_links]
        
        yield {'type': 'activity', 'message': f'✅ Found {len(all_discovered_links)} total pages for analysis', 'timestamp': time.time()}
        
        # Return the values properly
        return (initial_url, homepage_html, all_discovered_links)
        
    except Exception as e:
        error_msg = f'Error during page discovery: {e}'
        log("error", error_msg)
        yield {'type': 'error', 'message': error_msg}
        return (None, None, None)

def run_content_extraction_phase(initial_url: str, homepage_html: str, all_discovered_links: list, preferred_lang: str, shared_cache: dict | None = None):
    """Phase 2: Extract content from discovered pages."""
    yield {'type': 'status', 'message': 'Step 2/5: Analyzing and scoring all pages...', 'phase': 'content_extraction', 'progress': 35}
    yield {'type': 'activity', 'message': f'📄 Extracting content from {len(all_discovered_links)} pages...', 'timestamp': time.time()}
    
    try:
        # Import real scanner functions for content extraction
        from scanner import (
            score_link_pool, fetch_page_content_robustly, 
            get_social_media_text, cleanup_cache, detect_image_format, is_vetoed_url
        )
        from bs4 import BeautifulSoup
        import uuid
        
        # Utilities for high-signal filtering and novelty checks
        import re
        def is_high_signal_url(url: str) -> bool:
            u = url.lower()
            keywords = [
                '/about', '/company', '/our-story', '/strategy', '/vision', '/mission',
                '/products', '/solutions', '/platform', '/services', '/industries', '/segments',
                '/careers', '/culture', '/investors', '/esg', '/press', '/news', '/sustainability'
            ]
            return any(k in u for k in keywords) or u.rstrip('/') == initial_url.rstrip('/').lower()

        def is_locale_variant(url: str) -> bool:
            return re.search(r"/(en|fr|de|es|it|pt|ja|zh)(?:[-_][A-Za-z]{2})?(/|$)", url.lower()) is not None

        def is_search_or_paginated(url: str) -> bool:
            u = url.lower()
            return any(x in u for x in ['?q=', '/search', 'page=', '/page/'])

        def is_pdf(url: str) -> bool:
            return url.lower().endswith('.pdf')

        # Convert discovered links to basic tuples
        links_for_scoring = [(link['url'], link.get('title', '')) for link in all_discovered_links]
        # Basic prefilter: drop search/paginated and deep paths unless high-signal
        filtered_initial = []
        for url, title in links_for_scoring:
            if is_search_or_paginated(url):
                continue
            filtered_initial.append((url, title))
        
        # Score and filter links
        yield {'type': 'activity', 'message': f'📊 Scoring {len(links_for_scoring)} discovered links...', 'timestamp': time.time()}
        
        # Pre-emptive veto filtering
        filtered_links = []
        for url, text in links_for_scoring:
            is_vetoed, veto_category = is_vetoed_url(url)
            if not is_vetoed:
                filtered_links.append((url, text))
        
        if len(filtered_links) < len(links_for_scoring):
            vetoed_count = len(links_for_scoring) - len(filtered_links)
            yield {'type': 'activity', 'message': f'🛡️ Vetoed {vetoed_count} irrelevant links, analyzing {len(filtered_links)} remaining', 'timestamp': time.time()}
        
        # Score remaining links
        scored_links = score_link_pool(filtered_links, preferred_lang)
        yield {'type': 'activity', 'message': f'✨ Identified {len(scored_links)} business-relevant pages', 'timestamp': time.time()}
        
        # Select priority pages: 12 core high-signal seeds + novelty expansion up to 6 more
        priority_pages: List[str] = []
        found_urls: Set[str] = set()
        # Always include homepage
        priority_pages.append(initial_url)
        found_urls.add(initial_url)

        # Prefer high-signal URLs first
        high_signal = [l for l in scored_links if is_high_signal_url(l["url"]) and not is_locale_variant(l["url"]) and not is_pdf(l["url"])][:24]
        for link in high_signal:
            if len(priority_pages) >= 12:
                break
            u = link["url"]
            if u not in found_urls:
                priority_pages.append(u)
                found_urls.add(u)

        # Keep at most 1 PDF if it's likely a company overview/brand guide
        pdf_added = False
        for link in scored_links:
            u = link["url"]
            if is_pdf(u) and not pdf_added and any(k in u.lower() for k in ['overview', 'brand', 'corporate']):
                priority_pages.append(u)
                found_urls.add(u)
                pdf_added = True
                break

        # Novelty expansion placeholder list; will be filtered after fetching
        candidate_expansion = [l["url"] for l in scored_links if l["url"] not in found_urls and not is_locale_variant(l["url"]) and not is_search_or_paginated(l["url"])][:30]

        yield {'type': 'activity', 'message': f'🎯 Seeded {len(priority_pages)} core pages for analysis', 'timestamp': time.time()}
        
        # Capture homepage screenshot
        homepage_screenshot_b64 = None
        try:
            yield {'type': 'activity', 'message': f'📸 Capturing homepage screenshot...', 'timestamp': time.time()}
            homepage_screenshot_b64, final_homepage_html = fetch_page_content_robustly(initial_url, take_screenshot=True)
            if homepage_screenshot_b64:
                yield {'type': 'activity', 'message': f'✅ Homepage screenshot captured', 'timestamp': time.time()}
                # Cache screenshot on disk (failsafe) and in memory, then emit screenshot_ready
                try:
                    from scanner import detect_image_format
                    import uuid as _uuid
                    import os as _os
                    from io import BytesIO as _BytesIO
                    import base64 as _b64
                    screenshot_id = f"home-{_uuid.uuid4().hex}"
                    mime = detect_image_format(homepage_screenshot_b64)
                    # Persist to disk
                    base_dir = _os.getenv("PERSISTENT_DATA_DIR", _os.path.join(_os.getcwd(), "data"))
                    ss_dir = _os.path.join(base_dir, "screenshots")
                    _os.makedirs(ss_dir, exist_ok=True)
                    ext = 'png' if mime.endswith('png') else 'jpg'
                    file_path = _os.path.join(ss_dir, f"{screenshot_id}.{ext}")
                    with open(file_path, 'wb') as f:
                        f.write(_b64.b64decode(homepage_screenshot_b64))
                    # Cache reference
                    if shared_cache is not None:
                        shared_cache[screenshot_id] = { 'path': file_path, 'format': mime }
                    yield {
                        'type': 'screenshot_ready',
                        'id': screenshot_id,
                        'url': initial_url,
                    }
                except Exception as e:
                    log("warn", f"Failed to cache/emit screenshot: {e}")
            else:
                final_homepage_html = homepage_html
        except Exception as e:
            log("warn", f"Homepage screenshot failed: {e}")
            final_homepage_html = homepage_html
        
        # Extract content from priority pages
        page_html_map: Dict[str, str] = {initial_url: final_homepage_html}
        other_pages = [p for p in priority_pages if p != initial_url]

        yield {'type': 'activity', 'message': f'📑 Extracting content from {len(other_pages)} additional pages...', 'timestamp': time.time()}

        # Concurrent HTTP fetch (3-4 workers); Playwright is used only for homepage above
        def fetch_html(url: str) -> Tuple[str, Optional[str]]:
            try:
                _, html = fetch_page_content_robustly(url)
                return url, html
            except Exception as e:
                log("warn", f"Failed to extract content from {url}: {e}")
                return url, None

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fetch_html, url) for url in other_pages]
            for fut in futures:
                u, html = fut.result()
                if html:
                    page_html_map[u] = html
                    log("info", f"✅ Content extracted from {u}")
        
        # Distillation helpers
        from bs4 import BeautifulSoup
        def distill_page(url: str, html: str) -> Optional[str]:
            try:
                soup = BeautifulSoup(html, "html.parser")
                # Remove boilerplate
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    tag.decompose()
                title = (soup.title.string or '').strip() if soup.title else ''
                h1 = ' '.join(h.get_text(strip=True) for h in soup.find_all('h1')[:1])
                h2s = [h.get_text(strip=True) for h in soup.find_all('h2')[:3]]
                # Lead paragraphs: first 2-3 p
                paragraphs = [p.get_text(strip=True) for p in soup.find_all('p')[:3]]
                # Bullet lists near key sections
                bullets = []
                for ul in soup.find_all('ul')[:2]:
                    items = [li.get_text(strip=True) for li in ul.find_all('li')[:5]]
                    if items:
                        bullets.extend(items)
                parts = []
                if title: parts.append(f"TITLE: {title}")
                if h1: parts.append(f"H1: {h1}")
                for h2 in h2s: parts.append(f"H2: {h2}")
                for p in paragraphs: parts.append(f"P: {p}")
                for b in bullets[:6]: parts.append(f"BULLET: {b}")
                distilled = '\n'.join(parts)
                if len(distilled) < 50:
                    return None
                return f"=== {url} ===\n{distilled}\n"
            except Exception as e:
                log("warn", f"Failed to distill HTML from {url}: {e}")
                return None

        # Novelty checks using shingled Jaccard across distilled text
        def shingles(text: str, k: int = 12) -> Set[str]:
            tokens = text.split()
            return { ' '.join(tokens[i:i+k]) for i in range(0, max(0, len(tokens)-k+1)) }

        distilled_map: Dict[str, str] = {}
        global_shingles: Set[str] = set()
        novelty_threshold = 0.12

        # Distill seed pages first
        for u, html in list(page_html_map.items()):
            d = distill_page(u, html)
            if not d:
                continue
            s = shingles(d)
            inter = len(global_shingles & s)
            union = len(global_shingles | s) or 1
            novelty = 1.0 if not global_shingles else 1 - (inter / union)
            if novelty >= novelty_threshold or u == initial_url:
                distilled_map[u] = d
                global_shingles |= s
            if len(distilled_map) >= 12:
                break

        # Expand with novelty pages (fetch + distill concurrently up to cap 18)
        def fetch_and_distill(u: str) -> Tuple[str, Optional[str]]:
            _, html = fetch_page_content_robustly(u)
            if not html:
                return u, None
            return u, distill_page(u, html)

        remaining_slots = max(0, 18 - len(distilled_map))
        if remaining_slots > 0 and candidate_expansion:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(fetch_and_distill, u) for u in candidate_expansion[:30]]
                added = 0
                recent_novelties: List[float] = []
                for fut in futures:
                    u, d = fut.result()
                    if not d:
                        continue
                    s = shingles(d)
                    inter = len(global_shingles & s)
                    union = len(global_shingles | s) or 1
                    novelty = 1 - (inter / union)
                    recent_novelties.append(novelty)
                    if novelty >= novelty_threshold and u not in distilled_map:
                        distilled_map[u] = d
                        global_shingles |= s
                        added += 1
                    # Stop rule: break if average novelty of last 3 falls below threshold
                    if len(recent_novelties) >= 3 and sum(recent_novelties[-3:]) / 3.0 < novelty_threshold:
                        break
                    if added >= remaining_slots:
                        break
        
        # Add social media content if available (distillate captured to append later)
        social_distillate = None
        try:
            homepage_soup = BeautifulSoup(final_homepage_html, "html.parser")
            social_corpus = get_social_media_text(homepage_soup, initial_url)
            if social_corpus:
                social_distillate = f"=== SOCIAL MEDIA CONTENT ===\n{social_corpus}\n"
        except Exception as e:
            log("warn", f"Failed to extract social media content: {e}")
        
        # Combine distillates into corpus (cap ~18 pages)
        full_corpus_parts = [distilled_map[u] for u in list(distilled_map.keys())[:18]]
        if social_distillate:
            full_corpus_parts.append(social_distillate)
        full_corpus = '\n\n'.join(full_corpus_parts)
        
        if not full_corpus or len(full_corpus) < 300:
            raise Exception("Insufficient content extracted - less than 300 characters total")
        
        yield {'type': 'activity', 'message': f'✅ Content extraction completed: {len(full_corpus)} chars from {len(page_html_map)} pages', 'timestamp': time.time()}
        
        return (full_corpus, homepage_screenshot_b64)
        
    except Exception as e:
        error_msg = f'Error during content extraction: {e}'
        log("error", error_msg)
        yield {'type': 'error', 'message': error_msg}
        return (None, None)


def build_tone_candidates(full_corpus: str, max_chars: int = 4000) -> str:
    """
    Extract a smaller, tone-focused slice from the corpus:
    Prefer TITLE, H1, H2 lines and the first few paragraphs.
    Fallback to the first max_chars characters.
    """
    try:
        lines = full_corpus.splitlines()
        signal = []
        # Collect headings first
        for ln in lines:
            l = ln.strip()
            if l.startswith(("TITLE:", "H1:", "H2:")):
                signal.append(l)
        # Collect first ~10 paragraphs (lines starting with P: or plain text lines between headings)
        p_count = 0
        for ln in lines:
            l = ln.strip()
            if l.startswith("P:"):
                signal.append(l)
                p_count += 1
                if p_count >= 12:
                    break
        text = "\n".join(signal)
        if not text:
            return full_corpus[:max_chars]
        return text[:max_chars]
    except Exception:
        return full_corpus[:max_chars]
def run_analysis_phase(mode: str, scan_id: str, full_corpus: str, homepage_screenshot_b64: str, brand_summary: str, circuit_breaker):
    """Phase 3: Perform Discovery or Diagnosis analysis based on mode."""
    
    if mode == 'discovery' and DISCOVERY_AVAILABLE:
        yield {'type': 'status', 'message': 'Step 4/5: Performing Discovery analysis...', 'phase': 'discovery_analysis', 'progress': 75}
        yield {'type': 'activity', 'message': '🚀 Running concurrent Discovery analysis (positioning, messaging, tone)...', 'timestamp': time.time()}
        
        try:
            # Check content size and choose appropriate analyzer
            content_size = len(full_corpus) if full_corpus else 0
            
            if content_size > 40000:
                # Use optimized analyzer for very large content
                print(f"[INFO] Using optimized Discovery analyzer for large content ({content_size} chars)")
                from discovery_integration_optimized import OptimizedDiscoveryAnalyzer
                discovery_analyzer = OptimizedDiscoveryAnalyzer(scan_id, {})
                concurrent_result = discovery_analyzer.analyze_all_optimized(full_corpus)
            else:
                # Use standard analyzer for normal content
                from discovery_integration import DiscoveryAnalyzer
                discovery_analyzer = DiscoveryAnalyzer(scan_id, {})
                concurrent_result = discovery_analyzer.analyze_all_concurrent(full_corpus)
            
            if not concurrent_result.get('success'):
                error_msg = f"All Discovery analyses failed: {concurrent_result.get('message', 'Unknown error')}"
                user_error = _get_discovery_error_explanation(error_msg)
                yield {'type': 'error', 'message': user_error}
                log("error", error_msg)
                return []
            
            # Process concurrent results and yield individual discovery_result messages
            results = concurrent_result.get('results', {})
            metrics = concurrent_result.get('metrics', {})
            all_results = []
            
            yield {'type': 'activity', 'message': f'✅ Concurrent analysis completed: {metrics.get("analyses_completed", 0)}/3 successful in {metrics.get("total_latency_ms", 0)}ms', 'timestamp': time.time()}
            
            for key_name, result in results.items():
                if 'error' in result:
                    # Handle failed analysis
                    error_msg = f"Discovery analysis failed for {key_name}: {result.get('message', 'Unknown error')}"
                    user_error = _get_discovery_error_explanation(error_msg)
                    yield {'type': 'error', 'message': user_error}
                    log("error", error_msg)
                else:
                    # Handle successful analysis
                    all_results.append({
                        'type': 'discovery_result',
                        'key': key_name,
                        'analysis': result
                    })
                    
                    individual_metrics = metrics.get('individual_metrics', {}).get(key_name, {})
                    yield {
                        'type': 'discovery_result',
                        'key': key_name,
                        'analysis': result,
                        'metrics': {
                            'latency_ms': individual_metrics.get('latency_ms', 0),
                            'token_usage': individual_metrics.get('token_usage', 0),
                            'model': individual_metrics.get('model', 'gpt-5')
                        }
                    }
                    yield {'type': 'activity', 'message': f'✅ {key_name.replace("_", " ").title()} analysis complete', 'timestamp': time.time()}

            # Optionally run visual analysis (brand elements) and alignment based on env + screenshot size
            visual_enabled = True  # Always on as requested
            homepage_ok = False
            if visual_enabled and homepage_screenshot_b64:
                try:
                    import base64
                    bytes_len = len(base64.b64decode(homepage_screenshot_b64))
                    homepage_ok = bytes_len > 10 * 1024  # Lower threshold to ensure analysis runs
                except Exception:
                    homepage_ok = False

            brand_elements_result = None
            if visual_enabled:
                yield {'type': 'status', 'message': 'Running visual brand analysis…', 'phase': 'ai_analysis', 'progress': 80}
                try:
                    # Use same analyzer instance to run vision
                    screenshots = [homepage_screenshot_b64] if homepage_screenshot_b64 else []
                    brand_elements, be_metrics = discovery_analyzer.analyze_brand_elements(screenshots, full_corpus)
                    if brand_elements and isinstance(brand_elements, dict):
                        brand_elements_result = brand_elements
                        all_results.append({'type': 'discovery_result', 'key': 'brand_elements', 'analysis': brand_elements})
                        yield {
                            'type': 'discovery_result',
                            'key': 'brand_elements',
                            'analysis': brand_elements,
                            'metrics': {
                                'latency_ms': be_metrics.get('latency_ms', 0),
                                'token_usage': be_metrics.get('token_usage', 0),
                                'model': be_metrics.get('model', 'gpt-5')
                            }
                        }
                        yield {'type': 'activity', 'message': '✅ Brand elements (vision) analysis complete', 'timestamp': time.time()}
                except Exception as e:
                    log('warn', f'Brand elements analysis skipped: {e}')

            # Visual-text alignment only if we have positioning and brand elements
            if visual_enabled and brand_elements_result and isinstance(results.get('positioning_themes'), dict):
                yield {'type': 'status', 'message': 'Assessing visual-text alignment…', 'phase': 'ai_analysis', 'progress': 85}
                try:
                    alignment, align_metrics = discovery_analyzer.analyze_visual_text_alignment(
                        results.get('positioning_themes'), brand_elements_result
                    )
                    if alignment and isinstance(alignment, dict):
                        all_results.append({'type': 'discovery_result', 'key': 'visual_text_alignment', 'analysis': alignment})
                        yield {
                            'type': 'discovery_result',
                            'key': 'visual_text_alignment',
                            'analysis': alignment,
                            'metrics': {
                                'latency_ms': align_metrics.get('latency_ms', 0),
                                'token_usage': align_metrics.get('token_usage', 0),
                                'model': align_metrics.get('model', 'gpt-5')
                            }
                        }
                        yield {'type': 'activity', 'message': '✅ Visual-text alignment analysis complete', 'timestamp': time.time()}
                except Exception as e:
                    log('warn', f'Visual-text alignment skipped: {e}')
            
            # Summary of concurrent execution
            completion_rate = concurrent_result.get('completion_rate', 0)
            if completion_rate == 1.0:
                yield {'type': 'activity', 'message': '🎉 All Discovery analyses completed successfully', 'timestamp': time.time()}
            elif completion_rate > 0:
                yield {'type': 'activity', 'message': f'⚠️ Partial completion: {int(completion_rate * 100)}% of analyses succeeded', 'timestamp': time.time()}
            
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

def run_summary_phase(all_results: list):
    """Phase 4: Generate executive summary."""
    yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...', 'phase': 'summary', 'progress': 90}
    yield {'type': 'activity', 'message': '📋 Creating executive summary...', 'timestamp': time.time()}
    
    try:
        # Collect discovery results by key
        def _find(key_name: str):
            return next((r for r in all_results if r.get('type') == 'discovery_result' and r.get('key') == key_name and isinstance(r.get('analysis'), dict)), None)

        has_discovery = any(r.get('type') == 'discovery_result' for r in all_results)
        if not has_discovery:
            executive_summary = (
                "📊 Memorability Analysis Complete\n\n"
                "Detailed results and recommendations are provided above."
            )
            yield {'type': 'activity', 'message': '✅ Executive summary generated', 'timestamp': time.time()}
            return executive_summary

        pos = _find('positioning_themes')
        kms = _find('key_messages')
        tov = _find('tone_of_voice')
        be  = _find('brand_elements')
        vta = _find('visual_text_alignment')

        lines = []
        lines.append("🔍 Discovery Mode Summary\n")

        # Positioning Themes
        if pos:
            pt = pos['analysis']
            themes = pt.get('themes') or []
            if isinstance(themes, list) and themes:
                top_names = []
                for t in themes[:3]:
                    name = (t.get('theme') or '').strip()
                    conf = t.get('confidence')
                    if name:
                        top_names.append(f"{name}{f' ({conf}%)' if isinstance(conf, (int, float)) else ''}")
                if top_names:
                    lines.append(f"Positioning: {', '.join(top_names)}.")

        # Key Messages
        if kms:
            km = kms['analysis']
            klist = km.get('key_messages') or []
            if isinstance(klist, list) and klist:
                msgs = []
                for m in klist[:4]:
                    msg = (m.get('message') or '').strip()
                    typ = (m.get('type') or '').strip()
                    if msg:
                        if typ:
                            msgs.append(f"{msg} [{typ}]")
                        else:
                            msgs.append(msg)
                if msgs:
                    lines.append(f"Key messages: { '; '.join(msgs) }.")

        # Tone of Voice
        if tov:
            tv = tov['analysis']
            p = tv.get('primary_tone') or {}
            s = tv.get('secondary_tone') or {}
            p_name = (p.get('tone') or '—').strip()
            s_name = (s.get('tone') or '—').strip()
            # Quote snippets
            def _snip(q: str) -> str:
                q = (q or '').strip()
                return (q[:120] + '…') if len(q) > 120 else q
            p_q = _snip(p.get('evidence_quote') or '')
            s_q = _snip(s.get('evidence_quote') or '')
            part = f"Tone: primary {p_name}"
            if p_q:
                part += f" (\"{p_q}\")"
            part += f", secondary {s_name}"
            if s_q:
                part += f" (\"{s_q}\")"
            lines.append(part + ".")

        # Brand Elements
        if be:
            bea = be['analysis']
            impression = (bea.get('overall_impression', {}) or {})
            summary = (impression.get('summary') or '').strip()
            keywords = impression.get('keywords') or []
            if summary:
                lines.append(f"Visual identity: {summary}.")
            if isinstance(keywords, list) and keywords:
                lines.append(f"Visual keywords: {', '.join(keywords[:5])}.")
            cs = bea.get('coherence_score')
            if isinstance(cs, (int, float)):
                lines.append(f"Coherence score: {cs}/5.")

        # Visual-Text Alignment (optional)
        if vta:
            vtaa = vta['analysis']
            align = vtaa.get('alignment')
            just = (vtaa.get('justification') or '').strip()
            if align in ['Yes', 'No']:
                sentence = f"Visual-text alignment: {align}."
                if just:
                    sentence += f" {just}"
                lines.append(sentence)

        # Fallback if nothing assembled
        if len(lines) <= 1:
            lines.append("Key insights have been extracted and are available above.")

        executive_summary = "\n\n".join(lines)
        
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
        discovery_result = None
        
        # Consume all messages from generator and capture return value
        try:
            while True:
                message = next(discovery_generator)
                yield message
                if message.get('type') == 'error':
                    return
        except StopIteration as e:
            discovery_result = e.value
        
        # Validate discovery result
        if discovery_result and len(discovery_result) == 3:
            initial_url, homepage_html, all_discovered_links = discovery_result
        else:
            yield {'type': 'error', 'message': 'Page discovery failed - invalid return'}
            return
        
        if not initial_url or not all_discovered_links:
            yield {'type': 'error', 'message': 'Page discovery failed - no content found'}
            return

        # Phase 2: Content Extraction
        # Pass shared cache from scanner.py so screenshots can be cached and served by /screenshot/<id>
        try:
            from scanner import SHARED_CACHE as _SHARED_CACHE
        except Exception:
            _SHARED_CACHE = None
        extraction_generator = run_content_extraction_phase(initial_url, homepage_html, all_discovered_links, preferred_lang, _SHARED_CACHE)
        extraction_result = None
        
        # Consume all messages from generator and capture return value
        try:
            while True:
                message = next(extraction_generator)
                yield message
                if message.get('type') == 'error':
                    return
        except StopIteration as e:
            extraction_result = e.value
        
        # Validate extraction result
        if extraction_result and len(extraction_result) == 2:
            full_corpus, homepage_screenshot_b64 = extraction_result
        else:
            yield {'type': 'error', 'message': 'Content extraction failed - invalid return'}
            return
        
        if not full_corpus:
            yield {'type': 'error', 'message': 'Content extraction failed - insufficient content'}
            return

        # Phase 3: Brand Overview (real synthesis)
        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...', 'phase': 'analysis', 'progress': 65}
        yield {'type': 'activity', 'message': '🧠 AI analyzing brand identity and positioning...', 'timestamp': time.time()}
        
        try:
            from scanner import call_openai_for_synthesis, CircuitBreaker
            brand_summary = call_openai_for_synthesis(full_corpus)
            yield {'type': 'activity', 'message': '✅ Brand overview synthesis completed', 'timestamp': time.time()}
        except Exception as e:
            log("warn", f"Brand synthesis failed: {e}")
            brand_summary = "Brand synthesis failed - proceeding with content analysis"
        
        # Phase 4: Analysis (stream per-key completion in completion order)
        from scanner import CircuitBreaker
        circuit_breaker = CircuitBreaker(failure_threshold=3)
        all_results = []

        if mode == 'discovery' and DISCOVERY_AVAILABLE:
            try:
                from discovery_integration import DiscoveryAnalyzer
                analyzer = DiscoveryAnalyzer(scan_id, {})
                from concurrent.futures import ThreadPoolExecutor, as_completed
                # Build candidate lines for key_messages from distilled pages to reduce tokens
                try:
                    message_candidates_lines: List[str] = []
                    # Use already built distilled_map if available in this scope; otherwise, derive from full_corpus
                    # We reconstruct lightweight candidates from full_corpus sections markers
                    def add_if_prefix(line: str, prefixes: tuple[str, ...]):
                        return any(line.startswith(p) for p in prefixes)
                    prefixes = ("TITLE:", "H1:", "H2:", "P:", "BULLET:")
                    # Take up to ~1200 lines or 6000 chars, whichever first
                    total_chars = 0
                    for section in full_corpus.split("\n"):
                        s = section.strip()
                        if not s:
                            continue
                        if add_if_prefix(s, prefixes):
                            message_candidates_lines.append(s)
                            total_chars += len(s) + 1
                            if total_chars >= 6000:
                                break
                    message_candidates = "\n".join(message_candidates_lines)
                    if not message_candidates:
                        # Fallback to first 6000 chars of corpus
                        message_candidates = full_corpus[:6000]
                except Exception:
                    message_candidates = full_corpus[:6000]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    future_map = {
                        pool.submit(analyzer.analyze_positioning_themes, full_corpus): 'positioning_themes',
                        pool.submit(analyzer.analyze_key_messages, message_candidates): 'key_messages',
                        pool.submit(analyzer.analyze_tone_of_voice, build_tone_candidates(full_corpus)): 'tone_of_voice'
                    }
                    for fut in as_completed(list(future_map.keys())):
                        key_name = future_map[fut]
                        try:
                            result, metrics = fut.result()
                            if result:
                                payload = {
                                    'type': 'discovery_result',
                                    'key': key_name,
                                    'analysis': result,
                                    'metrics': {
                                        'latency_ms': metrics.get('latency_ms', 0),
                                        'token_usage': metrics.get('token_usage', 0),
                                        'model': metrics.get('model', 'gpt-5')
                                    }
                                }
                                yield payload
                                all_results.append(payload)
                                yield {'type': 'activity', 'message': f'✅ {key_name.replace("_"," ").title()} analysis complete', 'timestamp': time.time()}
                            else:
                                yield {'type': 'error', 'message': _get_discovery_error_explanation(metrics.get('error_details','analysis failed'))}
                        except Exception as e:
                            yield {'type': 'error', 'message': _get_discovery_error_explanation(str(e))}
                            continue

                # After text keys, run visual brand analysis and alignment (always on)
                try:
                    yield {'type': 'status', 'message': 'Running visual brand analysis…', 'phase': 'ai_analysis', 'progress': 80}
                    screenshots = [homepage_screenshot_b64] if homepage_screenshot_b64 else []
                    brand_elements, be_metrics = analyzer.analyze_brand_elements(screenshots, full_corpus)
                    if brand_elements:
                        be_payload = {
                            'type': 'discovery_result',
                            'key': 'brand_elements',
                            'analysis': brand_elements,
                            'metrics': {
                                'latency_ms': be_metrics.get('latency_ms', 0),
                                'token_usage': be_metrics.get('token_usage', 0),
                                'model': be_metrics.get('model', 'gpt-5')
                            }
                        }
                        yield be_payload
                        all_results.append(be_payload)
                        yield {'type': 'activity', 'message': '✅ Brand elements (vision) analysis complete', 'timestamp': time.time()}
                except Exception as e:
                    log('warn', f'Brand elements analysis skipped: {e}')

                # Visual-text alignment using positioning themes + brand elements
                try:
                    pos_payload = next((p for p in all_results if p.get('type') == 'discovery_result' and p.get('key') == 'positioning_themes'), None)
                    brand_payload = next((p for p in all_results if p.get('type') == 'discovery_result' and p.get('key') == 'brand_elements'), None)
                    if pos_payload and brand_payload and isinstance(pos_payload.get('analysis'), dict) and isinstance(brand_payload.get('analysis'), dict):
                        yield {'type': 'status', 'message': 'Assessing visual-text alignment…', 'phase': 'ai_analysis', 'progress': 85}
                        alignment, align_metrics = analyzer.analyze_visual_text_alignment(pos_payload['analysis'], brand_payload['analysis'])
                        if alignment:
                            align_payload = {
                                'type': 'discovery_result',
                                'key': 'visual_text_alignment',
                                'analysis': alignment,
                                'metrics': {
                                    'latency_ms': align_metrics.get('latency_ms', 0),
                                    'token_usage': align_metrics.get('token_usage', 0),
                                    'model': align_metrics.get('model', 'gpt-5')
                                }
                            }
                            yield align_payload
                            all_results.append(align_payload)
                            yield {'type': 'activity', 'message': '✅ Visual-text alignment analysis complete', 'timestamp': time.time()}
                except Exception as e:
                    log('warn', f'Visual-text alignment skipped: {e}')
            except Exception as e:
                yield {'type': 'error', 'message': _get_discovery_error_explanation(str(e))}
                return
        else:
            # Diagnosis fallback (unchanged mock)
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
            all_results.extend(mock_results)

        # Phase 5: Summary (consume generator manually to capture return value)
        summary_generator = run_summary_phase(all_results)
        executive_summary = None
        try:
            while True:
                message = next(summary_generator)
                yield message
        except StopIteration as e:
            executive_summary = e.value if e and e.value else "Summary generation completed"

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